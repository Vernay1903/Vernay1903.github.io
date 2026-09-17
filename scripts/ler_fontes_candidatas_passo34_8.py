#!/usr/bin/env python3
"""Passo 34.8 — coleta dirigida para estádio e retrospecto agregado.

Complementa o Passo 34.7 somente quando os dois requisitos críticos que restaram
não têm evidência textual suficiente:
- estádio/local: exige nome literal de estádio/arena em página que mencione os dois clubes;
- H2H da competição: exige página que mencione os dois clubes, a competição e sinais
  agregados de jogos/vitórias/empates ou invencibilidade.

A busca continua limitada a fontes oficiais e grande imprensa já permitidas pela
configuração. Nenhum fato é criado nesta etapa; as páginas ainda passam pelos
extratores determinísticos/OpenAI aterrado e pelo validador antes de qualquer redação.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from scripts import buscar_fontes_serper as source_search
from scripts import ler_fontes_candidatas_base as base
from scripts import ler_fontes_candidatas_passo34_7 as previous
from scripts.ler_fontes_candidatas_passo34_7 import *  # noqa: F401,F403

_PREVIOUS_CHECK_ARTICLE = previous.check_article


def _extend_keywords(requirement_id: str, extras: tuple[str, ...]) -> None:
    current = tuple(base.REQUIREMENT_KEYWORDS.get(requirement_id, ()))
    base.REQUIREMENT_KEYWORDS[requirement_id] = tuple(dict.fromkeys((*current, *extras)))


_extend_keywords(
    "stadium_and_location",
    (
        "stadion",
        "spielort",
        "spielstätte",
        "spielstaette",
        "heimspiel",
        "allianz arena",
    ),
)
_extend_keywords(
    "competition_specific_head_to_head",
    (
        "bilanz",
        "duell",
        "duelle",
        "spiele",
        "spielen",
        "siege",
        "unentschieden",
        "remis",
        "begegnungen",
        "ungeschlagen",
        "noch nie verloren",
    ),
)


def _source_blob(source: dict[str, Any]) -> str:
    return base.source_evidence_blob(source)


def _has_match_context(blob: str, context: dict[str, Any]) -> bool:
    home = context.get("home")
    away = context.get("away")
    return (
        isinstance(home, str)
        and isinstance(away, str)
        and base.mentions_team(blob, home)
        and base.mentions_team(blob, away)
    )


def stadium_source_has_explicit_venue(source: dict[str, Any], context: dict[str, Any]) -> bool:
    """Aceita apenas evidência literal de estádio/arena ligada ao confronto."""
    if not base.eligible_checked_source(source):
        return False
    blob = _source_blob(source)
    if not _has_match_context(blob, context):
        return False
    folded = base.normalize_text(blob)
    venue_signals = (
        " stadium ",
        " estadio ",
        " arena ",
        " venue ",
        " stadion ",
        " spielort ",
        " spielstaette ",
        " allianz arena ",
    )
    padded = f" {folded} "
    if not any(signal in padded for signal in venue_signals):
        return False
    # Exige pelo menos um nome com aparência de local, não apenas a palavra genérica.
    known = (
        "allianz arena",
        "emirates stadium",
        "etihad stadium",
        "parc des princes",
        "san siro",
        "giuseppe meazza",
        "maracana",
        "allianz parque",
        "arena do gremio",
        "camp nou",
        "santiago bernabeu",
    )
    if any(item in folded for item in known):
        return True
    return bool(
        re.search(
            r"\b(?:stadium|arena|stadion)\b.{0,80}\b[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’.-]{2,}",
            blob,
            flags=re.IGNORECASE,
        )
        or re.search(
            r"\b[A-ZÀ-Ý][A-Za-zÀ-ÿ'’.-]+(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ'’.-]+){0,4}\s+(?:Stadium|Arena)\b",
            blob,
        )
    )


def h2h_source_has_aggregate_signals(source: dict[str, Any], context: dict[str, Any]) -> bool:
    """Exige sinais de retrospecto agregado, não apenas um jogo anterior isolado."""
    if not base.eligible_checked_source(source):
        return False
    blob = _source_blob(source)
    if not _has_match_context(blob, context):
        return False
    folded = base.normalize_text(blob)
    competition = base.normalize_text(context.get("competition"))
    if competition and competition not in folded:
        return False

    padded = f" {folded} "
    games_signal = any(
        signal in padded
        for signal in (
            " games ", " matches ", " meetings ", " encounters ",
            " jogos ", " partidas ", " spiele ", " spielen ", " duelle ", " begegnungen ",
        )
    )
    wins_signal = any(
        signal in padded
        for signal in (
            " wins ", " victories ", " vitorias ", " venceu ", " siege ",
        )
    )
    draws_signal = any(
        signal in padded
        for signal in (
            " draws ", " empates ", " unentschieden ", " remis ",
        )
    )
    unbeaten_signal = any(
        signal in padded
        for signal in (
            " unbeaten ", " never lost ", " without ever losing ",
            " invicto ", " nunca perdeu ", " ungeschlagen ", " noch nie verloren ",
        )
    )
    number_count = len(re.findall(r"\b\d{1,3}\b", folded))
    return games_signal and wins_signal and (draws_signal or unbeaten_signal) and number_count >= 1


def _allowed_stage_domains(
    context: dict[str, Any],
    config: dict[str, Any],
) -> list[tuple[str, list[str]]]:
    discovery = config.get("research", {}).get("discovery", {})
    official = discovery.get("official_domains", {}) if isinstance(discovery, dict) else {}
    clubs = official.get("clubs", {}) if isinstance(official, dict) else {}
    competitions = official.get("competitions", {}) if isinstance(official, dict) else {}

    official_domains: list[str] = []
    for side in ("home", "away"):
        team = context.get(side)
        if not isinstance(team, str):
            continue
        club = source_search.canonical_monitored_club(team, config)
        if isinstance(club, dict) and isinstance(clubs, dict):
            rows = clubs.get(club.get("name"), [])
            if isinstance(rows, list):
                official_domains.extend(str(item) for item in rows if isinstance(item, str))

    slug = context.get("competition_slug")
    if isinstance(competitions, dict):
        rows = competitions.get(slug, [])
        if isinstance(rows, list):
            official_domains.extend(str(item) for item in rows if isinstance(item, str))

    major_raw = discovery.get("major_sports_media_domains", []) if isinstance(discovery, dict) else []
    major_domains = [str(item) for item in major_raw if isinstance(item, str) and item.strip()]

    def unique(rows: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for row in rows:
            value = row.strip().lower()
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return result

    stages: list[tuple[str, list[str]]] = []
    official_domains = unique(official_domains)
    major_domains = unique(major_domains)
    if official_domains:
        stages.append(("official", official_domains))
    if major_domains:
        stages.append(("major_sports_media", major_domains))
    return stages


def _queries_for_requirement(
    requirement_id: str,
    context: dict[str, Any],
    article_date: str,
) -> list[str]:
    home = context.get("home")
    away = context.get("away")
    competition = context.get("competition")
    if not all(isinstance(item, str) and item.strip() for item in (home, away, competition)):
        return []
    year_match = re.match(r"(20\d{2})-", article_date or "")
    year = year_match.group(1) if year_match else ""

    if requirement_id == "stadium_and_location":
        return [
            f'"{home}" "{away}" "{competition}" {year} stadium venue',
            f'"{home}" "{away}" "{competition}" {year} Stadion Spielort',
            f'"{home}" "{away}" {year} arena venue match',
        ]
    if requirement_id == "competition_specific_head_to_head":
        return [
            f'"{home}" "{away}" "{competition}" head to head record wins draws',
            f'"{home}" "{away}" "{competition}" meetings wins draws',
            f'"{home}" "{away}" "{competition}" Bilanz Spiele Siege Unentschieden',
            f'"{home}" "{away}" "{competition}" Duelle Siege Remis',
        ]
    return []


def _candidate_mentions_match(candidate: dict[str, Any], context: dict[str, Any], config: dict[str, Any]) -> bool:
    home = context.get("home")
    away = context.get("away")
    return (
        isinstance(home, str)
        and isinstance(away, str)
        and source_search.candidate_matches_team(candidate, home, config)
        and source_search.candidate_matches_team(candidate, away, config)
    )


def _search_targeted_sources(
    requirement_id: str,
    *,
    context: dict[str, Any],
    article_date: str,
    checked_at: str,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    queries = _queries_for_requirement(requirement_id, context, article_date)
    if not queries:
        return []

    for source_type, domains in _allowed_stage_domains(context, config):
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for query in queries:
            try:
                _, raw = source_search.request_serper(query=query, domains=domains, config=config)
            except Exception:
                continue
            for candidate in source_search.normalize_serper_response(raw, allowed_domains=domains):
                url = str(candidate.get("url", ""))
                if not url or url in seen:
                    continue
                if not _candidate_mentions_match(candidate, context, config):
                    continue
                seen.add(url)
                candidates.append(candidate)

        # Páginas mais específicas primeiro: ambos clubes no título/URL e competição no resultado.
        candidates.sort(
            key=lambda row: (
                1 if source_search.competition_matches_candidate(row, context, config) else 0,
                1 if (
                    source_search.candidate_matches_team_strict(row, str(context.get("home", "")), config)
                    and source_search.candidate_matches_team_strict(row, str(context.get("away", "")), config)
                ) else 0,
                -int(row.get("position", 999) if isinstance(row.get("position"), int) else 999),
            ),
            reverse=True,
        )

        accepted: list[dict[str, Any]] = []
        for candidate in candidates[:6]:
            row = deepcopy(candidate)
            row.update(
                {
                    "publisher": str(candidate.get("domain", "")),
                    "source_type": source_type,
                    "dynamic_relevance_required": False,
                    "passo34_8_targeted_refresh": True,
                    "passo34_8_requirement_id": requirement_id,
                }
            )
            rebuilt = previous._resegment_source(
                row,
                requirement_id,
                checked_at=checked_at,
                config=config,
            )
            if rebuilt is None:
                continue
            if requirement_id == "stadium_and_location":
                supported = stadium_source_has_explicit_venue(rebuilt, context)
            else:
                supported = h2h_source_has_aggregate_signals(rebuilt, context)
            if not supported:
                continue
            accepted.append(rebuilt)
            if source_type == "official":
                break
            if len(accepted) >= 2:
                break
        if accepted:
            return accepted
    return []


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = row.get("url")
        if not isinstance(url, str) or not url or url in seen:
            continue
        seen.add(url)
        result.append(row)
    return result


def _requirement_has_support(
    requirement: dict[str, Any],
    requirement_id: str,
    context: dict[str, Any],
) -> bool:
    predicate = (
        stadium_source_has_explicit_venue
        if requirement_id == "stadium_and_location"
        else h2h_source_has_aggregate_signals
    )
    return any(
        predicate(source, context)
        for source in requirement.get("source_candidates", [])
        if isinstance(source, dict)
    )


def check_article(
    article: dict[str, Any],
    *,
    config: dict[str, Any],
    checked_at: str,
) -> dict[str, Any]:
    result = _PREVIOUS_CHECK_ARTICLE(article, config=config, checked_at=checked_at)
    requirements = result.get("requirements", [])
    if not isinstance(requirements, list):
        requirements = []
    context = result.get("match_context") if isinstance(result.get("match_context"), dict) else {}
    article_date = str(result.get("date", ""))

    refreshed_total = 0
    refreshed_by_requirement: dict[str, int] = {}
    updated: list[dict[str, Any]] = []

    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        req = deepcopy(requirement)
        req_id = req.get("id")
        if req_id in {"stadium_and_location", "competition_specific_head_to_head"}:
            existing = [item for item in req.get("source_candidates", []) if isinstance(item, dict)]
            if not _requirement_has_support(req, str(req_id), context):
                fresh = _search_targeted_sources(
                    str(req_id),
                    context=context,
                    article_date=article_date,
                    checked_at=checked_at,
                    config=config,
                )
                if fresh:
                    existing = _dedupe(fresh + existing)
                    refreshed_total += len(fresh)
                    refreshed_by_requirement[str(req_id)] = len(fresh)
            req["source_candidates"] = existing
            req["ready_for_fact_extraction"] = any(
                base.eligible_checked_source(item) for item in existing
            )
            req["passo34_8_targeted_refresh"] = refreshed_by_requirement.get(str(req_id), 0) > 0
            req["passo34_8_supported_after_refresh"] = _requirement_has_support(req, str(req_id), context)
        updated.append(req)

    checked_sources: set[str] = set()
    eligible_sources: set[str] = set()
    blocking: list[str] = []
    for requirement in updated:
        req_id = requirement.get("id")
        for source in requirement.get("source_candidates", []):
            if not isinstance(source, dict):
                continue
            url = source.get("url")
            if isinstance(url, str) and source.get("content_checked") is True:
                checked_sources.add(url)
            if isinstance(url, str) and source.get("eligible_for_factual_validation") is True:
                eligible_sources.add(url)
        if requirement.get("required_for_drafting") is True and not requirement.get("ready_for_fact_extraction"):
            if isinstance(req_id, str):
                blocking.append(req_id)

    result["requirements"] = updated
    result["page_checked_source_count"] = len(checked_sources)
    result["eligible_source_count"] = len(eligible_sources)
    result["page_check_blocking_requirement_ids"] = blocking
    result["passo34_8_targeted_refresh_count"] = refreshed_total
    result["passo34_8_targeted_refresh_by_requirement"] = refreshed_by_requirement
    result["passo34_8_applied"] = True
    return result


base.check_article = check_article


def main() -> None:
    base.main()


if __name__ == "__main__":
    main()
