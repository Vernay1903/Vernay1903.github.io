#!/usr/bin/env python3
"""Passo 34.9 — seleção determinística por conteúdo para campos críticos.

Objetivo:
- não deixar a posição do Google/Serper decidir qual página vira evidência;
- estádio, forma recente e H2H só ocupam as primeiras vagas depois de o CONTEÚDO
  completo da página passar por validações específicas do requisito;
- páginas laterais, antigas ou de outro confronto são descartadas antes da extração;
- requisitos que a política permite marcar como indisponíveis recebem ao menos uma
  checagem exata do confronto, quando necessário.

Nenhum fato é criado aqui. Os extratores determinísticos/OpenAI aterrado e o validador
continuam obrigatórios. Redação, HTML e publicação permanecem bloqueados nesta etapa.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from scripts import buscar_fontes_serper as source_search
from scripts import ler_fontes_candidatas_base as base
from scripts import ler_fontes_candidatas_passo34_7 as step34_7
from scripts import ler_fontes_candidatas_passo34_8 as step34_8
from scripts.ler_fontes_candidatas_passo34_8 import *  # noqa: F401,F403

_PREVIOUS_CHECK_ARTICLE = step34_8.check_article

CRITICAL_REQUIREMENTS = {
    "stadium_and_location",
    "recent_form_both_teams",
    "competition_specific_head_to_head",
}
ALLOWED_GAP_REQUIREMENTS = {
    "transmission",
    "probable_lineups_and_coaches",
    "officiating",
}


def _target_year(article_date: str) -> str:
    match = re.match(r"(20\d{2})-", article_date or "")
    return match.group(1) if match else ""


def _season_signals(target_year: str) -> tuple[str, ...]:
    if not target_year:
        return ()
    yy = int(target_year[-2:])
    nxt = (yy + 1) % 100
    return (
        target_year,
        f"{target_year}/{nxt:02d}",
        f"{target_year}-{nxt:02d}",
        f"{target_year} {nxt:02d}",
        f"{yy:02d}/{nxt:02d}",
    )


def content_is_current_enough(
    content: str,
    source: dict[str, Any],
    *,
    target_year: str,
) -> bool:
    """Bloqueia páginas claramente antigas; aceita sinais explícitos da temporada-alvo."""
    if not target_year:
        return True
    published = str(source.get("published_hint", ""))
    published_years = set(re.findall(r"\b20\d{2}\b", published))
    if published_years:
        # Uma data editorial explícita tem precedência sobre título/URL.
        return target_year in published_years

    haystack = base.normalize_text(
        " ".join(
            [
                content,
                str(source.get("title", "")),
                str(source.get("url", "")),
            ]
        )
    )
    signals = tuple(base.normalize_text(item) for item in _season_signals(target_year))
    if any(signal and signal in haystack for signal in signals):
        return True

    # Se há ano explícito diferente em título/URL/conteúdo, a página é antiga.
    explicit_years = set(re.findall(r"\b20\d{2}\b", haystack))
    if explicit_years and target_year not in explicit_years:
        return False
    return False


def _match_in_text(text: str, context: dict[str, Any]) -> bool:
    home = context.get("home")
    away = context.get("away")
    return (
        isinstance(home, str)
        and isinstance(away, str)
        and base.mentions_team(text, home)
        and base.mentions_team(text, away)
    )


def _competition_in_text(text: str, context: dict[str, Any]) -> bool:
    competition = base.normalize_text(context.get("competition"))
    return bool(competition and competition in base.normalize_text(text))


def _clean_lines(content: str) -> list[str]:
    rows = [base.clean_markdown_line(line) for line in content.splitlines()]
    return [row for row in rows if len(row) >= 20]


def _contextual_segments(
    content: str,
    *,
    predicate,
    max_segments: int,
    max_chars: int,
) -> list[str]:
    lines = _clean_lines(content)
    selected: list[str] = []
    seen: set[str] = set()
    for idx, line in enumerate(lines):
        if not predicate(line):
            continue
        parts: list[str] = []
        if idx > 0:
            parts.append(lines[idx - 1])
        parts.append(line)
        if idx + 1 < len(lines):
            parts.append(lines[idx + 1])
        segment = " ".join(parts)
        segment = re.sub(r"\s+", " ", segment).strip()[:max_chars]
        key = base.normalize_text(segment)
        if len(key) < 12 or key in seen:
            continue
        seen.add(key)
        selected.append(segment)
        if len(selected) >= max_segments:
            break
    return selected


def stadium_content_support(
    content: str,
    source: dict[str, Any],
    context: dict[str, Any],
    *,
    target_year: str,
) -> bool:
    if not content or not content_is_current_enough(content, source, target_year=target_year):
        return False
    title = str(source.get("title", ""))
    joined = f"{title}\n{content}"
    if not _match_in_text(joined, context):
        return False

    home = context.get("home")
    away = context.get("away")
    title_has_match = _match_in_text(title, context)
    venue_names = (
        "allianz arena", "emirates stadium", "etihad stadium", "parc des princes",
        "san siro", "giuseppe meazza", "maracana", "allianz parque",
        "arena do gremio", "camp nou", "santiago bernabeu",
    )
    for line in _clean_lines(content):
        folded = base.normalize_text(line)
        padded = f" {folded} "
        has_venue = (
            any(item in folded for item in venue_names)
            or any(
                signal in padded
                for signal in (
                    " stadium ", " estadio ", " arena ", " venue ",
                    " stadion ", " spielort ", " spielstaette ",
                )
            )
        )
        if not has_venue:
            continue
        line_has_home = isinstance(home, str) and base.mentions_team(line, home)
        line_has_away = isinstance(away, str) and base.mentions_team(line, away)
        if line_has_home or line_has_away:
            if line_has_home and line_has_away:
                return True
            continue
        if title_has_match:
            return True
    return False


def h2h_content_support(
    content: str,
    source: dict[str, Any],
    context: dict[str, Any],
    *,
    target_year: str,
) -> bool:
    if not content or not content_is_current_enough(content, source, target_year=target_year):
        return False
    joined = f"{source.get('title', '')}\n{content}"
    if not _match_in_text(joined, context) or not _competition_in_text(joined, context):
        return False

    folded = base.normalize_text(joined)
    padded = f" {folded} "
    games = any(
        signal in padded
        for signal in (
            " games ", " matches ", " meetings ", " encounters ",
            " jogos ", " partidas ", " spiele ", " spielen ",
            " duelle ", " begegnungen ",
        )
    )
    wins = any(
        signal in padded
        for signal in (
            " wins ", " victories ", " vitorias ", " siege ",
        )
    )
    draws_or_unbeaten = any(
        signal in padded
        for signal in (
            " draws ", " empates ", " unentschieden ", " remis ",
            " unbeaten ", " never lost ", " without ever losing ",
            " invicto ", " nunca perdeu ", " ungeschlagen ",
            " noch nie verloren ", " ohne niederlage ",
        )
    )
    # Um placar isolado como 4-0 não basta. O conteúdo precisa ter linguagem agregada.
    numbers = re.findall(r"\b\d{1,3}\b", folded)
    return games and wins and draws_or_unbeaten and len(numbers) >= 2


def recent_form_content_support(
    content: str,
    source: dict[str, Any],
    team: str,
    context: dict[str, Any],
    *,
    target_year: str,
) -> bool:
    if not content or not content_is_current_enough(content, source, target_year=target_year):
        return False
    joined = f"{source.get('title', '')}\n{content}"
    if not base.mentions_team(joined, team):
        return False
    if not _competition_in_text(joined, context):
        return False

    folded = base.normalize_text(joined)
    padded = f" {folded} "
    result_signal = (
        bool(re.search(r"\b\d{1,2}\s*[-:]\s*\d{1,2}\b", joined))
        or any(
            signal in padded
            for signal in (
                " win ", " wins ", " won ", " victory ", " victories ",
                " draw ", " draws ", " unbeaten ", " defeat ", " loss ", " lost ",
                " vitoria ", " vitorias ", " venceu ", " empate ", " derrota ", " perdeu ",
                " sieg ", " siege ", " gewonnen ", " unentschieden ", " niederlage ",
            )
        )
    )
    recent_signal = any(
        signal in padded
        for signal in (
            " recent ", " latest ", " last ", " matchday ", " season ",
            " first three ", " first four ", " ultimos ", " ultimo ",
            " rodada ", " temporada ", " spieltag ", " zuletzt ",
        )
    )
    return result_signal and recent_signal


def _segments_for_stadium(content: str, *, max_segments: int, max_chars: int) -> list[str]:
    venue_terms = (
        "stadium", "estadio", "arena", "venue", "stadion", "spielort",
        "spielstaette", "allianz arena",
    )
    return _contextual_segments(
        content,
        predicate=lambda line: any(term in base.normalize_text(line) for term in venue_terms),
        max_segments=max_segments,
        max_chars=max_chars,
    )


def _segments_for_h2h(content: str, *, max_segments: int, max_chars: int) -> list[str]:
    terms = (
        "head to head", "meetings", "encounters", "games", "matches",
        "confront", "historico", "jogos", "partidas", "bilanz", "spiele",
        "spielen", "duelle", "begegnungen", "siege", "unentschieden",
        "remis", "ungeschlagen", "noch nie verloren",
    )
    return _contextual_segments(
        content,
        predicate=lambda line: (
            any(term in base.normalize_text(line) for term in terms)
            and bool(re.search(r"\d", line))
        ),
        max_segments=max_segments,
        max_chars=max_chars,
    )


def _segments_for_recent(
    content: str,
    *,
    team: str,
    source_title: str,
    max_segments: int,
    max_chars: int,
) -> list[str]:
    terms = (
        "recent", "latest", "last", "matchday", "season", "won", "wins", "draw",
        "defeat", "loss", "unbeaten", "vitoria", "venceu", "empate", "derrota",
        "spieltag", "zuletzt", "sieg", "gewonnen", "unentschieden", "niederlage",
    )
    return _contextual_segments(
        content,
        predicate=lambda line: (
            (base.mentions_team(line, team) or base.mentions_team(source_title, team))
            and (
                any(term in base.normalize_text(line) for term in terms)
                or bool(re.search(r"\b\d{1,2}\s*[-:]\s*\d{1,2}\b", line))
            )
        ),
        max_segments=max_segments,
        max_chars=max_chars,
    )


def _build_checked_source(
    source: dict[str, Any],
    raw: dict[str, Any],
    *,
    requirement_id: str,
    context: dict[str, Any],
    target_year: str,
    checked_at: str,
    config: dict[str, Any],
    recent_team: str | None = None,
) -> dict[str, Any] | None:
    normalized = base.normalize_scrape_response(raw)
    content = normalized["content"]
    if not content:
        return None

    reader = config["research"]["page_reader"]
    max_segments = int(reader.get("max_segments_per_source", 10))
    max_chars = int(reader.get("max_segment_chars", 700))

    if requirement_id == "stadium_and_location":
        supported = stadium_content_support(content, source, context, target_year=target_year)
        segments = _segments_for_stadium(content, max_segments=max_segments, max_chars=max_chars)
    elif requirement_id == "competition_specific_head_to_head":
        supported = h2h_content_support(content, source, context, target_year=target_year)
        segments = _segments_for_h2h(content, max_segments=max_segments, max_chars=max_chars)
    elif requirement_id == "recent_form_both_teams" and isinstance(recent_team, str):
        supported = recent_form_content_support(
            content,
            source,
            recent_team,
            context,
            target_year=target_year,
        )
        segments = _segments_for_recent(
            content,
            team=recent_team,
            source_title=str(source.get("title", "")),
            max_segments=max_segments,
            max_chars=max_chars,
        )
    else:
        supported = (
            _match_in_text(f"{source.get('title', '')}\n{content}", context)
            and content_is_current_enough(content, source, target_year=target_year)
        )
        segments = base.extract_evidence_segments(
            content,
            requirement_id,
            max_segments=max_segments,
            max_segment_chars=max_chars,
        )

    if not supported or not segments:
        return None

    source_title = re.sub(r"\s+", " ", str(source.get("title", ""))).strip()
    if requirement_id in CRITICAL_REQUIREMENTS and source_title:
        enriched: list[str] = []
        for segment in segments:
            if base.normalize_text(source_title) not in base.normalize_text(segment):
                segment = f"{source_title}. {segment}"
            enriched.append(segment[:max_chars].strip())
        segments = enriched

    rebuilt = deepcopy(source)
    metadata = normalized["metadata"]
    safe_metadata = {
        key: value
        for key, value in metadata.items()
        if key in {"title", "description", "og:title", "og:description", "language"}
        and isinstance(value, str)
    }
    rebuilt["checked_at"] = checked_at
    rebuilt["content_checked"] = True
    rebuilt["verification_status"] = "page_checked_content_selected_passo34_9"
    rebuilt["eligible_for_factual_validation"] = True
    rebuilt["dynamic_relevance_required"] = False
    rebuilt["passo34_9_content_selected"] = True
    if recent_team:
        rebuilt["passo34_9_recent_team"] = recent_team
    rebuilt["page_evidence"] = {
        "metadata": safe_metadata,
        "evidence_segments": segments,
        "segment_count": len(segments),
        "content_length": len(content),
        "content_sha256": base.hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "credits_used": normalized["credits"],
    }
    return rebuilt


def _scrape_candidate(
    source: dict[str, Any],
    *,
    requirement_id: str,
    context: dict[str, Any],
    target_year: str,
    checked_at: str,
    config: dict[str, Any],
    recent_team: str | None = None,
) -> dict[str, Any] | None:
    url = source.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        return None
    try:
        raw = step34_7._scrape_once(url, config=config)
    except Exception:
        return None
    return _build_checked_source(
        source,
        raw,
        requirement_id=requirement_id,
        context=context,
        target_year=target_year,
        checked_at=checked_at,
        config=config,
        recent_team=recent_team,
    )


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        url = row.get("url") if isinstance(row, dict) else None
        if not isinstance(url, str) or not url or url in seen:
            continue
        seen.add(url)
        result.append(row)
    return result


def _targeted_queries(
    requirement_id: str,
    context: dict[str, Any],
    article_date: str,
    *,
    team: str | None = None,
) -> list[str]:
    home = context.get("home")
    away = context.get("away")
    competition = context.get("competition")
    if not all(isinstance(item, str) and item.strip() for item in (home, away, competition)):
        return []
    year = _target_year(article_date)

    if requirement_id == "recent_form_both_teams" and isinstance(team, str):
        return [
            f'"{team}" "{competition}" {year} latest result matchday',
            f'"{team}" "{competition}" {year} recent form results',
            f'"{team}" "{competition}" {year} Spieltag Ergebnis zuletzt',
        ]
    if requirement_id == "stadium_and_location":
        return [
            f'"{home}" "{away}" "{competition}" {year} stadium venue',
            f'"{home}" "{away}" "{competition}" {year} Stadion Spielort',
            f'"{home}" "{away}" {year} arena',
        ]
    if requirement_id == "competition_specific_head_to_head":
        return [
            f'"{home}" "{away}" "{competition}" {year} head to head record wins draws',
            f'"{home}" "{away}" "{competition}" {year} Bilanz Spiele Siege Unentschieden',
            f'"{home}" "{away}" "{competition}" {year} Duelle Siege Remis',
        ]
    generic_terms = {
        "transmission": "broadcast TV stream transmissão onde assistir",
        "probable_lineups_and_coaches": "team news probable lineup predicted XI",
        "officiating": "referee officiating árbitro",
    }
    if requirement_id in generic_terms:
        return [
            f'"{home}" "{away}" "{competition}" {year} {generic_terms[requirement_id]}',
        ]
    return []


def _search_and_check(
    requirement_id: str,
    *,
    context: dict[str, Any],
    article_date: str,
    checked_at: str,
    config: dict[str, Any],
    recent_team: str | None = None,
) -> list[dict[str, Any]]:
    target_year = _target_year(article_date)
    queries = _targeted_queries(
        requirement_id,
        context,
        article_date,
        team=recent_team,
    )
    if not queries:
        return []

    for source_type, domains in step34_8._allowed_stage_domains(context, config):
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
                if not source_search.candidate_matches_team(candidate, str(context.get("home", "")), config):
                    if requirement_id != "recent_form_both_teams" or recent_team != context.get("away"):
                        continue
                if requirement_id in {"stadium_and_location", "competition_specific_head_to_head"}:
                    if not source_search.candidate_matches_team(candidate, str(context.get("away", "")), config):
                        continue
                if requirement_id == "recent_form_both_teams" and isinstance(recent_team, str):
                    if not source_search.candidate_matches_team(candidate, recent_team, config):
                        continue
                seen.add(url)
                candidates.append(candidate)

        candidates.sort(key=lambda row: int(row.get("position", 999) or 999))
        for candidate in candidates[:8]:
            row = deepcopy(candidate)
            row.update(
                {
                    "publisher": str(candidate.get("domain", "")),
                    "source_type": source_type,
                    "dynamic_relevance_required": False,
                    "passo34_9_targeted_search": True,
                    "passo34_9_requirement_id": requirement_id,
                }
            )
            checked = _scrape_candidate(
                row,
                requirement_id=requirement_id,
                context=context,
                target_year=target_year,
                checked_at=checked_at,
                config=config,
                recent_team=recent_team,
            )
            if checked is not None:
                return [checked]
    return []


def _select_existing(
    candidates: list[dict[str, Any]],
    *,
    requirement_id: str,
    context: dict[str, Any],
    article_date: str,
    checked_at: str,
    config: dict[str, Any],
    recent_team: str | None = None,
) -> list[dict[str, Any]]:
    target_year = _target_year(article_date)
    selected: list[dict[str, Any]] = []
    for source in candidates[:8]:
        if not isinstance(source, dict):
            continue
        checked = _scrape_candidate(
            source,
            requirement_id=requirement_id,
            context=context,
            target_year=target_year,
            checked_at=checked_at,
            config=config,
            recent_team=recent_team,
        )
        if checked is not None:
            selected.append(checked)
            break
    return selected


def _ensure_allowed_gap_check(
    requirement: dict[str, Any],
    *,
    context: dict[str, Any],
    article_date: str,
    checked_at: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    req = deepcopy(requirement)
    existing = [
        item for item in req.get("source_candidates", [])
        if isinstance(item, dict) and base.eligible_checked_source(item)
    ]
    if existing:
        return req

    fresh = _search_and_check(
        str(req.get("id")),
        context=context,
        article_date=article_date,
        checked_at=checked_at,
        config=config,
    )
    if fresh:
        req["source_candidates"] = fresh
        req["ready_for_fact_extraction"] = True
        req["passo34_9_allowed_gap_check"] = True
    return req


def _select_critical_requirement(
    requirement: dict[str, Any],
    *,
    context: dict[str, Any],
    article_date: str,
    checked_at: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    req = deepcopy(requirement)
    req_id = str(req.get("id"))
    original = [item for item in req.get("source_candidates", []) if isinstance(item, dict)]

    if req_id == "recent_form_both_teams":
        home = context.get("home")
        away = context.get("away")
        selected: list[dict[str, Any]] = []
        for team in (home, away):
            if not isinstance(team, str):
                continue
            rows = _select_existing(
                original,
                requirement_id=req_id,
                context=context,
                article_date=article_date,
                checked_at=checked_at,
                config=config,
                recent_team=team,
            )
            if not rows:
                rows = _search_and_check(
                    req_id,
                    context=context,
                    article_date=article_date,
                    checked_at=checked_at,
                    config=config,
                    recent_team=team,
                )
            selected.extend(rows)
        selected = _dedupe(selected)
        req["source_candidates"] = selected
        req["ready_for_fact_extraction"] = (
            isinstance(home, str)
            and isinstance(away, str)
            and any(item.get("passo34_9_recent_team") == home for item in selected)
            and any(item.get("passo34_9_recent_team") == away for item in selected)
        )
    else:
        selected = _select_existing(
            original,
            requirement_id=req_id,
            context=context,
            article_date=article_date,
            checked_at=checked_at,
            config=config,
        )
        if not selected:
            selected = _search_and_check(
                req_id,
                context=context,
                article_date=article_date,
                checked_at=checked_at,
                config=config,
            )
        req["source_candidates"] = _dedupe(selected)
        req["ready_for_fact_extraction"] = bool(req["source_candidates"])

    req["passo34_9_content_selection"] = True
    req["passo34_9_selected_source_count"] = len(req.get("source_candidates", []))
    req["passo34_9_rejected_previous_source_count"] = max(
        0,
        len(original) - len(req.get("source_candidates", [])),
    )
    return req


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

    updated: list[dict[str, Any]] = []
    selected_total = 0
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        req_id = requirement.get("id")
        if req_id in CRITICAL_REQUIREMENTS:
            req = _select_critical_requirement(
                requirement,
                context=context,
                article_date=article_date,
                checked_at=checked_at,
                config=config,
            )
        elif req_id in ALLOWED_GAP_REQUIREMENTS:
            req = _ensure_allowed_gap_check(
                requirement,
                context=context,
                article_date=article_date,
                checked_at=checked_at,
                config=config,
            )
        else:
            req = deepcopy(requirement)
        selected_total += int(req.get("passo34_9_selected_source_count", 0))
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
    result["passo34_9_selected_critical_source_count"] = selected_total
    result["passo34_9_applied"] = True

    slug = result.get("slug", "sem-slug")
    print(
        f"PASSO 34.9 — {slug}: fontes críticas selecionadas por conteúdo={selected_total}; "
        f"bloqueios após seleção={','.join(blocking) if blocking else 'nenhum'}"
    )
    return result


base.check_article = check_article


def main() -> None:
    base.main()


if __name__ == "__main__":
    main()
