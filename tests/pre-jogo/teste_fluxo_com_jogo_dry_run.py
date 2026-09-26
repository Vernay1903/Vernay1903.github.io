#!/usr/bin/env python3
"""Fluxo sintético com jogo: contrato -> rascunho -> preview -> aplicação dry-run.

Não usa rede, OpenAI, Serper, commit ou push.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

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
        assert result["changed_file_count"] == 3, result
        assert set(result["changed_files"]) == {slug, "noticias.json", "sitemap.xml"}
        assert result["commit_created"] is False and result["push_executed"] is False
        assert noticias.read_bytes() == before_news
        assert sitemap.read_bytes() == before_sitemap
        assert not (root / slug).exists()

    print("OK: jogo sintético atravessa contrato, redação, HTML e lote dry-run sem publicar.")


if __name__ == "__main__":
    main()
