#!/usr/bin/env python3
"""
Monta uma prévia HTML de matéria automática de pré-jogo.

Este script NÃO publica nada e NÃO altera noticias.json ou sitemap.xml.
Por padrão, grava apenas em build/pre-jogo/.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "templates" / "pre-jogo.html"
IMAGE_BLOCKS = (
    ROOT / "templates" / "imagens" / "01-bola-uhlsport.html",
    ROOT / "templates" / "imagens" / "02-bola-adidas.html",
    ROOT / "templates" / "imagens" / "03-bola-estadio.html",
)
IMAGE_NAMES = (
    "bola-uhlsport-gramado.jpg",
    "bola-adidas-gramado.jpg",
    "bola-estadio-futebol.jpg",
)
NOTICIAS_PATH = ROOT / "noticias.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo"

AUTO_SLUG_RE = re.compile(
    r"^[a-z0-9]+(?:-[a-z0-9]+)*-\d{4}-transmissao-horario-escalacoes\.html$"
)
WORD_RE = re.compile(r"\b[\wÀ-ÖØ-öø-ÿ'-]+\b", re.UNICODE)
TAG_RE = re.compile(r"<[^>]+>")


def fail(message: str) -> "NoReturn":
    print(f"ERRO: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"Arquivo de entrada não encontrado: {path}")
    except json.JSONDecodeError as exc:
        fail(f"JSON inválido em {path}: {exc}")
    if not isinstance(data, dict):
        fail("O arquivo de entrada deve conter um objeto JSON.")
    return data


def require_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        fail(f'Campo obrigatório ausente ou vazio: "{key}".')
    return value.strip()


def validate_date(value: str) -> None:
    try:
        datetime.strptime(value, "%d/%m/%Y")
    except ValueError:
        fail('O campo "date" deve estar no formato DD/MM/YYYY.')


def validate_slug(slug: str) -> None:
    if Path(slug).name != slug:
        fail('O campo "slug" deve conter apenas o nome do arquivo, sem pastas.')
    if not AUTO_SLUG_RE.fullmatch(slug):
        fail(
            'Slug fora do padrão: '
            "mandante-visitante-competicao-ano-transmissao-horario-escalacoes.html"
        )


def visible_text(body_html: str) -> str:
    no_tags = TAG_RE.sub(" ", body_html)
    return html.unescape(no_tags)


def count_words(body_html: str) -> int:
    return len(WORD_RE.findall(visible_text(body_html)))


def validate_body(body_html: str) -> int:
    if '<article id="articleBody">' in body_html:
        fail('O campo "body_html" não deve conter a tag <article id="articleBody">.')
    words = count_words(body_html)
    if words < 700:
        fail(f"A matéria tem {words} palavras; o mínimo definido é 700.")
    if "<strong>" not in body_html:
        fail("A matéria precisa conter subtítulos em <strong>.")
    if "https://cortedosesportes.com.br/" not in body_html:
        fail("A matéria precisa conter pelo menos um link interno do Corte dos Esportes.")
    return words


def load_template() -> str:
    try:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(f"Template mestre não encontrado: {TEMPLATE_PATH}")
    required = ("{{TITLE}}", "{{EXCERPT}}", "{{DATE}}", "{{IMAGE_BLOCK}}", "{{ARTICLE_BODY}}")
    missing = [token for token in required if token not in template]
    if missing:
        fail(f"Template mestre sem placeholders obrigatórios: {', '.join(missing)}")
    return template


def detect_last_image_index() -> int | None:
    """
    Procura, do mais recente para o mais antigo em noticias.json, a última matéria
    no padrão automático e identifica qual dos três blocos fixos ela utilizou.
    Não modifica nenhum arquivo.
    """
    if not NOTICIAS_PATH.exists():
        return None

    try:
        noticias = json.loads(NOTICIAS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        fail("noticias.json está inválido; a rotação de imagens foi interrompida.")

    if not isinstance(noticias, list):
        fail("noticias.json deve ser um array.")

    for item in noticias:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not AUTO_SLUG_RE.fullmatch(url):
            continue

        article_path = ROOT / url
        if not article_path.is_file():
            continue

        try:
            article_html = article_path.read_text(encoding="utf-8")
        except OSError:
            continue

        for idx, image_name in enumerate(IMAGE_NAMES):
            if image_name in article_html:
                return idx

    return None


def choose_image_index(rotation_offset: int) -> int:
    if rotation_offset < 0:
        fail("--rotation-offset não pode ser negativo.")
    last = detect_last_image_index()
    base = 0 if last is None else (last + 1) % len(IMAGE_BLOCKS)
    return (base + rotation_offset) % len(IMAGE_BLOCKS)


def load_image_block(index: int) -> str:
    path = IMAGE_BLOCKS[index]
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(f"Bloco fixo de imagem não encontrado: {path}")


def render(
    *,
    title: str,
    excerpt: str,
    date: str,
    body_html: str,
    image_block: str,
) -> str:
    template = load_template()
    rendered = (
        template.replace("{{TITLE}}", html.escape(title, quote=True))
        .replace("{{EXCERPT}}", html.escape(excerpt, quote=True))
        .replace("{{DATE}}", html.escape(date, quote=True))
        .replace("{{IMAGE_BLOCK}}", image_block)
        .replace("{{ARTICLE_BODY}}", body_html)
    )
    unresolved = re.findall(r"\{\{[A-Z0-9_]+\}\}", rendered)
    if unresolved:
        fail(f"Placeholders não resolvidos no HTML: {', '.join(sorted(set(unresolved)))}")
    return rendered


def output_path_for(slug: str, output_dir: Path) -> Path:
    output_dir = output_dir.resolve()
    return output_dir / slug


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monta uma prévia HTML de pré-jogo sem publicar no site."
    )
    parser.add_argument(
        "--data",
        required=True,
        type=Path,
        help='JSON com "title", "excerpt", "date", "slug" e "body_html".',
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Diretório de saída. Padrão: build/pre-jogo/.",
    )
    parser.add_argument(
        "--rotation-offset",
        type=int,
        default=0,
        help="Deslocamento para lotes com várias matérias: 0, 1, 2...",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite sobrescrever apenas o arquivo de prévia no diretório de saída.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = load_json(args.data)

    title = require_text(data, "title")
    excerpt = require_text(data, "excerpt")
    date = require_text(data, "date")
    slug = require_text(data, "slug")
    body_html = require_text(data, "body_html")

    validate_date(date)
    validate_slug(slug)
    words = validate_body(body_html)

    image_index = choose_image_index(args.rotation_offset)
    image_block = load_image_block(image_index)

    rendered = render(
        title=title,
        excerpt=excerpt,
        date=date,
        body_html=body_html,
        image_block=image_block,
    )

    destination = output_path_for(slug, args.output_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists() and not args.force:
        fail(
            f"A prévia já existe: {destination}. "
            "Use --force somente se quiser substituir essa prévia."
        )

    destination.write_text(rendered, encoding="utf-8")

    print("OK: prévia HTML montada.")
    print(f"Arquivo: {destination.relative_to(ROOT) if destination.is_relative_to(ROOT) else destination}")
    print(f"Palavras no corpo: {words}")
    print(f"Imagem: {IMAGE_NAMES[image_index]}")
    print("Nenhum arquivo publicado foi alterado.")


if __name__ == "__main__":
    main()
