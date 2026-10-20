#!/usr/bin/env python3
"""Extrai fatos estruturados de páginas já checadas com travas de conflito.

Passo 23:
- nunca usa snippets do buscador como evidência factual;
- só usa páginas com content_checked=true e eligible_for_factual_validation=true;
- mantém proveniência e consultas apenas como metadados internos;
- bloqueia campos conflitantes, incompletos ou inconsistentes;
- não redige matéria, não gera HTML e não libera publicação.

Extratores determinísticos habilitados:
stadium_and_location, transmission, probable_lineups_and_coaches, officiating,
recent_form_both_teams, competition_specific_head_to_head e
stakes_and_qualification_scenarios_when_applicable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, NoReturn
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import validar_pesquisa_factual as factual_validator  # noqa: E402
from scripts import qualidade_editorial_pre_jogo as editorial_quality  # noqa: E402

CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo"

ENABLED_EXTRACTORS = {
    "stadium_and_location",
    "transmission",
    "probable_lineups_and_coaches",
    "officiating",
    "recent_form_both_teams",
    "competition_specific_head_to_head",
    "stakes_and_qualification_scenarios_when_applicable",
}

LEAGUE_SLUGS = {
    "premier-league",
    "la-liga",
    "ligue-1",
    "bundesliga",
    "serie-a",
    "brasileirao",
}

KNOWN_VENUES = [
    "Mangueirão",
    "Emirates Stadium",
    "Etihad Stadium",
    "Parc des Princes",
    "Allianz Arena",
    "San Siro",
    "Stadio Giuseppe Meazza",
    "Giuseppe Meazza",
    "Maracanã",
    "Maracana",
    "Estadio Jornalista Mário Filho",
    "Estadio Jornalista Mario Filho",
    "Allianz Parque",
    "Arena do Grêmio",
    "Arena do Gremio",
    "Camp Nou",
    "Spotify Camp Nou",
    "Estadi Olímpic Lluís Companys",
    "Estadi Olimpic Lluis Companys",
    "Santiago Bernabéu",
    "Santiago Bernabeu",
    "Riyadh Air Metropolitano",
    "Estadio Metropolitano",
    "Cívitas Metropolitano",
    "Civitas Metropolitano",
    "Wanda Metropolitano",
    "Orange Vélodrome",
    "Orange Velodrome",
    "Stade Vélodrome",
    "Stade Velodrome",
    "CEPAC Vélodrome",
    "CEPAC Velodrome",
    "Vélodrome",
    "Velodrome",
]

VENUE_CANONICAL_ALIASES = {
    "maracana": "Maracanã",
    "estadio jornalista mario filho": "Maracanã",
    "riyadh air metropolitano": "Riyadh Air Metropolitano",
    "estadio metropolitano": "Riyadh Air Metropolitano",
    "civitas metropolitano": "Riyadh Air Metropolitano",
    "wanda metropolitano": "Riyadh Air Metropolitano",
    "orange velodrome": "Vélodrome",
    "stade velodrome": "Vélodrome",
    "cepac velodrome": "Vélodrome",
    "velodrome": "Vélodrome",
}


def canonical_venue(value: str) -> str:
    key = normalize_text(value)
    return VENUE_CANONICAL_ALIASES.get(key, value)

VENUE_CONTEXT_WORDS = (
    "venue", "stadium", "estádio", "estadio", "arena",
    "played at", "will be played at", "takes place at", "held at",
    "será disputado", "sera disputado", "será disputada", "sera disputada",
    "será jogado", "sera jogado", "será jogada", "sera jogada",
)

ATTRIBUTION_PREFIXES = (
    "segundo o ", "segundo a ", "conforme o ", "conforme a ",
    "de acordo com o ", "de acordo com a ", "according to ",
)

# Passo 34.11 — numerais naturais usados somente na leitura determinística
# de retrospecto. Não há soma/estimativa para criar fatos; o token precisa
# existir literalmente no trecho e a consistência final continua obrigatória.
NATURAL_COUNT_WORDS: dict[str, int] = {
    "zero": 0,
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4,
    "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
    "onze": 11, "doze": 12, "treze": 13, "catorze": 14, "quatorze": 14,
    "quinze": 15, "dezesseis": 16, "dezessete": 17, "dezoito": 18,
    "dezenove": 19, "vinte": 20,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20,
    "eins": 1, "eine": 1, "einen": 1, "zwei": 2, "drei": 3, "vier": 4,
    "funf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10,
    "elf": 11, "zwolf": 12, "dreizehn": 13, "vierzehn": 14,
    "funfzehn": 15, "sechzehn": 16, "siebzehn": 17, "achtzehn": 18,
    "neunzehn": 19, "zwanzig": 20,
}
NATURAL_COUNT_TOKEN_RE = (
    r"(?:\d{1,3}|" + "|".join(
        sorted((re.escape(item) for item in NATURAL_COUNT_WORDS), key=len, reverse=True)
    ) + r")"
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

    policy = config.get("editorial", {}).get("source_attribution_policy")
    if not isinstance(policy, dict):
        fail("Política editorial de atribuição de fontes ausente.")
    if policy.get("research_sources_are_internal_only") is not True:
        fail("Fontes de pesquisa devem permanecer internas.")
    if policy.get("forbid_source_names_in_article_body") is not True:
        fail("Nomes de fontes devem permanecer proibidos como atribuição no corpo da matéria.")
    if policy.get("forbid_research_process_mentions") is not True:
        fail("Menções ao processo de pesquisa devem permanecer proibidas.")

    validation = config.get("research", {}).get("validation")
    if not isinstance(validation, dict) or validation.get("publication_unlock_allowed") is not False:
        fail("A validação factual não pode liberar publicação.")
    return config


def parse_target_date(raw: str | None, tz: ZoneInfo) -> date:
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            fail("--date deve usar o formato YYYY-MM-DD.")
    return datetime.now(tz).date() + timedelta(days=1)


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def clean_value(value: str, *, max_chars: int = 350) -> str:
    value = re.sub(r"\s+", " ", value).strip(" \t\r\n.,;:-–—")
    return value[:max_chars].strip()


def contains_attribution_language(value: str) -> bool:
    folded = normalize_text(value)
    return any(normalize_text(prefix) in folded for prefix in ATTRIBUTION_PREFIXES)


def unmonitored_team_aliases(team: str) -> list[str]:
    """Gera somente variantes conservadoras de nomes vindos do provedor.

    Ex.: "1. FC Union Berlin" -> também "Union Berlin". Isso serve apenas
    para reconhecer o mesmo clube no texto das fontes; não cria qualquer fato.
    """
    if normalize_text(team) in {"clube do remo", "remo"}:
        return ["Clube do Remo", "Remo"]
    if normalize_text(team) in {"estudiantes de la plata", "club estudiantes de la plata"}:
        # O nome editorial nas manchetes é "Estudiantes", sem complemento geográfico.
        return [team.strip(), "Estudiantes", "Estudiantes LP"]
    variants = [team.strip()]
    raw = team.strip()
    prefix_pattern = (
        r"^\s*(?:\d+\.?\s+)?(?:FC|FK|F\.C\.|AFC|A\.F\.C\.|AC|A\.C\.|"
        r"SSC|S\.S\.C\.|AS|A\.S\.|SC|S\.C\.|RC|R\.C\.|CF|C\.F\.|FSV|TSG)\s+"
    )
    stripped = re.sub(prefix_pattern, "", raw, flags=re.IGNORECASE).strip()
    if stripped and normalize_text(stripped) != normalize_text(raw):
        variants.append(stripped)

    # Variações conservadoras vistas nos nomes oficiais do provedor.
    # Só geramos aliases quando o restante continua específico o bastante.
    provider_prefixes = (
        (r"^\s*Club\s+", ""),
        (r"^\s*Olympique\s+de\s+", ""),
        (r"^\s*Red\s+Bull\s+", ""),
    )
    for pattern, replacement in provider_prefixes:
        candidate = re.sub(pattern, replacement, raw, flags=re.IGNORECASE).strip()
        if candidate and len(normalize_text(candidate)) >= 5 and normalize_text(candidate) != normalize_text(raw):
            variants.append(candidate)

    if normalize_text(raw) in {"club atletico de madrid", "atletico de madrid"}:
        variants.extend(["Atlético de Madrid", "Atletico Madrid"])

    rb_match = re.match(r"^\s*RB\s+(.+)$", raw, flags=re.IGNORECASE)
    if rb_match:
        tail = rb_match.group(1).strip()
        if len(normalize_text(tail)) >= 5:
            variants.extend([f"Red Bull {tail}", tail])

    trailing = re.sub(
        r"\s+(?:FC|F\.C\.|AFC|A\.F\.C\.|AC|A\.C\.|SC|S\.C\.|CF|C\.F\.)\s*$",
        "",
        raw,
        flags=re.IGNORECASE,
    ).strip()
    if trailing and normalize_text(trailing) != normalize_text(raw):
        variants.append(trailing)

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in variants:
        key = normalize_text(candidate)
        if not key or key in seen:
            continue
        # Evita aliases excessivamente curtos/genericamente perigosos.
        if candidate != raw and len(key) < 5:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique or [team]


def aliases_for_team(team: str, config: dict[str, Any]) -> list[str]:
    key = normalize_text(team)
    for club in config.get("monitored_clubs", []):
        if not isinstance(club, dict):
            continue
        candidates = [club.get("name"), club.get("slug"), *club.get("aliases", [])]
        normalized = [normalize_text(str(item).replace("-", " ")) for item in candidates if item]
        if key in normalized:
            values = [str(item) for item in candidates if isinstance(item, str) and item.strip()]
            if team not in values:
                values.append(team)
            return values
    return unmonitored_team_aliases(team)


def mentions_team(corpus: str, team: str, config: dict[str, Any]) -> bool:
    folded = normalize_text(corpus)
    return any(
        normalize_text(alias.replace("-", " ")) in folded
        for alias in aliases_for_team(team, config)
    )


def context_mentions_match(corpus: str, match_context: dict[str, Any], config: dict[str, Any]) -> bool:
    home = match_context.get("home")
    away = match_context.get("away")
    return (
        isinstance(home, str)
        and isinstance(away, str)
        and mentions_team(corpus, home, config)
        and mentions_team(corpus, away, config)
    )


def relaxed_team_markers(team: str, config: dict[str, Any]) -> list[str]:
    """Marcadores curtos só para frases dentro de uma página já vinculada ao jogo."""
    markers: list[str] = []
    seen: set[str] = set()
    generic = {
        "fc", "cf", "sc", "ac", "afc", "club", "clube", "de", "da", "do",
        "munique", "munich", "munchen", "muenchen", "milan", "milano",
    }
    for alias in aliases_for_team(team, config):
        normalized = normalize_text(alias.replace("-", " "))
        if normalized and normalized not in seen:
            seen.add(normalized)
            markers.append(normalized)
        tokens = [item for item in normalized.split() if item not in generic]
        if len(tokens) == 1 and len(tokens[0]) >= 5 and tokens[0] not in seen:
            seen.add(tokens[0])
            markers.append(tokens[0])
        elif len(tokens) >= 2:
            pair = " ".join(tokens[-2:])
            if len(pair) >= 7 and pair not in seen:
                seen.add(pair)
                markers.append(pair)
            if len(tokens[0]) >= 6 and tokens[0] not in seen:
                seen.add(tokens[0])
                markers.append(tokens[0])
    if normalize_text(team) in {"sc internacional", "internacional", "sport club internacional"}:
        if "inter" not in seen:
            markers.append("inter")
    return markers


def relaxed_mentions_team(sentence: str, team: str, config: dict[str, Any]) -> bool:
    folded = f" {normalize_text(sentence)} "
    return any(f" {marker} " in folded for marker in relaxed_team_markers(team, config))


def competition_is_mentioned(corpus: str, match_context: dict[str, Any]) -> bool:
    competition = match_context.get("competition")
    if not isinstance(competition, str) or not competition.strip():
        return False
    return normalize_text(competition) in normalize_text(corpus)


def source_corpus(source: dict[str, Any]) -> str:
    parts: list[str] = []
    title = source.get("title")
    if isinstance(title, str):
        parts.append(title)
    page = source.get("page_evidence")
    if isinstance(page, dict):
        metadata = page.get("metadata")
        if isinstance(metadata, dict):
            for value in metadata.values():
                if isinstance(value, str):
                    parts.append(value)
        segments = page.get("evidence_segments")
        if isinstance(segments, list):
            parts.extend(str(item) for item in segments if isinstance(item, str))
    return "\n".join(parts)


def eligible_sources(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    raw = requirement.get("source_candidates")
    if not isinstance(raw, list):
        return []
    return [
        item for item in raw
        if isinstance(item, dict)
        and item.get("content_checked") is True
        and item.get("eligible_for_factual_validation") is True
    ]


def checked_source_records(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in requirement.get("source_candidates", []):
        if not isinstance(source, dict) or source.get("content_checked") is not True:
            continue
        url = source.get("url")
        if not isinstance(url, str) or not url.startswith("https://") or url in seen:
            continue
        seen.add(url)
        records.append({
            "publisher": source.get("publisher"),
            "url": url,
            "source_type": source.get("source_type"),
            "checked_at": source.get("checked_at"),
        })
    return records


def resolve_allowed_gap(
    requirement: dict[str, Any],
    *,
    competition_slug: str,
    config: dict[str, Any],
    competition_stage: str | None = None,
    competition_matchday: int | None = None,
) -> dict[str, Any]:
    """Resolve só ausências que a política já permite, sem fabricar fatos."""
    result = deepcopy(requirement)
    if result.get("status") == "verified" or result.get("conflict_detected") is True:
        return result

    req_id = result.get("id")
    policy = config.get("research", {}).get("requirement_policy", {}).get(req_id, {})
    sources = checked_source_records(result)

    # Só a fase LEAGUE_STAGE comprovada pelo provedor pode usar a exceção,
    # e apenas no início, sem cenário eliminatório da fase final.
    # Nunca dispensar contexto de tabela/notícias: gate editorial é independente.
    early_champions_league_phase = (
        competition_slug == "champions-league"
        and competition_stage == "LEAGUE_STAGE"
        and type(competition_matchday) is int
        and 1 <= competition_matchday <= 3
    )
    if req_id == "stakes_and_qualification_scenarios_when_applicable" and (
        competition_slug in LEAGUE_SLUGS or early_champions_league_phase
    ):
        result["status"] = "not_applicable"
        result["facts"] = []
        result["sources"] = sources
        result["notes"] = (
            "Fase de liga inicial da Champions sem cenário eliminatório imediato comprovado."
            if early_champions_league_phase else
            "Competição de pontos corridos: cenário de classificação mata-mata não se aplica."
        )
        result["fact_extraction_status"] = "automatic_not_applicable_for_league"
        result["validator_accepted"] = True
        result["conflict_detected"] = False
        return result

    no_candidates_after_search = (
        result.get("candidate_status") == "no_candidates"
        and int(result.get("candidate_source_count", 0) or 0) == 0
    )
    # Evidência não encontrada NÃO significa pesquisa não realizada.
    # Quando uma candidata foi efetivamente lida, mas sem conteúdo
    # utilizável, e uma segunda pesquisa dirigida foi executada, pode-se
    # omitir o serviço opcional; jamais promover escalação não verificada.
    exhausted_checked_search = (
        result.get("passo34_9_targeted_search_attempted") is True
        and int(result.get("page_check_attempt_count", 0) or 0) > 0
    )
    if (
        isinstance(policy, dict)
        and policy.get("allow_unavailable_after_check") is True
        and (sources or no_candidates_after_search or exhausted_checked_search)
    ):
        result["status"] = "unavailable_after_check"
        result["facts"] = []
        result["sources"] = sources
        result["notes"] = (
            "Informação não foi confirmada após a pesquisa disponível; nenhuma lacuna foi inventada."
        )
        result["fact_extraction_status"] = (
            "automatic_unavailable_after_checked_sources"
            if sources
            else (
                "automatic_unavailable_after_targeted_research"
                if exhausted_checked_search
                else "automatic_unavailable_after_search_without_candidates"
            )
        )
        result["validator_accepted"] = True
        result["conflict_detected"] = False
    return result


def internal_source_record(source: dict[str, Any], evidence_segment: str) -> dict[str, Any]:
    return {
        "publisher": source.get("publisher"),
        "url": source.get("url"),
        "source_type": source.get("source_type"),
        "checked_at": source.get("checked_at"),
        "evidence_sha256": hashlib.sha256(evidence_segment.encode("utf-8")).hexdigest(),
        "internal_only": True,
    }


def validator_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "publisher": str(source.get("publisher", "")).strip(),
        "url": str(source.get("url", "")).strip(),
        "source_type": str(source.get("source_type", "")).strip(),
        "checked_at": str(source.get("checked_at", "")).strip(),
    }


def unique_validator_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        normalized = validator_source(source)
        url = normalized["url"]
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(normalized)
    return unique


def make_claim(field: str, value: str, source: dict[str, Any], segment: str) -> dict[str, Any] | None:
    value = clean_value(value)
    if not value or contains_attribution_language(value):
        return None
    return {
        "field": field,
        "value": value,
        "normalized_value": normalize_text(value),
        "source": internal_source_record(source, segment),
        "validator_source": validator_source(source),
    }


def group_claims(claims: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for claim in claims:
        field = claim["field"]
        key = claim["normalized_value"]
        field_groups = grouped.setdefault(field, {})
        group = field_groups.setdefault(
            key,
            {
                "field": field,
                "value": claim["value"],
                "normalized_value": key,
                "supporting_sources": [],
            },
        )
        urls = {item.get("url") for item in group["supporting_sources"]}
        if claim["source"].get("url") not in urls:
            group["supporting_sources"].append(claim["source"])
    return grouped


def base_pending_result(requirement: dict[str, Any], claims: list[dict[str, Any]]) -> dict[str, Any]:
    result = deepcopy(requirement)
    grouped = group_claims(claims)
    result["extracted_claims"] = [
        group for field_groups in grouped.values() for group in field_groups.values()
    ]
    result["structured_fact_count"] = 0
    result["conflict_detected"] = False
    result["conflicts"] = []
    result["validator_accepted"] = False
    result["facts"] = []
    result["sources"] = []
    result["status"] = "pending"
    result["internal_provenance_only"] = True
    return result


def finalize_claims(
    requirement: dict[str, Any],
    claims: list[dict[str, Any]],
    *,
    required_fields: list[str],
    fact_builder: Callable[[dict[str, str]], list[dict[str, str]]],
    config: dict[str, Any],
    consistency_check: Callable[[dict[str, str]], str | None] | None = None,
) -> dict[str, Any]:
    result = base_pending_result(requirement, claims)
    grouped = group_claims(claims)

    conflicts = []
    for field, field_groups in grouped.items():
        if len(field_groups) > 1:
            conflicts.append({
                "field": field,
                "values": [item["value"] for item in field_groups.values()],
                "rule": "critical_field_conflict_blocks_validation",
            })

    if conflicts:
        result["fact_extraction_status"] = "conflict_blocked"
        result["conflict_detected"] = True
        result["conflicts"] = conflicts
        return result

    missing = [field for field in required_fields if field not in grouped or not grouped[field]]
    if missing:
        result["fact_extraction_status"] = "incomplete_structured_fact"
        result["missing_fields"] = missing
        return result

    values = {
        field: next(iter(field_groups.values()))["value"]
        for field, field_groups in grouped.items()
        if field_groups
    }
    if consistency_check is not None:
        consistency_error = consistency_check(values)
        if consistency_error:
            result["fact_extraction_status"] = "consistency_blocked"
            result["conflict_detected"] = True
            result["conflicts"] = [{
                "field": "cross_field_consistency",
                "values": values,
                "rule": consistency_error,
            }]
            return result

    facts = fact_builder(values)
    if not facts:
        result["fact_extraction_status"] = "no_supported_structured_fact"
        return result

    selected_urls: set[str] = set()
    # Incluir também as fontes de fatos opcionais efetivamente publicados no
    # contrato, não apenas os campos mínimos que destravam o requisito.
    fact_fields = {
        fact.get("field") for fact in facts
        if isinstance(fact, dict) and isinstance(fact.get("field"), str)
    }
    for field in set(required_fields) | fact_fields:
        if field not in grouped or not grouped[field]:
            continue
        group = next(iter(grouped[field].values()))
        selected_urls.update(
            str(item.get("url")) for item in group["supporting_sources"] if item.get("url")
        )
    validator_sources = unique_validator_sources([
        claim["validator_source"] for claim in claims
        if claim["validator_source"].get("url") in selected_urls
    ])
    evidence = {
        "status": "verified",
        "facts": facts,
        "sources": validator_sources,
        "notes": None,
    }
    validated, errors = factual_validator.validate_requirement_evidence(
        requirement, evidence, config=config
    )
    if errors:
        result["fact_extraction_status"] = "validator_rejected"
        result["validator_errors"] = errors
        return result

    result.update(validated)
    result["extracted_claims"] = [
        group for field_groups in grouped.values() for group in field_groups.values()
    ]
    result["structured_fact_count"] = len(validated.get("facts", []))
    result["conflict_detected"] = False
    result["conflicts"] = []
    result["validator_accepted"] = True
    result["fact_extraction_status"] = "validated_structured_fact"
    result["internal_provenance_only"] = True
    return result


def extract_venue_values(text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    segments = [line.strip() for line in text.splitlines() if line.strip()]
    for segment in segments:
        folded = normalize_text(segment)
        if not any(normalize_text(word) in folded for word in VENUE_CONTEXT_WORDS):
            continue
        for venue in KNOWN_VENUES:
            if normalize_text(venue) in folded:
                canonical = canonical_venue(venue)
                key = normalize_text(canonical)
                if key not in seen:
                    seen.add(key)
                    found.append((canonical, segment))
        if any(normalize_text(v) in folded for v in KNOWN_VENUES):
            continue
        patterns = [
            r"(?:venue\s*[:\-]?\s*|played at\s+|will be played at\s+|takes place at\s+|held at\s+)(?:the\s+)?([A-ZÀ-Ý][\wÀ-ÿ'’.-]*(?:\s+(?:[A-ZÀ-Ý][\wÀ-ÿ'’.-]*|do|da|de|dos|das)){0,5}\s+(?:Stadium|Arena|Park|Ground))",
            r"(?:estádio|estadio|local)\s*[:\-]?\s*([A-ZÀ-Ý][\wÀ-ÿ'’.-]*(?:\s+(?:[A-ZÀ-Ý][\wÀ-ÿ'’.-]*|do|da|de|dos|das)){0,5}(?:\s+(?:Stadium|Arena|Park|Ground))?)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, segment, flags=re.IGNORECASE):
                value = canonical_venue(clean_value(match.group(1), max_chars=120))
                key = normalize_text(value)
                if len(value) >= 4 and key and key not in seen:
                    seen.add(key)
                    found.append((value, segment))
    return found


def extract_stadium_requirement(
    requirement: dict[str, Any],
    *, match_context: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    claims: list[dict[str, Any]] = []
    for source in eligible_sources(requirement):
        if not source_current_for_match(source, match_context):
            continue
        corpus = source_corpus(source)
        if not corpus or not context_mentions_match(corpus, match_context, config):
            continue
        for value, segment in extract_venue_values(corpus):
            claim = make_claim("stadium", value, source, segment)
            if claim:
                claims.append(claim)
    return finalize_claims(
        requirement,
        claims,
        required_fields=["stadium"],
        fact_builder=lambda v: [{"field": "stadium", "text": f"A partida será disputada no {v['stadium']}."}],
        config=config,
    )


def labeled_value(segment: str, labels: tuple[str, ...], *, max_chars: int = 240) -> str | None:
    for label in labels:
        pattern = rf"(?:^|[\s|•;]){label}\s*[:\-–—]\s*(.+)$"
        match = re.search(pattern, segment, flags=re.IGNORECASE)
        if match:
            value = clean_value(match.group(1), max_chars=max_chars)
            return value or None
    return None


def normalize_transmission_broadcasters(value: str) -> str:
    """Unifica grafias de canais somente quando TODOS os nomes são reconhecidos.

    Não resolve divergências reais de emissoras: nesses casos os grupos seguem
    separados e finalize_claims continua bloqueando a publicação.
    """
    aliases = {
        "globo": "TV Globo", "tv globo": "TV Globo", "rede globo": "TV Globo",
        "ge tv": "ge tv", "getv": "ge tv", "ge.tv": "ge tv",
        "premiere": "Premiere", "premiere futebol": "Premiere",
        "espn": "ESPN", "disney": "Disney+", "disney+": "Disney+", "disney plus": "Disney+",
        "sportv": "SporTV", "tnt": "TNT", "hbo max": "HBO Max",
        "paramount": "Paramount+", "paramount plus": "Paramount+",
        "cazetv": "CazéTV", "caze tv": "CazéTV",
        "prime video": "Prime Video", "amazon prime video": "Prime Video",
        "band": "Band",
    }
    cleaned = re.sub(r"\([^)]{1,80}\)", "", value)
    parts = re.split(r"\s*,\s*|\s*;\s*|\s+e\s+|\s+ou\s+", cleaned, flags=re.IGNORECASE)
    if not parts:
        return value
    canonical = []
    for part in parts:
        label = re.sub(r"^\s*(?:do|da|de|no|na|pelo|pela)\s+", "", part.strip(), flags=re.IGNORECASE)
        label = label.strip(" \t\r\n.,;:-–—")
        normalized = normalize_text(label)
        broadcast = aliases.get(normalized)
        if not broadcast:
            return value
        if broadcast not in canonical:
            canonical.append(broadcast)
    if not canonical:
        return value
    order = ["TV Globo", "ge tv", "Premiere", "SporTV", "ESPN", "Disney+",
             "TNT", "HBO Max", "CazéTV", "Prime Video", "Paramount+", "Band"]
    canonical.sort(key=lambda label: order.index(label))
    return ", ".join(canonical[:-1]) + " e " + canonical[-1] if len(canonical) > 1 else canonical[0]


def current_fixture_headline_in_order(source, context, config):
    """Evita confundir ida e volta: exige mandante x visitante na manchete."""
    title = normalize_text(str(source.get("title") or ""))
    # "FC Inter vs FC Shakhtar" e "Inter vs Shakhtar" são o
    # mesmo mando; prefixos jurídicos não mudam a ordem dos clubes.
    title = re.sub(r"\b(?:fc|fk|afc|ac|ssc)\s+", "", title)
    home = str(context.get("home") or "")
    away = str(context.get("away") or "")
    if not home or not away or not title:
        return False
    for a in relaxed_team_markers(home, config):
        for b in relaxed_team_markers(away, config):
            if a == b or len(a) < 3 or len(b) < 3:
                continue
            if re.search(rf"\b{re.escape(a)}\s+(?:x|vs|contra|v)\s+{re.escape(b)}\b", title):
                return True
    return False


def broadcast_names_from_prose(segment):
    """Extrai apenas plataformas literalmente presentes em frase de transmissão.

    Nunca usa manchete 'onde assistir' isolada, palpite ou citação de TV sem
    afirmar que a partida terá transmissão por aqueles canais.
    """
    # Agregadores brasileiros frequentemente indicam "você pode assistir
    # em streaming ao vivo na HBO Max" sem usar a palavra transmissão.
    # Exigir afirmação explícita de disponibilidade atual, não só logo
    # ou lista solta de serviços em outras notícias do portal.
    positive = re.search(
        r"\btransmiss[aã]o\b|\bstreaming\s+ao\s+vivo\b|"
        r"\b(?:assistir|assista)\b.{0,80}\b(?:ao\s+vivo|pelo|pela|na|no)\b",
        segment, re.I,
    )
    if not positive:
        return None
    if re.search(r"\b(?:sem|n[aã]o\s+(?:tem|ter[aá]|haver[aá]))\s+transmiss[aã]o\b", segment, re.I):
        return None
    patterns = (
        (r"\b(?:TV\s+Globo|Rede\s+Globo)\b", "TV Globo"),
        (r"\b(?:ge\s*tv|ge\.tv|Getv)\b", "ge tv"),
        (r"\bPremiere\b", "Premiere"),
        (r"\bSporTV\b", "SporTV"),
        (r"\bESPN\b", "ESPN"),
        (r"\bDisney\s*\+", "Disney+"),
        (r"\bTNT\b", "TNT"),
        (r"\bHBO\s+Max\b", "HBO Max"),
        (r"\bCaz[eé]\s*TV\b", "CazéTV"),
        (r"\b(?:Amazon\s+)?Prime\s+Video\b", "Prime Video"),
        (r"\bParamount\s*\+", "Paramount+"),
        (r"\bBand\b", "Band"),
    )
    found = []
    for pattern, name in patterns:
        if re.search(pattern, segment, re.I):
            found.append(name)
    if not found:
        return None
    return ", ".join(found[:-1]) + " e " + found[-1] if len(found) > 1 else found[0]


def eliminate_incomplete_broadcast_claims(claims):
    """Uma mesma página pode dar resumo parcial e lista completa de canais.

    Elimina apenas lista de emissoras que seja subconjunto ESTRITO de outra
    na mesma fonte. Fontes/canais realmente conflitantes continuam bloqueados.
    """
    names = {
        "TV Globo", "ge tv", "Premiere", "SporTV", "ESPN", "Disney+",
        "TNT", "HBO Max", "CazéTV", "Prime Video", "Paramount+", "Band",
    }
    allowed = {normalize_text(name) for name in names}

    def channels(row):
        parts = re.split(r"\s*,\s*|\s+e\s+", str(row.get("value") or ""), flags=re.I)
        normalized = {normalize_text(part.strip()) for part in parts if part.strip()}
        return normalized if normalized and normalized <= allowed else None

    # Diferentes veículos brasileiros podem anunciar apenas algumas das
    # plataformas confirmadas. Uma lista estritamente contida em outra
    # NÃO é uma contradição (ge tv versus Globo + ge tv + Paramount+).
    # Canais incompatíveis ou sem um conjunto total comum continuam bloqueados.
    mapped = [channels(item) for item in claims]
    comparable = len(claims) >= 2 and all(value is not None for value in mapped)
    if comparable:
        largest = max(mapped, key=len)
        if all(value <= largest for value in mapped):
            return [
                claim for claim, subset in zip(claims, mapped)
                if subset == largest
            ]

    cleaned = []
    for claim in claims:
        current = channels(claim)
        if current is not None and any(
            claim is not other
            and claim.get("source", {}).get("url") == other.get("source", {}).get("url")
            and (other_channels := channels(other)) is not None
            and current < other_channels
            for other in claims
        ):
            continue
        cleaned.append(claim)
    return cleaned


def broadcast_list_from_label(raw: str) -> str | None:
    """Preserva apenas emissoras explicitamente citadas em serviço do jogo.

    Não aceita "Palmeiras" como canal, nem mantém um comentário sobre o ge
    após a lista de transmissões. Outros detalhes e conflitos continuam
    passando pelo validador tradicional.
    """
    text = re.split(r"\.\s+(?=[A-ZÀ-Ý])", raw.strip(), maxsplit=1)[0]
    result = normalize_transmission_broadcasters(text)
    allowed = {
        "TV Globo", "ge tv", "Premiere", "SporTV", "ESPN", "Disney+",
        "TNT", "HBO Max", "CazéTV", "Prime Video", "Paramount+", "Band",
    }
    parts = re.split(r"\s*,\s*|\s+e\s+", result, flags=re.I)
    return result if parts and all(item.strip() in allowed for item in parts) else None


def extract_transmission_requirement(
    requirement: dict[str, Any],
    *, match_context: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    labels = (
        r"transmiss(?:ão|ao)", r"onde assistir", r"broadcast", r"watch",
        r"tv(?:\s*/\s*streaming)?", r"streaming",
    )
    claims: list[dict[str, Any]] = []
    for source in eligible_sources(requirement):
        if not source_current_for_match(source, match_context):
            continue
        inverse = {**match_context, "home": match_context.get("away"),
                   "away": match_context.get("home")}
        if (current_fixture_headline_in_order(source, inverse, config)
                and not current_fixture_headline_in_order(source, match_context, config)):
            # Notícia da ida não é serviço verificável da volta.
            continue
        corpus = source_corpus(source)
        if not context_mentions_match(corpus, match_context, config):
            continue
        # Somente conteúdo da página original, não meta description / SEO.
        # "No Prime Video?" no título do JustWatch não comprova exibição.
        segments = (source.get("page_evidence") or {}).get("evidence_segments") or []
        for segment in segments:
            if not isinstance(segment, str):
                continue
            # "Segundo o portal X, ESPN" é atribuição indireta,
            # não comprovação original do canal do jogo.
            if contains_attribution_language(segment):
                continue
            raw_label = labeled_value(segment, labels, max_chars=180)
            value = broadcast_list_from_label(raw_label) if raw_label else None
            if not value and current_fixture_headline_in_order(source, match_context, config):
                # Apenas prova afirmativa de transmissão, nunca card de jogo.
                from_prose = broadcast_names_from_prose(segment)
                value = broadcast_list_from_label(from_prose) if from_prose else None
            if value and not re.search(
                r"\b(?:nao anunciado|a definir|to be announced|tba)\b",
                normalize_text(value),
            ):
                claim = make_claim("transmission", value, source, segment)
                if claim:
                    claims.append(claim)
    return finalize_claims(
        requirement,
        eliminate_incomplete_broadcast_claims(claims),
        required_fields=["transmission"],
        fact_builder=lambda v: [{"field": "transmission", "text": f"Transmissão: {v['transmission']}."}],
        config=config,
    )


def extract_referee_name(segment: str) -> str | None:
    """Aceita nome próprio, sem absorver o título da seção seguinte.

    Não usa IGNORECASE sobre o nome: sem isso, palavras comuns e títulos
    colados após o árbitro podem virar parte de uma pessoa inexistente.
    """
    pattern = (
        r"(?i:(?:match\s+referee|árbitro|arbitro|referee|schiedsrichter))"
        r"\s*[:\-–—]\s*"
        r"([A-ZÀ-Ý][a-zà-ÿ'’.-]+"
        r"(?:\s+(?:(?:de|da|do|dos|das|van|von|del|di)\s+)?[A-ZÀ-Ý][a-zà-ÿ'’.-]+){1,4})"
    )
    match = re.search(pattern, segment)
    if not match:
        return None
    value = re.split(
        r"\s+(?:Historial|Retrospecto|Head|Preview|Alineaciones|Escalações|Confrontos|Arbitragem)\b",
        match.group(1),
    )[0].strip()
    return value if len(value.split()) >= 2 else None


def current_referee_assignment(
    segment: str, match_context: dict[str, Any], config: dict[str, Any],
) -> str | None:
    """Lê somente nome ligado à DESIGNAÇÃO para este jogo, não históricos.

    Se uma matéria menciona vários árbitros de jogos passados, nunca usa o
    segundo nome como conflito factual. Prefere ausência a atribuição falsa.
    """
    for sentence in re.split(r"(?<=[.!?])\s+", segment):
        if not context_mentions_match(sentence, match_context, config):
            continue
        folded = normalize_text(sentence)
        year = str(match_context.get("kickoff_brasilia") or "")[:4]
        if any(y != year for y in re.findall(r"\b20\d{2}\b", folded)):
            continue
        name = (
            r"([A-ZÀ-Ý][a-zà-ÿ'’.-]+"
            r"(?:\s+[A-ZÀ-Ý][a-zà-ÿ'’.-]+){1,3})"
        )
        patterns = (
            name + r"\s+(?i:será|sera|foi designado|foi escalado)"
                   r"\s+(?i:(?:o|como|para ser)\s+)?"
                   r"(?i:árbitro|arbitro|juiz)\b",
            name + r"\s+(?i:apita|apitará|apitara)\s+",
        )
        for pattern in patterns:
            hit = re.search(pattern, sentence)
            if hit:
                return hit.group(1).strip()
    return None


def include_current_referee_sources(
    requirements: list[dict[str, Any]], *,
    match_context: dict[str, Any], config: dict[str, Any],
) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    seen: set[str] = set()
    for requirement in requirements:
        for source in eligible_sources(requirement):
            url = source.get("url")
            if not isinstance(url, str) or url in seen:
                continue
            if not source_current_for_match(source, match_context):
                continue
            segments = (source.get("page_evidence") or {}).get("evidence_segments", [])
            if not isinstance(segments, list):
                continue
            if any(
                current_referee_assignment(seg, match_context, config)
                for seg in segments if isinstance(seg, str)
            ):
                seen.add(url)
                verified.append(source)
    updated = []
    for req in requirements:
        if req.get("id") != "officiating":
            updated.append(req)
            continue
        row = deepcopy(req)
        existing = {
            s.get("url") for s in row.get("source_candidates", [])
            if isinstance(s, dict)
        }
        row["source_candidates"] = [
            *[deepcopy(x) for x in verified if x.get("url") not in existing],
            *row.get("source_candidates", []),
        ]
        updated.append(row)
    return updated


def extract_officiating_requirement(
    requirement: dict[str, Any],
    *,
    match_context: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    claims: list[dict[str, Any]] = []
    for source in eligible_sources(requirement):
        if not source_current_for_match(source, match_context):
            continue
        corpus = source_corpus(source)
        if not context_mentions_match(corpus, match_context, config):
            continue
        segments = (source.get("page_evidence") or {}).get("evidence_segments", [])
        if not isinstance(segments, list):
            continue
        for segment in segments:
            if not isinstance(segment, str):
                continue
            name = current_referee_assignment(segment, match_context, config)
            if name is None:
                # Ficha de serviço atual: o título deve ser EXATAMENTE o duelo.
                # "Árbitro de X x Y relembra 2025" não é ficha, é notícia
                # histórica e pode mencionar dezenas de outros profissionais.
                title = normalize_text(str(source.get("title") or ""))
                home = str(match_context.get("home") or "")
                away = str(match_context.get("away") or "")
                home_aliases = [normalize_text(x) for x in aliases_for_team(home, config)]
                away_aliases = [normalize_text(x) for x in aliases_for_team(away, config)]
                fixture_titles = {
                    f"{h} {versus} {a}"
                    for h in home_aliases for a in away_aliases
                    for versus in ("x", "vs")
                    if len(h) >= 4 and len(a) >= 4
                } | {
                    f"{a} {versus} {h}"
                    for h in home_aliases for a in away_aliases
                    for versus in ("x", "vs")
                    if len(h) >= 4 and len(a) >= 4
                }
                if title in fixture_titles and re.match(
                    r"(?i)^\s*[áa]rbitro\s*[:–—-]", segment,
                ):
                    name = extract_referee_name(segment)
            if name is None and source.get("source_type") == "official":
                # Ficha da própria competição: "Arsenal v Manchester City -
                # Premier League | Árbitro: Michael Oliver". Aceitar somente
                # se mandante, visitante e competição surgirem ANTES do campo,
                # não notícias históricas em que clubes foram apenas citados.
                separator = re.search(r"(?i)\b[áa]rbitro\s*[:–—-]", segment)
                if separator:
                    before = segment[:separator.start()]
                    simplified = normalize_text(before)
                    home = str(match_context.get("home") or "")
                    away = str(match_context.get("away") or "")
                    competition = str(match_context.get("competition") or "")
                    if (
                        home and away and competition
                        and mentions_team(before, home, config)
                        and mentions_team(before, away, config)
                        and normalize_text(competition) in simplified
                        and re.search(r"\b(?:v|vs|x)\b", simplified)
                        and len(before.split()) <= 18
                    ):
                        name = extract_referee_name(segment[separator.start():])
            if name:
                claim = make_claim("referee", name, source, segment)
                if claim:
                    claims.append(claim)
    return finalize_claims(
        requirement,
        claims,
        required_fields=["referee"],
        fact_builder=lambda v: [{"field": "referee", "text": f"Árbitro: {v['referee']}."}],
        config=config,
    )


def extract_team_labeled_claims(
    requirement: dict[str, Any],
    *, match_context: dict[str, Any],
    config: dict[str, Any],
    labels: tuple[str, ...],
    field_suffix: str,
    max_chars: int,
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    teams = [("home", match_context.get("home")), ("away", match_context.get("away"))]
    for source in eligible_sources(requirement):
        if not source_current_for_match(source, match_context):
            continue
        inverse = {**match_context, "home": match_context.get("away"),
                   "away": match_context.get("home")}
        if (current_fixture_headline_in_order(source, inverse, config)
                and not current_fixture_headline_in_order(source, match_context, config)):
            # A escalação provável da ida NÃO comprova a escalação da volta.
            continue
        corpus = source_corpus(source)
        for segment in corpus.splitlines():
            # Segmentos do leitor incluem a manchete dos DOIS clubes.
            # "Palmeiras | Provável escalação" deve alimentar apenas Palmeiras.
            scope = re.search(
                r"\|\s*(?:prov[aá]vel\s+escala[cç][aã]o|t[eé]cnico)\s*:",
                segment, re.I,
            )
            scoped_team = (
                segment[:scope.start()].rsplit(". ", 1)[-1].strip()
                if scope else None
            )
            if scoped_team:
                # Listas HTML por clube usam cabeçalho "Provável Time | Técnico".
                scoped_team = re.sub(
                    r"^(?:prov[aá]vel(?:\s+escala[cç][aã]o)?|"
                    r"escala[cç][aã]o\s+prov[aá]vel)\s+"
                    r"(?:(?:do|da|de)\s+)?",
                    "", scoped_team, flags=re.I,
                ).strip()
            for side, team in teams:
                if not isinstance(team, str) or not mentions_team(segment, team, config):
                    continue
                if scoped_team and not any(
                    normalize_text(scoped_team) == normalize_text(alias)
                    for alias in aliases_for_team(team, config)
                ):
                    continue
                # Não aceitar prévias do MESMO clube para uma partida anterior.
                if not context_mentions_match(corpus, match_context, config):
                    continue
                value = labeled_value(segment, labels, max_chars=max_chars)
                if not value:
                    aliases = aliases_for_team(team, config)
                    alias_pattern = "(?:" + "|".join(re.escape(alias) for alias in aliases) + ")"
                    for label in labels:
                        match = re.search(
                            rf"{alias_pattern}.*?{label}\s*[:\-–—]\s*(.+)$",
                            segment,
                            flags=re.IGNORECASE,
                        )
                        if match:
                            value = clean_value(match.group(1), max_chars=max_chars)
                            break
                    if not value and field_suffix == "lineup":
                        # Sites esportivos também escrevem "Provável Time: 11 nomes".
                        match = re.search(
                            rf"(?:prov[aá]vel(?:\s+escala[cç][aã]o)?|"
                            rf"probable\s+lineup|predicted\s+(?:lineup|xi))"
                            rf"\s*(?:(?:do|da|de)\s+)?{alias_pattern}"
                            rf"\s*[:\-–—]\s*(.+)$",
                            segment,
                            flags=re.IGNORECASE,
                        )
                        if match:
                            value = clean_value(match.group(1), max_chars=max_chars)
                if value:
                    claim = make_claim(f"{side}_{field_suffix}", value, source, segment)
                    if claim:
                        claims.append(claim)
    return claims


def source_current_for_match(
    source: dict[str, Any], match_context: dict[str, Any],
) -> bool:
    """Uma página checada hoje NÃO transforma um pré-jogo antigo em notícia de hoje."""
    kickoff = str(match_context.get("kickoff_brasilia") or "")
    target = re.search(r"20\d{2}", kickoff)
    if not target:
        return True  # testes de extração isolada ainda não possuem data-alvo
    target_year = target.group(0)

    # Notícia de preparação precisa ser RECENTE para o jogo-alvo. Uma página
    # de 2021 não pode virar notícia de elenco ou de classificação em 2026.
    # Publicado em RSS é metadado de descoberta, nunca o FATO em si;
    # pode, porém, desqualificar uma página antiga com segurança.
    try:
        kickoff_datetime = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
        if kickoff_datetime.tzinfo is None:
            kickoff_datetime = kickoff_datetime.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
    except ValueError:
        return False
    # Páginas de índice 'Palmeiras news' agrupam chamadas de outros
    # clubes (Neymar/Santos/Flamengo) numa única página. Não são reportagem
    # individual e não podem fundamentar contexto atual de um time.
    headline_index = normalize_text(str(source.get("title") or "")).strip()
    locator_url = str(source.get("url") or "").casefold()
    if (
        re.fullmatch(r"(?:[a-z0-9 ]{3,50} )?(?:news|noticias|ultimas noticias)", headline_index)
        or re.search(r"/team/[^/]+/news(?:/|$)", locator_url)
    ):
        return False

    # Rejeitar esporte errado antes de contar notícia atual de clube
    # multiesportivo. Ex.: "Sesc RJ Flamengo / vôlei" jamais deve ser
    # interpretado como contexto competitivo do futebol masculino.
    other_sports = r"(?:volei|voleibol|volleyball|basquete|basketball|tenis|handebol|futsal)"
    if re.search(rf"/{other_sports}(?:/|$)", locator_url):
        return False
    if re.search(rf"\b{other_sports}\b", headline_index):
        return False

    hint = source.get("published_hint")
    verified_publication_date = False
    if isinstance(hint, str) and hint.strip():
        try:
            published = parsedate_to_datetime(hint.strip())
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, IndexError):
            return False  # Metadado temporal inválido não autoriza notícia atual.
        if not kickoff_datetime - timedelta(days=14) <= published <= kickoff_datetime + timedelta(hours=4):
            return False
        verified_publication_date = True

    # Uma notícia sobre Libertadores Feminina, WSL ou outra categoria
    # não pode fundamentar o contexto esportivo de um jogo masculino.
    competition_category = normalize_text(
        str(match_context.get("competition") or "") + " "
        + str(match_context.get("gender") or "")
    )
    if not re.search(r"\b(?:feminina|feminino|women|womens|female|femminile|feminin)\b", competition_category):
        headline_category = normalize_text(
            str(source.get("title") or "") + " " + str(source.get("url") or "")
        )
        if re.search(r"\b(?:feminina|feminino|femininas|women|womens|female|"
                     r"femminile|feminin|femmes|frauen|wsl)\b", headline_category):
            return False
        # Algumas manchetes omitem "Feminina" embora a PRIMEIRA notícia
        # verificada diga explicitamente Libertadores Feminina (caso Kate Tapia).
        first_segments = (source.get("page_evidence") or {}).get("evidence_segments", [])
        opening = normalize_text(str(first_segments[0])[:600]) if first_segments else ""
        if re.search(r"\b(?:libertadores feminina|champions league feminina|"
                     r"copa feminina|womens champions|football feminino|"
                     r"futebol feminino|frauen bundesliga)\b", opening):
            return False

    # Pré-jogo profissional não pode usar fatos do Sub-20, Sub-17 ou de
    # outras divisões de base como se fossem preparação do time principal.
    match_category = normalize_text(
        str(match_context.get("competition") or "") + " "
        + str(match_context.get("category") or "") + " "
        + str(match_context.get("age_group") or "")
    )
    youth = r"\b(?:sub[ -]?(?:15|17|18|19|20|21|23)|u[ -]?(?:17|19|20|21|23)|under[ -]?(?:17|19|20|21|23))\b"
    if not re.search(youth, match_category):
        title_and_url = normalize_text(
            str(source.get("title") or "") + " " + str(source.get("url") or "")
        )
        evidence_segments = (source.get("page_evidence") or {}).get("evidence_segments", [])
        opening = normalize_text(str(evidence_segments[0])[:700]) if evidence_segments else ""
        if re.search(youth, title_and_url) or re.search(youth, opening):
            return False

    metadata = (source.get("page_evidence") or {}).get("metadata") or {}
    locator = " ".join(str(value) for value in (
        source.get("url", ""), source.get("title", ""),
        metadata.get("og:title", ""),
    ))
    years = set(re.findall(r"(?<!\d)20[12]\d(?!\d)", locator))
    if years and target_year not in years:
        return False
    # Não aplicar notícias de outra competição a um jogo atual.
    headline = normalize_text(" ".join(str(value) for value in (
        source.get("title", ""), metadata.get("og:title", ""),
        metadata.get("description", ""),
    )))
    league = normalize_text(str(match_context.get("competition_slug") or ""))
    if league == "brasileirao" and "copa do brasil" in headline and "brasileirao" not in headline and "serie a" not in headline:
        return False
    if league == "libertadores" and not "libertador" in headline and any(
        token in headline for token in (
            "brasileirao", "campeonato brasileiro", "brasileiro serie a",
            "campeonato paulista", "paulistao", "campeonato carioca",
        )
    ):
        # Uma matéria do Brasileirão pode comprovar a PREPARAÇÃO para a
        # Libertadores, mas apenas dentro da coleta editorial individual:
        # ex. Fluminense poupou titulares no Fla-Flu visando a semifinal.
        # Nunca usa este desvio para comprovar o serviço/placar/fase do jogo.
        side = source.get("editorial_target_side")
        team = match_context.get(side) if side in ("home", "away") else None
        segments = (source.get("page_evidence") or {}).get("evidence_segments", [])
        if not (
            isinstance(team, str)
            and team == source.get("editorial_target_team")
            and isinstance(segments, list)
            and any(
                isinstance(segment, str)
                and "libertador" in normalize_text(segment)
                and (
                    re.search(r"(?<!\w)" + re.escape(normalize_text(team)) + r"(?!\w)", normalize_text(segment))
                    or (
                        normalize_text(team) == "fluminense"
                        and re.search(r"\bFlu\b", segment)
                    )
                )
                for segment in segments
            )
        ):
            return False
    if league == "champions league" and "champions" not in headline and any(
        token in headline for token in ("premier league", "bundesliga", "la liga", "ligue 1", "serie a")
    ):
        return False
    # Para notícias de elenco, fonte jornalística sem nenhuma referência temporal
    # pode ser matéria histórica ou modelo de cobertura. Não a promover a fato.
    if not years and source.get("source_type") != "official" and not verified_publication_date:
        body = " ".join(str(item) for item in
            (source.get("page_evidence") or {}).get("evidence_segments", []))
        if target_year not in body:
            # Guia regional sem ano no texto: JustWatch informa dia/mês
            # do evento, e a própria URL fixa a temporada 26-27.
            # Ambos precisam corresponder à data-alvo. Não usa o
            # horário da consulta como suposta data de publicação.
            month = ("jan", "fev", "mar", "abr", "mai", "jun",
                     "jul", "ago", "set", "out", "nov", "dez")
            season = f"{target_year[-2:]}-{(int(target_year) + 1) % 100:02d}"
            expected_day = f"{kickoff_datetime.day} de {month[kickoff_datetime.month - 1]}"
            current_guide = (
                "sports.justwatch.com" in locator_url
                and season in locator_url
                and expected_day in normalize_text(body)
                and context_mentions_match(source_corpus(source), match_context, load_config())
            )
            if not current_guide:
                return False
    return True


TEAM_NEWS_PATTERNS = (
    r"\bdesfalques?\b", r"\bles(?:a|ã)o\b", r"\blesionad[oa]s?\b",
    r"\bsuspens[oa]s?\b", r"\bsuspens[aã]o\b", r"\bd[uú]vida\b",
    r"\bfora\s+do\s+jogo\b", r"\bn[aã]o\s+(?:joga|enfrenta)\b",
    r"\bretorn(?:a|o|am|ou)\b.{0,45}\bles(?:a|ã)o\b",
    r"\bvolta\b.{0,45}\bles(?:a|ã)o\b",
    r"\binjur(?:y|ed|ies)\b", r"\bsuspended\b", r"\bdoubtful\b",
    r"\bruled\s+out\b", r"\bunavailable\b",
    r"\breturns?\s+from\s+injury\b", r"\bback\s+in\s+contention\b",
    r"\bfit\s+again\b",
    r"\bbajas?\b", r"\blesionad[oa]s?\b", r"\bsancionad[oa]s?\b",
    r"\bregresa\b.{0,45}\blesi[oó]n\b", r"\bvuelve\b.{0,45}\blesi[oó]n\b",
    r"\bverletzt\b", r"\bgesperrt\b", r"\bfraglich\b",
    r"\bblesse\b", r"\bsuspendu\b", r"\bforfait\b", r"\bincertain\b",
    r"\binfortunato\b", r"\bsqualificato\b", r"\bdubbio\b",
)


def extract_optional_team_news_claims(
    requirement: dict[str, Any],
    *,
    match_context: dict[str, Any],
    config: dict[str, Any],
    max_per_team: int = 3,
) -> list[dict[str, Any]]:
    """Extrai disponibilidade/desfalques sem inferir clube ou condição médica.

    A frase precisa citar a própria equipe e conter marcador explícito de
    ausência, dúvida, suspensão ou retorno. O texto é preservado como evidência
    factual; o redator apenas o traduz/parafraseia depois.
    """
    teams = [("home", match_context.get("home")), ("away", match_context.get("away"))]
    collected: dict[str, list[tuple[str, dict[str, Any], str]]] = {"home": [], "away": []}
    seen: dict[str, set[str]] = {"home": set(), "away": set()}

    for source in eligible_sources(requirement):
        if not source_current_for_match(source, match_context):
            continue
        corpus = source_corpus(source)
        evidence_segments = (source.get("page_evidence") or {}).get("evidence_segments", [])
        if not corpus or not isinstance(evidence_segments, list) or not evidence_segments:
            continue
        if not context_mentions_match(corpus, match_context, config):
            continue
        for segment in evidence_segments:
            if not isinstance(segment, str) or not segment.strip():
                continue
            active_side = None
            for sentence in re.split(r"(?<=[.!?])\s+", segment):
                value = clean_value(sentence, max_chars=360)
                folded = normalize_text(value)
                # Resolver a equipe ANTES de filtrar por desfalque: manchetes
                # podem abrir o parágrafo ("O Flamengo terá reforços") e os
                # nomes dos jogadores aparecem apenas nas frases seguintes.
                mentioned = []
                for side, team in teams:
                    if not isinstance(team, str):
                        continue
                    identifier = normalize_text(team).split()[-1]
                    position = folded.find(identifier)
                    if position < 0:
                        # Apelidos só valem em uma página previamente vinculada
                        # aos DOIS clubes e apenas quando não servem ao rival.
                        # Assim "O Tricolor... Germán Cano" pertence ao
                        # Fluminense diante do Palmeiras, nunca ao Palmeiras.
                        known = {
                            "fluminense": ("tricolor carioca", "tricolor", "flu"),
                            "palmeiras": ("alviverde", "verdao"),
                            "sao paulo": ("tricolor paulista", "tricolor"),
                            "gremio": ("tricolor gaucho", "tricolor"),
                            "bahia": ("tricolor", "esquadrao"),
                        }
                        other = match_context.get("away" if side == "home" else "home")
                        aliases = set(known.get(normalize_text(team), ()))
                        aliases -= set(known.get(normalize_text(str(other)), ()))
                        for alias in sorted(aliases, key=len, reverse=True):
                            if alias == "flu" and not re.search(r"\bFlu\b", value):
                                continue
                            matched = re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", folded)
                            if matched:
                                position = matched.start()
                                break
                    if position < 0:
                        continue
                    if position >= 0:
                        # "Para enfrentar o Palmeiras, Germán Cano é dúvida"
                        # é notícia do ADVERSÁRIO, não do Palmeiras. O nome
                        # citado após enfrentar/contra/diante de não estabelece
                        # a equipe à qual o atleta pertence.
                        prefix = folded[max(0, position - 54):position]
                        if re.search(
                            r"(?:para enfrentar|enfrenta|enfrentara|contra|"
                            r"diante do|diante da|frente ao|frente a|"
                            r"against|to face|versus|vs|contro|contre|ante)"
                            r"\s+(?:(?:o|a|os|as|the|al|el|la)\s+)?$",
                            prefix,
                        ):
                            continue
                        mentioned.append((position, side))
                if mentioned:
                    mentioned.sort()
                    if len(mentioned) == 1 or mentioned[0][0] < mentioned[1][0]:
                        active_side = mentioned[0][1]
                    else:
                        active_side = None
                if len(value.split()) < 5:
                    continue
                if re.search(
                    r"(?i)\b(?:n[aã]o\s+(?:h[aá]|tem|existem|foram)\s+(?:confirma[cç][oõ]es|informa[cç][oõ]es)|"
                    r"ainda\s+n[aã]o\s+foi\s+divulgad|"
                    r"informa[cç][oõ]es\s+(?:devem|ser[aã]o)\s+(?:ser\s+)?adicionad|"
                    r"escala[cç][aã]o\s*,?\s*desfalques?\s+e\s+mais\s+do\s+jogo)\b",
                    value,
                ):
                    continue
                # Cabeçalhos de página e tags SEO não constituem fatos de elenco.
                if re.search(r"\b(?:onde assistir|hor[aá]rio|tudo sobre o jogo|pr[eé]-?jogo)\b", value, re.I) and re.search(
                    r"\b(?:escala[cç][aã]o|desfalques?|transmiss[aã]o)\b", value, re.I
                ) and not re.search(r"\b(?:ficar[aá]\s+fora|sofreu|fraturou|suspens[oa]|retornou|voltou|n[aã]o poder[aá]|recupera[cç][aã]o)\b", value, re.I):
                    continue
                # Teasers genéricos de "acompanhe ao vivo, escalações e desfalques"
                # não contêm notícia sobre um atleta: não entram como fatos.
                if re.search(
                    r"\b(?:acompanhe|acompanhamento|cobertura|ao vivo|tempo real)\b"
                    r".{0,110}\b(?:escalacoes|desfalques|onde assistir)\b",
                    folded,
                ) or "com informacoes sobre" in folded:
                    continue
                if not any(re.search(pattern, folded, flags=re.IGNORECASE) for pattern in TEAM_NEWS_PATTERNS):
                    continue
                # Em um mesmo parágrafo o atleta pode ser mencionado na frase
                # seguinte ("O Grêmio tem dúvidas. Wallace fraturou o nariz").
                # Só herdar contexto quando um único clube foi estabelecido.
                if active_side is None:
                    continue
                # Sem jogador/técnico identificado, não transformar chamada
                # genérica de "desfalques" em informação de elenco.
                people = re.findall(
                    r"(?<!\w)[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+){0,2}",
                    value,
                )
                team_tokens = {
                    token for _, team in teams if isinstance(team, str)
                    for token in normalize_text(team).split()
                }
                if not any(
                    normalize_text(name).split()[0] not in team_tokens
                    and name not in {"O", "A", "No", "Na", "Em", "Os", "As"}
                    for name in people
                ):
                    continue
                key = normalize_text(value)
                if key not in seen[active_side]:
                    seen[active_side].add(key)
                    collected[active_side].append((value, source, sentence))

    claims: list[dict[str, Any]] = []
    for side in ("home", "away"):
        for index, (value, source, sentence) in enumerate(collected[side][:max_per_team], start=1):
            claim = make_claim(f"{side}_team_news_{index}", value, source, sentence)
            if claim:
                claims.append(claim)
    return claims


def extract_lineups_requirement(
    requirement: dict[str, Any],
    *, match_context: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    lineup_labels = (
        r"provável escalação", r"provavel escalacao", r"probable lineup",
        r"predicted lineup", r"predicted xi",
    )
    coach_labels = (r"técnico", r"tecnico", r"coach", r"manager")
    claims = extract_team_labeled_claims(
        requirement,
        match_context=match_context,
        config=config,
        labels=lineup_labels,
        field_suffix="lineup",
        max_chars=320,
    )
    claims.extend(extract_team_labeled_claims(
        requirement,
        match_context=match_context,
        config=config,
        labels=coach_labels,
        field_suffix="coach",
        max_chars=100,
    ))
    claims.extend(extract_optional_team_news_claims(
        requirement,
        match_context=match_context,
        config=config,
    ))
    home = match_context.get("home", "Mandante")
    away = match_context.get("away", "Visitante")

    def build_lineup_facts(values: dict[str, str]) -> list[dict[str, str]]:
        facts = [
            {"field": "home_lineup", "text": f"Provável escalação do {home}: {values['home_lineup']}."},
            {"field": "home_coach", "text": f"Técnico do {home}: {values['home_coach']}."},
            {"field": "away_lineup", "text": f"Provável escalação do {away}: {values['away_lineup']}."},
            {"field": "away_coach", "text": f"Técnico do {away}: {values['away_coach']}."},
        ]
        for side, team in (("home", home), ("away", away)):
            for index in range(1, 4):
                field = f"{side}_team_news_{index}"
                if field in values:
                    facts.append({
                        "field": field,
                        "text": f"Informação de elenco do {team}: {values[field]}",
                    })
        return facts

    return finalize_claims(
        requirement,
        claims,
        required_fields=["home_lineup", "away_lineup", "home_coach", "away_coach"],
        fact_builder=build_lineup_facts,
        config=config,
    )



def extract_separate_team_news(
    requirements: list[dict[str, Any]], *,
    match_context: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """Preserva notícias de elenco mesmo sem projeções dos 11 atletas/técnicos.

    Nunca apresenta notícia de preparação como escalação provável. Só aceita
    frases efetivamente lidas em páginas checadas e com clube explicitamente
    mencionado na própria frase.
    """
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for requirement in requirements:
        if requirement.get("id") not in {
            "probable_lineups_and_coaches", "recent_form_both_teams",
        }:
            continue
        for source in eligible_sources(requirement):
            url = source.get("url")
            if not isinstance(url, str) or not url or url in seen:
                continue
            seen.add(url)
            sources.append(source)
    if not sources:
        return None

    provisional = {
        "id": "editorial_preparation_news",
        "required_for_drafting": False,
        "conditional": False,
        "allow_unavailable_after_check": False,
        "status": "pending",
        "facts": [],
        "sources": [],
        "source_candidates": sources,
    }
    claims = extract_optional_team_news_claims(
        provisional, match_context=match_context, config=config, max_per_team=2,
    )
    if not claims:
        return None
    teams = {
        "home": match_context.get("home"),
        "away": match_context.get("away"),
    }
    rows: list[dict[str, str]] = []
    for claim in claims:
        side = claim["field"].split("_", 1)[0]
        team = teams.get(side)
        if not isinstance(team, str) or not team:
            continue
        rows.append({
            "field": claim["field"],
            "text": f"Notícia verificada sobre o elenco do {team}: {claim['value']}",
        })
    if not rows:
        return None
    evidence = {
        "status": "verified",
        "facts": rows,
        "sources": unique_validator_sources(
            [claim["validator_source"] for claim in claims]
        ),
        "notes": None,
    }
    accepted, errors = factual_validator.validate_requirement_evidence(
        provisional, evidence, config=config,
    )
    if errors:
        return None
    accepted["fact_extraction_status"] = "verified_team_news_independent_of_lineups"
    accepted["structured_fact_count"] = len(rows)
    accepted["validator_accepted"] = True
    accepted["internal_provenance_only"] = True
    accepted["extracted_claims"] = [
        group for field_groups in group_claims(claims).values()
        for group in field_groups.values()
    ]
    return accepted


def extract_separate_competitive_context(
    requirements: list[dict[str, Any]], *,
    match_context: dict[str, Any], config: dict[str, Any],
) -> dict[str, Any] | None:
    """Coleta situações esportivas explícitas, jamais pressupõe posição na tabela."""
    sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for requirement in requirements:
        if requirement.get("id") not in {"probable_lineups_and_coaches", "recent_form_both_teams",
                                         "stakes_and_qualification_scenarios_when_applicable"}:
            continue
        for source in eligible_sources(requirement):
            url = source.get("url")
            if not isinstance(url, str) or url in seen_urls or not source_current_for_match(source, match_context):
                continue
            seen_urls.add(url)
            sources.append(source)

    by_side: dict[str, list[dict[str, Any]]] = {"home": [], "away": []}
    stakes_pattern = re.compile(
        r"\b(?:lideranca|lider|rebaixamento|queda|zona de|classificacao|vaga|"
        r"semifinal|final|estreia|primeiro classico|primeira vitoria|tabela|"
        r"empato?\w*|derrot\w*|vitori\w*|trein\w*|prepar\w*)\b"
    )
    seen_competitive_facts: set[str] = set()
    for source in sources:
        corpus = source_corpus(source)
        if not context_mentions_match(corpus, match_context, config):
            continue
        # Histórico de árbitros ou de jogos antigos não é situação competitiva
        # atual dos clubes; não transformar um juiz em protagonista da pauta.
        headline = normalize_text(str(source.get("title") or ""))
        if re.search(r"\b(?:arbitro|arbitragem|juiz|referee|officiating)\b", headline):
            continue
        segments = (source.get("page_evidence") or {}).get("evidence_segments", [])
        if not isinstance(segments, list):
            continue
        if source.get("source_type") == "official":
            description = (source.get("page_evidence") or {}).get("metadata", {}).get("description")
            if isinstance(description, str) and description:
                segments = [*segments, description]
        for segment in segments:
            if not isinstance(segment, str):
                continue
            for sentence in re.split(r"(?<=[.!?])\s+", segment):
                value = clean_value(sentence, max_chars=300)
                folded = normalize_text(value)
                if len(folded.split()) < 10 or not stakes_pattern.search(folded):
                    continue
                # Não promover cronograma, credenciamento ou arquibancadas a
                # contexto esportivo de equipe (falha real de 15/10/2026).
                if not editorial_quality.meaningful_sporting_context(value):
                    continue
                if any(
                    folded in previous or previous in folded
                    for previous in seen_competitive_facts
                ):
                    continue
                # Estatísticas retrospectivas e atuação do árbitro não comprovam
                # classificação, liderança ou pressão ATUAL sobre uma equipe.
                match_year = str(match_context.get("kickoff_brasilia") or "")[:4]
                years = set(re.findall(r"\b20\d{2}\b", folded))
                if (match_year and any(y != match_year for y in years)) or re.search(
                    r"\b(?:arbitro|arbitragem|apitou|apitar|apita|juiz|referee)\b", folded
                ):
                    continue
                if "tres pontos" in folded and not any(
                    signal in folded for signal in ("tabela", "lider", "vaga", "queda", "rebaix")
                ):
                    continue
                mentions = []
                for side in ("home", "away"):
                    team = match_context.get(side)
                    if not isinstance(team, str):
                        continue
                    markers = relaxed_team_markers(team, config)
                    places: list[int] = []
                    for marker in markers:
                        if len(marker) <= 3:
                            continue
                        for hit in re.finditer(r"(?<!\w)" + re.escape(marker) + r"(?!\w)", folded):
                            before = folded[max(0, hit.start() - 30):hit.start()]
                            # "contra o Fluminense" só informa o ADVERSÁRIO;
                            # não descreve a situação do Fluminense.
                            if re.search(
                                r"(?:contra|diante de|enfrenta|recebe|versus|vs)\s+"
                                r"(?:(?:o|a|os|as)\s+)?$",
                                before,
                            ):
                                continue
                            places.append(hit.start())
                    if places:
                        mentions.append((min(places), side))
                if not mentions:
                    continue
                mentions.sort()
                if len(mentions)>1 and mentions[0][0] == mentions[1][0]:
                    continue
                side = mentions[0][1]
                if len(by_side[side]) >= 2:
                    continue
                claim=make_claim(f"{side}_stakes_{len(by_side[side])+1}",value,source,sentence)
                if claim is not None:
                    by_side[side].append(claim)
                    seen_competitive_facts.add(folded)
    claims=[*by_side["home"],*by_side["away"]]
    if not claims:
        return None
    provisional={
        "id":"editorial_match_stakes","status":"pending","facts":[],
        "sources":[],"source_candidates":sources,
        "required_for_drafting":False,"conditional":False,
        "allow_unavailable_after_check":False,
    }
    teams={"home":match_context.get("home"),"away":match_context.get("away")}
    rows=[
        {"field":claim["field"],
         "text":f"Situação competitiva verificada do {teams[claim['field'].split('_',1)[0]]}: {claim['value']}"}
        for claim in claims
    ]
    evidence={
        "status":"verified","facts":rows,
        "sources":unique_validator_sources([c["validator_source"] for c in claims]),
        "notes":None,
    }
    accepted,errors=factual_validator.validate_requirement_evidence(provisional,evidence,config=config)
    if errors:
        return None
    accepted["fact_extraction_status"]="verified_sporting_context"
    accepted["structured_fact_count"]=len(rows)
    accepted["validator_accepted"]=True
    accepted["internal_provenance_only"]=True
    accepted["extracted_claims"]=[
        group for field_groups in group_claims(claims).values()
        for group in field_groups.values()
    ]
    return accepted


def natural_recent_form_value(
    corpus: str,
    team: str,
    *,
    config: dict[str, Any],
) -> tuple[str, str] | None:
    """Extrai uma frase de forma recente sem transformar números nem resultados."""
    sentences = [
        clean_value(item, max_chars=340)
        for item in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", corpus))
        if item.strip()
    ]
    # Forma recente precisa falar de uma sequência de JOGOS da própria equipe.
    # "último confronto" ou "encontro mais recente" pertence ao H2H e não pode
    # alimentar este requisito.
    form_markers = (
        "ultimos cinco jogos", "ultimos 5 jogos", "ultimos jogos",
        "seus ultimos", "recent form", "last five games", "last 5 games",
        "last five matches", "last 5 matches", "recent matches",
        "letzten funf spiele", "letzten 5 spiele", "zuletzt in der bundesliga",
    )
    result_markers = (
        "venceu", "vitoria", "vitorias", "empate", "empates", "derrota", "derrotas",
        "ganhou", "perdeu", "won", "wins", "victory", "draw", "draws", "lost",
        "loss", "defeat", "unbeaten", "sieg", "siege", "gewann", "unentschieden",
        "niederlage",
    )
    for sentence in sentences:
        if not relaxed_mentions_team(sentence, team, config):
            continue
        folded = f" {normalize_text(sentence)} "
        has_form_window = any(marker in folded for marker in form_markers)
        # Alternativa conservadora: "últimos/last/letzten" + palavra que
        # significa jogos/partidas, nunca confronto/encontro direto.
        if not has_form_window:
            has_form_window = (
                any(marker in folded for marker in (" ultimos ", " last ", " letzten "))
                and any(marker in folded for marker in (" jogos ", " partidas ", " games ", " matches ", " spiele "))
            )
        has_result = any(marker in folded for marker in result_markers)
        if has_form_window and has_result:
            return sentence, sentence
    return None


def source_supports_bilateral_recent_form(
    source: dict[str, Any],
    *,
    match_context: dict[str, Any],
    config: dict[str, Any],
) -> bool:
    corpus = source_corpus(source)
    if not corpus or not context_mentions_match(corpus, match_context, config):
        return False
    if not competition_is_mentioned(corpus, match_context):
        return False
    home = match_context.get("home")
    away = match_context.get("away")
    return (
        isinstance(home, str)
        and isinstance(away, str)
        and natural_recent_form_value(corpus, home, config=config) is not None
        and natural_recent_form_value(corpus, away, config=config) is not None
    )


def augment_requirements_with_final_cross_evidence(
    requirements: list[dict[str, Any]],
    *,
    match_context: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """34.11: reaproveita página já checada somente quando ela sustenta os dois lados."""
    pool: list[dict[str, Any]] = []
    seen_pool: set[str] = set()
    for requirement in requirements:
        for source in eligible_sources(requirement):
            url = source.get("url")
            if isinstance(url, str) and url and url not in seen_pool:
                seen_pool.add(url)
                pool.append(source)

    updated: list[dict[str, Any]] = []
    for requirement in requirements:
        result = deepcopy(requirement)
        if result.get("id") != "recent_form_both_teams":
            updated.append(result)
            continue
        current = [
            deepcopy(item)
            for item in result.get("source_candidates", [])
            if isinstance(item, dict)
        ]
        current_urls = {
            str(item.get("url"))
            for item in current
            if isinstance(item.get("url"), str)
        }
        reused = 0
        for source in pool:
            url = source.get("url")
            if not isinstance(url, str) or not url or url in current_urls:
                continue
            if not source_supports_bilateral_recent_form(
                source,
                match_context=match_context,
                config=config,
            ):
                continue
            copied = deepcopy(source)
            copied["passo34_11_cross_requirement_reuse"] = True
            copied["reused_for_requirement_id"] = "recent_form_both_teams"
            current.insert(0, copied)
            current_urls.add(url)
            reused += 1
        result["source_candidates"] = current
        result["passo34_11_reused_source_count"] = reused
        updated.append(result)
    return updated


def natural_count_token(value: str) -> int | None:
    token = normalize_text(value)
    if re.fullmatch(r"\d{1,3}", token):
        return int(token)
    return NATURAL_COUNT_WORDS.get(token)


def natural_h2h_counts(
    segment: str,
    *,
    home: str,
    away: str,
    config: dict[str, Any],
) -> dict[str, int] | None:
    """Lê frases como 'últimos cinco... Bayern venceu três... um empate...'."""
    folded = normalize_text(segment)
    h2h_markers = (
        "confrontos diretos", "retrospecto", "head to head", "previous meetings",
        "meetings", "duelle", "bilanz",
    )
    if not any(marker in folded for marker in h2h_markers):
        return None
    if not relaxed_mentions_team(segment, home, config) or not relaxed_mentions_team(segment, away, config):
        return None

    total_match = re.search(
        rf"(?:ultimos|ultimo|last|letzten?)\s+({NATURAL_COUNT_TOKEN_RE})\s+"
        rf"(?:confrontos|encontros|jogos|partidas|meetings|matches|duelle|spiele)",
        folded,
    )
    if not total_match:
        return None
    games = natural_count_token(total_match.group(1))
    if games is None:
        return None

    def team_win_count(team: str) -> int | None:
        markers = relaxed_team_markers(team, config)
        for marker in markers:
            patterns = (
                rf"(?:^|\s){re.escape(marker)}\s+(?:venceu|ganhou|won|gewann)\s+({NATURAL_COUNT_TOKEN_RE})(?:\s|$)",
                rf"({NATURAL_COUNT_TOKEN_RE})\s+(?:vitoria|vitorias|wins|siege)\s+(?:do|da|de|for)?\s*{re.escape(marker)}(?:\s|$)",
            )
            for pattern in patterns:
                match = re.search(pattern, folded)
                if match:
                    return natural_count_token(match.group(1))
        return None

    home_wins = team_win_count(home)
    away_wins = team_win_count(away)

    draw_match = re.search(
        rf"(?:^|\s)({NATURAL_COUNT_TOKEN_RE})\s+(?:empate|empates|draw|draws|unentschieden|remis)(?:\s|$)",
        folded,
    )
    draws = natural_count_token(draw_match.group(1)) if draw_match else None

    if None in (home_wins, away_wins, draws):
        return None
    values = {
        "h2h_games": int(games),
        "h2h_home_wins": int(home_wins),
        "h2h_away_wins": int(away_wins),
        "h2h_draws": int(draws),
    }
    if values["h2h_games"] != (
        values["h2h_home_wins"] + values["h2h_away_wins"] + values["h2h_draws"]
    ):
        return None
    return values


def extract_recent_form_requirement(
    requirement: dict[str, Any],
    *, match_context: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    labels = (
        r"forma recente", r"últimos cinco jogos", r"ultimos cinco jogos",
        r"últimos 5 jogos", r"ultimos 5 jogos", r"recent form", r"last five",
    )
    claims = extract_team_labeled_claims(
        requirement,
        match_context=match_context,
        config=config,
        labels=labels,
        field_suffix="recent_form",
        max_chars=240,
    )
    home = match_context.get("home", "Mandante")
    away = match_context.get("away", "Visitante")

    # 34.11: formato jornalístico natural, sem exigir rótulo "forma recente:".
    for source in eligible_sources(requirement):
        corpus = source_corpus(source)
        if not context_mentions_match(corpus, match_context, config):
            continue
        if not competition_is_mentioned(corpus, match_context):
            continue
        for side, team in (("home", home), ("away", away)):
            if not isinstance(team, str):
                continue
            natural = natural_recent_form_value(corpus, team, config=config)
            if natural is None:
                continue
            value, support = natural
            claim = make_claim(f"{side}_recent_form", value, source, support)
            if claim:
                claims.append(claim)
    return finalize_claims(
        requirement,
        claims,
        required_fields=["home_recent_form", "away_recent_form"],
        fact_builder=lambda v: [
            {"field": "home_recent_form", "text": f"Forma recente do {home}: {v['home_recent_form']}."},
            {"field": "away_recent_form", "text": f"Forma recente do {away}: {v['away_recent_form']}."},
        ],
        config=config,
    )


def extract_int_after_labels(segment: str, labels: list[str]) -> int | None:
    for label in labels:
        match = re.search(rf"{label}\s*[:\-–—]\s*(\d{{1,4}})\b", segment, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def extract_h2h_requirement(
    requirement: dict[str, Any],
    *, match_context: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    home = match_context.get("home")
    away = match_context.get("away")
    if not isinstance(home, str) or not isinstance(away, str):
        result = base_pending_result(requirement, [])
        result["fact_extraction_status"] = "missing_match_context"
        return result

    home_alias_pattern = "(?:" + "|".join(re.escape(alias) for alias in aliases_for_team(home, config)) + ")"
    away_alias_pattern = "(?:" + "|".join(re.escape(alias) for alias in aliases_for_team(away, config)) + ")"

    claims: list[dict[str, Any]] = []
    for source in eligible_sources(requirement):
        corpus = source_corpus(source)
        if not context_mentions_match(corpus, match_context, config):
            continue
        if not competition_is_mentioned(corpus, match_context):
            continue
        for segment in corpus.splitlines():
            natural_counts = natural_h2h_counts(
                segment,
                home=home,
                away=away,
                config=config,
            )
            if natural_counts is not None:
                for natural_field, natural_value in natural_counts.items():
                    claim = make_claim(natural_field, str(natural_value), source, segment)
                    if claim:
                        claims.append(claim)

            fields: list[tuple[str, int | None]] = [
                ("h2h_games", extract_int_after_labels(segment, [r"jogos", r"partidas", r"games", r"matches"])),
                ("h2h_home_wins", extract_int_after_labels(segment, [
                    rf"vitórias\s+(?:do\s+|da\s+)?{home_alias_pattern}",
                    rf"{home_alias_pattern}\s+vitórias",
                    rf"{home_alias_pattern}\s+wins",
                ])),
                ("h2h_away_wins", extract_int_after_labels(segment, [
                    rf"vitórias\s+(?:do\s+|da\s+)?{away_alias_pattern}",
                    rf"{away_alias_pattern}\s+vitórias",
                    rf"{away_alias_pattern}\s+wins",
                ])),
                ("h2h_draws", extract_int_after_labels(segment, [r"empates", r"draws"])),
            ]
            for field, value in fields:
                if value is not None:
                    claim = make_claim(field, str(value), source, segment)
                    if claim:
                        claims.append(claim)

    def consistency(values: dict[str, str]) -> str | None:
        try:
            games = int(values["h2h_games"])
            total = (
                int(values["h2h_home_wins"])
                + int(values["h2h_away_wins"])
                + int(values["h2h_draws"])
            )
        except (KeyError, ValueError):
            return "h2h_numeric_fields_invalid"
        return None if games == total else "h2h_games_must_equal_wins_plus_draws"

    competition = match_context.get("competition", "competição")
    return finalize_claims(
        requirement,
        claims,
        required_fields=["h2h_games", "h2h_home_wins", "h2h_away_wins", "h2h_draws"],
        fact_builder=lambda v: [
            {"field": "h2h_games", "text": f"Confrontos pela {competition}: {v['h2h_games']} jogos."},
            {"field": "h2h_home_wins", "text": f"Vitórias do {home} pela {competition}: {v['h2h_home_wins']}."},
            {"field": "h2h_away_wins", "text": f"Vitórias do {away} pela {competition}: {v['h2h_away_wins']}."},
            {"field": "h2h_draws", "text": f"Empates pela {competition}: {v['h2h_draws']}."},
        ],
        config=config,
        consistency_check=consistency,
    )


def verified_knockout_first_leg_segment(
    segment: str, match_context: dict[str, Any], config: dict[str, Any],
    source: dict[str, Any] | None = None,
) -> str | None:
    """Extrai apenas a fase explicitamente descrita para o confronto atual.

    Não infere placar agregado, vantagem, regulamento nem classificação.
    O texto precisa ligar os DOIS clubes à competição e a 'jogo de ida'.
    """
    # Para um confronto com mando definido, notícia da ida (mando invertido)
    # não pode rotular a volta como "jogo de ida".
    if source is not None and not current_fixture_headline_in_order(source, match_context, config):
        return None
    folded = normalize_text(segment)
    if not context_mentions_match(segment, match_context, config):
        return None
    if "libertador" not in folded or match_context.get("competition_slug") != "libertadores":
        return None
    if re.search(r"\b20\d{2}\b", folded) and any(
        y != str(match_context.get("kickoff_brasilia") or "")[:4]
        for y in re.findall(r"\b20\d{2}\b", folded)
    ):
        return None
    patterns = (
        (r"\b(?:ida da semifinal|jogo de ida da semifinal|primeiro jogo da semifinal)\b", "semifinal"),
        (r"\b(?:ida das quartas|jogo de ida das quartas|primeiro jogo das quartas)\b", "quartas de final"),
        (r"\b(?:ida das oitavas|jogo de ida das oitavas|primeiro jogo das oitavas)\b", "oitavas de final"),
    )
    for pattern, phase in patterns:
        if re.search(pattern, folded):
            home = str(match_context.get("home") or "").strip()
            away = str(match_context.get("away") or "").strip()
            return f"{home} e {away} disputam o jogo de ida das {phase} da Libertadores" if phase != "semifinal" else (
                f"{home} e {away} disputam o jogo de ida da semifinal da Libertadores"
            )
    return None


def verified_knockout_second_leg_segment(
    segment: str, match_context: dict[str, Any], config: dict[str, Any],
    source: dict[str, Any],
) -> str | None:
    """Reconhece volta quando a fonte atual nomeia o confronto e a fase."""
    if match_context.get("competition_slug") != "libertadores":
        return None
    if not current_fixture_headline_in_order(source, match_context, config):
        return None
    if not context_mentions_match(segment, match_context, config):
        return None
    folded = normalize_text(segment)
    title = normalize_text(str(source.get("title") or ""))
    if "libertador" not in (folded + " " + title):
        return None
    if not re.search(r"\b(?:jogo|duelo|confronto|partida)\s+de\s+volta\b|\bvolta\s+da\s+semifinal\b", folded):
        return None
    if "semifinal" not in (folded + " " + title):
        return None
    home = str(match_context.get("home") or "").strip()
    away = str(match_context.get("away") or "").strip()
    return f"{home} e {away} disputam o jogo de volta da semifinal da Libertadores"


def include_checked_first_leg_sources(
    requirements: list[dict[str, Any]], *,
    match_context: dict[str, Any], config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Reusa trechos atuais CHECADOS de outro requisito sobre a fase do jogo.

    Evita uma segunda busca desnecessária quando a notícia já chegou no lote,
    sem usar títulos/snippets RSS como prova factual.
    """
    if match_context.get("competition_slug") != "libertadores":
        return requirements
    pool: list[dict[str, Any]] = []
    seen: set[str] = set()
    for req in requirements:
        for source in eligible_sources(req):
            url = str(source.get("url") or "")
            if not url or url in seen or not source_current_for_match(source, match_context):
                continue
            segments = (source.get("page_evidence") or {}).get("evidence_segments", [])
            if not isinstance(segments, list):
                continue
            if not any(
                (verified_knockout_second_leg_segment(seg, match_context, config, source)
                 or verified_knockout_first_leg_segment(seg, match_context, config, source))
                for seg in segments if isinstance(seg, str)
            ):
                continue
            seen.add(url)
            pool.append(source)

    updated = []
    for req in requirements:
        if req.get("id") != "stakes_and_qualification_scenarios_when_applicable":
            updated.append(req)
            continue
        new = deepcopy(req)
        existing = {
            str(s.get("url")) for s in new.get("source_candidates", [])
            if isinstance(s, dict)
        }
        new["source_candidates"] = [
            *[deepcopy(s) for s in pool if s.get("url") not in existing],
            *new.get("source_candidates", []),
        ]
        updated.append(new)
    return updated


def extract_stakes_requirement(
    requirement: dict[str, Any],
    *, match_context: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    labels = (
        r"cenário de classificação", r"cenario de classificacao",
        r"cenário", r"cenario", r"o que está em jogo", r"o que esta em jogo",
        r"qualification scenario", r"what is at stake",
    )
    claims: list[dict[str, Any]] = []
    for source in eligible_sources(requirement):
        if not source_current_for_match(source, match_context):
            continue
        corpus = source_corpus(source)
        if not context_mentions_match(corpus, match_context, config):
            continue
        segments = (source.get("page_evidence") or {}).get("evidence_segments", [])
        for segment in corpus.splitlines():
            value = labeled_value(segment, labels, max_chars=320)
            if value and re.search(
                r"\b(classific|vaga|semifinal|quartas|oitavas|final|advance|qualif|penalt|prorroga|aggregate)\w*",
                normalize_text(value),
            ):
                claim = make_claim("qualification_scenario", value, source, segment)
                if claim:
                    claims.append(claim)
        # A fase do mata-mata pode aparecer no próprio relato de serviço,
        # sem o subtítulo literal 'cenário de classificação'.
        if isinstance(segments, list):
            for segment in segments:
                if not isinstance(segment, str):
                    continue
                value = (verified_knockout_second_leg_segment(segment, match_context, config, source)
                         or verified_knockout_first_leg_segment(segment, match_context, config, source))
                if value:
                    claim = make_claim("qualification_scenario", value, source, segment)
                    if claim:
                        claims.append(claim)
                    break
    return finalize_claims(
        requirement,
        claims,
        required_fields=["qualification_scenario"],
        fact_builder=lambda v: [{
            "field": "qualification_scenario",
            "text": f"Cenário de classificação: {v['qualification_scenario']}.",
        }],
        config=config,
    )


def extract_requirement(
    requirement: dict[str, Any],
    *,
    match_context: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    requirement_id = requirement.get("id")
    handlers = {
        "stadium_and_location": extract_stadium_requirement,
        "transmission": extract_transmission_requirement,
        "probable_lineups_and_coaches": extract_lineups_requirement,
        "officiating": extract_officiating_requirement,
        "recent_form_both_teams": extract_recent_form_requirement,
        "competition_specific_head_to_head": extract_h2h_requirement,
        "stakes_and_qualification_scenarios_when_applicable": extract_stakes_requirement,
    }
    handler = handlers.get(requirement_id)
    if handler is not None:
        return handler(requirement, match_context=match_context, config=config)

    result = base_pending_result(requirement, [])
    result["fact_extraction_status"] = "extractor_not_yet_enabled_for_requirement"
    return result


def configured_home_stadium(article: dict[str, Any], config: dict[str, Any]) -> str | None:
    """Estádio fixo aprovado pelo editor apenas se o MANDANTE é monitorado.

    Não simula confirmação externa. Um override por ID pode corrigir jogo
    excepcional antes do preparo, sem alterar a sede habitual de outros jogos.
    """
    settings = config.get("fixed_home_stadium", {})
    if settings.get("policy") != "fixed_when_monitored_club_is_home_user_approved_2026_09_19":
        return None
    home = (article.get("match_context") or {}).get("home")
    if not isinstance(home, str) or not home.strip():
        return None
    key = normalize_text(home)
    canonical = None
    for club in config.get("monitored_clubs", []):
        variants = [club.get("name"), club.get("slug", "").replace("-", " "), *club.get("aliases", [])]
        if any(isinstance(alias, str) and normalize_text(alias) == key for alias in variants):
            canonical = club.get("name")
            break
    if canonical is None:
        return None

    stadiums = settings.get("stadiums", {})
    stadium = stadiums.get(canonical)
    if not isinstance(stadium, str) or not stadium.strip():
        fail(f"Estádio fixo ausente para o mandante monitorado {canonical}.")

    exceptions = settings.get("exceptions_by_fixture_id", {})
    if not isinstance(exceptions, dict):
        fail("exceptions_by_fixture_id deve ser um objeto JSON.")
    fixture_id = article.get("fixture_id")
    if isinstance(fixture_id, int) and not isinstance(fixture_id, bool):
        replacement = exceptions.get(str(fixture_id))
        if replacement is not None:
            if not isinstance(replacement, str) or not replacement.strip():
                fail(f"Exceção de estádio inválida no jogo {fixture_id}.")
            stadium = replacement
    return stadium.strip()


def apply_fixed_home_stadium(
    requirements: list[dict[str, Any]],
    *,
    article: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    stadium = configured_home_stadium(article, config)
    if stadium is None:
        return requirements
    updated: list[dict[str, Any]] = []
    changed = False
    for requirement in requirements:
        if requirement.get("id") != "stadium_and_location":
            updated.append(requirement)
            continue
        if changed:
            fail("Mais de um requisito de estádio no mesmo artigo.")
        row = deepcopy(requirement)
        row["status"] = "verified"
        row["facts"] = [{"field": "stadium", "text": f"A partida será disputada no {stadium}."}]
        row["sources"] = []  # Configuração do editor NÃO é fonte jornalística externa.
        row["notes"] = "Estádio fixado pela regra editorial do mandante; não confirmado para este jogo."
        row["fact_extraction_status"] = "editorial_fixed_home_stadium"
        row["editorial_stadium_override"] = True
        row["editorial_config_path"] = "config/pre-jogo.json#fixed_home_stadium"
        row["structured_fact_count"] = 1
        row["validator_accepted"] = True  # Aceito pela regra editorial explícita do proprietário.
        row["conflict_detected"] = False
        row["conflicts"] = []
        row["internal_provenance_only"] = True
        updated.append(row)
        changed = True
    if not changed:
        fail("Requisito stadium_and_location ausente para mandante monitorado.")
    return updated


# A contextualização factual do pré-jogo exige notícias específicas por clube,
# inclusive quando uma matéria não menciona seu próximo adversário.
EDITORIAL_TEAM_SIGNALS = (
    r"\b(?:trein(?:ou|a|am|amento)|prepar(?:a|ou|acao)|desfalqu\w*|"
    r"lesionad\w*|lesao|suspens\w*|retorn\w*|recuper\w*|poupad\w*|"
    r"titular\w*|tecnico|convocad\w*|lider\w*|classific\w*|"
    r"rebaixamento|semifinal|quartas|oitavas|tabela|pontos|"
    r"invict\w*|vitori\w*|derrot\w*|empat\w*|marcou|hat.trick|"
    r"venceu|perdeu|perde|ganhou|derrotou|won|lost|beat|"
    r"training|trained|prepar\w*|injur\w*|"
    r"standings|unbeaten|winless|defeat|"
    r"entrain\w*|allenam\w*|infortunat\w*|convocat\w*|"
    r"entren\w*|lesion\w*|bajas?|regres\w*|clasific\w*)\b"
)
EDITORIAL_SERVICE_NOISE = (
    "onde assistir", "transmissao", "streaming", "ao vivo",
    "palpite", "aposta", "odds", "prognostico", "escalação provável",
    "ainda nao foram divulgadas", "nao ha confirmacao",
    "historico do arbitro", "historico da arbitragem",
)


def extract_individual_team_context(
    requirements: list[dict[str, Any]], *,
    match_context: dict[str, Any], config: dict[str, Any],
) -> dict[str, Any] | None:
    """Reúne fatos jornalísticos de cada clube, sem exigir o rival na página.

    A fonte tem que estar lida, atual e explicitamente identificada com um
    lado do confronto. Não inferir preparação nem inventar desfalques.
    """
    claims: list[dict[str, Any]] = []
    seen_facts: set[str] = set()
    per_side: dict[str, int] = {"home": 0, "away": 0}
    for requirement in requirements:
        if requirement.get("id") != "editorial_context_both_teams":
            continue
        for source in eligible_sources(requirement):
            if os.environ.get("CDE_EDITORIAL_DIAG") == "1":
                debug_side = source.get("editorial_target_side")
                debug_team = match_context.get(debug_side) if debug_side in ("home", "away") else None
                print(
                    "EDITORIAL-CANDIDATA: "
                    + json.dumps({
                        "title": str(source.get("title") or "")[:130],
                        "side": debug_side,
                        "target_match": debug_team == source.get("editorial_target_team"),
                        "fresh": source_current_for_match(source, match_context),
                        "team_in_title": isinstance(debug_team, str)
                        and mentions_team(str(source.get("title") or ""), debug_team, config),
                        "segments": len((source.get("page_evidence") or {}).get("evidence_segments") or []),
                    }, ensure_ascii=False),
                    flush=True,
                )
            side = source.get("editorial_target_side")
            if side not in ("home", "away") or per_side[side] >= 3:
                continue
            team = match_context.get(side)
            if not isinstance(team, str) or team != source.get("editorial_target_team"):
                continue
            if not source_current_for_match(source, match_context):
                continue
            headline = str(source.get("title") or "")
            if not mentions_team(headline, team, config):
                continue
            title_fold = normalize_text(headline)
            if re.search(r"\b(?:arbitro|arbitragem|referee|juiz|betting|apostas)\b", title_fold):
                continue
            evidence = (source.get("page_evidence") or {}).get("evidence_segments", [])
            if not isinstance(evidence, list):
                continue
            # No máximo dois fatos por fonte, mas precisam ser acontecimentos
            # realmente diferentes, não a mesma informação SEO em frases.
            count_this_source = 0
            for segment in evidence:
                if not isinstance(segment, str):
                    continue
                # O leitor adiciona a manchete antes do trecho checado.
                # A manchete identifica a reportagem, mas NÃO deve virar
                # fato de preparação nem obrigação para o redator. Isso
                # atribuiu ao Fluminense a titularidade de Saúl no Flamengo.
                clean_segment = segment.strip()
                if headline and clean_segment.casefold().startswith(headline.strip().casefold()):
                    clean_segment = clean_segment[len(headline.strip()):].lstrip(" .:;–—")
                if not clean_segment:
                    continue
                for sentence in re.split(r"(?<=[.!?])\s+", clean_segment):
                    value = clean_value(sentence, max_chars=390)
                    # Remover crédito editorial do início do parágrafo; a
                    # atribuição ao jornalista não é contexto esportivo.
                    value = re.sub(
                        r"^Por:\s*[^.]{0,100}?\s*/\s*Licenciado de [^.]{3,90}\s+",
                        "", value, flags=re.I,
                    )
                    folded = normalize_text(value)
                    if len(folded.split()) < 11:
                        continue
                    if not re.search(EDITORIAL_TEAM_SIGNALS, folded):
                        continue
                    # A manchete pode mencionar o clube só como adversário
                    # (ex.: "Mônaco ameaça PSG"); a frase precisa descrever
                    # explicitamente o clube-alvo. A única exceção é o
                    # relato em primeira pessoa de um site OFICIAL do clube.
                    direct_team = mentions_team(value, team, config)
                    # A manchete já identificou Fluminense, mas uma frase
                    # posterior pode chamá-lo apenas de "Flu". Reconhecer
                    # somente a abreviação com F maiúsculo dentro da própria
                    # reportagem vinculada ao clube. "flu" genérico em
                    # inglês ou notícias sem Fluminense no título não servem.
                    if (
                        not direct_team
                        and normalize_text(team) == "fluminense"
                        and mentions_team(headline, team, config)
                        and re.search(r"\bFlu\b", value)
                    ):
                        direct_team = True
                    official_voice = (
                        source.get("source_type") == "official"
                        and bool(re.search(
                            r"\b(?:nosso time|nossa equipe|nosso elenco|"
                            r"os titulares|a equipe treinou|o time treinou)\b",
                            folded,
                        ))
                    )
                    if not direct_team and not official_voice:
                        continue
                    if any(noise in folded for noise in EDITORIAL_SERVICE_NOISE):
                        continue
                    if re.search(r"\b(?:arbitro|arbitragem|apitou|apita|juiz|referee)\b", folded):
                        continue
                    # A notícia de 2026 pode relembrar 2025; não transformar
                    # essa lembrança em preparação ou classificação atual.
                    years = set(re.findall(r"\b20\d{2}\b", folded))
                    target = str(match_context.get("kickoff_brasilia") or "")[:4]
                    if years and any(year != target for year in years):
                        continue
                    if folded in seen_facts:
                        continue
                    # Não aceitar dados de serviço como notícia esportiva.
                    if re.search(r"\b(?:horario|estadio|transmissao|referee|onde assistir)\b", folded) and not re.search(
                        r"\b(?:trein|prepar|desfal|lesion|classific|lider|tabela|vitori|derrota|empate)\w*", folded
                    ):
                        continue
                    index = per_side[side] + 1
                    claim = make_claim(
                        f"{side}_stakes_individual_{index}", value, source, sentence,
                    )
                    if claim:
                        seen_facts.add(folded)
                        claims.append(claim)
                        per_side[side] += 1
                        count_this_source += 1
                    if count_this_source >= 2 or per_side[side] >= 3:
                        break
                if count_this_source >= 2 or per_side[side] >= 3:
                    break
    if os.environ.get("CDE_EDITORIAL_DIAG") == "1":
        print("EDITORIAL-EXTRAÇÃO: "
              + json.dumps({"home": per_side["home"], "away": per_side["away"],
                            "fields": [claim["field"] for claim in claims]},
                           ensure_ascii=False), flush=True)
    if not claims:
        return None
    result_rows = []
    for claim in claims:
        side = claim["field"].split("_", 1)[0]
        result_rows.append({
            "field": claim["field"],
            "text": f"Contexto esportivo atual verificado do {match_context[side]}: {claim['value']}",
        })
    provisional = {
        "id": "editorial_individual_team_context",
        "status": "pending", "required_for_drafting": False,
        "conditional": False, "allow_unavailable_after_check": False,
        "facts": [], "sources": [],
    }
    evidence = {
        "status": "verified", "facts": result_rows,
        "sources": unique_validator_sources([x["validator_source"] for x in claims]),
        "notes": None,
    }
    accepted, errors = factual_validator.validate_requirement_evidence(
        provisional, evidence, config=config,
    )
    if errors:
        if os.environ.get("CDE_EDITORIAL_DIAG") == "1":
            print("EDITORIAL-VALIDAÇÃO: " + json.dumps(errors, ensure_ascii=False), flush=True)
        return None
    accepted["fact_extraction_status"] = "verified_individual_team_context"
    accepted["structured_fact_count"] = len(result_rows)
    accepted["validator_accepted"] = True
    accepted["internal_provenance_only"] = True
    accepted["extracted_claims"] = [
        group for field_groups in group_claims(claims).values()
        for group in field_groups.values()
    ]
    return accepted


def extract_article(article: dict[str, Any], *, config: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(article)
    match_context = article.get("match_context")
    if not isinstance(match_context, dict):
        match_context = {}
    requirements = article.get("requirements")
    if not isinstance(requirements, list):
        requirements = []
    requirements = augment_requirements_with_final_cross_evidence(
        [item for item in requirements if isinstance(item, dict)],
        match_context=match_context,
        config=config,
    )

    requirements = include_checked_first_leg_sources(
        requirements, match_context=match_context, config=config,
    )
    requirements = include_current_referee_sources(
        requirements, match_context=match_context, config=config,
    )
    extracted = [
        extract_requirement(item, match_context=match_context, config=config)
        for item in requirements if isinstance(item, dict)
    ]
    competition_slug = str(match_context.get("competition_slug", ""))
    competition_stage = match_context.get("competition_stage")
    competition_matchday = match_context.get("competition_matchday")
    extracted = [
        resolve_allowed_gap(
            item, competition_slug=competition_slug, config=config,
            competition_stage=competition_stage,
            competition_matchday=competition_matchday,
        )
        for item in extracted
    ]
    independent_news = extract_separate_team_news(
        requirements, match_context=match_context, config=config,
    )
    if independent_news is not None:
        extracted.append(independent_news)
    competitive_news = extract_separate_competitive_context(
        requirements, match_context=match_context, config=config,
    )
    if competitive_news is not None:
        extracted.append(competitive_news)
    individual_context = extract_individual_team_context(
        requirements, match_context=match_context, config=config,
    )
    if individual_context is not None:
        extracted.append(individual_context)
    # Decisão editorial: o estádio do MANDANTE monitorado é fixo e prevalece
    # sobre lacunas ou estádio diferente encontrado em páginas de pré-jogo.
    # Visitantes monitorados em casa de outro clube continuam na pesquisa normal.
    extracted = apply_fixed_home_stadium(extracted, article=article, config=config)

    structured_fact_count = sum(int(item.get("structured_fact_count", 0)) for item in extracted)
    conflicts = [item.get("id") for item in extracted if item.get("conflict_detected") is True]
    validator_accepted = [item.get("id") for item in extracted if item.get("validator_accepted") is True]

    result["requirements"] = extracted
    result["research_status"] = "structured_fact_extraction_completed"
    result["enabled_fact_extractors"] = sorted(ENABLED_EXTRACTORS)
    result["structured_fact_count"] = structured_fact_count
    result["conflict_requirement_ids"] = [item for item in conflicts if isinstance(item, str)]
    result["validator_accepted_requirement_ids"] = [
        item for item in validator_accepted if isinstance(item, str)
    ]
    result["automatic_gap_resolution_applied"] = True
    result["ready_for_factual_validation"] = False
    result["ready_for_drafting"] = False
    result["ready_for_html"] = False
    result["publication_unlocked"] = False
    result["internal_provenance_only"] = True
    result["source_attribution_in_article_body"] = "forbidden"
    result["next_required_step"] = "resolve_remaining_requirements_and_prepare_drafting_input"
    return result


def load_checked_manifest(path: Path, target_date: date) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, dict):
        fail("O manifesto de páginas checadas deve ser um objeto JSON.")
    if data.get("target_date") != target_date.isoformat():
        fail("A data do manifesto de páginas checadas não coincide com a data-alvo.")
    articles = data.get("articles")
    if not isinstance(articles, list):
        fail('O manifesto deve conter um array "articles".')
    return [item for item in articles if isinstance(item, dict)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extrai fatos estruturados de páginas checadas com trava de conflito, sem publicar."
    )
    parser.add_argument("--date", help="Data-alvo YYYY-MM-DD. Vazio = amanhã em Brasília.")
    parser.add_argument("--checked", type=Path, help="Manifesto paginas-checadas-AAAA-MM-DD.json.")
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help="Diretório de saída. Padrão: build/pre-jogo/.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Permite substituir somente arquivos de fatos estruturados dentro de build/.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    tz = ZoneInfo(config["timezone"])
    target_date = parse_target_date(args.date, tz)
    checked_path = args.checked or DEFAULT_OUTPUT_DIR / f"paginas-checadas-{target_date.isoformat()}.json"
    articles = load_checked_manifest(checked_path, target_date)
    extracted_articles = [extract_article(article, config=config) for article in articles]

    output_dir = args.output_dir.resolve()
    articles_dir = output_dir / f"fatos-estruturados-{target_date.isoformat()}"
    manifest_path = output_dir / f"fatos-estruturados-{target_date.isoformat()}.json"
    destinations = [
        articles_dir / Path(item["slug"]).with_suffix(".json").name
        for item in extracted_articles
    ]
    destinations.append(manifest_path)

    existing = [path for path in destinations if path.exists()]
    if existing and not args.force:
        fail("Fatos estruturados já existem. Use --force somente para substituir arquivos de build/.")

    articles_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for article, destination in zip(extracted_articles, destinations[:-1]):
        destination.write_text(
            json.dumps(article, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(
            str(destination.relative_to(ROOT)) if destination.is_relative_to(ROOT) else str(destination)
        )

    manifest = {
        "generated_at": datetime.now(tz).isoformat(),
        "target_date": target_date.isoformat(),
        "timezone": config["timezone"],
        "source_checked_manifest": str(checked_path),
        "article_count": len(extracted_articles),
        "enabled_fact_extractors": sorted(ENABLED_EXTRACTORS),
        "structured_fact_count": sum(item["structured_fact_count"] for item in extracted_articles),
        "conflict_article_count": sum(bool(item["conflict_requirement_ids"]) for item in extracted_articles),
        "validator_accepted_requirement_count": sum(
            len(item["validator_accepted_requirement_ids"]) for item in extracted_articles
        ),
        "ready_for_drafting_count": 0,
        "ready_for_html_count": 0,
        "publication_unlocked": False,
        "source_attribution_in_article_body": "forbidden",
        "files": written,
        "articles": extracted_articles,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"OK: extração estruturada concluída para {target_date.isoformat()}.")
    print("Extratores habilitados: " + ", ".join(sorted(ENABLED_EXTRACTORS)))
    print(f"Fatos estruturados aceitos pelo validador: {manifest['structured_fact_count']}")
    print(f"Matérias com conflito detectado: {manifest['conflict_article_count']}")
    print("As fontes permanecem como proveniência interna e não podem aparecer como atribuição no texto.")
    print("Redação, HTML e publicação permanecem bloqueados.")


if __name__ == "__main__":
    main()
