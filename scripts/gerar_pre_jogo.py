#!/usr/bin/env python3
"""
Monta uma prévia HTML de matéria automática de pré-jogo.

Este script NÃO publica nada e NÃO altera noticias.json ou sitemap.xml.
Por padrão, grava apenas em build/pre-jogo/.
As regras fixas são lidas de config/pre-jogo.json.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
NOTICIAS_PATH = ROOT / "noticias.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo"

WORD_RE = re.compile(r"\b[\wÀ-ÖØ-öø-ÿ'-]+\b", re.UNICODE)
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


def load_config() -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    if not isinstance(config, dict):
        fail("config/pre-jogo.json deve conter um objeto JSON.")

    if config.get("timezone") != "America/Sao_Paulo":
        fail('A configuração de timezone deve ser "America/Sao_Paulo".')

    category = config.get("category")
    if not isinstance(category, dict):
        fail('Configuração "category" ausente ou inválida.')
    if category.get("slug") != "futebol" or category.get("name") != "Futebol":
        fail('A categoria da automação deve permanecer fixa como "Futebol".')

    article = config.get("article")
    if not isinstance(article, dict):
        fail('Configuração "article" ausente ou inválida.')
    min_words = article.get("min_words")
    if not isinstance(min_words, int) or min_words < 1:
        fail('Configuração "article.min_words" inválida.')

    monitored = config.get("monitored_clubs")
    if not isinstance(monitored, list) or len(monitored) != 10:
        fail("A configuração deve conter exatamente os 10 clubes monitorados.")

    images = config.get("images")
    if not isinstance(images, dict):
        fail('Configuração "images" ausente ou inválida.')
    if images.get("mode") != "sequential_rotation":
        fail('O modo de imagens deve permanecer "sequential_rotation".')
    if images.get("one_per_article") is not True:
        fail("A configuração deve manter exatamente uma imagem por matéria.")
    items = images.get("items")
    if not isinstance(items, list) or len(items) != 3:
        fail("A configuração deve conter exatamente os três blocos fixos de imagem.")

    scope = config.get("scope")
    if not isinstance(scope, dict):
        fail('Configuração "scope" ausente ou inválida.')
    if scope.get("official_first_team_only") is not True:
        fail("A automação deve permanecer limitada a jogos oficiais do time principal.")
    if scope.get("exclude_friendlies") is not True:
        fail("Amistosos devem permanecer excluídos da automação.")
    if scope.get("if_two_monitored_clubs_same_match") != "single_article":
        fail("Confrontos entre dois clubes monitorados devem gerar apenas uma matéria.")
    if scope.get("if_postponed_or_cancelled") != "skip":
        fail("Jogos adiados ou cancelados devem permanecer sem publicação.")

    return config


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


def slug_regex(config: dict[str, Any]) -> re.Pattern[str]:
    slug_config = config.get("slug")
    if not isinstance(slug_config, dict):
        fail('Configuração "slug" ausente ou inválida.')
    suffix = slug_config.get("suffix")
    if not isinstance(suffix, str) or not suffix:
        fail('Configuração "slug.suffix" ausente ou inválida.')
    return re.compile(
        rf"^[a-z0-9]+(?:-[a-z0-9]+)*-\d{{4}}-{re.escape(suffix)}$"
    )


def validate_slug(slug: str, config: dict[str, Any]) -> None:
    if Path(slug).name != slug:
        fail('O campo "slug" deve conter apenas o nome do arquivo, sem pastas.')
    if not slug_regex(config).fullmatch(slug):
        pattern = config.get("slug", {}).get(
            "pattern",
            "mandante-visitante-competicao-ano-transmissao-horario-escalacoes.html",
        )
        fail(f"Slug fora do padrão: {pattern}")


def visible_text(body_html: str) -> str:
    no_tags = TAG_RE.sub(" ", body_html)
    return html.unescape(no_tags)


def count_words(body_html: str) -> int:
    return len(WORD_RE.findall(visible_text(body_html)))


def validate_body(body_html: str, config: dict[str, Any]) -> int:
    if '<article id="articleBody">' in body_html:
        fail('O campo "body_html" não deve conter a tag <article id="articleBody">.')

    article_rules = config["article"]
    min_words = article_rules["min_words"]
    words = count_words(body_html)
    if words < min_words:
        fail(f"A matéria tem {words} palavras; o mínimo definido é {min_words}.")

    if article_rules.get("require_subtitles_strong") is True and "<strong>" not in body_html:
        fail("A matéria precisa conter subtítulos em <strong>.")

    if article_rules.get("require_internal_link") is True:
        domain = article_rules.get("internal_link_domain")
        if not isinstance(domain, str) or not domain:
            fail('Configuração "article.internal_link_domain" inválida.')
        if domain not in body_html:
            fail("A matéria precisa conter pelo menos um link interno do Corte dos Esportes.")

    return words


def template_path(config: dict[str, Any]) -> Path:
    value = config.get("template")
    if not isinstance(value, str) or not value:
        fail('Configuração "template" ausente ou inválida.')
    return ROOT / value


def load_template(config: dict[str, Any]) -> str:
    path = template_path(config)
    try:
        template = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(f"Template mestre não encontrado: {path}")

    required = (
        "{{TITLE}}",
        "{{EXCERPT}}",
        "{{DATE}}",
        "{{IMAGE_BLOCK}}",
        "{{ARTICLE_BODY}}",
    )
    missing = [token for token in required if token not in template]
    if missing:
        fail(f"Template mestre sem placeholders obrigatórios: {', '.join(missing)}")
    return template


def image_items(config: dict[str, Any]) -> list[dict[str, str]]:
    raw_items = config["images"]["items"]
    items: list[dict[str, str]] = []

    for item in raw_items:
        if not isinstance(item, dict):
            fail("Item de imagem inválido na configuração.")
        template = item.get("template")
        filename = item.get("filename")
        if not isinstance(template, str) or not template:
            fail('Cada imagem precisa de um campo "template" válido.')
        if not isinstance(filename, str) or not filename:
            fail('Cada imagem precisa de um campo "filename" válido.')
        items.append({"template": template, "filename": filename})

    return items


def detect_last_image_index(config: dict[str, Any]) -> int | None:
    """
    Procura, do mais recente para o mais antigo em noticias.json, a última matéria
    no padrão automático e identifica qual dos três blocos fixos ela utilizou.
    Não modifica nenhum arquivo.
    """
    if not NOTICIAS_PATH.exists():
        return None

    noticias = load_json(NOTICIAS_PATH)
    if not isinstance(noticias, list):
        fail("noticias.json deve ser um array.")

    auto_slug_re = slug_regex(config)
    items = image_items(config)

    for item in noticias:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not auto_slug_re.fullmatch(url):
            continue

        article_path = ROOT / url
        if not article_path.is_file():
            continue

        try:
            article_html = article_path.read_text(encoding="utf-8")
        except OSError:
            continue

        for idx, image in enumerate(items):
            if image["filename"] in article_html:
                return idx

    return None


def choose_image_index(config: dict[str, Any], rotation_offset: int) -> int:
    if rotation_offset < 0:
        fail("--rotation-offset não pode ser negativo.")

    items = image_items(config)
    last = detect_last_image_index(config)
    base = 0 if last is None else (last + 1) % len(items)
    return (base + rotation_offset) % len(items)


def load_image_block(config: dict[str, Any], index: int) -> str:
    item = image_items(config)[index]
    path = ROOT / item["template"]
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(f"Bloco fixo de imagem não encontrado: {path}")


def render(
    *,
    config: dict[str, Any],
    title: str,
    excerpt: str,
    date: str,
    body_html: str,
    image_block: str,
) -> str:
    template = load_template(config)
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

    marker = config["images"].get("insert_immediately_after")
    if isinstance(marker, str) and marker:
        expected = marker + "\n" + image_block
        if expected not in rendered:
            fail("O bloco de imagem não ficou na posição fixa definida para a matéria.")

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
    config = load_config()

    data = load_json(args.data)
    if not isinstance(data, dict):
        fail("O arquivo de entrada deve conter um objeto JSON.")

    title = require_text(data, "title")
    excerpt = require_text(data, "excerpt")
    date = require_text(data, "date")
    slug = require_text(data, "slug")
    body_html = require_text(data, "body_html")

    validate_date(date)
    validate_slug(slug, config)
    words = validate_body(body_html, config)

    image_index = choose_image_index(config, args.rotation_offset)
    image_block = load_image_block(config, image_index)
    selected_image = image_items(config)[image_index]["filename"]

    rendered = render(
        config=config,
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
    print(f"Imagem: {selected_image}")
    print(f"Timezone configurado: {config['timezone']}")
    print("Nenhum arquivo publicado foi alterado.")


if __name__ == "__main__":
    main()
