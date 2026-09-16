#!/usr/bin/env python3
"""Prepara o pacote exato de publicação do pré-jogo sem publicar nada.

Entrada:
- prévia HTML validada do Passo 27;
- metadata do Passo 27;
- contrato editorial limpo;
- noticias.json e sitemap.xml atuais do repositório.

Saída, exclusivamente dentro de build/pre-jogo/publication-package/:
- <slug>.html: cópia exata da prévia que futuramente iria para a raiz;
- noticias.json: cópia com a nova notícia como primeiro objeto;
- sitemap.xml: cópia com a nova URL como primeira matéria;
- manifest.json: descrição das três alterações preparadas.

Este script NÃO grava na raiz do site e NÃO altera os arquivos publicados.
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo" / "publication-package"
NOTICIAS_PATH = ROOT / "noticias.json"
SITEMAP_PATH = ROOT / "sitemap.xml"
SITEMAP_MARKER = "<!-- MATÉRIAS -->"
SITE_BASE = "https://cortedosesportes.com.br/"

H1_RE = re.compile(r'<h1\s+id=["\']articleTitle["\'][^>]*>(.*?)</h1>', re.I | re.S)
EXCERPT_RE = re.compile(
    r'<p\s+class=["\']subhead["\']\s+id=["\']articleExcerpt["\'][^>]*>(.*?)</p>',
    re.I | re.S,
)
DATE_RE = re.compile(r'<span\s+id=["\']articleDate["\'][^>]*>(.*?)</span>', re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


def fail(message: str) -> NoReturn:
    print(f"ERRO: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"Arquivo não encontrado: {path}")
    except json.JSONDecodeError as exc:
        fail(f"JSON inválido em {path}: {exc}")


def require_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        fail(f"Campo obrigatório ausente ou vazio: {key}")
    return value.strip()


def clean_html_text(value: str) -> str:
    return " ".join(html_lib.unescape(TAG_RE.sub(" ", value)).split())


def extract_one(pattern: re.Pattern[str], source: str, label: str) -> str:
    match = pattern.search(source)
    if not match:
        fail(f"Não foi possível localizar {label} na prévia HTML.")
    return clean_html_text(match.group(1))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def date_to_iso(date_br: str) -> str:
    try:
        return datetime.strptime(date_br, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        fail(f"Data inválida, esperado DD/MM/YYYY: {date_br}")


def render_news_object(title: str, excerpt: str, slug: str, date_br: str) -> str:
    # Mantém a ordem editorial exigida e usa json.dumps apenas para escapar valores.
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


def build_noticias_copy(
    original: str, *, title: str, excerpt: str, slug: str, date_br: str
) -> str:
    try:
        current = json.loads(original)
    except json.JSONDecodeError as exc:
        fail(f"noticias.json atual é inválido: {exc}")
    if not isinstance(current, list):
        fail("noticias.json atual não é um array.")

    urls = [item.get("url") for item in current if isinstance(item, dict)]
    if slug in urls:
        fail(f"URL já existe em noticias.json: {slug}")

    stripped = original.lstrip("\ufeff")
    open_pos = stripped.find("[")
    if open_pos < 0:
        fail("Não foi possível localizar o início do array em noticias.json.")

    obj = render_news_object(title, excerpt, slug, date_br)
    updated = stripped[: open_pos + 1] + "\n\n" + obj + "," + stripped[open_pos + 1 :]

    try:
        parsed = json.loads(updated)
    except json.JSONDecodeError as exc:
        fail(f"Cópia preparada de noticias.json ficou inválida: {exc}")

    expected_first = {
        "title": title,
        "excerpt": excerpt,
        "url": slug,
        "date": date_br,
        "category": "Futebol",
    }
    if not parsed or parsed[0] != expected_first:
        fail("A nova notícia não ficou como primeiro objeto de noticias.json.")
    if parsed[1:] != current:
        fail("O conteúdo antigo de noticias.json foi alterado ou reordenado.")
    return updated


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


def build_sitemap_copy(original: str, *, slug: str, lastmod: str) -> str:
    target_url = f"{SITE_BASE}{slug}"
    if target_url in original:
        fail(f"URL já existe em sitemap.xml: {target_url}")
    if original.count(SITEMAP_MARKER) != 1:
        fail("sitemap.xml precisa conter exatamente um marcador <!-- MATÉRIAS -->.")

    marker_pos = original.index(SITEMAP_MARKER) + len(SITEMAP_MARKER)
    entry = sitemap_entry(slug, lastmod)
    updated = original[:marker_pos] + "\n\n  " + entry.replace("\n", "\n  ") + original[marker_pos:]

    try:
        ET.fromstring(updated)
    except ET.ParseError as exc:
        fail(f"Cópia preparada de sitemap.xml ficou inválida: {exc}")

    if updated.index(target_url) <= updated.index(SITEMAP_MARKER):
        fail("A nova URL não foi inserida depois do marcador de matérias.")

    tail = updated[updated.index(SITEMAP_MARKER) + len(SITEMAP_MARKER) :]
    first_loc = re.search(r"<loc>(.*?)</loc>", tail, flags=re.S)
    if not first_loc or first_loc.group(1).strip() != target_url:
        fail("A nova URL não ficou como a primeira matéria do sitemap.xml.")
    return updated


def validate_preview(
    preview_html: str, metadata: dict[str, Any], contract: dict[str, Any], preview_path: Path
) -> tuple[str, str, str, str]:
    slug = require_text(contract, "slug")
    title = require_text(contract, "title")
    excerpt = require_text(contract, "excerpt")
    date_br = require_text(contract, "date")

    if preview_path.name != slug:
        fail(f"Nome da prévia não corresponde ao slug: {preview_path.name} != {slug}")
    if metadata.get("step") != 27:
        fail("Metadata não pertence ao Passo 27.")
    if metadata.get("slug") != slug:
        fail("Slug do metadata diverge do contrato.")
    if metadata.get("preview_only") is not True:
        fail("Metadata não está marcado como preview_only.")
    if metadata.get("ready_for_publication") is not False:
        fail("A trava ready_for_publication do Passo 27 foi alterada.")
    if metadata.get("noticias_json_touched") is not False:
        fail("Metadata indica alteração indevida de noticias.json no Passo 27.")
    if metadata.get("sitemap_xml_touched") is not False:
        fail("Metadata indica alteração indevida de sitemap.xml no Passo 27.")
    if metadata.get("published_html_touched") is not False:
        fail("Metadata indica alteração indevida de HTML publicado no Passo 27.")

    h1 = extract_one(H1_RE, preview_html, "articleTitle")
    shown_excerpt = extract_one(EXCERPT_RE, preview_html, "articleExcerpt")
    shown_date = extract_one(DATE_RE, preview_html, "articleDate")

    if h1 != title:
        fail("Título da prévia diverge do contrato editorial.")
    if shown_excerpt != excerpt:
        fail("Excerpt da prévia diverge do contrato editorial.")
    if shown_date != date_br:
        fail("Data da prévia diverge do contrato editorial.")

    if preview_html.count('data-ad-slot="8702501261"') != 3:
        fail("Prévia não contém exatamente três anúncios internos.")
    if preview_html.count('data-ad-slot="5521804159"') != 1:
        fail("Prévia não preserva exatamente um anúncio de sidebar.")
    selected_image = metadata.get("selected_image")
    if not isinstance(selected_image, str) or not selected_image or selected_image not in preview_html:
        fail("Imagem selecionada pelo Passo 27 não está presente na prévia.")

    return slug, title, excerpt, date_br


def ensure_output_dir(output_dir: Path) -> Path:
    allowed = (ROOT / "build" / "pre-jogo").resolve()
    resolved = output_dir.resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError:
        fail("Passo 28 só pode gravar dentro de build/pre-jogo/.")
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepara pacote de publicação do Passo 28 sem publicar.")
    parser.add_argument("--preview", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = ensure_output_dir(args.output_dir)

    try:
        preview_html = args.preview.read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(f"Prévia não encontrada: {args.preview}")

    metadata = load_json(args.metadata)
    contract = load_json(args.contract)
    if not isinstance(metadata, dict) or not isinstance(contract, dict):
        fail("Metadata ou contrato inválido.")

    slug, title, excerpt, date_br = validate_preview(
        preview_html, metadata, contract, args.preview
    )

    target_html = ROOT / slug
    if target_html.exists():
        fail(f"Arquivo HTML de destino já existe na raiz: {slug}")

    noticias_original = NOTICIAS_PATH.read_text(encoding="utf-8")
    sitemap_original = SITEMAP_PATH.read_text(encoding="utf-8")

    noticias_prepared = build_noticias_copy(
        noticias_original, title=title, excerpt=excerpt, slug=slug, date_br=date_br
    )
    sitemap_prepared = build_sitemap_copy(
        sitemap_original, slug=slug, lastmod=date_to_iso(date_br)
    )

    targets = {
        slug: preview_html,
        "noticias.json": noticias_prepared,
        "sitemap.xml": sitemap_prepared,
    }

    if output_dir.exists() and any(output_dir.iterdir()) and not args.force:
        fail(f"Diretório do pacote já contém arquivos: {output_dir}")
    if output_dir.exists() and args.force:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for relative_target, content in targets.items():
        (output_dir / relative_target).write_text(content, encoding="utf-8")

    manifest = {
        "step": 28,
        "mode": "publication_package_only",
        "slug": slug,
        "source_step": 27,
        "source_preview_validated": True,
        "prepared_changes": [
            {
                "target": slug,
                "operation": "create",
                "sha256": sha256_text(preview_html),
            },
            {
                "target": "noticias.json",
                "operation": "modify",
                "rule": "new article is first object; older objects preserved",
                "sha256": sha256_text(noticias_prepared),
            },
            {
                "target": "sitemap.xml",
                "operation": "modify",
                "rule": "new URL is first entry after <!-- MATÉRIAS -->",
                "sha256": sha256_text(sitemap_prepared),
            },
        ],
        "prepared_change_count": 3,
        "duplicate_slug_checked": True,
        "noticias_json_validated": True,
        "sitemap_xml_validated": True,
        "published_files_touched": False,
        "commit_executed": False,
        "publication_unlocked": False,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print("OK: pacote de publicação do Passo 28 preparado somente em build/.")
    print(f"HTML preparado: {slug}")
    print("noticias.json preparado: nova notícia em primeiro")
    print("sitemap.xml preparado: nova URL como primeira matéria")
    print("Alterações preparadas para futuro commit: 3")
    print("Arquivos publicados alterados: não")
    print("Commit executado: não")
    print("Publicação liberada: não")


if __name__ == "__main__":
    main()
