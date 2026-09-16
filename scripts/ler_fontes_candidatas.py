#!/usr/bin/env python3
"""Lê páginas candidatas via Serper Scrape sem transformar conteúdo em fato publicado.

Este passo abre páginas descobertas anteriormente, registra evidências textuais limitadas
para futura extração factual e mantém redação, HTML e publicação bloqueados.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
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
    reader = research.get("page_reader")
    if not isinstance(reader, dict):
        fail('Configuração "research.page_reader" ausente ou inválida.')

    expected = {
        "name": "serper-scrape",
        "base_url": "https://scrape.serper.dev",
        "method": "POST",
        "api_key_env": "SERPER_API_KEY",
        "auth_header": "X-API-KEY",
    }
    for key, value in expected.items():
        if reader.get(key) != value:
            fail(f'Configuração do leitor de páginas inválida em "{key}".')
    if reader.get("execute_requires_explicit_flag") is not True:
        fail("A leitura externa deve exigir autorização explícita.")
    if reader.get("publication_unlock_allowed") is not False:
        fail("A leitura de páginas não pode liberar publicação.")

    policy = config.get("editorial", {}).get("source_attribution_policy")
    if not isinstance(policy, dict):
        fail("Política editorial de atribuição de fontes ausente.")
    if policy.get("research_sources_are_internal_only") is not True:
        fail("As fontes de pesquisa devem permanecer internas.")
    if policy.get("forbid_source_names_in_article_body") is not True:
        fail("A matéria deve proibir nomes de fontes de pesquisa no corpo.")
    if policy.get("forbid_research_process_mentions") is not True:
        fail("A matéria deve proibir menções ao processo de pesquisa.")

    return config


def parse_target_date(raw: str | None, tz: ZoneInfo) -> date:
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            fail("--date deve usar o formato YYYY-MM-DD.")
    return datetime.now(tz).date() + timedelta(days=1)


def load_candidate_manifest(path: Path, target_date: date) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, dict):
        fail("O manifesto de evidências candidatas deve ser um objeto JSON.")
    if data.get("target_date") != target_date.isoformat():
        fail("A data do manifesto não coincide com a data-alvo.")
    articles = data.get("articles")
    if not isinstance(articles, list):
        fail('O manifesto deve conter um array "articles".')
    return [item for item in articles if isinstance(item, dict)]


def request_serper_scrape(
    url: str,
    *,
    config: dict[str, Any],
    timeout: int = 30,
    retries: int = 1,
) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Somente URLs HTTPS válidas podem ser lidas.")

    reader = config["research"]["page_reader"]
    secret_name = reader["api_key_env"]
    api_key = os.environ.get(secret_name, "").strip()
    if not api_key:
        raise RuntimeError(f"Secret/variável {secret_name} não configurado.")

    payload: dict[str, Any] = {"url": url}
    if reader.get("include_markdown") is True:
        payload["includeMarkdown"] = True

    body = json.dumps(payload).encode("utf-8")
    headers = {
        reader["auth_header"]: api_key,
        "Content-Type": reader.get("content_type", "application/json"),
        "Accept": "application/json",
        "User-Agent": "Corte-dos-Esportes-pre-jogo/1.0",
    }

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = Request(
                reader["base_url"],
                data=body,
                headers=headers,
                method=reader["method"],
            )
            with urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise RuntimeError("Resposta inesperada do Serper Scrape.")
                return data
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= retries:
                raise RuntimeError(f"Serper Scrape retornou HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if attempt >= retries:
                raise RuntimeError(f"Falha ao ler página via Serper Scrape: {exc}") from exc
        time.sleep(1 + attempt)

    raise RuntimeError(f"Falha ao ler página via Serper Scrape: {last_error}")


def normalize_scrape_response(payload: dict[str, Any]) -> dict[str, Any]:
    markdown = payload.get("markdown")
    text = payload.get("text")
    content = markdown if isinstance(markdown, str) and markdown.strip() else text
    if not isinstance(content, str):
        content = ""
    content = content.strip()

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    credits = payload.get("credits")
    if not isinstance(credits, int):
        credits = None

    return {
        "content": content,
        "metadata": metadata,
        "credits": credits,
    }


REQUIREMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "stadium_and_location": (
        "stadium", "estádio", "estadio", "arena", "venue", "local", "emirates",
    ),
    "transmission": (
        "transmiss", "onde assistir", "tv", "stream", "broadcast", "canal",
    ),
    "probable_lineups_and_coaches": (
        "escala", "lineup", "team news", "coach", "treinador", "manager", "starting xi",
    ),
    "officiating": (
        "árbit", "arbit", "referee", "officiat", "var",
    ),
    "recent_form_both_teams": (
        "últimos", "ultimos", "recent", "form", "vitória", "vitoria", "derrota", "empate",
    ),
    "competition_specific_head_to_head": (
        "confront", "head-to-head", "head to head", "histórico", "historico", "previous meeting",
    ),
    "competition_internal_link": (
        "história", "historia", "campeões", "campeoes", "competition",
    ),
    "stakes_and_qualification_scenarios_when_applicable": (
        "classifica", "vaga", "semifinal", "quartas", "oitavas", "final", "aggregate", "penalt",
    ),
    "upcoming_fixtures_when_useful": (
        "próximo", "proximo", "next match", "fixtures", "schedule", "calendário", "calendario",
    ),
}


def clean_markdown_line(line: str) -> str:
    value = line.strip()
    if not value:
        return ""
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"[`*_>#|]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def extract_evidence_segments(
    content: str,
    requirement_id: str,
    *,
    max_segments: int,
    max_segment_chars: int,
) -> list[str]:
    if not content.strip():
        return []

    lines = [clean_markdown_line(line) for line in content.splitlines()]
    lines = [line for line in lines if len(line) >= 25]
    keywords = tuple(item.casefold() for item in REQUIREMENT_KEYWORDS.get(requirement_id, ()))

    matched: list[str] = []
    fallback: list[str] = []
    seen: set[str] = set()

    for line in lines:
        clipped = line[:max_segment_chars].strip()
        if not clipped or clipped in seen:
            continue
        seen.add(clipped)
        fallback.append(clipped)
        folded = clipped.casefold()
        if keywords and any(keyword in folded for keyword in keywords):
            matched.append(clipped)

    chosen = matched if matched else fallback
    return chosen[:max_segments]


def apply_scrape_to_candidate(
    candidate: dict[str, Any],
    raw_payload: dict[str, Any],
    *,
    requirement_id: str,
    checked_at: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(candidate)
    normalized = normalize_scrape_response(raw_payload)
    content = normalized["content"]
    reader = config["research"]["page_reader"]
    segments = extract_evidence_segments(
        content,
        requirement_id,
        max_segments=int(reader.get("max_segments_per_source", 6)),
        max_segment_chars=int(reader.get("max_segment_chars", 500)),
    )

    metadata = normalized["metadata"]
    safe_metadata = {
        key: value
        for key, value in metadata.items()
        if key in {"title", "description", "og:title", "og:description", "language"}
        and isinstance(value, str)
    }

    result["checked_at"] = checked_at
    result["content_checked"] = bool(content)
    result["verification_status"] = (
        "page_checked_pending_fact_extraction" if content else "page_checked_no_content"
    )
    result["page_evidence"] = {
        "metadata": safe_metadata,
        "evidence_segments": segments,
        "segment_count": len(segments),
        "content_length": len(content),
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest() if content else None,
        "credits_used": normalized["credits"],
    }

    dynamic = result.get("dynamic_relevance_required") is True
    result["eligible_for_factual_validation"] = bool(content and segments and not dynamic)
    if dynamic:
        result["local_relevance_verified"] = False
    return result


def check_requirement_candidates(
    requirement: dict[str, Any],
    *,
    config: dict[str, Any],
    checked_at: str,
    max_attempts: int | None = None,
) -> dict[str, Any]:
    result = deepcopy(requirement)
    candidates = result.get("source_candidates")
    if not isinstance(candidates, list):
        candidates = []

    reader = config["research"]["page_reader"]
    limit = max_attempts
    if limit is None:
        raw_limit = reader.get("max_candidates_per_requirement", 1)
        limit = raw_limit if isinstance(raw_limit, int) and raw_limit > 0 else 1

    checked: list[dict[str, Any]] = []
    successful = 0
    attempts = 0
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if attempts >= limit:
            checked.append(deepcopy(candidate))
            continue
        attempts += 1
        try:
            raw = request_serper_scrape(candidate["url"], config=config)
            updated = apply_scrape_to_candidate(
                candidate,
                raw,
                requirement_id=str(result.get("id", "")),
                checked_at=checked_at,
                config=config,
            )
            if updated.get("content_checked") is True:
                successful += 1
            checked.append(updated)
        except Exception as exc:  # rede/API pode falhar por URL; registramos sem promover a fonte.
            failed = deepcopy(candidate)
            failed["content_checked"] = False
            failed["checked_at"] = checked_at
            failed["verification_status"] = "page_fetch_failed"
            failed["eligible_for_factual_validation"] = False
            failed["page_evidence"] = {
                "metadata": {},
                "evidence_segments": [],
                "segment_count": 0,
                "content_length": 0,
                "content_sha256": None,
                "credits_used": None,
                "error": str(exc)[:300],
            }
            checked.append(failed)

    result["source_candidates"] = checked
    result["page_check_attempt_count"] = attempts
    result["page_check_success_count"] = successful
    result["ready_for_fact_extraction"] = any(
        isinstance(item, dict) and item.get("eligible_for_factual_validation") is True
        for item in checked
    )
    result["facts"] = []
    result["sources"] = []
    result["status"] = "pending"
    return result


def check_article(
    article: dict[str, Any],
    *,
    config: dict[str, Any],
    checked_at: str,
) -> dict[str, Any]:
    result = deepcopy(article)
    requirements = result.get("requirements")
    if not isinstance(requirements, list):
        requirements = []

    checked_requirements = [
        check_requirement_candidates(item, config=config, checked_at=checked_at)
        for item in requirements
        if isinstance(item, dict)
    ]

    checked_sources: set[str] = set()
    eligible_sources: set[str] = set()
    blocking: list[str] = []
    for requirement in checked_requirements:
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

    result["requirements"] = checked_requirements
    result["research_status"] = "candidate_pages_checked"
    result["page_checked_source_count"] = len(checked_sources)
    result["eligible_source_count"] = len(eligible_sources)
    result["ready_for_fact_extraction"] = bool(eligible_sources)
    result["page_check_blocking_requirement_ids"] = blocking
    result["verified_fact_count"] = 0
    result["verified_source_count"] = 0
    result["ready_for_factual_validation"] = False
    result["ready_for_drafting"] = False
    result["ready_for_html"] = False
    result["publication_unlocked"] = False
    result["next_required_step"] = "extract_structured_facts_from_checked_page_evidence"
    result["article_source_attribution_policy"] = deepcopy(
        config["editorial"]["source_attribution_policy"]
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lê fontes candidatas via Serper Scrape sem validar fatos ou publicar."
    )
    parser.add_argument("--date", help="Data-alvo YYYY-MM-DD. Vazio = amanhã em Brasília.")
    parser.add_argument(
        "--candidates",
        type=Path,
        help="Manifesto evidencias-candidatas-AAAA-MM-DD.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Diretório de saída. Padrão: build/pre-jogo/.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Obrigatório para permitir chamadas reais ao Serper Scrape.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite substituir somente arquivos de páginas checadas dentro de build/.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    if not args.execute:
        fail("Leitura externa bloqueada. Use --execute somente em execução autorizada.")

    reader = config["research"]["page_reader"]
    if not os.environ.get(reader["api_key_env"], "").strip():
        fail(f"Secret/variável {reader['api_key_env']} não configurado.")

    tz = ZoneInfo(config["timezone"])
    target_date = parse_target_date(args.date, tz)
    candidate_path = args.candidates or DEFAULT_OUTPUT_DIR / f"evidencias-candidatas-{target_date.isoformat()}.json"
    articles = load_candidate_manifest(candidate_path, target_date)
    checked_at = datetime.now(tz).isoformat()
    checked_articles = [check_article(item, config=config, checked_at=checked_at) for item in articles]

    output_dir = args.output_dir.resolve()
    articles_dir = output_dir / f"paginas-checadas-{target_date.isoformat()}"
    manifest_path = output_dir / f"paginas-checadas-{target_date.isoformat()}.json"
    destinations = [articles_dir / Path(item["slug"]).with_suffix(".json").name for item in checked_articles]
    destinations.append(manifest_path)

    existing = [path for path in destinations if path.exists()]
    if existing and not args.force:
        fail("Páginas checadas já existem. Use --force somente para substituir arquivos de build/.")

    articles_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for article, destination in zip(checked_articles, destinations[:-1]):
        destination.write_text(json.dumps(article, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(str(destination.relative_to(ROOT)) if destination.is_relative_to(ROOT) else str(destination))

    manifest = {
        "generated_at": checked_at,
        "target_date": target_date.isoformat(),
        "timezone": config["timezone"],
        "source_candidate_manifest": str(candidate_path),
        "article_count": len(checked_articles),
        "page_checked_source_count": sum(item["page_checked_source_count"] for item in checked_articles),
        "eligible_source_count": sum(item["eligible_source_count"] for item in checked_articles),
        "verified_fact_count": 0,
        "ready_for_factual_validation_count": 0,
        "ready_for_drafting_count": 0,
        "ready_for_html_count": 0,
        "publication_unlocked": False,
        "source_attribution_in_article_body": "forbidden",
        "files": written,
        "articles": checked_articles,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"OK: páginas candidatas checadas para {target_date.isoformat()}.")
    print(f"Páginas checadas com conteúdo: {manifest['page_checked_source_count']}")
    print(f"Fontes elegíveis para futura extração factual: {manifest['eligible_source_count']}")
    print("Fatos verificados: 0")
    print("As fontes de pesquisa permanecem internas e não podem ser citadas no texto da matéria.")
    print("Validação factual, redação, HTML e publicação permanecem bloqueados.")


if __name__ == "__main__":
    main()
