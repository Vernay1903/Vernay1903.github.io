#!/usr/bin/env python3
"""Passo 34.10 — fechamento dirigido de estádio e arbitragem.

Complementa o Passo 34.9:
- revalida estádio com contexto do jogo ATUAL, rejeitando menções históricas;
- procura arbitragem em páginas atuais do confronto e, se o árbitro ainda não estiver
  anunciado, preserva uma checagem atual válida para a política de
  unavailable_after_check;
- usa fontes oficiais, grande imprensa e, somente por último, domínios que o próprio
  pipeline já classificou como imprensa local relevante para esta partida.

Nenhum fato é criado aqui. Extração, grounding, validação, redação e publicação
continuam em etapas posteriores e com as mesmas travas.
"""

from __future__ import annotations

import os
import re
from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

from scripts import buscar_fontes_serper as source_search
from scripts import ler_fontes_candidatas_base as base
from scripts import ler_fontes_candidatas_passo34_7 as _step34_7
from scripts import ler_fontes_candidatas_passo34_8 as _step34_8
from scripts import ler_fontes_candidatas_passo34_9 as _step34_9
from scripts.ler_fontes_candidatas_passo34_9 import *  # noqa: F401,F403

_PREVIOUS_CHECK_ARTICLE = _step34_9.check_article


def _article_local_press_domains(article: dict[str, Any]) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()
    for requirement in article.get("requirements", []):
        if not isinstance(requirement, dict):
            continue
        for source in requirement.get("source_candidates", []):
            if not isinstance(source, dict) or source.get("source_type") != "relevant_local_press":
                continue
            domain = source.get("domain")
            if not isinstance(domain, str) or not domain.strip():
                url = source.get("url")
                if isinstance(url, str):
                    domain = (urlparse(url).hostname or "").lower()
            if not isinstance(domain, str):
                continue
            domain = domain.lower().removeprefix("www.").strip()
            if not domain or domain in seen or domain == "cortedosesportes.com.br":
                continue
            seen.add(domain)
            domains.append(domain)
    return domains


def _current_match_blob(source: dict[str, Any]) -> str:
    return base.source_evidence_blob(source)


def _contains_current_venue_statement(text: str) -> bool:
    folded = base.normalize_text(text)
    historical = (
        "previous meeting", "last meeting", "most recent meeting", "previous game",
        "last time", "ultimo confronto", "último confronto", "encontro mais recente",
        "partida anterior", "jogo anterior", "quando venceu", "when they won",
    )
    if any(base.normalize_text(item) in folded for item in historical):
        return False
    current = (
        "venue", "stadium", "arena", "spielort", "stadion", "estádio", "estadio", "local",
        "will be played", "takes place", "will take place", "held at",
        "será disputado", "sera disputado", "será disputada", "sera disputada",
        "será jogado", "sera jogado", "recebe", "receberá", "recebera",
        "empfangt", "empfängt", "findet", "statt",
    )
    return any(base.normalize_text(item) in folded for item in current)


def stadium_source_is_current(
    source: dict[str, Any],
    context: dict[str, Any],
    *,
    target_year: str,
) -> bool:
    if not base.eligible_checked_source(source):
        return False
    blob = _current_match_blob(source)
    if not _step34_9._match_in_text(blob, context):
        return False
    if not _step34_9._competition_in_text(blob, context):
        return False
    if not _step34_9.content_is_current_enough(blob, source, target_year=target_year):
        return False

    page = source.get("page_evidence") if isinstance(source.get("page_evidence"), dict) else {}
    segments = page.get("evidence_segments", []) if isinstance(page, dict) else []
    for segment in segments:
        if not isinstance(segment, str):
            continue
        folded = base.normalize_text(segment)
        has_venue = any(
            item in folded
            for item in (
                "allianz arena", "emirates stadium", "etihad stadium", "parc des princes",
                "san siro", "giuseppe meazza", "maracana", "allianz parque",
                "arena do gremio", "camp nou", "santiago bernabeu",
            )
        ) or any(
            signal in f" {folded} "
            for signal in (" stadium ", " estadio ", " arena ", " venue ", " stadion ", " spielort ")
        )
        if has_venue and _contains_current_venue_statement(segment):
            return True
    return False


def officiating_source_is_current(
    source: dict[str, Any],
    context: dict[str, Any],
    *,
    target_year: str,
) -> bool:
    if not base.eligible_checked_source(source):
        return False
    blob = _current_match_blob(source)
    return (
        _step34_9._match_in_text(blob, context)
        and _step34_9._competition_in_text(blob, context)
        and _step34_9.content_is_current_enough(blob, source, target_year=target_year)
    )


def _officiating_segments(content: str, *, max_segments: int, max_chars: int) -> list[str]:
    terms = (
        "arbitro", "árbitro", "referee", "match referee", "officiating",
        "schiedsrichter", "var", "video assistant",
    )
    selected = _step34_9._contextual_segments(
        content,
        predicate=lambda line: any(
            base.normalize_text(term) in base.normalize_text(line) for term in terms
        ),
        max_segments=max_segments,
        max_chars=max_chars,
    )
    if selected:
        return selected
    return base.extract_evidence_segments(
        content,
        "officiating",
        max_segments=max_segments,
        max_segment_chars=max_chars,
    )


def _checked_from_raw(
    source: dict[str, Any],
    raw: dict[str, Any],
    *,
    requirement_id: str,
    context: dict[str, Any],
    target_year: str,
    checked_at: str,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    normalized = base.normalize_scrape_response(raw)
    content = normalized["content"]
    if not content:
        return None
    title = str(source.get("title", ""))
    joined = f"{title}\n{content}"
    if not _step34_9._match_in_text(joined, context):
        return None
    if not _step34_9._competition_in_text(joined, context):
        return None
    if not _step34_9.content_is_current_enough(content, source, target_year=target_year):
        return None

    reader = config["research"]["page_reader"]
    max_segments = int(reader.get("max_segments_per_source", 10))
    max_chars = int(reader.get("max_segment_chars", 700))

    if requirement_id == "stadium_and_location":
        temp = deepcopy(source)
        temp["checked_at"] = checked_at
        temp["content_checked"] = True
        temp["eligible_for_factual_validation"] = True
        temp["page_evidence"] = {
            "metadata": normalized["metadata"],
            "evidence_segments": _step34_9._segments_for_stadium(
                content,
                max_segments=max_segments,
                max_chars=max_chars,
            ),
        }
        if not stadium_source_is_current(temp, context, target_year=target_year):
            return None
        segments = temp["page_evidence"]["evidence_segments"]
    elif requirement_id == "officiating":
        segments = _officiating_segments(
            content,
            max_segments=max_segments,
            max_chars=max_chars,
        )
        if not segments:
            return None
    else:
        return None

    if title:
        enriched: list[str] = []
        for segment in segments:
            if base.normalize_text(title) not in base.normalize_text(segment):
                segment = f"{title}. {segment}"
            enriched.append(segment[:max_chars].strip())
        segments = enriched

    metadata = normalized["metadata"]
    safe_metadata = {
        key: value
        for key, value in metadata.items()
        if key in {"title", "description", "og:title", "og:description", "language"}
        and isinstance(value, str)
    }
    result = deepcopy(source)
    result["checked_at"] = checked_at
    result["content_checked"] = True
    result["eligible_for_factual_validation"] = True
    result["dynamic_relevance_required"] = False
    result["verification_status"] = "page_checked_content_selected_passo34_10"
    result["passo34_10_targeted"] = True
    result["passo34_10_requirement_id"] = requirement_id
    result["page_evidence"] = {
        "metadata": safe_metadata,
        "evidence_segments": segments,
        "segment_count": len(segments),
        "content_length": len(content),
        "content_sha256": base.hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "credits_used": normalized["credits"],
    }
    return result


def _queries(requirement_id: str, context: dict[str, Any], article_date: str) -> list[str]:
    home = context.get("home")
    away = context.get("away")
    competition = context.get("competition")
    if not all(isinstance(x, str) and x.strip() for x in (home, away, competition)):
        return []
    year = _step34_9._target_year(article_date)
    if requirement_id == "stadium_and_location":
        return [
            f'"{home}" "{away}" "{competition}" {year} stadium venue',
            f'"{home}" "{away}" "{competition}" {year} Stadion Spielort',
            f'"{home}" "{away}" {year} arena jogo local',
        ]
    if requirement_id == "officiating":
        return [
            f'"{home}" "{away}" "{competition}" {year} referee officiating',
            f'"{home}" "{away}" "{competition}" {year} Schiedsrichter',
            f'"{home}" "{away}" "{competition}" {year} árbitro',
        ]
    return []


def _search_stages(
    context: dict[str, Any],
    config: dict[str, Any],
    local_domains: list[str],
) -> list[tuple[str, list[str]]]:
    stages = list(_step34_8._allowed_stage_domains(context, config))
    if local_domains:
        stages.append(("relevant_local_press", local_domains))
    return stages


def _search_targeted(
    requirement_id: str,
    *,
    context: dict[str, Any],
    article_date: str,
    checked_at: str,
    config: dict[str, Any],
    local_domains: list[str],
) -> list[dict[str, Any]]:
    target_year = _step34_9._target_year(article_date)
    queries = _queries(requirement_id, context, article_date)
    for source_type, domains in _search_stages(context, config, local_domains):
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for query in queries:
            try:
                _, raw = source_search.request_serper(query=query, domains=domains, config=config)
            except Exception:
                continue
            for candidate in source_search.normalize_serper_response(
                raw,
                allowed_domains=domains or None,
            ):
                url = str(candidate.get("url", ""))
                if not url or url in seen:
                    continue
                seen.add(url)
                rows.append(candidate)

        rows.sort(key=lambda item: int(item.get("position", 999) or 999))
        for candidate in rows[:10]:
            source = deepcopy(candidate)
            source.update(
                {
                    "publisher": str(candidate.get("domain", "")),
                    "source_type": source_type,
                    "dynamic_relevance_required": False,
                    "passo34_10_search_stage": source_type,
                }
            )
            try:
                raw = _step34_7._scrape_once(source["url"], config=config)
            except Exception:
                continue
            checked = _checked_from_raw(
                source,
                raw,
                requirement_id=requirement_id,
                context=context,
                target_year=target_year,
                checked_at=checked_at,
                config=config,
            )
            if checked is not None:
                return [checked]
    return []


def _reuse_original_pages(
    article: dict[str, Any],
    *,
    requirement_id: str,
    context: dict[str, Any],
    article_date: str,
    checked_at: str,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Releitura dirigida de fontes já checadas do MESMO jogo, sem nova busca.

    RSS é só descoberta. A fonte original deve passar novamente por checagem
    de jogo, competição, data e trecho de fato específico do requisito.
    """
    if os.environ.get("CDE_FREE_RESEARCH") != "1":
        return []
    pool = []
    seen = set()
    for req in article.get("requirements", []):
        if not isinstance(req, dict):
            continue
        for candidate in req.get("source_candidates", []):
            if not base.eligible_checked_source(candidate):
                continue
            url = candidate.get("url")
            if not isinstance(url, str) or not url.startswith("https://") or url in seen:
                continue
            seen.add(url)
            pool.append(candidate)
    priority = {"official": 0, "major_sports_media": 1, "relevant_local_press": 2}
    pool.sort(key=lambda x: priority.get(str(x.get("source_type", "")), 3))
    year = _step34_9._target_year(article_date)
    for candidate in pool[:12]:
        try:
            raw = _step34_7._scrape_once(candidate["url"], config=config)
            checked = _checked_from_raw(
                candidate, raw,
                requirement_id=requirement_id,
                context=context,
                target_year=year,
                checked_at=checked_at,
                config=config,
            )
        except Exception:
            continue
        if checked is not None:
            checked["passo34_10_reused_original_page"] = True
            return [checked]
    return []


def _existing_current(
    requirement: dict[str, Any],
    *,
    requirement_id: str,
    context: dict[str, Any],
    target_year: str,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for source in requirement.get("source_candidates", []):
        if not isinstance(source, dict):
            continue
        if requirement_id == "stadium_and_location":
            ok = stadium_source_is_current(source, context, target_year=target_year)
        else:
            ok = officiating_source_is_current(source, context, target_year=target_year)
        if ok:
            selected.append(deepcopy(source))
            break
    return selected


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
    target_year = _step34_9._target_year(article_date)
    local_domains = _article_local_press_domains(result)

    updated: list[dict[str, Any]] = []
    targeted_count = 0
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        req = deepcopy(requirement)
        req_id = req.get("id")
        if req_id in {"stadium_and_location", "officiating"}:
            selected = _existing_current(
                req,
                requirement_id=str(req_id),
                context=context,
                target_year=target_year,
            )
            if not selected:
                selected = _reuse_original_pages(
                    result,
                    requirement_id=str(req_id),
                    context=context,
                    article_date=article_date,
                    checked_at=checked_at,
                    config=config,
                )
            if not selected:
                selected = _search_targeted(
                    str(req_id),
                    context=context,
                    article_date=article_date,
                    checked_at=checked_at,
                    config=config,
                    local_domains=local_domains,
                )
            if selected:
                req["source_candidates"] = selected
                req["ready_for_fact_extraction"] = True
                req["passo34_10_selected"] = True
                targeted_count += len(selected)
            else:
                req["source_candidates"] = []
                req["ready_for_fact_extraction"] = False
                req["passo34_10_selected"] = False
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
    result["passo34_10_targeted_source_count"] = targeted_count
    result["passo34_10_local_press_domains_considered"] = local_domains
    result["passo34_10_applied"] = True

    slug = result.get("slug", "sem-slug")
    print(
        f"PASSO 34.10 — {slug}: estádio/arbitragem selecionados={targeted_count}; "
        f"bloqueios={','.join(blocking) if blocking else 'nenhum'}"
    )
    return result


base.check_article = check_article


def main() -> None:
    base.main()


if __name__ == "__main__":
    main()
