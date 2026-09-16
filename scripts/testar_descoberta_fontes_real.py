#!/usr/bin/env python3
"""Teste real controlado da hierarquia, estruturação e leitura de fontes via Serper.

Executa a descoberta em ordem:
1. fontes oficiais;
2. grandes veículos esportivos;
3. pesquisa ampla para possível imprensa local relevante.

Depois estrutura as URLs candidatas e lê uma quantidade mínima de páginas pelo
Serper Scrape. Não transforma conteúdo em fato, não redige matéria, não gera HTML
e não libera publicação. As fontes e consultas permanecem apenas como metadados
internos de pesquisa e não podem ser citadas no corpo da matéria.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import buscar_fontes_serper as serper  # noqa: E402
from scripts import estruturar_evidencias_candidatas as evidence  # noqa: E402
from scripts import ler_fontes_candidatas as reader  # noqa: E402
from scripts import preparar_pesquisa_factual as research  # noqa: E402

OUTPUT_PATH = ROOT / "build" / "pre-jogo" / "serper-discovery-test.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Testa descoberta e leitura real de fontes sem publicar nada."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Obrigatório para permitir chamadas reais ao Serper.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite substituir apenas o relatório do teste dentro de build/.",
    )
    return parser.parse_args()


def stage_domains(stage: dict[str, Any]) -> list[str]:
    domains = stage.get("domains", [])
    if not isinstance(domains, list):
        return []
    return [str(item).strip().lower() for item in domains if str(item).strip()]


def main() -> None:
    args = parse_args()
    if not args.execute:
        serper.fail("Teste externo bloqueado. Use --execute explicitamente.")

    config = reader.load_config()
    provider = config["research"]["discovery"]["search_provider"]
    secret_name = provider["api_key_env"]
    if not os.environ.get(secret_name, "").strip():
        serper.fail(f"Secret/variável {secret_name} não configurado.")

    runtime_config = deepcopy(config)
    runtime_config["research"]["discovery"]["external_search_enabled"] = True

    requirement_id = "stadium_and_location"
    query = '"Arsenal" "Manchester City" "Premier League" estádio local jogo'
    stages = [
        {
            "order": 1,
            "source_type": "official",
            "domains": ["arsenal.com", "mancity.com", "premierleague.com"],
            "dynamic_relevance_required": False,
        },
        {
            "order": 2,
            "source_type": "major_sports_media",
            "domains": ["ge.globo.com", "espn.com.br"],
            "dynamic_relevance_required": False,
        },
        {
            "order": 3,
            "source_type": "relevant_local_press",
            "domains": [],
            "dynamic_relevance_required": True,
        },
    ]

    attempts: list[dict[str, Any]] = []
    selected_stage: dict[str, Any] | None = None
    selected_candidates: list[dict[str, Any]] = []

    for stage in stages:
        domains = stage_domains(stage)
        final_query, raw = serper.request_serper(
            query=query,
            domains=domains,
            config=runtime_config,
            timeout=20,
            retries=1,
        )
        candidates = serper.normalize_serper_response(
            raw,
            allowed_domains=domains if domains else None,
        )
        attempts.append(
            {
                "order": stage["order"],
                "source_type": stage["source_type"],
                "domains": domains,
                "query": final_query,
                "candidate_count": len(candidates),
                "candidate_domains": sorted({item["domain"] for item in candidates}),
            }
        )
        if candidates:
            selected_stage = stage
            selected_candidates = candidates
            break

    selected_type = selected_stage.get("source_type") if selected_stage else None
    expected_attempts = {
        "official": 1,
        "major_sports_media": 2,
        "relevant_local_press": 3,
        None: 3,
    }
    hierarchy_respected = len(attempts) == expected_attempts[selected_type]

    if not hierarchy_respected:
        serper.fail("A sequência de fallback não respeitou a hierarquia configurada.")

    if selected_stage:
        domains = stage_domains(selected_stage)
        if domains:
            for candidate in selected_candidates:
                host = candidate["domain"]
                if not any(serper.domain_matches(host, domain) for domain in domains):
                    serper.fail(
                        f"Candidato fora dos domínios permitidos para {selected_type}: {host}"
                    )

    tz = ZoneInfo(config["timezone"])
    discovered_at = datetime.now(tz).isoformat()
    base_requirement = research.build_requirement(requirement_id, config=config)
    discovery_task = {
        "requirement_id": requirement_id,
        "selected_source_type": selected_type,
        "dynamic_relevance_required": bool(
            selected_stage and selected_stage.get("dynamic_relevance_required")
        ),
        "candidates": selected_candidates,
    }
    structured_requirement = evidence.structure_requirement_from_discovery(
        base_requirement,
        discovery_task,
        discovered_at=discovered_at,
        config=config,
    )

    if structured_requirement["facts"]:
        serper.fail("O Passo 20 não pode criar fatos a partir de snippets do buscador.")
    if structured_requirement["sources"]:
        serper.fail("Fontes candidatas não podem ser promovidas a fontes validadas.")

    checked_requirement = reader.check_requirement_candidates(
        structured_requirement,
        config=config,
        checked_at=datetime.now(tz).isoformat(),
        max_attempts=2,
    )

    if selected_candidates and checked_requirement.get("page_check_success_count", 0) < 1:
        serper.fail("Nenhuma das páginas candidatas testadas pôde ser lida pelo Serper Scrape.")
    if checked_requirement.get("facts"):
        serper.fail("A leitura de página não pode criar fatos automaticamente.")
    if checked_requirement.get("sources"):
        serper.fail("A leitura de página não pode promover a fonte a validada.")

    checked_sources = [
        item
        for item in checked_requirement.get("source_candidates", [])
        if isinstance(item, dict) and item.get("content_checked") is True
    ]
    eligible_sources = [
        item
        for item in checked_sources
        if item.get("eligible_for_factual_validation") is True
    ]

    policy = config["editorial"]["source_attribution_policy"]
    if policy.get("research_sources_are_internal_only") is not True:
        serper.fail("Fontes de pesquisa devem permanecer internas.")
    if policy.get("forbid_source_names_in_article_body") is not True:
        serper.fail("A política deve proibir nomes das fontes no corpo da matéria.")
    if policy.get("forbid_research_process_mentions") is not True:
        serper.fail("A política deve proibir menções ao processo de consulta na matéria.")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_PATH.exists() and not args.force:
        serper.fail(f"Relatório já existe: {OUTPUT_PATH}. Use --force apenas em build/.")

    report = {
        "step": 21,
        "mode": "serper_discovery_candidate_and_page_read_test",
        "generated_at": discovered_at,
        "provider": "serper",
        "page_reader": config["research"]["page_reader"]["name"],
        "external_search_performed": True,
        "page_read_performed": bool(checked_sources),
        "query_base": query,
        "requirement_id": requirement_id,
        "source_priority": [
            "official",
            "major_sports_media",
            "relevant_local_press",
        ],
        "query_count": len(attempts),
        "attempts": attempts,
        "selected_source_type": selected_type,
        "candidate_count": len(selected_candidates),
        "candidates": selected_candidates[:10],
        "hierarchy_respected": hierarchy_respected,
        "local_dynamic_relevance_required": bool(
            selected_stage and selected_stage.get("dynamic_relevance_required")
        ),
        "structured_evidence_candidate": structured_requirement,
        "checked_requirement": checked_requirement,
        "page_check_attempt_count": checked_requirement.get("page_check_attempt_count", 0),
        "page_check_success_count": len(checked_sources),
        "eligible_source_count": len(eligible_sources),
        "facts_verified": False,
        "ready_for_factual_validation": False,
        "ready_for_drafting": False,
        "ready_for_html": False,
        "publication_unlocked": False,
        "research_sources_internal_only": True,
        "source_attribution_in_article_body": "forbidden",
        "research_process_mentions_in_article_body": "forbidden",
        "repository_files_modified": False,
    }
    OUTPUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("OK: descoberta, estruturação e leitura real controlada de fontes concluídas.")
    print(f"Consultas Serper executadas: {len(attempts)}")
    print("Ordem testada: oficial -> grande imprensa -> imprensa local relevante.")
    if selected_type:
        print(f"Primeira etapa com candidatos: {selected_type}")
        print(f"Candidatos encontrados nessa etapa: {len(selected_candidates)}")
    else:
        print("Nenhuma das três etapas encontrou candidatos.")
    print(f"Páginas lidas com conteúdo: {len(checked_sources)}")
    print(f"Fontes elegíveis para futura extração factual: {len(eligible_sources)}")
    print("Nenhum fato foi validado automaticamente.")
    print("As fontes e consultas são internas e não podem aparecer no texto da matéria.")
    print("Validação factual, redação, HTML e publicação permanecem bloqueados.")
    print("O valor de SERPER_API_KEY não foi exibido.")


if __name__ == "__main__":
    main()
