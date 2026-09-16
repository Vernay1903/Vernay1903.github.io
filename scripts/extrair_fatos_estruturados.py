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
import re
import sys
import unicodedata
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, NoReturn
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import validar_pesquisa_factual as factual_validator  # noqa: E402

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

KNOWN_VENUES = [
    "Emirates Stadium",
    "Etihad Stadium",
    "Parc des Princes",
    "Allianz Arena",
    "San Siro",
    "Stadio Giuseppe Meazza",
    "Giuseppe Meazza",
    "Maracanã",
    "Maracana",
    "Allianz Parque",
    "Arena do Grêmio",
    "Arena do Gremio",
    "Camp Nou",
    "Spotify Camp Nou",
    "Estadi Olímpic Lluís Companys",
    "Estadi Olimpic Lluis Companys",
    "Santiago Bernabéu",
    "Santiago Bernabeu",
]

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


def aliases_for_team(team: str, config: dict[str, Any]) -> list[str]:
    key = normalize_text(team)
    for club in config.get("monitored_clubs", []):
        if not isinstance(club, dict):
            continue
        candidates = [club.get("name"), club.get("slug"), *club.get("aliases", [])]
        normalized = [normalize_text(str(item).replace("-", " ")) for item in candidates if item]
        if key in normalized:
            return [str(item) for item in candidates if isinstance(item, str) and item.strip()]
    return [team]


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
    for field in required_fields:
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
                key = normalize_text(venue)
                if key not in seen:
                    seen.add(key)
                    found.append((venue, segment))
        patterns = [
            r"(?:venue\s*[:\-]?\s*|played at\s+|will be played at\s+|takes place at\s+|held at\s+)(?:the\s+)?([A-ZÀ-Ý][\wÀ-ÿ'’.-]*(?:\s+(?:[A-ZÀ-Ý][\wÀ-ÿ'’.-]*|do|da|de|dos|das)){0,5}\s+(?:Stadium|Arena|Park|Ground))",
            r"(?:estádio|estadio|local)\s*[:\-]?\s*([A-ZÀ-Ý][\wÀ-ÿ'’.-]*(?:\s+(?:[A-ZÀ-Ý][\wÀ-ÿ'’.-]*|do|da|de|dos|das)){0,5}(?:\s+(?:Stadium|Arena|Park|Ground))?)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, segment, flags=re.IGNORECASE):
                value = clean_value(match.group(1), max_chars=120)
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
        corpus = source_corpus(source)
        if not context_mentions_match(corpus, match_context, config):
            continue
        for segment in corpus.splitlines():
            value = labeled_value(segment, labels, max_chars=180)
            if value and not re.search(
                r"\b(?:nao anunciado|a definir|to be announced|tba)\b",
                normalize_text(value),
            ):
                claim = make_claim("transmission", value, source, segment)
                if claim:
                    claims.append(claim)
    return finalize_claims(
        requirement,
        claims,
        required_fields=["transmission"],
        fact_builder=lambda v: [{"field": "transmission", "text": f"Transmissão: {v['transmission']}."}],
        config=config,
    )


def extract_officiating_requirement(
    requirement: dict[str, Any],
    *, match_context: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    claims: list[dict[str, Any]] = []
    patterns = [
        r"(?:árbitro|arbitro|referee)\s*[:\-–—]\s*([A-ZÀ-Ý][A-Za-zÀ-ÿ'’.-]+(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ'’.-]+){1,5})",
        r"(?:match referee)\s*[:\-–—]\s*([A-ZÀ-Ý][A-Za-zÀ-ÿ'’.-]+(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ'’.-]+){1,5})",
    ]
    for source in eligible_sources(requirement):
        corpus = source_corpus(source)
        if not context_mentions_match(corpus, match_context, config):
            continue
        for segment in corpus.splitlines():
            if re.search(r"\b(?:var|video assistant)\b", normalize_text(segment)):
                continue
            for pattern in patterns:
                match = re.search(pattern, segment, flags=re.IGNORECASE)
                if match:
                    claim = make_claim("referee", match.group(1), source, segment)
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
        corpus = source_corpus(source)
        for segment in corpus.splitlines():
            for side, team in teams:
                if not isinstance(team, str) or not mentions_team(segment, team, config):
                    continue
                value = labeled_value(segment, labels, max_chars=max_chars)
                if not value:
                    for label in labels:
                        match = re.search(
                            rf"{re.escape(team)}.*?{label}\s*[:\-–—]\s*(.+)$",
                            segment,
                            flags=re.IGNORECASE,
                        )
                        if match:
                            value = clean_value(match.group(1), max_chars=max_chars)
                            break
                if value:
                    claim = make_claim(f"{side}_{field_suffix}", value, source, segment)
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
    home = match_context.get("home", "Mandante")
    away = match_context.get("away", "Visitante")
    return finalize_claims(
        requirement,
        claims,
        required_fields=["home_lineup", "away_lineup", "home_coach", "away_coach"],
        fact_builder=lambda v: [
            {"field": "home_lineup", "text": f"Provável escalação do {home}: {v['home_lineup']}."},
            {"field": "home_coach", "text": f"Técnico do {home}: {v['home_coach']}."},
            {"field": "away_lineup", "text": f"Provável escalação do {away}: {v['away_lineup']}."},
            {"field": "away_coach", "text": f"Técnico do {away}: {v['away_coach']}."},
        ],
        config=config,
    )


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

    claims: list[dict[str, Any]] = []
    for source in eligible_sources(requirement):
        corpus = source_corpus(source)
        if not context_mentions_match(corpus, match_context, config):
            continue
        if not competition_is_mentioned(corpus, match_context):
            continue
        for segment in corpus.splitlines():
            fields: list[tuple[str, int | None]] = [
                ("h2h_games", extract_int_after_labels(segment, [r"jogos", r"partidas", r"games", r"matches"])),
                ("h2h_home_wins", extract_int_after_labels(segment, [
                    rf"vitórias\s+(?:do\s+|da\s+)?{re.escape(home)}",
                    rf"{re.escape(home)}\s+vitórias",
                    rf"{re.escape(home)}\s+wins",
                ])),
                ("h2h_away_wins", extract_int_after_labels(segment, [
                    rf"vitórias\s+(?:do\s+|da\s+)?{re.escape(away)}",
                    rf"{re.escape(away)}\s+vitórias",
                    rf"{re.escape(away)}\s+wins",
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
        corpus = source_corpus(source)
        if not context_mentions_match(corpus, match_context, config):
            continue
        for segment in corpus.splitlines():
            value = labeled_value(segment, labels, max_chars=320)
            if value and re.search(
                r"\b(classific|vaga|semifinal|quartas|oitavas|final|advance|qualif|penalt|prorroga|aggregate)\w*",
                normalize_text(value),
            ):
                claim = make_claim("qualification_scenario", value, source, segment)
                if claim:
                    claims.append(claim)
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


def extract_article(article: dict[str, Any], *, config: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(article)
    match_context = article.get("match_context")
    if not isinstance(match_context, dict):
        match_context = {}
    requirements = article.get("requirements")
    if not isinstance(requirements, list):
        requirements = []

    extracted = [
        extract_requirement(item, match_context=match_context, config=config)
        for item in requirements if isinstance(item, dict)
    ]
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
