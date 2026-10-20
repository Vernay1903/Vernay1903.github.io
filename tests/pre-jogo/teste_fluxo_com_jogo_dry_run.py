#!/usr/bin/env python3
"""Fluxo sintético com jogo: contrato -> rascunho -> preview -> aplicação dry-run.

Não usa rede, OpenAI, Serper, commit ou push.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import subprocess
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen
from pathlib import Path
from unittest import mock
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import aplicar_lote_pre_jogo_automatico as apply_batch
from scripts import montar_preview_html_pre_jogo as preview
from scripts import preparar_redacao_pre_jogo as prepare
from scripts import validar_rascunho_pre_jogo as validate


def load_controlled_test():
    path = ROOT / "tests" / "pre-jogo" / "teste_redacao_controlada.py"
    spec = importlib.util.spec_from_file_location("cde_controlled_draft", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Não foi possível carregar fixture editorial controlada.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    fixture = load_controlled_test()
    config = prepare.load_config()
    contract = prepare.build_contract(fixture.clean_package(), config=config)

    raw_draft = {
        "slug": contract["slug"],
        "body_html": fixture.valid_body(),
        "fact_fields_used": contract["required_fact_fields"],
    }
    draft, errors = validate.validate_draft(raw_draft, contract, config=config)
    assert errors == [], errors
    assert draft["draft_validated"] is True

    rendered, metadata = preview.build_preview(draft=draft, contract=contract)
    assert metadata["source_draft_validated"] is True
    assert metadata["ready_for_publication"] is False
    assert rendered.count('data-ad-slot="8702501261"') == 3
    assert rendered.count('data-ad-slot="5521804159"') == 1

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build = root / "build" / "pre-jogo"
        artifact = build / "automatico-source"
        previews = build / "automatico-publish"
        for folder in (
            artifact / "contracts", artifact / "drafts", artifact / "status",
            previews / "previews", root / "config",
        ):
            folder.mkdir(parents=True, exist_ok=True)

        slug = contract["slug"]
        name = Path(slug).with_suffix(".json").name
        contract_rel = f"contracts/{name}"
        draft_rel = f"drafts/{name}"
        status_rel = f"status/{name}"

        contract_path = artifact / contract_rel
        draft_path = artifact / draft_rel
        status_path = artifact / status_rel
        contract_path.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
        draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
        status_path.write_text(json.dumps({"step": 34, "synthetic": True}), encoding="utf-8")
        (previews / "previews" / slug).write_text(rendered, encoding="utf-8")

        (root / "config" / "pre-jogo.json").write_text(
            (ROOT / "config" / "pre-jogo.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        noticias = root / "noticias.json"
        sitemap = root / "sitemap.xml"
        noticias.write_text(
            json.dumps([
                {
                    "title": "Matéria anterior",
                    "excerpt": "Resumo anterior.",
                    "url": "materia-anterior.html",
                    "date": "16/09/2026",
                    "category": "Futebol",
                }
            ], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        sitemap.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            '  <!-- MATÉRIAS -->\n</urlset>\n',
            encoding="utf-8",
        )

        article = {
            "slug": slug,
            "title": contract["title"],
            "home": contract["match_context"]["home"],
            "away": contract["match_context"]["away"],
            "kickoff_time_brasilia": contract["match_context"]["kickoff_time_brasilia"],
            "contract": contract_rel,
            "draft": draft_rel,
            "status_snapshot": status_rel,
            "sha256": {
                "contract": apply_batch.sha256_file(contract_path),
                "draft": apply_batch.sha256_file(draft_path),
                "status_snapshot": apply_batch.sha256_file(status_path),
            },
        }
        manifest = {
            "step": 34,
            "mode": "automatic_preparation",
            "target_date": "2026-09-17",
            "timezone": "America/Sao_Paulo",
            "prepared_count": 1,
            "skipped_count": 0,
            "articles": [article],
            "skipped": [],
            "publication_unlocked": False,
        }
        manifest_path = artifact / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        approved = build / "approved.txt"
        approved.write_text(slug + "\n", encoding="utf-8")
        report = build / "report.json"

        before_news = noticias.read_bytes()
        before_sitemap = sitemap.read_bytes()
        with mock.patch.object(apply_batch, "ROOT", root), \
             mock.patch.object(apply_batch, "BUILD", build), \
             mock.patch.object(apply_batch, "NOTICIAS", noticias), \
             mock.patch.object(apply_batch, "SITEMAP", sitemap), \
             mock.patch.object(sys, "argv", [
                 "script",
                 "--manifest", str(manifest_path),
                 "--artifact-root", str(artifact),
                 "--approved", str(approved),
                 "--previews-root", str(previews),
                 "--report", str(report),
                 "--dry-run",
             ]):
            apply_batch.main()

        result = json.loads(report.read_text(encoding="utf-8"))
        assert result["selected_count"] == 1, result
        assert result["skipped_count"] == 0, result
        assert result["changed_file_count"] == 4, result
        assert set(result["changed_files"]) == {slug, "noticias.json", "sitemap.xml", "noticias-home.json"}
        assert result["commit_created"] is False and result["push_executed"] is False
        assert noticias.read_bytes() == before_news
        assert sitemap.read_bytes() == before_sitemap
        assert not (root / slug).exists()

        class FixedDate(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 9, 17, 0, 2, tzinfo=ZoneInfo("America/Sao_Paulo"))
        argv = ["script", "--manifest", str(manifest_path), "--artifact-root", str(artifact),
                "--approved", str(approved), "--previews-root", str(previews), "--report", str(report)]
        with mock.patch.object(apply_batch, "ROOT", root), \
             mock.patch.object(apply_batch, "BUILD", build), \
             mock.patch.object(apply_batch, "NOTICIAS", noticias), \
             mock.patch.object(apply_batch, "SITEMAP", sitemap), \
             mock.patch.object(apply_batch, "datetime", FixedDate), \
             mock.patch.object(sys, "argv", argv):
            apply_batch.main()
            assert (root / slug).read_text() == rendered
            assert json.loads((root / "noticias-home.json").read_text()) == json.loads(noticias.read_text())[:10]
            first = noticias.read_bytes()
            apply_batch.main()
            assert json.loads(report.read_text())["changed_file_count"] == 0
            assert noticias.read_bytes() == first

        # Teste ponta a ponta do destino: os 4 arquivos efetivamente aplicados
        # são commitados em um repositório LOCAL e servidos via HTTP loopback.
        # A main e o GitHub Pages do site real permanecem intactos.
        expected = {slug, "noticias.json", "sitemap.xml", "noticias-home.json"}
        def git(*args):
            return subprocess.check_output(
                ["git", "-C", str(root), *args], text=True, stderr=subprocess.PIPE
            ).strip()
        git("init", "-q")
        git("add", *sorted(expected))
        subprocess.run(
            ["git", "-C", str(root), "-c", "user.name=CDE E2E Test",
             "-c", "user.email=cde-e2e@example.invalid",
             "commit", "-qm", "E2E local: pré-jogo aprovado"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        committed = set(git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines())
        assert committed == expected, (committed, expected)
        assert git("show", "HEAD:" + slug) == rendered.strip()
        assert git("status", "--porcelain", "--", *sorted(expected)) == ""
        live_entry = json.loads(noticias.read_text(encoding="utf-8"))[0]
        assert live_entry["url"] == slug
        assert live_entry["title"] == contract["title"]
        assert live_entry["excerpt"] == contract["excerpt"]
        assert slug in sitemap.read_text(encoding="utf-8")

        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, *_args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0),
                                     partial(QuietHandler, directory=str(root)))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            address = f"http://127.0.0.1:{server.server_port}"
            with urlopen(address + "/" + slug, timeout=5) as response:
                assert response.status == 200
                assert response.read().decode("utf-8") == rendered
            with urlopen(address + "/noticias.json", timeout=5) as response:
                assert json.loads(response.read().decode("utf-8"))[0]["url"] == slug
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    print("OK E2E: jogo sintético -> contrato -> redação -> HTML -> "
          "lote -> commit local -> HTTP 200 -> noticiaJSON/sitemap; sem push remoto.")


if __name__ == "__main__":
    main()
