#!/usr/bin/env python3
"""Prepara dossiês de pesquisa factual sem consultar fontes externas e sem publicar nada."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo"


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

    editorial = config.get("editorial")
    research = config.get("research")
    if not isinstance(editorial, dict):
        fail('Configuração "editorial" ausente ou inválida.')
    if not isinstance(research, dict):
        fail('Configuração "research" ausente ou inválida.')
    if research.get("auto_fetch_enabled") is not False:
        fail("O Passo 14 deve permanecer sem busca externa automática.")

    requirements = editorial.get("research_requirements")
    policies = research.get("requirement_policy")
    if not isinstance(requirements, list) or not requirements:
        fail('Configuração "editorial.research_requirements" inválida.')
    if not isinstance(policies, dict):
        fail('Configuração "research.requirement_policy" inválida.')

    missing = [item for item in requirements if item not in policies]
    if missing:
        fail("Faltam políticas de pesquisa para: " + ", ".join(missing))

    priority = research.get("source_priority")
    if priority != ["official", "major_sports_media", "relevant_local_press"]:
        fail("A prioridade de fontes deve permanecer oficial > grande imprensa > imprensa local.")

    source_fields = research.get("required_source_fields")
    if not isinstance(source_fields, list) or not source_fields:
        fail('Configuração "research.required_source_fields" inválida.')

    statuses = research.get("allowed_resolution_statuses")
    if not isinstance(statuses, list) or not statuses:
        fail('Configuração "research.allowed_resolution_statuses" inválida.')

    return config


def parse_target_date(raw: str | None, tz: ZoneInfo) -> date:
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            fail("--date deve usar o formato YYYY-MM-DD.")
    return datetime.now(tz).date() + timedelta(days=1)


def load_editorial_records(path: Path, target_date: date) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, dict):
        fail("O manifesto editorial deve ser um objeto JSON.")
    if data.get("target_date") != target_date.isoformat():
        fail("A data do manifesto editorial não coincide com a data-alvo.")
    records = data.get("records")
    if not isinstance(records, list):
        fail('O manifesto editorial deve conter um array "records".')
    for idx, item in enumerate(records):
        if not isinstance(item, dict):
            fail(f"Registro editorial na posição {idx} não é um objeto JSON.")
    return records


def build_requirement(
    requirement_id: str,
    *,
    config: dict[str, Any],
) -> dict[str, Any]:
    policy = config["research"]["requirement_policy"][requirement_id]
    if not isinstance(policy, dict):
        fail(f'Política inválida para "{requirement_id}".')

    return {
        "id": requirement_id,
        "status": "pending",
        "required_for_drafting": bool(policy.get("required_for_drafting")),
        "conditional": bool(policy.get("conditional")),
        "allow_unavailable_after_check": bool(policy.get("allow_unavailable_after_check")),
        "facts": [],
        "sources": [],
        "notes": None,
    }


def build_research_dossier(
    editorial_record: dict[str, Any],
    *,
    config: dict[str, Any],
) -> dict[str, Any]:
    slug = editorial_record.get("slug")
    title = editorial_record.get("title")
    article_date = editorial_record.get("date")
    match_context = editorial_record.get("match_context")

    if not isinstance(slug, str) or not slug.endswith(".html"):
        fail("Registro editorial sem slug HTML válido.")
    if not isinstance(title, str) or not title.strip():
        fail("Registro editorial sem título válido.")
    if not isinstance(article_date, str) or not article_date.strip():
        fail("Registro editorial sem data válida.")
    if not isinstance(match_context, dict):
        fail("Registro editorial sem match_context válido.")
    if editorial_record.get("ready_for_html") is not False:
        fail("A pesquisa factual só pode começar com ready_for_html=false.")

    requirements = editorial_record.get("research_requirements")
    expected = config["editorial"]["research_requirements"]
    if requirements != expected:
        fail(f"Requisitos de pesquisa divergentes para {slug}.")

    requirement_records = [
        build_requirement(requirement_id, config=config)
        for requirement_id in requirements
    ]
    blocking = [
        item["id"] for item in requirement_records if item["required_for_drafting"]
    ]

    research = config["research"]
    return {
        "title": title,
        "slug": slug,
        "date": article_date,
        "fixture_id": editorial_record.get("fixture_id"),
        "match_context": match_context,
        "research_status": "pending",
        "external_research_performed": False,
        "ready_for_drafting": False,
        "ready_for_html": False,
        "source_policy": {
            "priority": list(research["source_priority"]),
            "google_discovery_only": bool(research.get("google_discovery_only")),
            "required_source_fields": list(research["required_source_fields"]),
            "allowed_resolution_statuses": list(research["allowed_resolution_statuses"]),
            "source_rule": research.get("source_rule"),
            "lineup_rule": research.get("lineup_rule"),
        },
        "requirements": requirement_records,
        "blocking_requirement_ids": blocking,
        "verified_fact_count": 0,
        "source_count": 0,
        "editorial_input": {
            "title": editorial_record.get("title"),
            "excerpt": editorial_record.get("excerpt"),
            "slug": slug,
            "noticias_entry": editorial_record.get("noticias_entry"),
        },
    }


def build_research_dossiers(
    editorial_records: list[dict[str, Any]],
    *,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    dossiers = [
        build_research_dossier(record, config=config)
        for record in editorial_records
    ]
    seen: set[str] = set()
    for dossier in dossiers:
        slug = dossier["slug"]
        if slug in seen:
            fail(f"Slug duplicado nos dossiês de pesquisa: {slug}")
        seen.add(slug)
    return dossiers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepara checklists e dossiês de pesquisa factual para matérias de pré-jogo "
            "sem acessar a web e sem publicar nada."
        )
    )
    parser.add_argument(
        "--date",
        help="Data-alvo YYYY-MM-DD. Se omitida, usa amanhã em America/Sao_Paulo.",
    )
    parser.add_argument(
        "--editorial",
        type=Path,
        help="Manifesto dados-editoriais-AAAA-MM-DD.json. Se omitido, usa build/pre-jogo/.",
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
        help="Permite substituir somente arquivos de pesquisa dentro de build/.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    tz = ZoneInfo(config["timezone"])
    target_date = parse_target_date(args.date, tz)

    editorial_path = args.editorial
    if editorial_path is None:
        editorial_path = DEFAULT_OUTPUT_DIR / f"dados-editoriais-{target_date.isoformat()}.json"

    records = load_editorial_records(editorial_path, target_date)
    dossiers = build_research_dossiers(records, config=config)

    output_dir = args.output_dir.resolve()
    dossiers_dir = output_dir / f"pesquisa-{target_date.isoformat()}"
    manifest_path = output_dir / f"pesquisa-{target_date.isoformat()}.json"

    destinations = [
        dossiers_dir / Path(dossier["slug"]).with_suffix(".json").name
        for dossier in dossiers
    ]
    destinations.append(manifest_path)

    existing = [path for path in destinations if path.exists()]
    if existing and not args.force:
        relative = ", ".join(
            str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
            for path in existing
        )
        fail(
            "Dossiês de pesquisa já existem: "
            + relative
            + ". Use --force somente para substituir arquivos de build."
        )

    dossiers_dir.mkdir(parents=True, exist_ok=True)
    written_files: list[str] = []
    for dossier, destination in zip(dossiers, destinations[:-1]):
        destination.write_text(
            json.dumps(dossier, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written_files.append(
            str(destination.relative_to(ROOT)) if destination.is_relative_to(ROOT) else str(destination)
        )

    manifest = {
        "generated_at": datetime.now(tz).isoformat(),
        "target_date": target_date.isoformat(),
        "timezone": config["timezone"],
        "source_editorial": str(editorial_path),
        "research_dossier_count": len(dossiers),
        "external_research_performed": False,
        "ready_for_drafting_count": 0,
        "files": written_files,
        "dossiers": dossiers,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"OK: dossiês de pesquisa preparados para {target_date.isoformat()}.")
    print(f"Dossiês preparados: {len(dossiers)}")
    print("Pesquisa externa executada: não")
    print("Prontas para redação: 0")
    for dossier in dossiers:
        print(
            f'- PESQUISA PENDENTE | {dossier["title"]} | '
            f'{len(dossier["blocking_requirement_ids"])} requisitos bloqueadores'
        )
    print(
        f"Manifesto: {manifest_path.relative_to(ROOT) if manifest_path.is_relative_to(ROOT) else manifest_path}"
    )
    print("Nenhum HTML, noticias.json ou sitemap.xml foi alterado.")


if __name__ == "__main__":
    main()
