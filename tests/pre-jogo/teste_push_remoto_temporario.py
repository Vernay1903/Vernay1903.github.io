#!/usr/bin/env python3
"""Testes locais das travas do Passo 30, sem acesso ao GitHub remoto."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from testar_push_remoto_pre_jogo import validate_package, validate_test_branch_name  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expect_failure(callback, label: str) -> None:
    try:
        callback()
    except SystemExit as exc:
        if exc.code == 0:
            raise AssertionError(f"{label}: falha esperada terminou com código 0")
        return
    raise AssertionError(f"{label}: deveria ter falhado")


def test_branch_guard() -> None:
    validate_test_branch_name("pre-jogo-teste-remoto-123456-1")
    validate_test_branch_name("pre-jogo-teste-remoto-987654-12")

    for bad in (
        "main",
        "pre-jogo-teste-remoto",
        "pre-jogo-teste-remoto-x-1",
        "pre-jogo-teste-remoto-123-x",
        "refs/heads/pre-jogo-teste-remoto-123-1",
        "outra-branch",
    ):
        expect_failure(lambda value=bad: validate_test_branch_name(value), f"branch inválida {bad}")


def make_package(root: Path) -> tuple[Path, str]:
    slug = "arsenal-manchester-city-premier-league-2026-transmissao-horario-escalacoes.html"
    files = {
        slug: b"<html><body>teste</body></html>\n",
        "noticias.json": b"[]\n",
        "sitemap.xml": b"<?xml version=\"1.0\"?><urlset></urlset>\n",
    }
    for name, content in files.items():
        (root / name).write_bytes(content)

    manifest = {
        "step": 28,
        "slug": slug,
        "prepared_change_count": 3,
        "prepared_changes": [
            {"target": slug, "operation": "create", "sha256": sha256(files[slug])},
            {"target": "noticias.json", "operation": "modify", "sha256": sha256(files["noticias.json"])},
            {"target": "sitemap.xml", "operation": "modify", "sha256": sha256(files["sitemap.xml"])},
        ],
        "published_files_touched": False,
        "commit_executed": False,
        "publication_unlocked": False,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root, slug


def test_package_guard() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root, slug = make_package(Path(temp))
        manifest, returned_slug, targets = validate_package(root)
        assert manifest["step"] == 28
        assert returned_slug == slug
        assert targets == [slug, "noticias.json", "sitemap.xml"]

        (root / "arquivo-extra.txt").write_text("não permitido", encoding="utf-8")
        expect_failure(lambda: validate_package(root), "quarto arquivo")

    with tempfile.TemporaryDirectory() as temp:
        root, _slug = make_package(Path(temp))
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["prepared_changes"][1]["operation"] = "create"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        expect_failure(lambda: validate_package(root), "operação errada")

    with tempfile.TemporaryDirectory() as temp:
        root, _slug = make_package(Path(temp))
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["publication_unlocked"] = True
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        expect_failure(lambda: validate_package(root), "publicação liberada")


def main() -> None:
    test_branch_guard()
    test_package_guard()
    print("OK: travas locais do Passo 30 validadas sem acesso remoto.")
    print("Branch permitida: somente pre-jogo-teste-remoto-<run_id>-<attempt>")
    print("Pacote permitido: exatamente HTML + noticias.json + sitemap.xml")


if __name__ == "__main__":
    main()
