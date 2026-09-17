#!/usr/bin/env python3
"""Fallback factual aterrado em evidências para o Passo 34.3.

O modelo recebe somente trechos de páginas já checadas pelo pipeline. Ele não recebe
URLs, não pesquisa, não usa ferramentas e não pode completar lacunas por memória.
Cada valor factual aceito precisa apontar para um único segmento fornecido e ser
extrativo: o valor normalizado deve existir literalmente no segmento de suporte.
Depois disso, o validador factual determinístico continua sendo obrigatório.

Este script nunca redige matéria, nunca gera HTML e nunca libera publicação.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import extrair_fatos_estruturados as deterministic  # noqa: E402
from scripts import validar_pesquisa_factual as factual_validator  # noqa: E402

CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
PROVIDER_CONFIG_PATH = ROOT / "config" / "extracao-factual-pre-jogo.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo"
RETRYABLE_HTTP = {408, 409, 429, 500, 502, 503, 504}
RESOLVED_STATUSES = {"verified", "verified_not_announced", "unavailable_after_check", "not_applicable"}

SUPPORTED_REQUIREMENTS: dict[str, list[str]] = {
    "stadium_and_location": ["stadium"],
    "transmission": ["transmission"],
    "probable_lineups_and_coaches": ["home_lineup", "home_coach", "away_lineup", "away_coach"],
    "officiating": ["referee"],
    "recent_form_both_teams": ["home_recent_form", "away_recent_form"],
    "competition_specific_head_to_head": ["h2h_games", "h2h_home_wins", "h2h_away_wins", "h2h_draws"],
    "stakes_and_qualification_scenarios_when_applicable": ["qualification_scenario"],
}
ALL_FIELDS = sorted({field for fields in SUPPORTED_REQUIREMENTS.values() for field in fields})


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


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def parse_target_date(raw: str | None, tz: ZoneInfo) -> date:
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            fail("--date deve usar o formato YYYY-MM-DD.")
    return datetime.now(tz).date() + timedelta(days=1)


def load_provider_config() -> dict[str, Any]:
    config = load_json(PROVIDER_CONFIG_PATH)
    if not isinstance(config, dict):
        fail("config/extracao-factual-pre-jogo.json deve conter um objeto JSON.")
    provider = config.get("provider")
    scope = config.get("scope")
    safety = config.get("safety")
    if not isinstance(provider, dict) or not isinstance(scope, dict) or not isinstance(safety, dict):
        fail("Configuração de extração factual incompleta.")

    required_provider = {
        "name": "openai-responses",
        "endpoint": "https://api.openai.com/v1/responses",
        "api_key_env": "OPENAI_API_KEY",
        "execute_requires_explicit_flag": True,
    }
    for key, expected in required_provider.items():
        if provider.get(key) != expected:
            fail(f"Configuração inválida em provider.{key}.")

    if scope.get("allow_web_search") is not False or scope.get("allow_tools") is not False:
        fail("O extrator factual não pode usar web search ou ferramentas.")
    if scope.get("input_mode") != "checked_page_evidence_only":
        fail("O extrator deve receber somente páginas previamente checadas.")

    required_false = [
        "publication_unlock_allowed",
        "drafting_allowed",
        "html_generation_allowed",
        "invent_missing_facts_allowed",
        "source_attribution_output_allowed",
        "external_urls_sent_to_model",
        "publisher_names_sent_to_model",
    ]
    for key in required_false:
        if safety.get(key) is not False:
            fail(f"Trava obrigatória inválida em safety.{key}.")
    if safety.get("support_segment_required") is not True or safety.get("extractive_value_required") is not True:
        fail("Grounding extrativo obrigatório ausente.")
    return config


def load_site_config() -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    if not isinstance(config, dict) or config.get("timezone") != "America/Sao_Paulo":
        fail("config/pre-jogo.json inválido.")
    validation = config.get("research", {}).get("validation")
    if not isinstance(validation, dict) or validation.get("publication_unlock_allowed") is not False:
        fail("A pesquisa factual não pode liberar publicação.")
    return config


def sanitize_segment(text: str, *, max_chars: int) -> str:
    text = re.sub(r"https?://\S+", "[URL_REMOVIDA]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars].strip()


def requirement_is_resolved(requirement: dict[str, Any]) -> bool:
    if requirement.get("conflict_detected") is True:
        return False
    status = requirement.get("status")
    if status not in RESOLVED_STATUSES:
        return False
    if status == "verified":
        return bool(requirement.get("facts"))
    if status == "unavailable_after_check":
        return requirement.get("allow_unavailable_after_check") is True
    if status == "not_applicable":
        return requirement.get("conditional") is True
    return True


def checked_articles(path: Path, target_date: date) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, dict) or data.get("target_date") != target_date.isoformat():
        fail("Manifesto de páginas checadas inválido ou com data divergente.")
    articles = data.get("articles")
    if not isinstance(articles, list):
        fail("Manifesto de páginas checadas sem articles.")
    return [item for item in articles if isinstance(item, dict)]


def facts_manifest(path: Path, target_date: date) -> dict[str, Any]:
    data = load_json(path)
    if not isinstance(data, dict) or data.get("target_date") != target_date.isoformat():
        fail("Manifesto de fatos inválido ou com data divergente.")
    if not isinstance(data.get("articles"), list):
        fail("Manifesto de fatos sem articles.")
    return data


def eligible_source(source: Any) -> bool:
    return (
        isinstance(source, dict)
        and source.get("content_checked") is True
        and source.get("eligible_for_factual_validation") is True
    )


def collect_segments(
    checked_requirement: dict[str, Any],
    requirement_id: str,
    *,
    scope: dict[str, Any],
) -> tuple[list[dict[str, str]], dict[str, dict[str, Any]]]:
    max_sources = int(scope.get("max_sources_per_requirement", 3))
    max_segments = int(scope.get("max_segments_per_requirement", 14))
    max_chars = int(scope.get("max_segment_chars", 650))
    segments: list[dict[str, str]] = []
    segment_map: dict[str, dict[str, Any]] = {}
    seen_text: set[str] = set()

    candidates = checked_requirement.get("source_candidates", [])
    if not isinstance(candidates, list):
        return segments, segment_map

    used_sources = 0
    for source_idx, source in enumerate(candidates):
        if not eligible_source(source):
            continue
        used_sources += 1
        if used_sources > max_sources:
            break

        raw_segments: list[tuple[str, str]] = []
        title = source.get("title")
        if isinstance(title, str) and title.strip():
            raw_segments.append(("title", title.strip()))
        page = source.get("page_evidence")
        if isinstance(page, dict):
            evidence_segments = page.get("evidence_segments")
            if isinstance(evidence_segments, list):
                raw_segments.extend(
                    ("page", item) for item in evidence_segments if isinstance(item, str) and item.strip()
                )

        for local_idx, (kind, raw) in enumerate(raw_segments):
            if len(segments) >= max_segments:
                break
            clean = sanitize_segment(raw, max_chars=max_chars)
            normalized = normalize_text(clean)
            if len(normalized) < 8 or normalized in seen_text:
                continue
            seen_text.add(normalized)
            seg_id = f"{requirement_id[:4]}-{source_idx}-{local_idx}-{len(segments)}"
            segments.append({
                "segment_id": seg_id,
                "requirement_id": requirement_id,
                "source_type": str(source.get("source_type", "unknown")),
                "text": clean,
            })
            segment_map[seg_id] = {
                "requirement_id": requirement_id,
                "source": source,
                "raw_text": raw,
                "model_text": clean,
                "kind": kind,
            }
    return segments, segment_map


def target_requirements(
    fact_article: dict[str, Any],
    checked_article: dict[str, Any],
    *,
    scope: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    checked_by_id = {
        item.get("id"): item
        for item in checked_article.get("requirements", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    targets: list[dict[str, Any]] = []
    global_map: dict[str, dict[str, Any]] = {}

    for requirement in fact_article.get("requirements", []):
        if not isinstance(requirement, dict):
            continue
        req_id = requirement.get("id")
        if req_id not in SUPPORTED_REQUIREMENTS:
            continue
        if requirement.get("required_for_drafting") is not True:
            continue
        if requirement_is_resolved(requirement):
            continue
        checked = checked_by_id.get(req_id)
        if not isinstance(checked, dict):
            continue
        segments, segment_map = collect_segments(checked, req_id, scope=scope)
        if not segments:
            continue
        global_map.update(segment_map)
        targets.append({
            "id": req_id,
            "required_fields": SUPPORTED_REQUIREMENTS[req_id],
            "segments": segments,
        })
    return targets, global_map


def output_schema(requirement_ids: list[str], segment_ids: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "requirements": {
                "type": "array",
                "minItems": len(requirement_ids),
                "maxItems": len(requirement_ids),
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": requirement_ids},
                        "status": {"type": "string", "enum": ["verified", "pending", "conflict"]},
                        "facts": {
                            "type": "array",
                            "maxItems": 8,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "field": {"type": "string", "enum": ALL_FIELDS},
                                    "value": {"type": "string", "minLength": 1, "maxLength": 600},
                                    "support_segment_id": {"type": "string", "enum": segment_ids},
                                },
                                "required": ["field", "value", "support_segment_id"],
                                "additionalProperties": False,
                            },
                        },
                        "conflict_note": {"type": "string", "maxLength": 500},
                    },
                    "required": ["id", "status", "facts", "conflict_note"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["requirements"],
        "additionalProperties": False,
    }


def system_instructions() -> str:
    return (
        "Você é um extrator factual estritamente aterrado para matérias de pré-jogo. "
        "Não redija notícia e não use conhecimento externo, memória, pesquisa ou ferramentas. "
        "Use SOMENTE os segmentos fornecidos. Para cada requisito, retorne verified apenas quando todos os campos obrigatórios daquele requisito estiverem explicitamente presentes nos segmentos. "
        "Cada fato verified deve apontar para exatamente um support_segment_id e o campo value deve ser COPIADO ou minimamente normalizado de um trecho contínuo desse segmento; não parafraseie o value. "
        "Se o suporte estiver incompleto, use pending. Se fontes fornecidas discordarem sobre o mesmo dado crítico, use conflict. "
        "Não faça inferências, não combine competições no retrospecto, não transforme escalação provável em oficial e não invente transmissão, árbitro, estádio, placar, forma, jogadores ou números. "
        "No retrospecto, aceite apenas números explicitamente ligados à competição indicada. "
        "Em recent_form_both_teams, é obrigatório haver suporte explícito para os dois times. "
        "Não inclua nomes de fontes, URLs, atribuições como 'segundo'/'conforme' ou comentários sobre o processo de pesquisa. "
        "Retorne somente o JSON exigido pelo schema."
    )


def user_payload(article: dict[str, Any], targets: list[dict[str, Any]]) -> str:
    context = article.get("match_context") if isinstance(article.get("match_context"), dict) else {}
    compact = {
        "match": {
            "home": context.get("home"),
            "away": context.get("away"),
            "competition": context.get("competition"),
            "competition_slug": context.get("competition_slug"),
            "date": article.get("date"),
            "kickoff_time_brasilia": context.get("kickoff_time_brasilia"),
        },
        "requirements": targets,
    }
    return (
        "Extraia somente valores factuais explicitamente sustentados pelos segmentos abaixo. "
        "Os required_fields de cada requisito precisam estar todos presentes para status verified.\n\n"
        + json.dumps(compact, ensure_ascii=False, indent=2)
    )


def build_request(
    article: dict[str, Any],
    targets: list[dict[str, Any]],
    provider_config: dict[str, Any],
    segment_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    provider = provider_config["provider"]
    requirement_ids = [item["id"] for item in targets]
    segment_ids = list(segment_map)
    return {
        "model": provider["model"],
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_instructions()}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_payload(article, targets)}]},
        ],
        "reasoning": {"effort": provider.get("reasoning_effort", "low")},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "grounded_fact_extraction",
                "schema": output_schema(requirement_ids, segment_ids),
                "strict": True,
            }
        },
        "max_output_tokens": int(provider.get("max_output_tokens", 6000)),
        "store": bool(provider.get("store", False)),
    }


def post_json(endpoint: str, api_key: str, payload: dict[str, Any], *, timeout: int) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Falha de rede: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Responses API devolveu JSON inválido.") from exc


def response_http_code(error: RuntimeError) -> int | None:
    match = re.match(r"HTTP\s+(\d+):", str(error))
    return int(match.group(1)) if match else None


def call_api(payload: dict[str, Any], provider_config: dict[str, Any], api_key: str) -> dict[str, Any]:
    provider = provider_config["provider"]
    attempts = int(provider.get("max_attempts", 3))
    timeout = int(provider.get("timeout_seconds", 120))
    last_error: RuntimeError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return post_json(provider["endpoint"], api_key, payload, timeout=timeout)
        except RuntimeError as exc:
            last_error = exc
            code = response_http_code(exc)
            if attempt >= attempts or (code is not None and code not in RETRYABLE_HTTP):
                break
            time.sleep(min(2 ** (attempt - 1), 8))
    fail(f"Falha no extrator factual OpenAI após {attempts} tentativa(s): {last_error}")


def extract_output_text(response: dict[str, Any]) -> str:
    texts: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
    if not texts:
        fail("Resposta do extrator não contém output_text utilizável.")
    return "\n".join(texts)


def parse_model_output(response: dict[str, Any]) -> dict[str, Any]:
    if response.get("error"):
        fail(f"Responses API retornou erro: {response.get('error')}")
    if response.get("status") not in {"completed", None}:
        fail(f"Extração não concluída: {response.get('status')!r}")
    try:
        data = json.loads(extract_output_text(response))
    except json.JSONDecodeError as exc:
        fail(f"Extrator devolveu JSON inválido: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("requirements"), list):
        fail("Saída factual do modelo inválida.")
    return data


def usage_summary(response: dict[str, Any]) -> dict[str, int]:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return {}
    result: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            result[key] = value
    return result


def source_for_segment(segment_info: dict[str, Any]) -> dict[str, Any]:
    source = segment_info["source"]
    return {
        "publisher": str(source.get("publisher", "")).strip(),
        "url": str(source.get("url", "")).strip(),
        "source_type": str(source.get("source_type", "")).strip(),
        "checked_at": str(source.get("checked_at", "")).strip(),
    }


def unique_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        url = source.get("url")
        if not isinstance(url, str) or not url or url in seen:
            continue
        seen.add(url)
        result.append(source)
    return result


def exact_grounded_value(value: str, support: str) -> bool:
    value_norm = normalize_text(value)
    support_norm = normalize_text(support)
    return bool(value_norm) and value_norm in support_norm


def fact_text(field: str, value: str, context: dict[str, Any]) -> str:
    home = str(context.get("home", "Mandante"))
    away = str(context.get("away", "Visitante"))
    competition = str(context.get("competition", "competição"))
    builders = {
        "stadium": lambda: f"A partida será disputada no {value}.",
        "transmission": lambda: f"Transmissão: {value}.",
        "referee": lambda: f"Árbitro: {value}.",
        "home_lineup": lambda: f"Provável escalação do {home}: {value}.",
        "home_coach": lambda: f"Técnico do {home}: {value}.",
        "away_lineup": lambda: f"Provável escalação do {away}: {value}.",
        "away_coach": lambda: f"Técnico do {away}: {value}.",
        "home_recent_form": lambda: f"Forma recente do {home}: {value}.",
        "away_recent_form": lambda: f"Forma recente do {away}: {value}.",
        "h2h_games": lambda: f"Confrontos pela {competition}: {value} jogos.",
        "h2h_home_wins": lambda: f"Vitórias do {home} pela {competition}: {value}.",
        "h2h_away_wins": lambda: f"Vitórias do {away} pela {competition}: {value}.",
        "h2h_draws": lambda: f"Empates pela {competition}: {value}.",
        "qualification_scenario": lambda: f"Cenário de classificação: {value}.",
    }
    return builders[field]()


def validate_h2h_values(facts: list[dict[str, str]]) -> bool:
    values = {item["field"]: item["value"] for item in facts}
    required = SUPPORTED_REQUIREMENTS["competition_specific_head_to_head"]
    if not all(field in values for field in required):
        return False
    try:
        games = int(values["h2h_games"])
        home = int(values["h2h_home_wins"])
        away = int(values["h2h_away_wins"])
        draws = int(values["h2h_draws"])
    except ValueError:
        return False
    return games == home + away + draws


def apply_requirement_result(
    base: dict[str, Any],
    model_result: dict[str, Any],
    *,
    segment_map: dict[str, dict[str, Any]],
    context: dict[str, Any],
    site_config: dict[str, Any],
) -> dict[str, Any]:
    req_id = base.get("id")
    result = deepcopy(base)
    status = model_result.get("status")

    if status == "conflict":
        result["status"] = "pending"
        result["facts"] = []
        result["sources"] = []
        result["conflict_detected"] = True
        result["conflicts"] = [{
            "field": "openai_grounded_extraction",
            "values": [],
            "rule": str(model_result.get("conflict_note", "conflict_reported_from_checked_evidence"))[:500],
        }]
        result["validator_accepted"] = False
        result["structured_fact_count"] = 0
        result["fact_extraction_status"] = "openai_grounded_conflict_blocked"
        return result

    if status != "verified":
        result["openai_grounded_attempted"] = True
        result["openai_grounded_status"] = "pending"
        return result

    expected_fields = SUPPORTED_REQUIREMENTS.get(str(req_id), [])
    raw_facts = model_result.get("facts")
    if not isinstance(raw_facts, list):
        return result

    accepted: list[dict[str, str]] = []
    source_rows: list[dict[str, Any]] = []
    grounding: list[dict[str, str]] = []
    seen_fields: set[str] = set()

    for item in raw_facts:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        value = item.get("value")
        seg_id = item.get("support_segment_id")
        if field not in expected_fields or field in seen_fields:
            continue
        if not isinstance(value, str) or not value.strip() or not isinstance(seg_id, str):
            continue
        segment_info = segment_map.get(seg_id)
        if not isinstance(segment_info, dict) or segment_info.get("requirement_id") != req_id:
            continue
        value = re.sub(r"\s+", " ", value).strip(" \t\r\n.,;:-–—")
        support = str(segment_info.get("model_text", ""))
        if not exact_grounded_value(value, support):
            continue
        if deterministic.contains_attribution_language(value):
            continue
        if field.startswith("h2h_") and not re.fullmatch(r"\d{1,4}", value):
            continue
        numbers = re.findall(r"\d+(?:[.,]\d+)?", value)
        support_norm = normalize_text(support)
        if any(normalize_text(number) not in support_norm for number in numbers):
            continue

        accepted.append({"field": field, "value": value})
        seen_fields.add(field)
        source_rows.append(source_for_segment(segment_info))
        grounding.append({
            "field": field,
            "support_segment_id": seg_id,
            "support_sha256": hashlib.sha256(str(segment_info.get("raw_text", "")).encode("utf-8")).hexdigest(),
        })

    if set(seen_fields) != set(expected_fields):
        result["openai_grounded_attempted"] = True
        result["openai_grounded_status"] = "incomplete_after_grounding_check"
        return result
    if req_id == "competition_specific_head_to_head" and not validate_h2h_values(accepted):
        result["openai_grounded_attempted"] = True
        result["openai_grounded_status"] = "h2h_consistency_rejected"
        return result

    evidence = {
        "status": "verified",
        "facts": [
            {"field": item["field"], "text": fact_text(item["field"], item["value"], context)}
            for item in accepted
        ],
        "sources": unique_sources(source_rows),
        "notes": None,
    }
    validated, errors = factual_validator.validate_requirement_evidence(base, evidence, config=site_config)
    if errors:
        result["openai_grounded_attempted"] = True
        result["openai_grounded_status"] = "validator_rejected"
        result["openai_validator_errors"] = errors
        return result

    result.update(validated)
    result["validator_accepted"] = True
    result["structured_fact_count"] = len(validated.get("facts", []))
    result["conflict_detected"] = False
    result["conflicts"] = []
    result["fact_extraction_status"] = "openai_grounded_validated"
    result["openai_grounded_attempted"] = True
    result["openai_grounded_status"] = "verified"
    result["openai_grounding"] = grounding
    result["internal_provenance_only"] = True
    return result


def merge_article(
    fact_article: dict[str, Any],
    checked_article: dict[str, Any],
    model_data: dict[str, Any],
    *,
    segment_map: dict[str, dict[str, Any]],
    site_config: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(fact_article)
    model_rows = model_data.get("requirements", [])
    model_by_id: dict[str, dict[str, Any]] = {}
    for item in model_rows:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            if item["id"] in model_by_id:
                fail(f"Modelo repetiu requisito {item['id']}.")
            model_by_id[item["id"]] = item

    context = result.get("match_context") if isinstance(result.get("match_context"), dict) else {}
    merged: list[dict[str, Any]] = []
    for requirement in result.get("requirements", []):
        if not isinstance(requirement, dict):
            continue
        req_id = requirement.get("id")
        row = model_by_id.get(str(req_id))
        updated = requirement
        if row is not None and not requirement_is_resolved(requirement):
            updated = apply_requirement_result(
                requirement,
                row,
                segment_map=segment_map,
                context=context,
                site_config=site_config,
            )
        competition_slug = str(context.get("competition_slug", ""))
        updated = deterministic.resolve_allowed_gap(
            updated,
            competition_slug=competition_slug,
            config=site_config,
        )
        merged.append(updated)

    structured_count = sum(int(item.get("structured_fact_count", 0)) for item in merged)
    conflicts = [str(item.get("id")) for item in merged if item.get("conflict_detected") is True]
    accepted_ids = [str(item.get("id")) for item in merged if item.get("validator_accepted") is True]
    result["requirements"] = merged
    result["structured_fact_count"] = structured_count
    result["conflict_requirement_ids"] = conflicts
    result["validator_accepted_requirement_ids"] = accepted_ids
    result["openai_grounded_fallback_used"] = True
    result["research_status"] = "structured_fact_extraction_completed_with_grounded_fallback"
    result["ready_for_factual_validation"] = False
    result["ready_for_drafting"] = False
    result["ready_for_html"] = False
    result["publication_unlocked"] = False
    result["internal_provenance_only"] = True
    result["source_attribution_in_article_body"] = "forbidden"
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fallback OpenAI aterrado para fatos de pré-jogo, sem publicar.")
    parser.add_argument("--date", help="Data-alvo YYYY-MM-DD. Vazio = amanhã em Brasília.")
    parser.add_argument("--checked", type=Path, help="Manifesto paginas-checadas-AAAA-MM-DD.json.")
    parser.add_argument("--facts", type=Path, help="Manifesto fatos-estruturados-AAAA-MM-DD.json.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    provider_config = load_provider_config()
    site_config = load_site_config()
    tz = ZoneInfo(site_config["timezone"])
    target_date = parse_target_date(args.date, tz)
    checked_path = args.checked or DEFAULT_OUTPUT_DIR / f"paginas-checadas-{target_date.isoformat()}.json"
    facts_path = args.facts or DEFAULT_OUTPUT_DIR / f"fatos-estruturados-{target_date.isoformat()}.json"

    if provider_config["provider"].get("execute_requires_explicit_flag") is True and not args.execute:
        fail("Chamada real bloqueada: use --execute explicitamente.")
    api_key = os.environ.get(provider_config["provider"]["api_key_env"], "").strip()
    if not api_key:
        fail("OPENAI_API_KEY não configurada.")

    checked = checked_articles(checked_path, target_date)
    facts = facts_manifest(facts_path, target_date)
    checked_by_slug = {
        item.get("slug"): item for item in checked
        if isinstance(item.get("slug"), str)
    }

    updated_articles: list[dict[str, Any]] = []
    call_count = 0
    usage_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    grounded_verified = 0

    for fact_article in facts.get("articles", []):
        if not isinstance(fact_article, dict):
            continue
        slug = fact_article.get("slug")
        checked_article = checked_by_slug.get(slug)
        if not isinstance(slug, str) or not isinstance(checked_article, dict):
            updated_articles.append(deepcopy(fact_article))
            continue

        targets, segment_map = target_requirements(
            fact_article,
            checked_article,
            scope=provider_config["scope"],
        )
        if not targets:
            updated_articles.append(deepcopy(fact_article))
            continue

        payload = build_request(fact_article, targets, provider_config, segment_map)
        response = call_api(payload, provider_config, api_key)
        call_count += 1
        for key, value in usage_summary(response).items():
            usage_totals[key] += value
        model_data = parse_model_output(response)

        expected_ids = {item["id"] for item in targets}
        returned_ids = [item.get("id") for item in model_data.get("requirements", []) if isinstance(item, dict)]
        if len(returned_ids) != len(expected_ids) or set(returned_ids) != expected_ids:
            fail(f"Extrator factual devolveu requisitos inesperados para {slug}.")

        merged = merge_article(
            fact_article,
            checked_article,
            model_data,
            segment_map=segment_map,
            site_config=site_config,
        )
        grounded_verified += sum(
            1 for item in merged.get("requirements", [])
            if isinstance(item, dict) and item.get("fact_extraction_status") == "openai_grounded_validated"
        )
        updated_articles.append(merged)

    output_dir = args.output_dir.resolve()
    default_root = DEFAULT_OUTPUT_DIR.resolve()
    try:
        output_dir.relative_to(default_root)
    except ValueError:
        fail("A extração factual só pode gravar dentro de build/pre-jogo/.")

    article_dir = output_dir / f"fatos-estruturados-{target_date.isoformat()}"
    manifest_path = output_dir / f"fatos-estruturados-{target_date.isoformat()}.json"
    if manifest_path.exists() and not args.force:
        fail("Manifesto factual já existe; use --force para substituir somente build/.")
    article_dir.mkdir(parents=True, exist_ok=True)

    files: list[str] = []
    for article in updated_articles:
        slug = article.get("slug")
        if not isinstance(slug, str):
            continue
        destination = article_dir / Path(slug).with_suffix(".json").name
        destination.write_text(json.dumps(article, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files.append(str(destination.relative_to(ROOT)))

    manifest = deepcopy(facts)
    manifest["generated_at"] = datetime.now(tz).isoformat()
    manifest["articles"] = updated_articles
    manifest["article_count"] = len(updated_articles)
    manifest["structured_fact_count"] = sum(int(item.get("structured_fact_count", 0)) for item in updated_articles)
    manifest["conflict_article_count"] = sum(bool(item.get("conflict_requirement_ids")) for item in updated_articles)
    manifest["validator_accepted_requirement_count"] = sum(
        len(item.get("validator_accepted_requirement_ids", [])) for item in updated_articles
    )
    manifest["openai_grounded_fallback"] = {
        "used": call_count > 0,
        "model_call_count": call_count,
        "grounded_verified_requirement_count": grounded_verified,
        "usage": usage_totals,
        "web_search": False,
        "tools": False,
        "publication_unlocked": False,
    }
    manifest["files"] = files
    manifest["publication_unlocked"] = False
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"OK: fallback factual aterrado concluído para {target_date.isoformat()}.")
    print(f"Chamadas ao modelo: {call_count}")
    print(f"Requisitos aceitos com grounding extrativo: {grounded_verified}")
    print(f"Fatos estruturados totais após fallback: {manifest['structured_fact_count']}")
    print("Web search e ferramentas do modelo: desativadas.")
    print("Redação, HTML e publicação permanecem bloqueados nesta etapa.")


if __name__ == "__main__":
    main()
