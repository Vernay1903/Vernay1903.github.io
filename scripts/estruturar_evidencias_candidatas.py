#!/usr/bin/env python3
"""Liga fontes candidatas do Serper aos dossiês factuais sem validar fatos.

Este passo transforma URLs descobertas em registros estruturados de fontes candidatas.
Ele NÃO lê o conteúdo das páginas, NÃO marca fatos como verificados, NÃO libera redação,
HTML ou publicação.
"""

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
    discovery = research.get("discovery")
    if not isinstance(discovery, dict):
        fail('Configuração "research.discovery" ausente ou inválida.')
    if discovery.get("publication_unlock_allowed") is not False:
        fail("A estruturação de fontes candidatas não pode liberar publicação.")

    allowed = research.get("allowed_source_types")
    if not isinstance(allowed, list) or not allowed:
        fail("research.allowed_source_types ausente ou inválido.")
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
    return [item for item in dossiers if isinstance(item, dict)]


def load_discovery_manifest(path: Path, target_date: date) -> tuple[str, list[dict[str, Any]]]:
    data = load_json(path)
    if not isinstance(data, dict):
        fail("O manifesto de fontes candidatas deve ser um objeto JSON.")
    if data.get("target_date") != target_date.isoformat():
        fail("A data do manifesto de fontes candidatas não coincide com a data-alvo.")
    generated_at = data.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at.strip():
        fail("Manifesto de fontes candidatas sem generated_at válido.")
    results = data.get("results")
    if not isinstance(results, list):
        fail('O manifesto de fontes candidatas deve conter um array "results".')
    return generated_at.strip(), [item for item in results if isinstance(item, dict)]


def domain_matches(host: str, allowed_domain: str) -> bool:
    host = host.strip().lower().rstrip(".")
    allowed = allowed_domain.strip().lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if allowed.startswith("www."):
        allowed = allowed[4:]
    return host == allowed or host.endswith("." + allowed)


def publisher_from_domain(domain: str, source_type: str, config: dict[str, Any]) -> str:
    host = domain.strip().lower()
    if source_type == "internal_site":
        return "Corte dos Esportes"

    if source_type == "major_sports_media":
        known = {
            "ge.globo.com": "ge",
            "espn.com.br": "ESPN Brasil",
        }
        for candidate, publisher in known.items():
            if domain_matches(host, candidate):
                return publisher

    if source_type == "official":
        discovery = config["research"]["discovery"]
        official = discovery.get("official_domains", {})
        clubs = official.get("clubs", {}) if isinstance(official, dict) else {}
        if isinstance(clubs, dict):
            for name, domains in clubs.items():
                if isinstance(domains, list) and any(domain_matches(host, str(item)) for item in domains):
                    return str(name)
        competitions = official.get("competitions", {}) if isinstance(official, dict) else {}
        labels = config.get("editorial", {}).get("competition_labels", {})
        if isinstance(competitions, dict):
            for slug, domains in competitions.items():
                if isinstance(domains, list) and any(domain_matches(host, str(item)) for item in domains):
                    label = labels.get(slug) if isinstance(labels, dict) else None
                    if isinstance(label, dict) and isinstance(label.get("name"), str):
                        return label["name"]
                    return str(slug)

    return host


def normalize_candidate(
    candidate: Any,
    *,
    source_type: str,
    discovered_at: str,
    dynamic_relevance_required: bool,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    url = candidate.get("url")
    domain = candidate.get("domain")
    if not isinstance(url, str) or not url.startswith("https://"):
        return None
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    if not isinstance(domain, str) or not domain.strip():
        domain = parsed.hostname or ""
    domain = domain.strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if not domain:
        return None

    title = candidate.get("title")
    snippet = candidate.get("snippet")
    position = candidate.get("position")
    published_hint = candidate.get("published_hint")

    return {
        "publisher": publisher_from_domain(domain, source_type, config),
        "url": url.strip(),
        "source_type": source_type,
        "domain": domain,
        "title": title.strip() if isinstance(title, str) else "",
        "snippet": snippet.strip() if isinstance(snippet, str) else "",
        "position": position if isinstance(position, int) else None,
        "published_hint": published_hint if isinstance(published_hint, str) else None,
        "discovered_at": discovered_at,
        "checked_at": None,
        "content_checked": False,
        "verification_status": "pending_page_check",
        "dynamic_relevance_required": dynamic_relevance_required,
        "local_relevance_verified": False if dynamic_relevance_required else None,
        "eligible_for_factual_validation": False,
    }


def structure_requirement_from_discovery(
    base_requirement: dict[str, Any],
    discovery_task: dict[str, Any] | None,
    *,
    discovered_at: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(base_requirement)
    result["facts"] = []
    result["sources"] = []
    result["source_candidates"] = []
    result["candidate_source_count"] = 0
    result["ready_for_factual_validation"] = False

    if not isinstance(discovery_task, dict):
        result["candidate_status"] = "no_discovery_record"
        result["status"] = "pending"
        return result

    source_type = discovery_task.get("selected_source_type")
    allowed = config["research"]["allowed_source_types"]
    candidates = discovery_task.get("candidates", [])
    dynamic = bool(discovery_task.get("dynamic_relevance_required"))

    if not isinstance(candidates, list) or not candidates:
        result["candidate_status"] = "no_candidates"
        result["status"] = "pending"
        return result

    if not isinstance(source_type, str) or source_type not in allowed:
        result["candidate_status"] = "invalid_source_type"
        result["status"] = "pending"
        return result

    normalized: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for candidate in candidates:
        item = normalize_candidate(
            candidate,
            source_type=source_type,
            discovered_at=discovered_at,
            dynamic_relevance_required=dynamic,
            config=config,
        )
        if item is None or item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        normalized.append(item)

    result["source_candidates"] = normalized
    result["candidate_source_count"] = len(normalized)
    result["candidate_status"] = "candidate_sources_found" if normalized else "no_candidates"
    result["status"] = "pending"
    return result


def structure_article(
    dossier: dict[str, Any],
    discovery_result: dict[str, Any] | None,
    *,
    discovered_at: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    slug = dossier.get("slug")
    if not isinstance(slug, str) or not slug:
        fail("Dossiê sem slug válido.")

    tasks_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(discovery_result, dict):
        tasks = discovery_result.get("tasks", [])
        if isinstance(tasks, list):
            for task in tasks:
                if isinstance(task, dict) and isinstance(task.get("requirement_id"), str):
                    tasks_by_id[task["requirement_id"]] = task

    requirements: list[dict[str, Any]] = []
    candidate_urls: set[str] = set()
    for base_requirement in dossier.get("requirements", []):
        if not isinstance(base_requirement, dict) or not isinstance(base_requirement.get("id"), str):
            continue
        structured = structure_requirement_from_discovery(
            base_requirement,
            tasks_by_id.get(base_requirement["id"]),
            discovered_at=discovered_at,
            config=config,
        )
        requirements.append(structured)
        for source in structured.get("source_candidates", []):
            if isinstance(source.get("url"), str):
                candidate_urls.add(source["url"])

    editorial_input = dossier.get("editorial_input") if isinstance(dossier.get("editorial_input"), dict) else {}
    return {
        "title": dossier.get("title"),
        "excerpt": editorial_input.get("excerpt"),
        "noticias_entry": deepcopy(editorial_input.get("noticias_entry")),
        "slug": slug,
        "date": dossier.get("date"),
        "fixture_id": dossier.get("fixture_id"),
        "match_context": dossier.get("match_context"),
        "research_status": "candidate_sources_structured",
        "external_research_performed": bool(
            isinstance(discovery_result, dict) and discovery_result.get("external_search_performed") is True
        ),
        "requirements": requirements,
        "candidate_source_count": len(candidate_urls),
        "verified_fact_count": 0,
        "verified_source_count": 0,
        "ready_for_factual_validation": False,
        "ready_for_drafting": False,
        "ready_for_html": False,
        "publication_unlocked": False,
        "next_required_step": "fetch_and_check_candidate_pages_before_fact_validation",
    }


def structure_batch(
    dossiers: list[dict[str, Any]],
    discovery_results: list[dict[str, Any]],
    *,
    discovered_at: str,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    discovery_by_slug: dict[str, dict[str, Any]] = {}
    for item in discovery_results:
        slug = item.get("slug")
        if isinstance(slug, str) and slug and slug not in discovery_by_slug:
            discovery_by_slug[slug] = item

    return [
        structure_article(
            dossier,
            discovery_by_slug.get(dossier.get("slug")),
            discovered_at=discovered_at,
            config=config,
        )
        for dossier in dossiers
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estrutura URLs candidatas do Serper dentro do dossiê factual sem validar fatos."
    )
    parser.add_argument("--date", help="Data-alvo YYYY-MM-DD. Vazio = amanhã em Brasília.")
    parser.add_argument("--research", type=Path, help="Manifesto pesquisa-AAAA-MM-DD.json.")
    parser.add_argument("--candidates", type=Path, help="Manifesto fontes-candidatas-AAAA-MM-DD.json.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Diretório de saída. Padrão: build/pre-jogo/.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite substituir somente os arquivos de evidências candidatas dentro de build/.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    tz = ZoneInfo(config["timezone"])
    target_date = parse_target_date(args.date, tz)

    research_path = args.research or DEFAULT_OUTPUT_DIR / f"pesquisa-{target_date.isoformat()}.json"
    candidates_path = args.candidates or DEFAULT_OUTPUT_DIR / f"fontes-candidatas-{target_date.isoformat()}.json"

    dossiers = load_research_manifest(research_path, target_date)
    discovered_at, discovery_results = load_discovery_manifest(candidates_path, target_date)
    articles = structure_batch(
        dossiers,
        discovery_results,
        discovered_at=discovered_at,
        config=config,
    )

    output_dir = args.output_dir.resolve()
    articles_dir = output_dir / f"evidencias-candidatas-{target_date.isoformat()}"
    manifest_path = output_dir / f"evidencias-candidatas-{target_date.isoformat()}.json"
    destinations = [articles_dir / Path(item["slug"]).with_suffix(".json").name for item in articles]
    destinations.append(manifest_path)

    existing = [path for path in destinations if path.exists()]
    if existing and not args.force:
        fail("Evidências candidatas já existem. Use --force somente para substituir arquivos de build/.")

    articles_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for article, destination in zip(articles, destinations[:-1]):
        destination.write_text(json.dumps(article, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(str(destination.relative_to(ROOT)) if destination.is_relative_to(ROOT) else str(destination))

    manifest = {
        "generated_at": datetime.now(tz).isoformat(),
        "target_date": target_date.isoformat(),
        "timezone": config["timezone"],
        "source_research": str(research_path),
        "source_candidates": str(candidates_path),
        "article_count": len(articles),
        "candidate_source_count": sum(item["candidate_source_count"] for item in articles),
        "verified_fact_count": 0,
        "ready_for_factual_validation_count": 0,
        "ready_for_drafting_count": 0,
        "ready_for_html_count": 0,
        "publication_unlocked": False,
        "files": written,
        "articles": articles,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"OK: fontes candidatas estruturadas para {target_date.isoformat()}.")
    print(f"Matérias: {len(articles)}")
    print(f"URLs candidatas estruturadas: {manifest['candidate_source_count']}")
    print("Fatos verificados: 0")
    print("Validação factual, redação, HTML e publicação permanecem bloqueados.")


if __name__ == "__main__":
    main()
