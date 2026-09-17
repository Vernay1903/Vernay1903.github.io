#!/usr/bin/env python3
"""Diagnóstico interno do fallback factual do Passo 34.4.

Este script NÃO altera fatos, NÃO redige matéria, NÃO gera HTML e NÃO publica.
Ele repete somente a chamada extrativa aterrada do Passo 34.3 para registrar:
- quais segmentos chegaram ao modelo por requisito;
- o status devolvido pelo modelo;
- quais campos obrigatórios foram/nao foram devolvidos;
- quais checks determinísticos rejeitariam cada valor;
- o resultado que apply_requirement_result produziria sem persistir a alteração.

Nenhuma URL ou nome de publisher é enviado ao modelo. O relatório é interno e fica
somente dentro de build/pre-jogo/automatico/ para auditoria do dry-run manual.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import extrair_fatos_openai as grounded  # noqa: E402

DEFAULT_BUILD = ROOT / "build" / "pre-jogo"


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


def check_candidate(
    requirement_id: str,
    item: dict[str, Any],
    *,
    expected_fields: list[str],
    segment_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    field = item.get("field")
    value = item.get("value")
    segment_id = item.get("support_segment_id")
    reasons: list[str] = []

    if field not in expected_fields:
        reasons.append("field_not_expected_for_requirement")
    if not isinstance(value, str) or not value.strip():
        reasons.append("value_missing_or_empty")
        clean_value = ""
    else:
        clean_value = re.sub(r"\s+", " ", value).strip(" \t\r\n.,;:-–—")
    if not isinstance(segment_id, str):
        reasons.append("support_segment_id_missing")
        segment_info = None
    else:
        segment_info = segment_map.get(segment_id)
        if not isinstance(segment_info, dict):
            reasons.append("support_segment_not_found")
        elif segment_info.get("requirement_id") != requirement_id:
            reasons.append("support_segment_belongs_to_other_requirement")

    support = ""
    if isinstance(segment_info, dict):
        support = str(segment_info.get("model_text", ""))
        if clean_value and not grounded.exact_grounded_value(clean_value, support):
            reasons.append("value_not_literal_inside_support_segment")

    if clean_value and grounded.deterministic.contains_attribution_language(clean_value):
        reasons.append("value_contains_forbidden_attribution_language")

    if isinstance(field, str) and field.startswith("h2h_") and clean_value:
        if not re.fullmatch(r"\d{1,4}", clean_value):
            reasons.append("h2h_value_is_not_plain_integer")

    if clean_value and support:
        support_norm = grounded.normalize_text(support)
        numbers = re.findall(r"\d+(?:[.,]\d+)?", clean_value)
        if any(grounded.normalize_text(number) not in support_norm for number in numbers):
            reasons.append("number_not_present_in_support_segment")

    return {
        "field": field,
        "value": value,
        "support_segment_id": segment_id,
        "accepted_by_grounding_checks": not reasons,
        "rejection_reasons": reasons,
    }


def requirement_diagnostic(
    base_requirement: dict[str, Any],
    target: dict[str, Any],
    model_result: dict[str, Any] | None,
    *,
    segment_map: dict[str, dict[str, Any]],
    context: dict[str, Any],
    site_config: dict[str, Any],
) -> dict[str, Any]:
    requirement_id = str(target["id"])
    required_fields = list(target.get("required_fields", []))
    raw_facts = model_result.get("facts", []) if isinstance(model_result, dict) else []
    raw_facts = [item for item in raw_facts if isinstance(item, dict)]
    checks = [
        check_candidate(
            requirement_id,
            item,
            expected_fields=required_fields,
            segment_map=segment_map,
        )
        for item in raw_facts
    ]

    accepted_fields = {
        str(item.get("field"))
        for item in checks
        if item.get("accepted_by_grounding_checks") is True
    }
    missing_fields = [field for field in required_fields if field not in accepted_fields]

    if isinstance(model_result, dict):
        simulated = grounded.apply_requirement_result(
            deepcopy(base_requirement),
            model_result,
            segment_map=segment_map,
            context=context,
            site_config=site_config,
        )
        model_status = model_result.get("status")
        conflict_note = model_result.get("conflict_note")
    else:
        simulated = deepcopy(base_requirement)
        model_status = "missing_result"
        conflict_note = None

    if model_status == "pending":
        outcome_reason = "model_returned_pending"
    elif model_status == "conflict":
        outcome_reason = "model_reported_conflict"
    elif model_status == "missing_result":
        outcome_reason = "model_did_not_return_requirement"
    elif missing_fields:
        outcome_reason = "required_fields_missing_or_rejected_after_grounding"
    elif simulated.get("openai_grounded_status") == "h2h_consistency_rejected":
        outcome_reason = "h2h_arithmetic_inconsistent"
    elif simulated.get("openai_grounded_status") == "validator_rejected":
        outcome_reason = "factual_validator_rejected"
    elif simulated.get("fact_extraction_status") == "openai_grounded_validated":
        outcome_reason = "would_be_accepted"
    else:
        outcome_reason = str(
            simulated.get("openai_grounded_status")
            or simulated.get("fact_extraction_status")
            or "not_accepted_unknown_reason"
        )

    segments: list[dict[str, Any]] = []
    for segment in target.get("segments", []):
        if not isinstance(segment, dict):
            continue
        segment_id = segment.get("segment_id")
        info = segment_map.get(str(segment_id), {}) if isinstance(segment_id, str) else {}
        source = info.get("source", {}) if isinstance(info, dict) else {}
        source_url = source.get("url") if isinstance(source, dict) else None
        segments.append({
            "segment_id": segment_id,
            "source_type": segment.get("source_type"),
            "kind": info.get("kind") if isinstance(info, dict) else None,
            "text": segment.get("text"),
            "source_url_sha256": (
                hashlib.sha256(source_url.encode("utf-8")).hexdigest()
                if isinstance(source_url, str) and source_url else None
            ),
        })

    return {
        "id": requirement_id,
        "required_fields": required_fields,
        "segment_count": len(segments),
        "segments_sent_to_model": segments,
        "model_status": model_status,
        "model_conflict_note": conflict_note,
        "model_facts": raw_facts,
        "grounding_checks": checks,
        "accepted_fields_after_grounding": sorted(accepted_fields),
        "missing_required_fields_after_grounding": missing_fields,
        "simulated_final_status": simulated.get("status"),
        "simulated_fact_extraction_status": simulated.get("fact_extraction_status"),
        "simulated_openai_grounded_status": simulated.get("openai_grounded_status"),
        "simulated_validator_errors": simulated.get("openai_validator_errors", []),
        "diagnostic_outcome": outcome_reason,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnóstico interno do Passo 34.4, sem publicar.")
    parser.add_argument("--date", required=True, help="Data-alvo YYYY-MM-DD.")
    parser.add_argument("--checked", required=True, type=Path)
    parser.add_argument("--facts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.execute:
        fail("Diagnóstico com chamada real bloqueado: use --execute explicitamente.")

    provider_config = grounded.load_provider_config()
    site_config = grounded.load_site_config()
    tz = ZoneInfo(site_config["timezone"])
    target_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    api_key = os.environ.get(provider_config["provider"]["api_key_env"], "").strip()
    if not api_key:
        fail("OPENAI_API_KEY não configurada.")

    checked = grounded.checked_articles(args.checked, target_date)
    facts = grounded.facts_manifest(args.facts, target_date)
    checked_by_slug = {
        item.get("slug"): item for item in checked
        if isinstance(item, dict) and isinstance(item.get("slug"), str)
    }

    articles_report: list[dict[str, Any]] = []
    total_calls = 0
    usage_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    for fact_article in facts.get("articles", []):
        if not isinstance(fact_article, dict):
            continue
        slug = fact_article.get("slug")
        checked_article = checked_by_slug.get(slug)
        if not isinstance(slug, str) or not isinstance(checked_article, dict):
            continue

        targets, segment_map = grounded.target_requirements(
            fact_article,
            checked_article,
            scope=provider_config["scope"],
        )
        if not targets:
            articles_report.append({
                "slug": slug,
                "diagnostic_status": "no_unresolved_supported_targets_with_segments",
                "requirements": [],
            })
            continue

        response = grounded.call_api(
            grounded.build_request(fact_article, targets, provider_config, segment_map),
            provider_config,
            api_key,
        )
        total_calls += 1
        for key, value in grounded.usage_summary(response).items():
            usage_totals[key] += value
        model_data = grounded.parse_model_output(response)
        model_by_id = {
            item.get("id"): item
            for item in model_data.get("requirements", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        base_by_id = {
            item.get("id"): item
            for item in fact_article.get("requirements", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        context = fact_article.get("match_context") if isinstance(fact_article.get("match_context"), dict) else {}

        requirement_reports = []
        for target in targets:
            req_id = str(target["id"])
            base = base_by_id.get(req_id)
            if not isinstance(base, dict):
                continue
            requirement_reports.append(
                requirement_diagnostic(
                    base,
                    target,
                    model_by_id.get(req_id),
                    segment_map=segment_map,
                    context=context,
                    site_config=site_config,
                )
            )

        articles_report.append({
            "slug": slug,
            "home": context.get("home"),
            "away": context.get("away"),
            "competition": context.get("competition"),
            "diagnostic_status": "completed",
            "requirements": requirement_reports,
        })

    output = args.output.resolve()
    try:
        output.relative_to(DEFAULT_BUILD.resolve())
    except ValueError:
        fail("O diagnóstico só pode ser gravado dentro de build/pre-jogo/.")
    output.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "step": "34.4",
        "mode": "internal_grounded_extraction_diagnostic",
        "generated_at": datetime.now(tz).isoformat(),
        "target_date": args.date,
        "model_call_count": total_calls,
        "usage": usage_totals,
        "safety": {
            "web_search": False,
            "tools": False,
            "changes_facts": False,
            "drafting": False,
            "html_generation": False,
            "publication_unlock": False,
            "external_urls_sent_to_model": False,
            "publisher_names_sent_to_model": False,
        },
        "articles": articles_report,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("PASSO 34.4 — DIAGNÓSTICO FACTUAL CONCLUÍDO")
    print(f"Data-alvo: {args.date}")
    print(f"Chamadas de diagnóstico ao modelo: {total_calls}")
    for article in articles_report:
        print(f"- {article.get('slug')}")
        for req in article.get("requirements", []):
            print(
                f"  {req['id']}: modelo={req['model_status']} | segmentos={req['segment_count']} | "
                f"faltando={','.join(req['missing_required_fields_after_grounding']) or '-'} | "
                f"resultado={req['diagnostic_outcome']}"
            )
    print(f"Relatório interno: {output.relative_to(ROOT)}")
    print("Nenhum fato, HTML, JSON publicado ou sitemap foi alterado por este diagnóstico.")


if __name__ == "__main__":
    main()
