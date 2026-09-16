#!/usr/bin/env python3
"""Teste real controlado da hierarquia de descoberta de fontes via Serper.

Executa no máximo três consultas, sempre nesta ordem:
1. fontes oficiais;
2. grandes veículos esportivos;
3. pesquisa ampla para possível imprensa local relevante.

Este teste apenas descobre URLs candidatas. Não valida fatos, não redige matéria,
não gera HTML e não libera publicação.
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

OUTPUT_PATH = ROOT / "build" / "pre-jogo" / "serper-discovery-test.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Testa a hierarquia real de descoberta de fontes no Serper sem publicar nada."
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

    config = serper.load_config()
    provider = config["research"]["discovery"]["search_provider"]
    secret_name = provider["api_key_env"]
    if not os.environ.get(secret_name, "").strip():
        serper.fail(f"Secret/variável {secret_name} não configurado.")

    # A configuração persistente continua segura. A busca é liberada somente nesta cópia em memória.
    runtime_config = deepcopy(config)
    runtime_config["research"]["discovery"]["external_search_enabled"] = True

    query = '"Arsenal" "Manchester City" "Premier League"'
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

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_PATH.exists() and not args.force:
        serper.fail(f"Relatório já existe: {OUTPUT_PATH}. Use --force apenas em build/.")

    tz = ZoneInfo(config["timezone"])
    report = {
        "step": 19,
        "mode": "serper_discovery_test",
        "generated_at": datetime.now(tz).isoformat(),
        "provider": "serper",
        "external_search_performed": True,
        "query_base": query,
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
        "facts_verified": False,
        "ready_for_drafting": False,
        "ready_for_html": False,
        "publication_unlocked": False,
        "repository_files_modified": False,
    }
    OUTPUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("OK: descoberta real controlada de fontes concluída.")
    print(f"Consultas executadas: {len(attempts)}")
    print("Ordem testada: oficial -> grande imprensa -> imprensa local relevante.")
    if selected_type:
        print(f"Primeira etapa com candidatos: {selected_type}")
        print(f"Candidatos encontrados nessa etapa: {len(selected_candidates)}")
    else:
        print("Nenhuma das três etapas encontrou candidatos.")
    if selected_type == "relevant_local_press":
        print("A relevância local ainda precisa ser validada antes de aceitar qualquer fonte.")
    print("Nenhum fato foi validado.")
    print("Redação, HTML e publicação permanecem bloqueados.")
    print("O valor de SERPER_API_KEY não foi exibido.")


if __name__ == "__main__":
    main()
