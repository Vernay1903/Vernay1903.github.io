#!/usr/bin/env python3
"""Valida evidências factuais de pré-jogo sem publicar nenhuma matéria."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlparse
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
    if research.get("evidence_ingestion_mode") != "validated_json":
        fail('research.evidence_ingestion_mode deve permanecer "validated_json".')

    allowed_types = research.get("allowed_source_types")
    if not isinstance(allowed_types, list) or not allowed_types:
        fail('Configuração "research.allowed_source_types" inválida.')

    validation = research.get("validation")
    if not isinstance(validation, dict):
        fail('Configuração "research.validation" ausente ou inválida.')
    if validation.get("publication_unlock_allowed") is not False:
        fail("O Passo 15 não pode liberar publicação.")

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
    for idx, dossier in enumerate(dossiers):
        if not isinstance(dossier, dict):
            fail(f"Dossiê na posição {idx} não é um objeto JSON.")
    return dossiers


def load_evidence_package(path: Path, target_date: date) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, dict):
        fail("O pacote de evidências deve ser um objeto JSON.")
    if data.get("target_date") != target_date.isoformat():
        fail("A data do pacote de evidências não coincide com a data-alvo.")
    articles = data.get("articles")
    if not isinstance(articles, list):
        fail('O pacote de evidências deve conter um array "articles".')
    for idx, article in enumerate(articles):
        if not isinstance(article, dict):
            fail(f"Artigo de evidências na posição {idx} não é um objeto JSON.")
    return articles


def parse_checked_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def validate_source(
    source: Any,
    *,
    config: dict[str, Any],
    requirement_id: str,
    index: int,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(source, dict):
        return None, [f"{requirement_id}.sources[{index}] não é um objeto"]

    required_fields = config["research"]["required_source_fields"]
    normalized = deepcopy(source)
    for field in required_fields:
        value = source.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{requirement_id}.sources[{index}].{field} ausente ou vazio")
        else:
            normalized[field] = value.strip()

    source_type = source.get("source_type")
    allowed_types = config["research"]["allowed_source_types"]
    if isinstance(source_type, str) and source_type.strip() not in allowed_types:
        errors.append(
            f"{requirement_id}.sources[{index}].source_type inválido: {source_type.strip()}"
        )

    url = source.get("url")
    validation = config["research"]["validation"]
    if isinstance(url, str) and url.strip():
        parsed = urlparse(url.strip())
        if validation.get("require_https_sources") is True and parsed.scheme != "https":
            errors.append(f"{requirement_id}.sources[{index}].url deve usar https")
        if not parsed.netloc:
            errors.append(f"{requirement_id}.sources[{index}].url inválida")

        if requirement_id == "competition_internal_link":
            domain = validation.get("internal_link_domain")
            if not isinstance(domain, str) or not url.strip().startswith(domain):
                errors.append(
                    f"{requirement_id}.sources[{index}].url deve apontar para {domain}"
                )
            if source_type != "internal_site":
                errors.append(
                    f"{requirement_id}.sources[{index}].source_type deve ser internal_site"
                )

    checked_at = source.get("checked_at")
    parsed_checked = parse_checked_at(checked_at)
    if parsed_checked is None:
        errors.append(
            f"{requirement_id}.sources[{index}].checked_at deve ser ISO 8601 com timezone"
        )

    return normalized, errors


def normalize_facts(value: Any, requirement_id: str) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    if not isinstance(value, list):
        return [], [f"{requirement_id}.facts deve ser um array"]

    facts: list[dict[str, str]] = []
    for idx, item in enumerate(value):
        if isinstance(item, str):
            text = item.strip()
            if not text:
                errors.append(f"{requirement_id}.facts[{idx}] vazio")
                continue
            facts.append({"text": text})
            continue
        if not isinstance(item, dict):
            errors.append(f"{requirement_id}.facts[{idx}] inválido")
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{requirement_id}.facts[{idx}].text ausente ou vazio")
            continue
        fact = {"text": text.strip()}
        field = item.get("field")
        if isinstance(field, str) and field.strip():
            fact["field"] = field.strip()
        facts.append(fact)
    return facts, errors


def validate_requirement_evidence(
    base_requirement: dict[str, Any],
    evidence: Any,
    *,
    config: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    result = deepcopy(base_requirement)
    requirement_id = result["id"]
    errors: list[str] = []

    if not isinstance(evidence, dict):
        return result, [f"{requirement_id}: evidência ausente ou inválida"]

    status = evidence.get("status")
    allowed_statuses = config["research"]["allowed_resolution_statuses"]
    if status not in allowed_statuses:
        errors.append(f"{requirement_id}.status inválido: {status!r}")
        return result, errors

    facts, fact_errors = normalize_facts(evidence.get("facts", []), requirement_id)
    errors.extend(fact_errors)

    raw_sources = evidence.get("sources", [])
    if not isinstance(raw_sources, list):
        errors.append(f"{requirement_id}.sources deve ser um array")
        raw_sources = []

    sources: list[dict[str, Any]] = []
    for idx, source in enumerate(raw_sources):
        normalized_source, source_errors = validate_source(
            source,
            config=config,
            requirement_id=requirement_id,
            index=idx,
        )
        errors.extend(source_errors)
        if normalized_source is not None:
            sources.append(normalized_source)

    unique_urls = {
        source.get("url")
        for source in sources
        if isinstance(source.get("url"), str) and source.get("url")
    }
    notes = evidence.get("notes")
    if notes is not None and (not isinstance(notes, str) or not notes.strip()):
        errors.append(f"{requirement_id}.notes deve ser texto não vazio ou null")
    notes_value = notes.strip() if isinstance(notes, str) else None

    validation = config["research"]["validation"]
    minimum_sources = validation.get("minimum_unique_sources_for_verified", 1)

    if status == "verified":
        if not facts:
            errors.append(f"{requirement_id}: status verified exige ao menos um fato")
        if len(unique_urls) < minimum_sources:
            errors.append(
                f"{requirement_id}: status verified exige ao menos {minimum_sources} fonte(s) única(s)"
            )

    elif status == "verified_not_announced":
        if not sources:
            errors.append(f"{requirement_id}: verified_not_announced exige fonte consultada")
        if not notes_value:
            errors.append(f"{requirement_id}: verified_not_announced exige notes")

    elif status == "unavailable_after_check":
        if result.get("allow_unavailable_after_check") is not True:
            errors.append(f"{requirement_id}: unavailable_after_check não é permitido")
        if not sources:
            errors.append(f"{requirement_id}: unavailable_after_check exige fonte consultada")
        if not notes_value:
            errors.append(f"{requirement_id}: unavailable_after_check exige notes")

    elif status == "not_applicable":
        if result.get("conditional") is not True:
            errors.append(f"{requirement_id}: not_applicable só é permitido em requisito condicional")
        if not notes_value:
            errors.append(f"{requirement_id}: not_applicable exige notes")

    result["status"] = status
    result["facts"] = facts
    result["sources"] = sources
    result["notes"] = notes_value
    return result, errors


def requirement_resolved_for_drafting(requirement: dict[str, Any]) -> bool:
    status = requirement.get("status")
    if status == "verified":
        return True
    if status == "verified_not_announced":
        return True
    if status == "unavailable_after_check":
        return requirement.get("allow_unavailable_after_check") is True
    if status == "not_applicable":
        return requirement.get("conditional") is True
    return False


def validate_dossier_with_evidence(
    dossier: dict[str, Any],
    evidence_article: dict[str, Any],
    *,
    config: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    slug = dossier.get("slug")
    if not isinstance(slug, str) or not slug:
        fail("Dossiê sem slug válido.")
    if evidence_article.get("slug") != slug:
        return deepcopy(dossier), [f"Slug de evidência não corresponde ao dossiê: {slug}"]

    evidence_requirements = evidence_article.get("requirements")
    if not isinstance(evidence_requirements, dict):
        return deepcopy(dossier), [f"{slug}: requirements de evidência ausente ou inválido"]

    validated = deepcopy(dossier)
    errors: list[str] = []
    validated_requirements: list[dict[str, Any]] = []

    for base_requirement in dossier.get("requirements", []):
        requirement_id = base_requirement.get("id")
        evidence = evidence_requirements.get(requirement_id)

        if evidence is None and base_requirement.get("required_for_drafting") is not True:
            validated_requirements.append(deepcopy(base_requirement))
            continue

        requirement, req_errors = validate_requirement_evidence(
            base_requirement,
            evidence,
            config=config,
        )
        validated_requirements.append(requirement)
        errors.extend(req_errors)

    extra_ids = sorted(set(evidence_requirements) - {item["id"] for item in dossier["requirements"]})
    if extra_ids:
        errors.append("Requisitos desconhecidos no pacote de evidências: " + ", ".join(extra_ids))

    unique_source_urls: set[str] = set()
    verified_fact_count = 0
    external_research_performed = False
    for requirement in validated_requirements:
        verified_fact_count += len(requirement.get("facts", []))
        for source in requirement.get("sources", []):
            url = source.get("url")
            if isinstance(url, str) and url:
                unique_source_urls.add(url)
            if source.get("source_type") != "internal_site":
                external_research_performed = True

    unresolved_blocking = [
        item["id"]
        for item in validated_requirements
        if item.get("required_for_drafting") is True
        and not requirement_resolved_for_drafting(item)
    ]

    ready_for_drafting = not errors and not unresolved_blocking
    validated["requirements"] = validated_requirements
    validated["verified_fact_count"] = verified_fact_count
    validated["source_count"] = len(unique_source_urls)
    validated["external_research_performed"] = external_research_performed
    validated["ready_for_drafting"] = ready_for_drafting
    validated["ready_for_html"] = False
    validated["blocking_requirement_ids"] = unresolved_blocking
    validated["research_status"] = (
        "validated_ready_for_drafting" if ready_for_drafting else "validated_incomplete"
    )
    validated["validation_errors"] = errors
    validated["publication_unlocked"] = False
    return validated, errors


def validate_batch(
    dossiers: list[dict[str, Any]],
    evidence_articles: list[dict[str, Any]],
    *,
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    evidence_by_slug: dict[str, dict[str, Any]] = {}
    batch_errors: list[str] = []
    for article in evidence_articles:
        slug = article.get("slug")
        if not isinstance(slug, str) or not slug:
            batch_errors.append("Há artigo de evidências sem slug válido")
            continue
        if slug in evidence_by_slug:
            batch_errors.append(f"Slug duplicado no pacote de evidências: {slug}")
            continue
        evidence_by_slug[slug] = article

    validated: list[dict[str, Any]] = []
    dossier_slugs = {dossier.get("slug") for dossier in dossiers}
    extra_evidence = sorted(slug for slug in evidence_by_slug if slug not in dossier_slugs)
    if extra_evidence:
        batch_errors.append("Evidências sem dossiê correspondente: " + ", ".join(extra_evidence))

    for dossier in dossiers:
        slug = dossier.get("slug")
        article = evidence_by_slug.get(slug)
        if article is None:
            result = deepcopy(dossier)
            result["research_status"] = "validated_incomplete"
            result["validation_errors"] = ["Pacote de evidências ausente para este dossiê"]
            result["ready_for_drafting"] = False
            result["ready_for_html"] = False
            result["publication_unlocked"] = False
            validated.append(result)
            continue
        result, errors = validate_dossier_with_evidence(dossier, article, config=config)
        validated.append(result)
        batch_errors.extend(f"{slug}: {error}" for error in errors)

    return validated, batch_errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ingere e valida evidências factuais de pré-jogo. "
            "Não acessa a web, não redige HTML e não publica nada."
        )
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
        "--evidence",
        type=Path,
        required=True,
        help="JSON contendo as evidências factuais coletadas para validação.",
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
        help="Permite substituir somente arquivos validados dentro de build/.",
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
    evidence_articles = load_evidence_package(args.evidence, target_date)
    validated, batch_errors = validate_batch(dossiers, evidence_articles, config=config)

    output_dir = args.output_dir.resolve()
    records_dir = output_dir / f"pesquisa-validada-{target_date.isoformat()}"
    manifest_path = output_dir / f"pesquisa-validada-{target_date.isoformat()}.json"
    destinations = [
        records_dir / Path(item["slug"]).with_suffix(".json").name
        for item in validated
    ]
    destinations.append(manifest_path)

    existing = [path for path in destinations if path.exists()]
    if existing and not args.force:
        relative = ", ".join(
            str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
            for path in existing
        )
        fail(
            "Pesquisa validada já existe: "
            + relative
            + ". Use --force somente para substituir arquivos de build."
        )

    records_dir.mkdir(parents=True, exist_ok=True)
    written_files: list[str] = []
    for item, destination in zip(validated, destinations[:-1]):
        destination.write_text(
            json.dumps(item, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written_files.append(
            str(destination.relative_to(ROOT)) if destination.is_relative_to(ROOT) else str(destination)
        )

    manifest = {
        "generated_at": datetime.now(tz).isoformat(),
        "target_date": target_date.isoformat(),
        "timezone": config["timezone"],
        "source_research": str(research_path),
        "source_evidence": str(args.evidence),
        "validated_count": len(validated),
        "ready_for_drafting_count": sum(1 for item in validated if item["ready_for_drafting"]),
        "ready_for_html_count": 0,
        "publication_unlocked_count": 0,
        "batch_error_count": len(batch_errors),
        "batch_errors": batch_errors,
        "files": written_files,
        "dossiers": validated,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"OK: evidências factuais validadas para {target_date.isoformat()}.")
    print(f"Dossiês validados: {len(validated)}")
    print(f"Prontos para redação: {manifest['ready_for_drafting_count']}")
    print(f"Erros de validação: {len(batch_errors)}")
    print("Prontos para HTML: 0")
    print("Publicação liberada: 0")
    for item in validated:
        print(
            f'- {item["research_status"]} | {item["title"]} | '
            f'{item["verified_fact_count"]} fatos | {item["source_count"]} fontes'
        )
    print(
        f"Manifesto: {manifest_path.relative_to(ROOT) if manifest_path.is_relative_to(ROOT) else manifest_path}"
    )
    print("Nenhum HTML, noticias.json ou sitemap.xml foi alterado.")


if __name__ == "__main__":
    main()
