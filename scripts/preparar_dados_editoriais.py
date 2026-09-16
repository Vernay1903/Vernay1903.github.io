#!/usr/bin/env python3
"""Prepara metadados editoriais de pré-jogo sem redigir ou publicar a matéria."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo"

MONTHS_PT = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


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
        fail('O timezone deve permanecer "America/Sao_Paulo".')

    category = config.get("category")
    if not isinstance(category, dict):
        fail('Configuração "category" ausente ou inválida.')
    if category.get("slug") != "futebol" or category.get("name") != "Futebol":
        fail('A categoria deve permanecer fixa como "Futebol".')

    editorial = config.get("editorial")
    if not isinstance(editorial, dict):
        fail('Configuração "editorial" ausente ou inválida.')

    title_tail = editorial.get("title_tail")
    if not isinstance(title_tail, str) or not title_tail.strip():
        fail('Configuração "editorial.title_tail" ausente ou inválida.')

    labels = editorial.get("competition_labels")
    if not isinstance(labels, dict) or not labels:
        fail('Configuração "editorial.competition_labels" ausente ou inválida.')

    provider = config.get("fixtures_provider")
    if not isinstance(provider, dict):
        fail('Configuração "fixtures_provider" ausente ou inválida.')
    competition_slugs = provider.get("competition_slugs")
    if not isinstance(competition_slugs, dict):
        fail('Configuração "fixtures_provider.competition_slugs" inválida.')

    missing_labels = sorted(
        slug for slug in set(competition_slugs.values()) if slug not in labels
    )
    if missing_labels:
        fail("Faltam rótulos editoriais para: " + ", ".join(missing_labels))

    for slug, item in labels.items():
        if not isinstance(item, dict):
            fail(f'Rótulo editorial inválido para "{slug}".')
        if not isinstance(item.get("name"), str) or not item["name"].strip():
            fail(f'Nome editorial inválido para "{slug}".')
        if item.get("connector") not in {"pela", "pelo"}:
            fail(f'Conector editorial inválido para "{slug}".')

    requirements = editorial.get("research_requirements")
    if not isinstance(requirements, list) or not requirements:
        fail('Configuração "editorial.research_requirements" inválida.')
    if not all(isinstance(item, str) and item.strip() for item in requirements):
        fail("Todos os requisitos de pesquisa devem ser textos não vazios.")

    article = config.get("article")
    if not isinstance(article, dict):
        fail('Configuração "article" ausente ou inválida.')
    min_words = article.get("min_words")
    if not isinstance(min_words, int) or min_words < 700:
        fail("O mínimo editorial deve permanecer em pelo menos 700 palavras.")

    monitored = config.get("monitored_clubs")
    if not isinstance(monitored, list) or len(monitored) != 10:
        fail("A configuração deve conter exatamente os 10 clubes monitorados.")

    return config


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def monitored_name_index(config: dict[str, Any]) -> dict[str, str]:
    index: dict[str, str] = {}
    for club in config["monitored_clubs"]:
        if not isinstance(club, dict):
            fail("Há um clube inválido em monitored_clubs.")
        name = club.get("name")
        slug = club.get("slug")
        aliases = club.get("aliases", [])
        if not isinstance(name, str) or not name.strip():
            fail("Clube monitorado sem nome válido.")
        if not isinstance(slug, str) or not slug.strip():
            fail(f"Clube sem slug válido: {name}")
        if not isinstance(aliases, list) or not all(isinstance(x, str) for x in aliases):
            fail(f"Aliases inválidos para {name}.")
        for candidate in [name, slug.replace("-", " "), *aliases]:
            key = normalize_text(candidate)
            if key:
                index[key] = name.strip()
    return index


def display_team_name(value: Any, config: dict[str, Any]) -> str:
    if not isinstance(value, str) or not value.strip():
        fail("Jogo planejado sem nome de equipe válido.")
    raw = value.strip()
    return monitored_name_index(config).get(normalize_text(raw), raw)


def parse_target_date(raw: str | None, tz: ZoneInfo) -> date:
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            fail("--date deve usar o formato YYYY-MM-DD.")
    return datetime.now(tz).date() + timedelta(days=1)


def load_plans(path: Path, target_date: date) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, dict):
        fail("O arquivo de planos deve ser um objeto JSON.")
    if data.get("target_date") != target_date.isoformat():
        fail("A data do arquivo de planos não coincide com a data-alvo.")
    planned = data.get("planned")
    if not isinstance(planned, list):
        fail('O arquivo de planos deve conter um array "planned".')
    for idx, item in enumerate(planned):
        if not isinstance(item, dict):
            fail(f"Plano na posição {idx} não é um objeto JSON.")
    return planned


def long_date_pt(target_date: date) -> str:
    return f"{target_date.day} de {MONTHS_PT[target_date.month - 1]} de {target_date.year}"


def format_kickoff(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
        fail("Plano sem kickoff_time_brasilia válido no formato HH:MM.")
    hour, minute = value.split(":")
    hour_number = int(hour)
    minute_number = int(minute)
    if not 0 <= hour_number <= 23 or not 0 <= minute_number <= 59:
        fail("kickoff_time_brasilia fora de uma hora válida.")
    if minute_number == 0:
        return f"{hour_number}h"
    return f"{hour_number}h{minute_number:02d}"


def competition_label(plan: dict[str, Any], config: dict[str, Any]) -> dict[str, str]:
    slug = plan.get("competition_slug")
    if not isinstance(slug, str) or not slug.strip():
        fail("Plano sem competition_slug válido.")
    raw = config["editorial"]["competition_labels"].get(slug.strip())
    if not isinstance(raw, dict):
        fail(f'Sem rótulo editorial para a competição "{slug}".')
    return {"name": raw["name"].strip(), "connector": raw["connector"]}


def build_editorial_record(
    plan: dict[str, Any],
    *,
    target_date: date,
    config: dict[str, Any],
) -> dict[str, Any]:
    home = display_team_name(plan.get("home"), config)
    away = display_team_name(plan.get("away"), config)
    label = competition_label(plan, config)

    slug = plan.get("slug")
    if not isinstance(slug, str) or not slug.endswith(".html"):
        fail("Plano sem slug HTML válido.")

    article_date = plan.get("article_date")
    expected_date = target_date.strftime("%d/%m/%Y")
    if article_date != expected_date:
        fail(f"article_date do plano deve ser {expected_date}.")

    kickoff_raw = plan.get("kickoff_time_brasilia")
    kickoff_display = format_kickoff(kickoff_raw)
    connector = label["connector"]
    competition_name = label["name"]
    title_tail = config["editorial"]["title_tail"].strip()

    title = f"{home} x {away} {connector} {competition_name}: {title_tail}"
    excerpt = (
        f"{home} e {away} se enfrentam em {long_date_pt(target_date)}, às "
        f"{kickoff_display} (de Brasília), {connector} {competition_name}; veja "
        "transmissão, prováveis escalações, arbitragem e informações do confronto."
    )

    noticias_entry = {
        "title": title,
        "excerpt": excerpt,
        "url": slug,
        "date": expected_date,
        "category": config["category"]["name"],
    }

    return {
        "title": title,
        "excerpt": excerpt,
        "date": expected_date,
        "slug": slug,
        "body_html": None,
        "body_html_status": "pending_research_and_drafting",
        "ready_for_html": False,
        "fixture_id": plan.get("fixture_id"),
        "match_context": {
            "home": home,
            "away": away,
            "competition": competition_name,
            "competition_slug": plan.get("competition_slug"),
            "kickoff_brasilia": plan.get("kickoff_brasilia"),
            "kickoff_time_brasilia": kickoff_raw,
            "prepare_at_brasilia": plan.get("prepare_at_brasilia"),
            "target_publish_at_brasilia": plan.get("target_publish_at_brasilia"),
            "monitored_clubs": plan.get("monitored_clubs", []),
            "two_monitored_clubs_same_match": bool(
                plan.get("two_monitored_clubs_same_match")
            ),
        },
        "research_requirements": list(config["editorial"]["research_requirements"]),
        "html_requirements": {
            "minimum_words": config["article"]["min_words"],
            "subtitles_in_strong": bool(config["article"].get("require_subtitles_strong")),
            "internal_link_required": bool(config["article"].get("require_internal_link")),
            "category": config["category"]["name"],
            "image_rotation": "deferred_until_html_generation",
        },
        "noticias_entry": noticias_entry,
    }


def build_editorial_records(
    plans: list[dict[str, Any]],
    *,
    target_date: date,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    records = [
        build_editorial_record(plan, target_date=target_date, config=config)
        for plan in plans
    ]
    seen_slugs: set[str] = set()
    for record in records:
        slug = record["slug"]
        if slug in seen_slugs:
            fail(f"Slug editorial duplicado no lote: {slug}")
        seen_slugs.add(slug)
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepara título, excerpt, slug, data e contexto editorial para o HTML "
            "sem redigir ou publicar matérias."
        )
    )
    parser.add_argument(
        "--date",
        help="Data-alvo YYYY-MM-DD. Se omitida, usa amanhã em America/Sao_Paulo.",
    )
    parser.add_argument(
        "--plans",
        type=Path,
        help="Arquivo planos-AAAA-MM-DD.json. Se omitido, usa build/pre-jogo/.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Diretório de saída. Padrão: build/pre-jogo/.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite substituir somente arquivos editoriais dentro de build/.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    tz = ZoneInfo(config["timezone"])
    target_date = parse_target_date(args.date, tz)

    plans_path = args.plans
    if plans_path is None:
        plans_path = DEFAULT_OUTPUT_DIR / f"planos-{target_date.isoformat()}.json"

    plans = load_plans(plans_path, target_date)
    records = build_editorial_records(
        plans,
        target_date=target_date,
        config=config,
    )

    output_dir = args.output_dir.resolve()
    records_dir = output_dir / f"dados-editoriais-{target_date.isoformat()}"
    manifest_path = output_dir / f"dados-editoriais-{target_date.isoformat()}.json"

    destinations = [
        records_dir / Path(record["slug"]).with_suffix(".json").name
        for record in records
    ]
    destinations.append(manifest_path)

    existing = [path for path in destinations if path.exists()]
    if existing and not args.force:
        relative = ", ".join(
            str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
            for path in existing
        )
        fail(
            "Dados editoriais já existem: "
            + relative
            + ". Use --force somente para substituir arquivos de build."
        )

    records_dir.mkdir(parents=True, exist_ok=True)
    written_files: list[str] = []
    for record, destination in zip(records, destinations[:-1]):
        destination.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written_files.append(
            str(destination.relative_to(ROOT)) if destination.is_relative_to(ROOT) else str(destination)
        )

    manifest = {
        "generated_at": datetime.now(tz).isoformat(),
        "target_date": target_date.isoformat(),
        "timezone": config["timezone"],
        "source_plans": str(plans_path),
        "editorial_count": len(records),
        "ready_for_html_count": sum(1 for item in records if item["ready_for_html"]),
        "files": written_files,
        "records": records,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"OK: dados editoriais preparados para {target_date.isoformat()}.")
    print(f"Matérias preparadas: {len(records)}")
    print("Prontas para HTML: 0 (o corpo ainda depende de pesquisa e redação).")
    for record in records:
        print(f'- {record["title"]} | {record["slug"]}')
    print(
        f"Manifesto: {manifest_path.relative_to(ROOT) if manifest_path.is_relative_to(ROOT) else manifest_path}"
    )
    print("Nenhum HTML, noticias.json ou sitemap.xml foi alterado.")


if __name__ == "__main__":
    main()
