#!/usr/bin/env python3
"""Teste determinístico das travas do Passo 29, sem commit e sem push."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import simular_commit_pre_jogo as simulator  # noqa: E402


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_package(root: Path, *, extra_file: bool = False) -> str:
    slug = "arsenal-manchester-city-premier-league-2026-transmissao-horario-escalacoes.html"
    contents = {
        slug: "<!doctype html><html><body>prévia</body></html>\n",
        "noticias.json": "[]\n",
        "sitemap.xml": "<?xml version=\"1.0\"?><urlset></urlset>\n",
    }
    for name, content in contents.items():
        (root / name).write_text(content, encoding="utf-8")

    manifest = {
        "step": 28,
        "mode": "publication_package_only",
        "slug": slug,
        "prepared_changes": [
            {"target": slug, "operation": "create", "sha256": sha(contents[slug])},
            {"target": "noticias.json", "operation": "modify", "sha256": sha(contents["noticias.json"])},
            {"target": "sitemap.xml", "operation": "modify", "sha256": sha(contents["sitemap.xml"])},
        ],
        "prepared_change_count": 3,
        "published_files_touched": False,
        "commit_executed": False,
        "publication_unlocked": False,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if extra_file:
        (root / "quarto-arquivo.txt").write_text("não permitido\n", encoding="utf-8")
    return slug


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        package = Path(tmp)
        slug = write_package(package)
        manifest, found_slug, targets = simulator.validate_package(package)
        assert manifest["step"] == 28
        assert found_slug == slug
        assert targets == [slug, "noticias.json", "sitemap.xml"]

    with tempfile.TemporaryDirectory() as tmp:
        package = Path(tmp)
        write_package(package, extra_file=True)
        try:
            simulator.validate_package(package)
        except SystemExit:
            pass
        else:
            raise AssertionError("Pacote com quarto arquivo deveria ser bloqueado.")

    with tempfile.TemporaryDirectory() as tmp:
        package = Path(tmp)
        slug = write_package(package)
        (package / "noticias.json").write_text('[{"alterado":true}]\n', encoding="utf-8")
        try:
            simulator.validate_package(package)
        except SystemExit:
            pass
        else:
            raise AssertionError("Pacote com SHA divergente deveria ser bloqueado.")

    print("OK: travas determinísticas do Passo 29 validadas.")
    print("Pacote permitido: exatamente 3 alterações")
    print("Quarto arquivo: bloqueado")
    print("SHA divergente: bloqueado")
    print("Commit remoto: não executado")


if __name__ == "__main__":
    main()
