#!/usr/bin/env python3
"""Passo 34.7 — leitura/resegmentação contextual de evidências de pré-jogo.

Este arquivo mantém o leitor do Passo 34.6 como núcleo imutável e acrescenta uma
camada conservadora antes da extração factual:
- páginas já checadas podem ser resegmentadas especificamente para o novo requisito;
- o texto da página é relido no máximo uma vez por URL nesta etapa e continua interno;
- forma recente descarta fonte interna do próprio site e conteúdo claramente antigo;
- se um dos clubes ainda não tiver forma recente utilizável, uma busca complementar
  restrita a fonte oficial/competição e grande imprensa é tentada;
- nenhuma informação é promovida a fato aqui: os extratores e validadores continuam
  obrigatórios e publicação permanece bloqueada.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from scripts import buscar_fontes_serper as source_search
from scripts import ler_fontes_candidatas_base as base
from scripts.ler_fontes_candidatas_base import *  # noqa: F401,F403

_BASE_CHECK_ARTICLE = base.check_article
_SCRAPE_CACHE: dict[str, dict[str, Any] | Exception] = {}


def _target_year(article_date: Any) -> str:
    if not isinstance(article_date, str):
        return ""
    match = re.match(r"(20\d{2})-", article_date.strip())
    return match.group(1) if match else ""


def _scrape_once(url: str, *, config: dict[str, Any]) -> dict[str, Any]:
    cached = _SCRAPE_CACHE.get(url)
    if isinstance(cached, Exception):
        raise cached
    if isinstance(cached, dict):
        return cached
    try:
        payload = base.request_serper_scrape(url, config=config)
    except Exception as exc:
        _SCRAPE_CACHE[url] = exc
        raise
    _SCRAPE_CACHE[url] = payload
    return payload


def _resegment_source(
    source: dict[str, Any],
    requirement_id: str,
    *,
    checked_at: str,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    url = source.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        return None
    try:
        raw = _scrape_once(url, config=config)
        rebuilt = base.apply_scrape_to_candidate(
            deepcopy(source),
            raw,
            requirement_id=requirement_id,
            checked_at=checked_at,
            config=config,
        )
    except Exception:
        return None
    if rebuilt.get("eligible_for_factual_validation") is not True:
        return None
    rebuilt["passo34_7_target_resegmented"] = True
    rebuilt["passo34_7_target_requirement_id"] = requirement_id
    return rebuilt


def _source_year_is_acceptable(source: dict[str, Any], target_year: str) -> bool:
    if not target_year:
        return True
    published = str(source.get("published_hint", ""))
    years = set(re.findall(r"\b20\d{2}\b", published))
    if years and target_year not in years:
        return False
    return True


def _recent_supports_team(source: dict[str, Any], team: Any, *, target_year: str) -> bool:
    if not base.eligible_checked_source(source):
        return False
    if source.get("source_type") == "internal_site":
        return False
    if not _source_year_is_acceptable(source, target_year):
        return False

    blob = base.source_evidence_blob(source)
    folded = base.normalize_text(blob)
    if not base.mentions_team(blob, team):
        return False

    outcome = any(
        signal in folded
        for signal in (
            " win ", " wins ", " won ", " victory ", " victories ",
            " draw ", " draws ", " unbeaten ", " defeat ", " defeats ",
            " loss ", " losses ", " lost ", " vitoria ", " vitorias ",
            " venceu ", " empate ", " empates ", " derrota ", " derrotas ",
            " perdeu ", " points ", " pontos ",
        )
    )
    padded = f" {folded} "
    outcome = outcome or any(
        signal in padded
        for signal in (
            " win ", " wins ", " won ", " draw ", " draws ", " unbeaten ",
            " defeat ", " loss ", " lost ", " vitoria ", " venceu ",
            " empate ", " derrota ", " perdeu ", " points ", " pontos ",
        )
    )
    recency = any(
        signal in padded
        for signal in (
            " recent ", " latest ", " last ", " matchday ", " season ",
            " first three ", " first four ", " ultimos ", " ultimo ",
            " rodada ", " temporada ",
        )
    )
    if target_year and target_year in folded:
        recency = True
    return outcome and recency


def _classify_source_type(domain: str, *, official_domains: set[str], major_domains: set[str]) -> str | None:
    if any(source_search.domain_matches(domain, item) for item in official_domains):
        return "official"
    if any(source_search.domain_matches(domain, item) for item in major_domains):
        return "major_sports_media"
    return None


def _official_domains_for_team_and_competition(
    team: str,
    context: dict[str, Any],
    config: dict[str, Any],
) -> list[str]:
    discovery = config.get("research", {}).get("discovery", {})
    official = discovery.get("official_domains", {}) if isinstance(discovery, dict) else {}
    club_map = official.get("clubs", {}) if isinstance(official, dict) else {}
    competition_map = official.get("competitions", {}) if isinstance(official, dict) else {}

    domains: list[str] = []
    club = source_search.canonical_monitored_club(team, config)
    if isinstance(club, dict):
        raw = club_map.get(club.get("name"), []) if isinstance(club_map, dict) else []
        if isinstance(raw, list):
            domains.extend(str(item) for item in raw)
    slug = context.get("competition_slug")
    raw_comp = competition_map.get(slug, []) if isinstance(competition_map, dict) else []
    if isinstance(raw_comp, list):
        domains.extend(str(item) for item in raw_comp)

    result: list[str] = []
    seen: set[str] = set()
    for domain in domains:
        value = domain.strip().lower()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _candidate_current_enough(candidate: dict[str, Any], target_year: str) -> bool:
    if not target_year:
        return True
    text = source_search.candidate_haystack(candidate)
    published = base.normalize_text(str(candidate.get("published_hint", "")))
    years = set(re.findall(r"\b20\d{2}\b", f"{text} {published}"))
    if years and target_year not in years:
        return False
    if target_year in text or target_year in published:
        return True
    padded = f" {text} "
    return any(signal in padded for signal in (" latest ", " recent ", " matchday ", " last ", " season "))


def _candidate_score(candidate: dict[str, Any], team: str, target_year: str) -> int:
    title = base.normalize_text(str(candidate.get("title", "")))
    haystack = source_search.candidate_haystack(candidate)
    score = 0
    variants = source_search.team_variants(team, _ACTIVE_CONFIG)
    if any(variant in title for variant in variants):
        score += 6
    if target_year and target_year in haystack:
        score += 5
    for signal in ("latest", "recent", "matchday", "last", "results", "result", "form"):
        if signal in haystack:
            score += 1
    return score


_ACTIVE_CONFIG: dict[str, Any] = {}


def _search_recent_sources_for_team(
    team: str,
    *,
    context: dict[str, Any],
    article_date: str,
    checked_at: str,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    target_year = _target_year(article_date)
    competition = context.get("competition")
    if not isinstance(competition, str) or not competition.strip():
        return []

    official_domains = _official_domains_for_team_and_competition(team, context, config)
    discovery = config.get("research", {}).get("discovery", {})
    major_raw = discovery.get("major_sports_media_domains", []) if isinstance(discovery, dict) else []
    major_domains = [str(item) for item in major_raw if isinstance(item, str) and item.strip()]

    stages: list[tuple[str, list[str]]] = []
    if official_domains:
        stages.append(("official", official_domains))
    if major_domains:
        stages.append(("major_sports_media", major_domains))

    queries = [
        f'"{team}" "{competition}" {target_year} latest result last match'.strip(),
        f'"{team}" "{competition}" {target_year} recent form last matches'.strip(),
        f'"{team}" "{competition}" {target_year} resultados últimos jogos'.strip(),
        f'"{team}" "{competition}" {target_year} matchday result'.strip(),
    ]

    official_set = set(official_domains)
    major_set = set(major_domains)
    for stage_type, domains in stages:
        discovered: list[dict[str, Any]] = []
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
                if not source_search.candidate_matches_team(candidate, team, config):
                    continue
                if not source_search.recent_form_candidate_has_result_signal(candidate):
                    continue
                if not _candidate_current_enough(candidate, target_year):
                    continue
                seen.add(url)
                discovered.append(candidate)

        if not discovered:
            continue
        discovered.sort(key=lambda item: _candidate_score(item, team, target_year), reverse=True)
        checked: list[dict[str, Any]] = []
        for candidate in discovered[:4]:
            domain = str(candidate.get("domain", "")).strip().lower()
            source_type = _classify_source_type(
                domain,
                official_domains=official_set,
                major_domains=major_set,
            ) or stage_type
            row = deepcopy(candidate)
            row.update({
                "publisher": domain,
                "source_type": source_type,
                "dynamic_relevance_required": False,
                "passo34_7_recent_form_refresh": True,
                "passo34_7_team": team,
            })
            rebuilt = _resegment_source(
                row,
                "recent_form_both_teams",
                checked_at=checked_at,
                config=config,
            )
            if rebuilt is None:
                continue
            if _recent_supports_team(rebuilt, team, target_year=target_year):
                checked.append(rebuilt)
                break
        if checked:
            return checked
    return []


def _dedupe_sources(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def _promote_cross_requirement_sources(
    requirements: list[dict[str, Any]],
    *,
    context: dict[str, Any],
    article_date: str,
    checked_at: str,
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, int]:
    pool: list[dict[str, Any]] = []
    for requirement in requirements:
        for source in requirement.get("source_candidates", []):
            if base.eligible_checked_source(source) and source.get("source_type") != "internal_site":
                pool.append(source)
    pool = _dedupe_sources(pool)

    target_ids = {
        "stadium_and_location",
        "recent_form_both_teams",
        "competition_specific_head_to_head",
    }
    reused_count = 0
    refreshed_recent_count = 0
    target_year = _target_year(article_date)
    home = context.get("home")
    away = context.get("away")
    updated: list[dict[str, Any]] = []

    for requirement in requirements:
        result = deepcopy(requirement)
        req_id = result.get("id")
        original = [item for item in result.get("source_candidates", []) if isinstance(item, dict)]

        if req_id in target_ids:
            rebuilt_existing: list[dict[str, Any]] = []
            for source in original:
                if source.get("source_type") == "internal_site" and req_id != "competition_internal_link":
                    continue
                if source.get("passo34_6_cross_requirement_reuse") is True:
                    rebuilt = _resegment_source(
                        source,
                        str(req_id),
                        checked_at=checked_at,
                        config=config,
                    )
                    if rebuilt is not None:
                        source = rebuilt
                rebuilt_existing.append(source)
            original = rebuilt_existing

            existing_urls = {str(item.get("url")) for item in original if item.get("url")}
            extras: list[dict[str, Any]] = []
            for source in pool:
                url = source.get("url")
                if not isinstance(url, str) or url in existing_urls:
                    continue
                rebuilt = _resegment_source(
                    source,
                    str(req_id),
                    checked_at=checked_at,
                    config=config,
                )
                if rebuilt is None:
                    continue
                if req_id == "recent_form_both_teams":
                    supports = (
                        _recent_supports_team(rebuilt, home, target_year=target_year)
                        or _recent_supports_team(rebuilt, away, target_year=target_year)
                    )
                else:
                    supports = base.source_supports_cross_requirement_reuse(rebuilt, str(req_id), context)
                if not supports:
                    continue
                rebuilt["reused_from_requirement_id"] = source.get("reused_from_requirement_id") or "cross_requirement_pool"
                rebuilt["passo34_7_cross_requirement_reuse"] = True
                extras.append(rebuilt)
                existing_urls.add(url)
                reused_count += 1

            original = extras + original

        if req_id == "recent_form_both_teams":
            original = [
                item for item in original
                if item.get("source_type") != "internal_site"
                and (
                    _recent_supports_team(item, home, target_year=target_year)
                    or _recent_supports_team(item, away, target_year=target_year)
                )
            ]
            have_home = any(_recent_supports_team(item, home, target_year=target_year) for item in original)
            have_away = any(_recent_supports_team(item, away, target_year=target_year) for item in original)

            if isinstance(home, str) and not have_home:
                fresh = _search_recent_sources_for_team(
                    home,
                    context=context,
                    article_date=article_date,
                    checked_at=checked_at,
                    config=config,
                )
                original = fresh + original
                refreshed_recent_count += len(fresh)
            if isinstance(away, str) and not have_away:
                fresh = _search_recent_sources_for_team(
                    away,
                    context=context,
                    article_date=article_date,
                    checked_at=checked_at,
                    config=config,
                )
                original = fresh + original
                refreshed_recent_count += len(fresh)

            original = _dedupe_sources(original)
            home_rows = [item for item in original if _recent_supports_team(item, home, target_year=target_year)]
            away_rows = [item for item in original if _recent_supports_team(item, away, target_year=target_year)]
            ordered: list[dict[str, Any]] = []
            if home_rows:
                ordered.append(home_rows[0])
            if away_rows and (not ordered or away_rows[0].get("url") != ordered[0].get("url")):
                ordered.append(away_rows[0])
            ordered.extend(original)
            original = _dedupe_sources(ordered)

        result["source_candidates"] = original
        result["passo34_7_target_resegmentation"] = req_id in target_ids
        result["ready_for_fact_extraction"] = any(base.eligible_checked_source(item) for item in original)
        updated.append(result)

    return updated, reused_count, refreshed_recent_count


def check_article(
    article: dict[str, Any],
    *,
    config: dict[str, Any],
    checked_at: str,
) -> dict[str, Any]:
    global _ACTIVE_CONFIG
    _ACTIVE_CONFIG = config
    result = _BASE_CHECK_ARTICLE(article, config=config, checked_at=checked_at)
    requirements = result.get("requirements", [])
    if not isinstance(requirements, list):
        requirements = []
    context = result.get("match_context") if isinstance(result.get("match_context"), dict) else {}
    article_date = str(result.get("date", ""))

    refined, reused_count, refreshed_recent_count = _promote_cross_requirement_sources(
        [item for item in requirements if isinstance(item, dict)],
        context=context,
        article_date=article_date,
        checked_at=checked_at,
        config=config,
    )

    checked_sources: set[str] = set()
    eligible_sources: set[str] = set()
    blocking: list[str] = []
    for requirement in refined:
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

    result["requirements"] = refined
    result["page_checked_source_count"] = len(checked_sources)
    result["eligible_source_count"] = len(eligible_sources)
    result["page_check_blocking_requirement_ids"] = blocking
    result["passo34_7_resegmented_reuse_count"] = reused_count
    result["passo34_7_recent_form_refresh_count"] = refreshed_recent_count
    result["passo34_7_applied"] = True
    return result


# O núcleo chama seu próprio global check_article; substituímos apenas essa função.
base.check_article = check_article


def main() -> None:
    base.main()


if __name__ == "__main__":
    main()
