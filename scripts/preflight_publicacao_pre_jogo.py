#!/usr/bin/env python3
"""Preflight final da publicação de pré-jogo, sem commit e sem push.

Este script representa a última porta antes da publicação real. Ele valida o pacote
aprovado do Passo 28 contra o estado ATUAL da main, aplica os três arquivos apenas
no checkout temporário, coloca exatamente esses três arquivos no stage, inspeciona
o diff que seria publicado e depois desfaz tudo.

Nenhum commit é criado. Nenhum push é executado. O relatório é salvo apenas em
build/pre-jogo/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, NoReturn

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PACKAGE = ROOT / "build" / "pre-jogo" / "source-step28"
DEFAULT_REPORT = ROOT / "build" / "pre-jogo" / "publication-preflight" / "report.json"
NOTICIAS_PATH = ROOT / "noticias.json"
SITEMAP_PATH = ROOT / "sitemap.xml"
SITEMAP_MARKER = "<!-- MATÉRIAS -->"
SITE_BASE = "https://cortedosesportes.com.br/"


def fail(message: str) -> NoReturn:
    print(f"ERRO: {message}", file=sys.stderr)
    raise SystemExit(1)


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git_output(*args: str) -> str:
    return run_git(*args).stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"Arquivo não encontrado: {path}")
    except json.JSONDecodeError as exc:
        fail(f"JSON inválido em {path}: {exc}")


def render_news_object(title: str, excerpt: str, slug: str, date_br: str) -> str:
    def q(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    return "\n".join(
        [
            "{",
            f'"title": {q(title)},',
            f'"excerpt": {q(excerpt)},',
            f'"url": {q(slug)},',
            f'"date": {q(date_br)},',
            '"category": "Futebol"',
            "}",
        ]
    )


def expected_noticias_from_current(current_text: str, prepared_text: str, slug: str) -> str:
    try:
        current = json.loads(current_text)
        prepared = json.loads(prepared_text)
    except json.JSONDecodeError as exc:
        fail(f"noticias.json inválido no preflight: {exc}")

    if not isinstance(current, list) or not isinstance(prepared, list) or not prepared:
        fail("noticias.json atual/preparado precisa ser array não vazio.")

    new_item = prepared[0]
    if not isinstance(new_item, dict):
        fail("Primeiro objeto preparado de noticias.json é inválido.")
    if new_item.get("url") != slug:
        fail("Primeiro objeto de noticias.json preparado não corresponde ao slug.")
    if new_item.get("category") != "Futebol":
        fail("Categoria preparada precisa ser Futebol.")
    if prepared[1:] != current:
        fail(
            "Pacote ficou obsoleto: o conteúdo antigo de noticias.json preparado "
            "não corresponde ao noticias.json atual da main."
        )
    if any(isinstance(item, dict) and item.get("url") == slug for item in current):
        fail(f"Slug já existe no noticias.json atual: {slug}")

    title = new_item.get("title")
    excerpt = new_item.get("excerpt")
    date_br = new_item.get("date")
    if not all(isinstance(v, str) and v.strip() for v in (title, excerpt, date_br)):
        fail("Objeto novo de noticias.json possui campos editoriais inválidos.")

    stripped = current_text.lstrip("\ufeff")
    open_pos = stripped.find("[")
    if open_pos < 0:
        fail("Não foi possível localizar o início de noticias.json atual.")
    obj = render_news_object(title.strip(), excerpt.strip(), slug, date_br.strip())
    return stripped[: open_pos + 1] + "\n\n" + obj + "," + stripped[open_pos + 1 :]


def sitemap_entry(slug: str, lastmod: str) -> str:
    return "\n".join(
        [
            "<url>",
            f"  <loc>{SITE_BASE}{slug}</loc>",
            f"  <lastmod>{lastmod}</lastmod>",
            "  <priority>0.9</priority>",
            "</url>",
        ]
    )


def prepared_lastmod(prepared_text: str, slug: str) -> str:
    target = re.escape(f"{SITE_BASE}{slug}")
    pattern = re.compile(
        rf"<url>\s*<loc>\s*{target}\s*</loc>\s*<lastmod>\s*([^<]+?)\s*</lastmod>",
        re.S,
    )
    match = pattern.search(prepared_text)
    if not match:
        fail("Não foi possível localizar lastmod da nova URL no sitemap preparado.")
    return match.group(1).strip()


def expected_sitemap_from_current(current_text: str, prepared_text: str, slug: str) -> str:
    target_url = f"{SITE_BASE}{slug}"
    if target_url in current_text:
        fail(f"URL já existe no sitemap.xml atual: {target_url}")
    if current_text.count(SITEMAP_MARKER) != 1:
        fail("sitemap.xml atual precisa conter exatamente um marcador de matérias.")

    lastmod = prepared_lastmod(prepared_text, slug)
    marker_pos = current_text.index(SITEMAP_MARKER) + len(SITEMAP_MARKER)
    entry = sitemap_entry(slug, lastmod)
    expected = current_text[:marker_pos] + "\n\n  " + entry.replace("\n", "\n  ") + current_text[marker_pos:]

    try:
        ET.fromstring(expected)
        ET.fromstring(prepared_text)
    except ET.ParseError as exc:
        fail(f"sitemap.xml inválido no preflight: {exc}")

    return expected


def validate_package(package_dir: Path) -> tuple[dict[str, Any], str, list[str]]:
    manifest_path = package_dir / "manifest.json"
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        fail("manifest.json precisa ser objeto JSON.")
    if manifest.get("step") != 28:
        fail("Pacote não pertence ao Passo 28.")
    if manifest.get("prepared_change_count") != 3:
        fail("Pacote precisa conter exatamente três alterações.")
    if manifest.get("published_files_touched") is not False:
        fail("Pacote indica alteração publicada anterior.")
    if manifest.get("commit_executed") is not False:
        fail("Pacote indica commit anterior.")
    if manifest.get("publication_unlocked") is not False:
        fail("Pacote indica publicação liberada indevidamente.")

    slug = manifest.get("slug")
    if not isinstance(slug, str) or not slug.endswith(".html") or "/" in slug or "\\" in slug:
        fail("Slug inválido no manifest.")

    targets = [slug, "noticias.json", "sitemap.xml"]
    prepared = manifest.get("prepared_changes")
    if not isinstance(prepared, list) or len(prepared) != 3:
        fail("prepared_changes precisa conter exatamente três itens.")
    if [item.get("target") for item in prepared if isinstance(item, dict)] != targets:
        fail("Escopo/ordem do pacote diverge do contrato de publicação.")

    expected_files = sorted([*targets, "manifest.json"])
    actual_files = sorted(path.name for path in package_dir.iterdir() if path.is_file())
    if actual_files != expected_files:
        fail(f"Pacote contém arquivos inesperados: {actual_files}")

    for item in prepared:
        if not isinstance(item, dict):
            fail("Item inválido em prepared_changes.")
        target = item.get("target")
        path = package_dir / str(target)
        expected_sha = item.get("sha256")
        if not path.is_file() or not isinstance(expected_sha, str):
            fail(f"Arquivo/hash ausente no pacote: {target}")
        if sha256_file(path) != expected_sha:
            fail(f"SHA-256 divergente no pacote: {target}")

    return manifest, slug, targets


def ensure_current_main_matches_package(package_dir: Path, slug: str) -> None:
    if (ROOT / slug).exists():
        fail(f"HTML de destino já existe na main atual: {slug}")

    current_news = NOTICIAS_PATH.read_text(encoding="utf-8")
    prepared_news = (package_dir / "noticias.json").read_text(encoding="utf-8")
    expected_news = expected_noticias_from_current(current_news, prepared_news, slug)
    if expected_news != prepared_news:
        fail(
            "Pacote ficou obsoleto: noticias.json preparado não é exatamente o resultado "
            "de inserir a nova notícia sobre o arquivo atual."
        )

    current_sitemap = SITEMAP_PATH.read_text(encoding="utf-8")
    prepared_sitemap = (package_dir / "sitemap.xml").read_text(encoding="utf-8")
    expected_sitemap = expected_sitemap_from_current(current_sitemap, prepared_sitemap, slug)
    if expected_sitemap != prepared_sitemap:
        fail(
            "Pacote ficou obsoleto: sitemap.xml preparado não é exatamente o resultado "
            "de inserir a nova URL sobre o arquivo atual."
        )


def clean_status() -> str:
    return git_output("status", "--porcelain=v1", "--untracked-files=all")


def preflight(package_dir: Path, report_path: Path) -> dict[str, Any]:
    manifest, slug, targets = validate_package(package_dir)
    ensure_current_main_matches_package(package_dir, slug)

    if clean_status():
        fail("Checkout não está limpo antes do preflight.")

    base_sha = git_output("rev-parse", "HEAD")
    branch = git_output("rev-parse", "--abbrev-ref", "HEAD")
    if branch != "main":
        fail(f"Preflight definitivo só pode partir de main; branch atual: {branch}")

    commit_name_status: list[str] = []
    staged_diff_check_passed = False
    try:
        for target in targets:
            shutil.copyfile(package_dir / target, ROOT / target)

        modified = set(filter(None, git_output("diff", "--name-only").splitlines()))
        untracked = set(filter(None, git_output("ls-files", "--others", "--exclude-standard").splitlines()))
        observed = modified | untracked
        if observed != set(targets):
            fail(f"Aplicação do pacote alterou escopo inesperado: {sorted(observed)}")

        run_git("add", "--", *targets)
        staged = list(filter(None, git_output("diff", "--cached", "--name-only").splitlines()))
        if set(staged) != set(targets) or len(staged) != 3:
            fail(f"Stage final precisa conter exatamente três arquivos: {staged}")

        unstaged = git_output("diff", "--name-only")
        if unstaged:
            fail("Há alterações não staged após preparar a publicação: " + unstaged)

        check = run_git("diff", "--cached", "--check", check=False)
        if check.returncode != 0:
            fail("git diff --cached --check falhou:\n" + check.stdout + check.stderr)
        staged_diff_check_passed = True

        commit_name_status = list(
            filter(None, git_output("diff", "--cached", "--name-status").splitlines())
        )
        actual = {
            line.split("\t", 1)[1]: line.split("\t", 1)[0]
            for line in commit_name_status
            if "\t" in line
        }
        expected = {slug: "A", "noticias.json": "M", "sitemap.xml": "M"}
        if actual != expected:
            fail(f"Tipos de alteração do preflight são inesperados: {actual}")

        report = {
            "step": 31,
            "mode": "definitive_publication_preflight_locked",
            "source_step": manifest.get("step"),
            "slug": slug,
            "base_main_sha": base_sha,
            "changed_files": targets,
            "changed_file_count": 3,
            "staged_name_status": commit_name_status,
            "package_matches_current_main": True,
            "duplicate_checks_passed": True,
            "staged_diff_check_passed": staged_diff_check_passed,
            "commit_created": False,
            "push_executed": False,
            "main_published": False,
            "publication_authorized": False,
            "publication_unlocked": False,
            "publication_gate_reached": True,
        }
    finally:
        run_git("reset", "--hard", base_sha, check=False)
        run_git("clean", "-fd", "--", slug, check=False)

    if git_output("rev-parse", "HEAD") != base_sha:
        fail("HEAD mudou durante o preflight bloqueado.")
    if clean_status():
        fail("Checkout não voltou limpo após o preflight.")

    report["checkout_restored_clean"] = True
    report["main_unchanged_locally"] = True
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preflight definitivo de publicação, ainda bloqueado.")
    parser.add_argument("--package-dir", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    package_dir = args.package_dir.resolve()
    report_path = args.report.resolve()
    allowed = (ROOT / "build" / "pre-jogo").resolve()
    try:
        package_dir.relative_to(allowed)
        report_path.relative_to(allowed)
    except ValueError:
        fail("Pacote e relatório do Passo 31 precisam ficar em build/pre-jogo/.")

    report = preflight(package_dir, report_path)
    print("OK: porta final de publicação alcançada, mas permanece bloqueada.")
    print(f"HTML futuro: {report['slug']}")
    for item in report["staged_name_status"]:
        print(f"  {item}")
    print("Arquivos preparados no stage: 3")
    print("Commit criado: não")
    print("Push executado: não")
    print("Main publicada: não")
    print("Publicação autorizada: não")
    print("Checkout restaurado: sim")


if __name__ == "__main__":
    main()
