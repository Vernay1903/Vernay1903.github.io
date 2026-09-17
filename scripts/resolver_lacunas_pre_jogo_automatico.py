#!/usr/bin/env python3
"""Resolve somente lacunas que a política editorial permite não bloquear.

Não cria fatos. Não transforma ausência em dado. Apenas converte requisitos que a
configuração permite como indisponíveis após checagem e marca cenários de
classificação como não aplicáveis nas ligas de pontos corridos.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "pre-jogo.json"
BUILD = ROOT / "build" / "pre-jogo"

LEAGUE_SLUGS = {
    "premier-league",
    "la-liga",
    "ligue-1",
    "bundesliga",
    "serie-a",
    "brasileirao",
}


def fail(message: str) -> NoReturn:
    print(f"ERRO: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"Arquivo não encontrado: {path}")
    except json.JSONDecodeError as exc:
        fail(f"JSON inválido: {path}: {exc}")


def checked_sources(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in requirement.get("source_candidates", []):
        if not isinstance(source, dict) or source.get("content_checked") is not True:
            continue
        url = source.get("url")
        if not isinstance(url, str) or not url.startswith("https://") or url in seen:
            continue
        seen.add(url)
        result.append({
            "publisher": source.get("publisher"),
            "url": url,
            "source_type": source.get("source_type"),
            "checked_at": source.get("checked_at"),
        })
    return result


def resolve_requirement(requirement: dict[str, Any], *, competition_slug: str, config: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(requirement)
    if result.get("status") == "verified":
        return result

    req_id = result.get("id")
    policy = config.get("research", {}).get("requirement_policy", {}).get(req_id, {})
    sources = checked_sources(result)

    if req_id == "stakes_and_qualification_scenarios_when_applicable" and competition_slug in LEAGUE_SLUGS:
        result["status"] = "not_applicable"
        result["facts"] = []
        result["sources"] = sources
        result["notes"] = "Competição de liga: cenário de classificação mata-mata não se aplica a este pré-jogo."
        result["fact_extraction_status"] = "automatic_not_applicable_for_league"
        result["validator_accepted"] = True
        result["conflict_detected"] = False
        return result

    if policy.get("allow_unavailable_after_check") is True and sources:
        result["status"] = "unavailable_after_check"
        result["facts"] = []
        result["sources"] = sources
        result["notes"] = "Informação não foi confirmada de forma completa nas páginas efetivamente checadas; nenhuma lacuna foi inventada."
        result["fact_extraction_status"] = "automatic_unavailable_after_checked_sources"
        result["validator_accepted"] = True
        result["conflict_detected"] = False
        return result

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve lacunas permitidas sem criar fatos.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--facts", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_json(CONFIG)
    data = load_json(args.facts)
    if not isinstance(config, dict) or not isinstance(data, dict):
        fail("Configuração ou manifesto inválido.")
    if data.get("target_date") != args.date:
        fail("Manifesto de fatos não corresponde à data-alvo.")

    articles = []
    changed = 0
    for article in data.get("articles", []):
        if not isinstance(article, dict):
            continue
        item = deepcopy(article)
        context = item.get("match_context") if isinstance(item.get("match_context"), dict) else {}
        competition_slug = str(context.get("competition_slug", ""))
        resolved_requirements = []
        for requirement in item.get("requirements", []):
            if not isinstance(requirement, dict):
                continue
            before = requirement.get("status")
            resolved = resolve_requirement(requirement, competition_slug=competition_slug, config=config)
            if resolved.get("status") != before:
                changed += 1
            resolved_requirements.append(resolved)
        item["requirements"] = resolved_requirements
        item["automatic_gap_resolution_applied"] = True
        articles.append(item)

    output = args.output or (BUILD / f"fatos-automaticos-{args.date}.json")
    resolved_output = output.resolve()
    try:
        resolved_output.relative_to(BUILD.resolve())
    except ValueError:
        fail("Saída deve ficar dentro de build/pre-jogo/.")
    if output.exists() and not args.force:
        fail(f"Saída já existe: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    result = deepcopy(data)
    result["generated_at_gap_resolution"] = datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat()
    result["source_facts_manifest"] = str(args.facts)
    result["automatic_gap_resolution_count"] = changed
    result["articles"] = articles
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"OK: lacunas permitidas resolvidas sem inventar fatos: {changed} requisito(s).")
    print(f"Saída: {output}")


if __name__ == "__main__":
    main()
