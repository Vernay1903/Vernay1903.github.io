#!/usr/bin/env python3
"""Planeja a descoberta/coleta de fontes factuais sem executar buscas externas."""

from __future__ import annotations

import argparse
import json
import re
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

    research = config.get("research")
    if not isinstance(research, dict):
        fail('Configuração "research" ausente ou inválida.')
    discovery = research.get("discovery")
    if not isinstance(discovery, dict):
        fail('Configuração "research.discovery" ausente ou inválida.')
    if discovery.get("external_search_enabled") is not False:
        fail("O Passo 16 deve permanecer sem execução de busca externa real.")
    if discovery.get("mode") != "planned_queries":
        fail('research.discovery.mode deve permanecer "planned_queries".')
    if discovery.get("publication_unlock_allowed") is not False:
        fail("O planejamento de coleta não pode liberar publicação.")

    fallback = discovery.get("fallback_order")
    if fallback != ["official", "major_sports_media", "relevant_local_press"]:
        fail("A ordem de descoberta deve permanecer oficial > grande imprensa > imprensa local.")

    official = discovery.get("official_domains")
    if not isinstance(official, dict):
        fail('research.discovery.official_domains ausente ou inválido.')
    clubs = official.get("clubs")
    competitions = official.get("competitions")
    if not isinstance(clubs, dict) or not isinstance(competitions, dict):
        fail("Mapas de domínios oficiais inválidos.")

    monitored = config.get("monitored_clubs")
    if not isinstance(monitored, list) or len(monitored) != 10:
        fail("A configuração deve conter exatamente os 10 clubes monitorados.")
    missing_clubs = [
        club.get("name")
        for club in monitored
        if not isinstance(club, dict)
        or not isinstance(club.get("name"), str)
        or club.get("name") not in clubs
    ]
    if missing_clubs:
        fail("Faltam domínios oficiais para clubes monitorados: " + ", ".join(map(str, missing_clubs)))

    labels = config.get("editorial", {}).get("competition_labels", {})
    if not isinstance(labels, dict):
        fail("Rótulos de competição inválidos.")
    missing_competitions = [slug for slug in labels if slug not in competitions]
    if missing_competitions:
        fail("Faltam domínios oficiais para competições: " + ", ".join(missing_competitions))

    major_domains = discovery.get("major_sports_media_domains")
    if not isinstance(major_domains, list) or not major_domains:
        fail("É necessário configurar ao menos um domínio de grande imprensa esportiva.")
    if not all(isinstance(item, str) and item.strip() for item in major_domains):
        fail("Domínios de grande imprensa inválidos.")

    return config


def parse_target_date(raw: str | None, tz: ZoneInfo) -> date:
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            fail("--date deve usar o formato YYYY-MM-DD.")
    return datetime.now(tz).date() + timedelta(days=1)


def load_research_manifest(path: Path, target_date: date) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, dict):
        fail("O manifesto de pesquisa deve ser um objeto JSON.")
    if data.get("target_date") != target_date.isoformat():
        fail("A data do manifesto de pesquisa não coincide com a data-alvo.")
    dossiers = data.get("dossiers")
    if not isinstance(dossiers, list):
        fail('O manifesto de pesquisa deve conter um array "dossiers".')
    return [item for item in dossiers if isinstance(item, dict)]


def normalize_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        fail("Contexto da partida sem nome de equipe válido.")
    return value.strip()


def canonical_monitored_name(value: str, config: dict[str, Any]) -> str | None:
    folded = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    for club in config["monitored_clubs"]:
        candidates = [club["name"], club["slug"].replace("-", " "), *club.get("aliases", [])]
        for candidate in candidates:
            key = re.sub(r"[^a-z0-9]+", " ", str(candidate).casefold()).strip()
            if key == folded:
                return club["name"]
    return None


def unique_domains(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        domain = value.strip().lower()
        if domain and domain not in seen:
            seen.add(domain)
            result.append(domain)
    return result


def official_domains_for(dossier: dict[str, Any], config: dict[str, Any]) -> list[str]:
    context = dossier.get("match_context")
    if not isinstance(context, dict):
        fail("Dossiê sem match_context válido.")
    discovery = config["research"]["discovery"]
    club_domains = discovery["official_domains"]["clubs"]
    competition_domains = discovery["official_domains"]["competitions"]

    domains: list[str] = []
    for key in ("home", "away"):
        team = normalize_name(context.get(key))
        canonical = canonical_monitored_name(team, config)
        if canonical and isinstance(club_domains.get(canonical), list):
            domains.extend(club_domains[canonical])

    competition_slug = context.get("competition_slug")
    if isinstance(competition_slug, str) and isinstance(competition_domains.get(competition_slug), list):
        domains.extend(competition_domains[competition_slug])
    return unique_domains(domains)


def query_variants(requirement_id: str, context: dict[str, Any], article_date: str) -> list[str]:
    home = normalize_name(context.get("home"))
    away = normalize_name(context.get("away"))
    competition = context.get("competition")
    if not isinstance(competition, str) or not competition.strip():
        fail("Contexto da partida sem competição válida.")
    competition = competition.strip()
    base = f'"{home}" "{away}" "{competition}"'

    templates: dict[str, list[str]] = {
        "stadium_and_location": [f"{base} estádio local jogo {article_date}"],
        "transmission": [f"{base} transmissão onde assistir {article_date}"],
        "probable_lineups_and_coaches": [
            f"{base} provável escalação desfalques técnico {article_date}",
            f'"{home}" provável escalação desfalques técnico {article_date}',
            f'"{away}" provável escalação desfalques técnico {article_date}',
        ],
        "officiating": [f"{base} arbitragem árbitro {article_date}"],
        "recent_form_both_teams": [
            f'"{home}" últimos jogos momento recente {competition}',
            f'"{away}" últimos jogos momento recente {competition}',
        ],
        "competition_specific_head_to_head": [
            f"{base} histórico confrontos {competition} resultados"
        ],
        "competition_internal_link": [
            f'site:cortedosesportes.com.br "{competition}" história campeões'
        ],
        "stakes_and_qualification_scenarios_when_applicable": [
            f"{base} classificação cenário vaga pontos mata-mata {article_date}"
        ],
        "upcoming_fixtures_when_useful": [
            f'"{home}" próximos jogos calendário',
            f'"{away}" próximos jogos calendário',
        ],
    }
    if requirement_id not in templates:
        fail(f"Sem modelo de consulta para requisito: {requirement_id}")
    return templates[requirement_id]


def stages_for_requirement(
    requirement_id: str,
    *,
    dossier: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    discovery = config["research"]["discovery"]
    if requirement_id == "competition_internal_link":
        return [
            {
                "order": 1,
                "source_type": "internal_site",
                "domains": ["cortedosesportes.com.br"],
                "dynamic_relevance_required": False,
                "stop_if_resolved": True,
            }
        ]

    return [
        {
            "order": 1,
            "source_type": "official",
            "domains": official_domains_for(dossier, config),
            "dynamic_relevance_required": False,
            "stop_if_resolved": True,
        },
        {
            "order": 2,
            "source_type": "major_sports_media",
            "domains": unique_domains(discovery["major_sports_media_domains"]),
            "dynamic_relevance_required": False,
            "stop_if_resolved": True,
        },
        {
            "order": 3,
            "source_type": "relevant_local_press",
            "domains": [],
            "dynamic_relevance_required": True,
            "stop_if_resolved": True,
        },
    ]


def build_collection_plan(dossier: dict[str, Any], *, config: dict[str, Any]) -> dict[str, Any]:
    slug = dossier.get("slug")
    if not isinstance(slug, str) or not slug.endswith(".html"):
        fail("Dossiê sem slug HTML válido.")
    if dossier.get("ready_for_drafting") is not False or dossier.get("ready_for_html") is not False:
        fail("O planejamento de coleta deve começar com redação e HTML bloqueados.")

    context = dossier.get("match_context")
    if not isinstance(context, dict):
        fail("Dossiê sem match_context válido.")
    article_date = dossier.get("date")
    if not isinstance(article_date, str) or not article_date.strip():
        fail("Dossiê sem data editorial válida.")

    requirements = dossier.get("requirements")
    if not isinstance(requirements, list):
        fail("Dossiê sem requisitos de pesquisa válidos.")

    tasks: list[dict[str, Any]] = []
    for requirement in requirements:
        if not isinstance(requirement, dict):
            fail("Requisito de pesquisa inválido.")
        requirement_id = requirement.get("id")
        if not isinstance(requirement_id, str) or not requirement_id:
            fail("Requisito sem id válido.")
        if requirement.get("status") != "pending":
            continue
        tasks.append(
            {
                "requirement_id": requirement_id,
                "required_for_drafting": bool(requirement.get("required_for_drafting")),
                "conditional": bool(requirement.get("conditional")),
                "queries": query_variants(requirement_id, context, article_date),
                "stages": stages_for_requirement(
                    requirement_id,
                    dossier=dossier,
                    config=config,
                ),
                "execution_status": "planned_not_executed",
            }
        )

    discovery = config["research"]["discovery"]
    return {
        "title": dossier.get("title"),
        "slug": slug,
        "date": article_date,
        "fixture_id": dossier.get("fixture_id"),
        "match_context": context,
        "collection_status": "planned_waiting_search_provider",
        "external_search_enabled": False,
        "external_search_performed": False,
        "search_provider": discovery.get("search_provider"),
        "source_priority": list(discovery["fallback_order"]),
        "tasks": tasks,
        "ready_for_drafting": False,
        "ready_for_html": False,
        "publication_unlocked": False,
    }


def build_collection_plans(dossiers: list[dict[str, Any]], *, config: dict[str, Any]) -> list[dict[str, Any]]:
    plans = [build_collection_plan(item, config=config) for item in dossiers]
    seen: set[str] = set()
    for plan in plans:
        slug = plan["slug"]
        if slug in seen:
            fail(f"Slug duplicado no planejamento de coleta: {slug}")
        seen.add(slug)
    return plans


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Planeja consultas e prioridade de fontes sem executar pesquisa externa."
    )
    parser.add_argument(
        "--date",
        help="Data-alvo YYYY-MM-DD. Se omitida, usa amanhã em America/Sao_Paulo.",
    )
    parser.add_argument(
        "--research",
        type=Path,
        help="Manifesto pesquisa-AAAA-MM-DD.json. Se omitido, usa build/pre-jogo/.",
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
        help="Permite substituir somente arquivos de planejamento dentro de build/.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    tz = ZoneInfo(config["timezone"])
    target_date = parse_target_date(args.date, tz)

    research_path = args.research
    if research_path is None:
        research_path = DEFAULT_OUTPUT_DIR / f"pesquisa-{target_date.isoformat()}.json"

    dossiers = load_research_manifest(research_path, target_date)
    plans = build_collection_plans(dossiers, config=config)

    output_dir = args.output_dir.resolve()
    plans_dir = output_dir / f"coleta-fontes-{target_date.isoformat()}"
    manifest_path = output_dir / f"coleta-fontes-{target_date.isoformat()}.json"
    destinations = [plans_dir / Path(item["slug"]).with_suffix(".json").name for item in plans]
    destinations.append(manifest_path)

    existing = [path for path in destinations if path.exists()]
    if existing and not args.force:
        relative = ", ".join(
            str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
            for path in existing
        )
        fail("Planejamento de coleta já existe: " + relative + ". Use --force apenas em build/.")

    plans_dir.mkdir(parents=True, exist_ok=True)
    written_files: list[str] = []
    for plan, destination in zip(plans, destinations[:-1]):
        destination.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written_files.append(
            str(destination.relative_to(ROOT)) if destination.is_relative_to(ROOT) else str(destination)
        )

    manifest = {
        "generated_at": datetime.now(tz).isoformat(),
        "target_date": target_date.isoformat(),
        "timezone": config["timezone"],
        "source_research": str(research_path),
        "collection_plan_count": len(plans),
        "external_search_enabled": False,
        "external_search_performed": False,
        "search_provider": config["research"]["discovery"].get("search_provider"),
        "files": written_files,
        "plans": plans,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"OK: planejamento de coleta preparado para {target_date.isoformat()}.")
    print(f"Planos preparados: {len(plans)}")
    print("Busca externa executada: não")
    print("Redação, HTML e publicação permanecem bloqueados.")
    for plan in plans:
        print(f'- COLETA PLANEJADA | {plan["title"]} | {len(plan["tasks"])} tarefas')
    print(
        f"Manifesto: {manifest_path.relative_to(ROOT) if manifest_path.is_relative_to(ROOT) else manifest_path}"
    )


if __name__ == "__main__":
    main()
