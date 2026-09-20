#!/usr/bin/env python3
"""Monta o pacote editorial limpo para redação, separando completamente a proveniência.

Passo 24:
- recebe apenas fatos já estruturados/validados pelo pipeline factual;
- injeta o link interno aprovado da competição;
- remove fontes, URLs externas, consultas, evidências e metadados de pesquisa da entrada da redação;
- grava a proveniência em arquivo separado, marcado como interno;
- pode liberar apenas a etapa de redação quando todos os requisitos obrigatórios estiverem resolvidos;
- nunca libera HTML nem publicação.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import validar_politica_editorial as editorial_policy  # noqa: E402

CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
LINKS_PATH = ROOT / "config" / "links-internos-competicoes.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo"

PROVENANCE_KEYS = {
    "sources",
    "source_candidates",
    "publisher",
    "source_type",
    "checked_at",
    "discovered_at",
    "query",
    "queries",
    "query_base",
    "evidence_segments",
    "page_evidence",
    "extracted_claims",
    "validator_source",
    "supporting_sources",
    "evidence_sha256",
    "content_sha256",
}

RESOLVED_STATUSES = {
    "verified",
    "verified_not_announced",
    "unavailable_after_check",
    "not_applicable",
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
        fail(f"JSON inválido em {path}: {exc}")


def load_config() -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    if not isinstance(config, dict):
        fail("config/pre-jogo.json deve conter um objeto JSON.")
    if config.get("timezone") != "America/Sao_Paulo":
        fail('O timezone deve permanecer "America/Sao_Paulo".')

    policy = config.get("editorial", {}).get("source_attribution_policy")
    if not isinstance(policy, dict):
        fail("Política editorial de fontes ausente.")
    required_policy = {
        "research_sources_are_internal_only": True,
        "forbid_source_names_in_article_body": True,
        "forbid_research_process_mentions": True,
        "forbid_query_mentions": True,
        "write_verified_facts_directly": True,
    }
    for key, expected in required_policy.items():
        if policy.get(key) is not expected:
            fail(f"Política editorial obrigatória inválida em {key}.")

    validation = config.get("research", {}).get("validation")
    if not isinstance(validation, dict) or validation.get("publication_unlock_allowed") is not False:
        fail("A pesquisa não pode liberar publicação.")
    return config


def load_links() -> dict[str, Any]:
    data = load_json(LINKS_PATH)
    if not isinstance(data, dict) or data.get("version") != 1:
        fail("config/links-internos-competicoes.json inválido.")
    domain = data.get("domain")
    links = data.get("links")
    if domain != "https://cortedosesportes.com.br/" or not isinstance(links, dict):
        fail("Mapa de links internos inválido.")

    for slug, item in links.items():
        if not isinstance(slug, str) or not isinstance(item, dict):
            fail("Entrada inválida no mapa de links internos.")
        url = item.get("url")
        anchor = item.get("anchor_hint")
        if not isinstance(url, str) or not url.startswith(domain):
            fail(f"Link interno inválido para {slug}.")
        if not isinstance(anchor, str) or not anchor.strip():
            fail(f"anchor_hint inválido para {slug}.")
    return data


def parse_target_date(raw: str | None, tz: ZoneInfo) -> date:
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            fail("--date deve usar o formato YYYY-MM-DD.")
    return datetime.now(tz).date() + timedelta(days=1)


def load_fact_manifest(path: Path, target_date: date) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, dict):
        fail("O manifesto de fatos estruturados deve ser um objeto JSON.")
    if data.get("target_date") != target_date.isoformat():
        fail("A data do manifesto de fatos não coincide com a data-alvo.")
    articles = data.get("articles")
    if not isinstance(articles, list):
        fail('O manifesto de fatos deve conter um array "articles".')
    return [item for item in articles if isinstance(item, dict)]


def safe_fact(fact: Any, *, config: dict[str, Any]) -> dict[str, str] | None:
    if not isinstance(fact, dict):
        return None
    text = fact.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    text = text.strip()
    errors = editorial_policy.validate_body_policy(f"<p>{text}</p>", config)
    if errors:
        fail("Fato validado contém linguagem proibida de atribuição: " + "; ".join(errors))

    clean = {"text": text}
    field = fact.get("field")
    if isinstance(field, str) and field.strip():
        clean["field"] = field.strip()
    return clean


def requirement_is_resolved(requirement: dict[str, Any]) -> bool:
    if requirement.get("conflict_detected") is True:
        return False
    status = requirement.get("status")
    if status not in RESOLVED_STATUSES:
        return False
    if status == "verified":
        facts = requirement.get("facts")
        return isinstance(facts, list) and bool(facts)
    if status == "unavailable_after_check":
        return requirement.get("allow_unavailable_after_check") is True
    if status == "not_applicable":
        return requirement.get("conditional") is True
    return True


def internal_link_for_article(
    article: dict[str, Any],
    *,
    links: dict[str, Any],
) -> dict[str, str] | None:
    context = article.get("match_context")
    if not isinstance(context, dict):
        return None
    competition_slug = context.get("competition_slug")
    if not isinstance(competition_slug, str) or not competition_slug.strip():
        return None
    item = links["links"].get(competition_slug.strip())
    if not isinstance(item, dict):
        return None
    return {
        "competition_slug": competition_slug.strip(),
        "url": item["url"],
        "anchor_hint": item["anchor_hint"],
    }


def clean_requirement(
    requirement: dict[str, Any],
    *,
    config: dict[str, Any],
) -> dict[str, Any]:
    req_id = requirement.get("id")
    status = requirement.get("status")
    facts = []
    for fact in requirement.get("facts", []):
        clean = safe_fact(fact, config=config)
        if clean is not None:
            facts.append(clean)

    return {
        "id": req_id,
        "status": status,
        "facts": facts,
        "resolved": requirement_is_resolved(requirement),
    }


def provenance_requirement(requirement: dict[str, Any]) -> dict[str, Any]:
    sources = []
    for source in requirement.get("sources", []):
        if not isinstance(source, dict):
            continue
        sources.append(
            {
                "publisher": source.get("publisher"),
                "url": source.get("url"),
                "source_type": source.get("source_type"),
                "checked_at": source.get("checked_at"),
            }
        )

    candidates = []
    for source in requirement.get("source_candidates", []):
        if not isinstance(source, dict):
            continue
        candidates.append(
            {
                "publisher": source.get("publisher"),
                "url": source.get("url"),
                "source_type": source.get("source_type"),
                "checked_at": source.get("checked_at"),
                "content_checked": source.get("content_checked"),
                "verification_status": source.get("verification_status"),
                "eligible_for_factual_validation": source.get("eligible_for_factual_validation"),
            }
        )

    return {
        "id": requirement.get("id"),
        "status": requirement.get("status"),
        "validator_accepted": bool(requirement.get("validator_accepted")),
        "fact_extraction_status": requirement.get("fact_extraction_status"),
        "editorial_stadium_override": bool(requirement.get("editorial_stadium_override")),
        "editorial_config_path": requirement.get("editorial_config_path"),
        "notes": requirement.get("notes"),
        "conflict_detected": bool(requirement.get("conflict_detected")),
        "conflicts": deepcopy(requirement.get("conflicts", [])),
        "sources": sources,
        "source_candidates": candidates,
        "internal_only": True,
    }


def scan_forbidden_keys(value: Any, path: str = "root") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in PROVENANCE_KEYS:
                errors.append(f"{path}.{key}")
            errors.extend(scan_forbidden_keys(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            errors.extend(scan_forbidden_keys(item, f"{path}[{idx}]"))
    return errors


def scan_external_urls(value: Any, internal_domain: str, path: str = "root") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            errors.extend(scan_external_urls(item, internal_domain, f"{path}.{key}"))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            errors.extend(scan_external_urls(item, internal_domain, f"{path}[{idx}]"))
    elif isinstance(value, str) and re.match(r"^https?://", value, flags=re.IGNORECASE):
        parsed = urlparse(value)
        internal = urlparse(internal_domain)
        if parsed.netloc.lower() != internal.netloc.lower():
            errors.append(f"{path}: {value}")
    return errors


def verified_promised_service_gaps(
    requirement_by_id: dict[str, dict[str, Any]],
    *,
    title: str,
    excerpt: str,
    config: dict[str, Any],
) -> list[str]:
    """A headline não pode prometer transmissão, escalações e arbitragem ausentes.

    'unavailable_after_check' continua útil para rastreio, mas NÃO satisfaz
    uma promessa factual explícita do título ou excerpt. Aplica-se à redação
    antes de chamar OpenAI, economizando créditos de rascunhos rejeitados.
    """
    model = config.get("editorial", {}).get("approved_pre_match_model", {})
    required = model.get("promised_service_requirements", {})
    headline = editorial_policy.normalize_text(f"{title} {excerpt}") if hasattr(editorial_policy, "normalize_text") else f"{title} {excerpt}".casefold()
    triggers = {
        "transmission": ("transmissao", "onde assistir"),
        "probable_lineups_and_coaches": ("escalac",),
        "officiating": ("arbitragem", "arbitro", "var"),
    }
    # Normalização de acentos é independente de dependências de NLP.
    import unicodedata
    folded = "".join(c for c in unicodedata.normalize("NFKD", headline) if not unicodedata.combining(c))
    missing: list[str] = []
    for requirement_id, fields in required.items():
        if not any(trigger in folded for trigger in triggers.get(requirement_id, ())):
            continue
        req = requirement_by_id.get(requirement_id)
        if not isinstance(req, dict) or req.get("status") != "verified" or req.get("conflict_detected") is True:
            missing.append(f"promised_{requirement_id}_not_verified")
            continue
        observed = {
            fact.get("field"): fact.get("text")
            for fact in req.get("facts", [])
            if isinstance(fact, dict) and isinstance(fact.get("text"), str)
        }
        for field in fields:
            if not isinstance(observed.get(field), str) or not observed[field].strip():
                missing.append(f"promised_{field}_missing")
        if requirement_id == "probable_lineups_and_coaches":
            minimum = int(model.get("minimum_players_per_team", 11))
            for field in ("home_lineup", "away_lineup"):
                text = observed.get(field, "")
                value = text.split(":", 1)[-1].rstrip(".").strip()
                players = [
                    item.strip() for item in re.split(r"[;,]", value)
                    if len(item.strip()) >= 3
                ]
                if len(players) < minimum:
                    missing.append(f"promised_{field}_less_than_{minimum}_names")
    return missing


def build_article_packages(
    article: dict[str, Any],
    *,
    config: dict[str, Any],
    links: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    slug = article.get("slug")
    if not isinstance(slug, str) or not slug.endswith(".html"):
        fail("Artigo factual sem slug HTML válido.")

    requirements = article.get("requirements")
    if not isinstance(requirements, list):
        requirements = []

    clean_requirements: list[dict[str, Any]] = []
    provenance_requirements: list[dict[str, Any]] = []
    requirement_by_id: dict[str, dict[str, Any]] = {}

    for requirement in requirements:
        if not isinstance(requirement, dict) or not isinstance(requirement.get("id"), str):
            continue
        req_id = requirement["id"]
        requirement_by_id[req_id] = requirement
        if req_id != "competition_internal_link":
            clean_requirements.append(clean_requirement(requirement, config=config))
        provenance_requirements.append(provenance_requirement(requirement))

    internal_link = internal_link_for_article(article, links=links)
    required_policies = config["research"]["requirement_policy"]
    unresolved: list[str] = []
    resolution_status: dict[str, str] = {}

    for req_id, policy in required_policies.items():
        if not isinstance(policy, dict) or policy.get("required_for_drafting") is not True:
            continue
        if req_id == "competition_internal_link":
            if internal_link is None:
                unresolved.append(req_id)
                resolution_status[req_id] = "missing_internal_link_mapping"
            else:
                resolution_status[req_id] = "verified_internal_link"
            continue

        requirement = requirement_by_id.get(req_id)
        if requirement is None or not requirement_is_resolved(requirement):
            unresolved.append(req_id)
            resolution_status[req_id] = (
                str(requirement.get("status")) if isinstance(requirement, dict) else "missing"
            )
        else:
            resolution_status[req_id] = str(requirement.get("status"))

    # A política antiga aceita informação indisponível após consulta;
    # o modelo aprovado NÃO aceita publicar uma chamada que a prometa.
    unresolved.extend(verified_promised_service_gaps(
        requirement_by_id,
        title=str(article.get("title") or ""),
        excerpt=str(article.get("excerpt") or ""),
        config=config,
    ))
    unresolved = list(dict.fromkeys(unresolved))

    clean_package = {
        "step": 24,
        "title": article.get("title"),
        "excerpt": article.get("excerpt"),
        "date": article.get("date"),
        "slug": slug,
        "match_context": deepcopy(article.get("match_context", {})),
        "facts_by_requirement": clean_requirements,
        "competition_internal_link": internal_link,
        "resolution_status": resolution_status,
        "unresolved_required_requirement_ids": unresolved,
        "editorial_constraints": {
            "minimum_words": config["article"]["min_words"],
            "subtitles_in_strong": bool(config["article"].get("require_subtitles_strong")),
            "internal_link_required": True,
            "research_sources_must_not_be_cited": True,
            "research_process_must_not_be_mentioned": True,
            "write_verified_facts_directly": True,
        },
        "ready_for_drafting": not unresolved,
        "ready_for_html": False,
        "publication_unlocked": False,
        "provenance_available_to_drafter": False,
    }

    forbidden_keys = scan_forbidden_keys(clean_package)
    if forbidden_keys:
        fail("Pacote limpo vazou campos de proveniência: " + ", ".join(forbidden_keys))
    external_urls = scan_external_urls(clean_package, links["domain"])
    if external_urls:
        fail("Pacote limpo contém URL externa: " + ", ".join(external_urls))

    provenance_package = {
        "step": 24,
        "slug": slug,
        "fixture_id": article.get("fixture_id"),
        "internal_only": True,
        "available_to_drafter": False,
        "must_never_be_rendered_in_article": True,
        "requirements": provenance_requirements,
        "conflict_requirement_ids": deepcopy(article.get("conflict_requirement_ids", [])),
        "validator_accepted_requirement_ids": deepcopy(
            article.get("validator_accepted_requirement_ids", [])
        ),
        "research_status": article.get("research_status"),
    }
    return clean_package, provenance_package


def safe_json_name(slug: str) -> str:
    return Path(slug).with_suffix(".json").name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monta pacote editorial sem fontes e grava proveniência em arquivo interno separado."
    )
    parser.add_argument("--date", help="Data-alvo YYYY-MM-DD. Vazio = amanhã em Brasília.")
    parser.add_argument("--facts", type=Path, help="Manifesto fatos-estruturados-AAAA-MM-DD.json.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Diretório de saída. Padrão: build/pre-jogo/.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite substituir somente os pacotes do Passo 24 dentro de build/.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    links = load_links()
    tz = ZoneInfo(config["timezone"])
    target_date = parse_target_date(args.date, tz)
    facts_path = args.facts or DEFAULT_OUTPUT_DIR / f"fatos-estruturados-{target_date.isoformat()}.json"
    articles = load_fact_manifest(facts_path, target_date)

    output_dir = args.output_dir.resolve()
    clean_dir = output_dir / f"pacotes-editoriais-{target_date.isoformat()}"
    provenance_dir = output_dir / f"proveniencia-interna-{target_date.isoformat()}"
    clean_manifest_path = output_dir / f"pacotes-editoriais-{target_date.isoformat()}.json"
    provenance_manifest_path = output_dir / f"proveniencia-interna-{target_date.isoformat()}.json"

    built = [build_article_packages(article, config=config, links=links) for article in articles]
    clean_packages = [item[0] for item in built]
    provenance_packages = [item[1] for item in built]

    destinations: list[Path] = []
    for package in clean_packages:
        destinations.append(clean_dir / safe_json_name(package["slug"]))
    for package in provenance_packages:
        destinations.append(provenance_dir / safe_json_name(package["slug"]))
    destinations.extend([clean_manifest_path, provenance_manifest_path])

    existing = [path for path in destinations if path.exists()]
    if existing and not args.force:
        fail("Pacotes do Passo 24 já existem. Use --force somente dentro de build/.")

    clean_dir.mkdir(parents=True, exist_ok=True)
    provenance_dir.mkdir(parents=True, exist_ok=True)

    clean_files: list[str] = []
    for package in clean_packages:
        destination = clean_dir / safe_json_name(package["slug"])
        destination.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        clean_files.append(str(destination.relative_to(ROOT)) if destination.is_relative_to(ROOT) else str(destination))

    provenance_files: list[str] = []
    for package in provenance_packages:
        destination = provenance_dir / safe_json_name(package["slug"])
        destination.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        provenance_files.append(str(destination.relative_to(ROOT)) if destination.is_relative_to(ROOT) else str(destination))

    generated_at = datetime.now(tz).isoformat()
    clean_manifest = {
        "generated_at": generated_at,
        "target_date": target_date.isoformat(),
        "article_count": len(clean_packages),
        "ready_for_drafting_count": sum(bool(item["ready_for_drafting"]) for item in clean_packages),
        "ready_for_html_count": 0,
        "publication_unlocked": False,
        "contains_research_provenance": False,
        "files": clean_files,
        "articles": clean_packages,
    }
    provenance_manifest = {
        "generated_at": generated_at,
        "target_date": target_date.isoformat(),
        "article_count": len(provenance_packages),
        "internal_only": True,
        "available_to_drafter": False,
        "must_never_be_rendered_in_article": True,
        "files": provenance_files,
        "articles": provenance_packages,
    }

    clean_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    clean_manifest_path.write_text(
        json.dumps(clean_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    provenance_manifest_path.write_text(
        json.dumps(provenance_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"OK: pacote editorial limpo montado para {target_date.isoformat()}.")
    print(f"Matérias: {len(clean_packages)}")
    print(f"Liberadas apenas para redação: {clean_manifest['ready_for_drafting_count']}")
    print("Proveniência gravada em arquivo separado e indisponível ao redator.")
    print("Fontes, consultas e URLs externas não entram no pacote de redação.")
    print("HTML e publicação permanecem bloqueados.")


if __name__ == "__main__":
    main()
