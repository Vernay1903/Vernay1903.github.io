#!/usr/bin/env python3
"""Extrai fatos estruturados de páginas já checadas, detecta conflitos e alimenta o validador factual.

Este passo é deliberadamente conservador:
- nunca usa snippets do buscador;
- só usa páginas com content_checked=true e eligible_for_factual_validation=true;
- mantém toda a proveniência de fontes como metadado interno;
- bloqueia promoção quando encontra valores conflitantes;
- não redige matéria, não gera HTML e não libera publicação.

A primeira extração determinística liberada é stadium_and_location. Os demais
requisitos permanecem pendentes até terem extratores específicos seguros.
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
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import validar_pesquisa_factual as factual_validator  # noqa: E402

CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo"

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
    "venue",
    "stadium",
    "estádio",
    "estadio",
    "arena",
    "played at",
    "will be played at",
    "takes place at",
    "held at",
    "será disputado",
    "sera disputado",
    "será disputada",
    "sera disputada",
    "será jogado",
    "sera jogado",
    "será jogada",
    "sera jogada",
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
        fail("Nomes de fontes devem permanecer proibidos no corpo da matéria.")
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


def context_mentions_match(corpus: str, match_context: dict[str, Any], config: dict[str, Any]) -> bool:
    folded = normalize_text(corpus)
    home = match_context.get("home")
    away = match_context.get("away")
    if not isinstance(home, str) or not isinstance(away, str):
        return False

    def present(team: str) -> bool:
        return any(normalize_text(alias) in folded for alias in aliases_for_team(team, config))

    return present(home) and present(away)


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


def extract_venue_values(text: str) -> list[tuple[str, str]]:
    """Retorna pares (valor, segmento de evidência) apenas quando há contexto de estádio/local."""
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
                value = re.sub(r"\s+", " ", match.group(1)).strip(" .,:;-")
                if len(value) < 4:
                    continue
                key = normalize_text(value)
                if key and key not in seen:
                    seen.add(key)
                    found.append((value, segment))

    return found


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


def extract_stadium_requirement(
    requirement: dict[str, Any],
    *,
    match_context: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(requirement)
    source_candidates = requirement.get("source_candidates")
    if not isinstance(source_candidates, list):
        source_candidates = []

    claims: list[dict[str, Any]] = []
    for source in source_candidates:
        if not isinstance(source, dict):
            continue
        if source.get("content_checked") is not True:
            continue
        if source.get("eligible_for_factual_validation") is not True:
            continue
        corpus = source_corpus(source)
        if not corpus or not context_mentions_match(corpus, match_context, config):
            continue
        for value, evidence_segment in extract_venue_values(corpus):
            claims.append(
                {
                    "field": "stadium",
                    "value": value,
                    "normalized_value": normalize_text(value),
                    "source": internal_source_record(source, evidence_segment),
                    "validator_source": validator_source(source),
                }
            )

    grouped: dict[str, dict[str, Any]] = {}
    for claim in claims:
        key = claim["normalized_value"]
        group = grouped.setdefault(
            key,
            {
                "field": "stadium",
                "value": claim["value"],
                "normalized_value": key,
                "supporting_sources": [],
            },
        )
        if claim["source"]["url"] not in {s.get("url") for s in group["supporting_sources"]}:
            group["supporting_sources"].append(claim["source"])

    result["extracted_claims"] = list(grouped.values())
    result["structured_fact_count"] = 0
    result["conflict_detected"] = False
    result["conflicts"] = []
    result["validator_accepted"] = False
    result["facts"] = []
    result["sources"] = []
    result["status"] = "pending"

    if not grouped:
        result["fact_extraction_status"] = "no_supported_structured_fact"
        return result

    if len(grouped) > 1:
        result["fact_extraction_status"] = "conflict_blocked"
        result["conflict_detected"] = True
        result["conflicts"] = [
            {
                "field": "stadium",
                "values": [item["value"] for item in grouped.values()],
                "rule": "critical_field_conflict_blocks_validation",
            }
        ]
        return result

    group = next(iter(grouped.values()))
    value = group["value"]
    supporting_urls = {item["url"] for item in group["supporting_sources"]}
    validator_sources = unique_validator_sources(
        [claim["validator_source"] for claim in claims if claim["source"]["url"] in supporting_urls]
    )
    evidence = {
        "status": "verified",
        "facts": [
            {
                "field": "stadium",
                "text": f"A partida será disputada no {value}.",
            }
        ],
        "sources": validator_sources,
        "notes": None,
    }
    validated, errors = factual_validator.validate_requirement_evidence(
        requirement,
        evidence,
        config=config,
    )
    if errors:
        result["fact_extraction_status"] = "validator_rejected"
        result["validator_errors"] = errors
        return result

    result.update(validated)
    result["extracted_claims"] = list(grouped.values())
    result["structured_fact_count"] = len(validated.get("facts", []))
    result["conflict_detected"] = False
    result["conflicts"] = []
    result["validator_accepted"] = True
    result["fact_extraction_status"] = "validated_structured_fact"
    result["internal_provenance_only"] = True
    return result


def extract_requirement(
    requirement: dict[str, Any],
    *,
    match_context: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    requirement_id = requirement.get("id")
    if requirement_id == "stadium_and_location":
        return extract_stadium_requirement(
            requirement,
            match_context=match_context,
            config=config,
        )

    result = deepcopy(requirement)
    result["extracted_claims"] = []
    result["structured_fact_count"] = 0
    result["conflict_detected"] = False
    result["conflicts"] = []
    result["validator_accepted"] = False
    result["facts"] = []
    result["sources"] = []
    result["status"] = "pending"
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
        for item in requirements
        if isinstance(item, dict)
    ]
    structured_fact_count = sum(int(item.get("structured_fact_count", 0)) for item in extracted)
    conflicts = [item.get("id") for item in extracted if item.get("conflict_detected") is True]
    validator_accepted = [item.get("id") for item in extracted if item.get("validator_accepted") is True]

    result["requirements"] = extracted
    result["research_status"] = "structured_fact_extraction_completed"
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
    result["next_required_step"] = "enable_safe_extractors_for_remaining_requirements"
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
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Diretório de saída. Padrão: build/pre-jogo/.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
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
    destinations = [articles_dir / Path(item["slug"]).with_suffix(".json").name for item in extracted_articles]
    destinations.append(manifest_path)

    existing = [path for path in destinations if path.exists()]
    if existing and not args.force:
        fail("Fatos estruturados já existem. Use --force somente para substituir arquivos de build/.")

    articles_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for article, destination in zip(extracted_articles, destinations[:-1]):
        destination.write_text(json.dumps(article, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(str(destination.relative_to(ROOT)) if destination.is_relative_to(ROOT) else str(destination))

    manifest = {
        "generated_at": datetime.now(tz).isoformat(),
        "target_date": target_date.isoformat(),
        "timezone": config["timezone"],
        "source_checked_manifest": str(checked_path),
        "article_count": len(extracted_articles),
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
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"OK: extração estruturada concluída para {target_date.isoformat()}.")
    print(f"Fatos estruturados aceitos pelo validador: {manifest['structured_fact_count']}")
    print(f"Matérias com conflito detectado: {manifest['conflict_article_count']}")
    print("As fontes permanecem como proveniência interna e não podem aparecer no texto da matéria.")
    print("Redação, HTML e publicação permanecem bloqueados.")


if __name__ == "__main__":
    main()
