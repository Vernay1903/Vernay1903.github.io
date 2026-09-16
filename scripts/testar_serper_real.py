#!/usr/bin/env python3
"""Executa uma única consulta real ao Serper para validar chave e conectividade.

Este smoke test não valida fatos, não redige conteúdo e não publica nada.
A configuração persistente continua com external_search_enabled=false; a liberação
ocorre apenas em memória e somente quando --execute é informado explicitamente.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import buscar_fontes_serper as serper  # noqa: E402

OUTPUT_PATH = ROOT / "build" / "pre-jogo" / "serper-smoke-test.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Faz uma única consulta real ao Serper sem validar fatos nem publicar."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Obrigatório para permitir a chamada real ao Serper.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite substituir apenas o relatório de smoke test dentro de build/.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.execute:
        serper.fail("Smoke test externo bloqueado. Use --execute explicitamente.")

    config = serper.load_config()
    provider = config["research"]["discovery"]["search_provider"]
    secret_name = provider["api_key_env"]
    if not os.environ.get(secret_name, "").strip():
        serper.fail(f"Secret/variável {secret_name} não configurado.")

    # Mantém o arquivo de configuração seguro (false) e libera somente esta cópia em memória.
    runtime_config = deepcopy(config)
    runtime_config["research"]["discovery"]["external_search_enabled"] = True

    query = '"Premier League" site oficial'
    domains = ["premierleague.com"]
    final_query, raw = serper.request_serper(
        query=query,
        domains=domains,
        config=runtime_config,
        timeout=20,
        retries=1,
    )
    candidates = serper.normalize_serper_response(raw, allowed_domains=domains)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_PATH.exists() and not args.force:
        serper.fail(f"Relatório já existe: {OUTPUT_PATH}. Use --force apenas em build/.")

    tz = ZoneInfo(config["timezone"])
    report = {
        "step": 18,
        "mode": "serper_smoke_test",
        "generated_at": datetime.now(tz).isoformat(),
        "provider": "serper",
        "external_search_performed": True,
        "query_count": 1,
        "query": final_query,
        "restricted_domains": domains,
        "candidate_count": len(candidates),
        "candidates": candidates[:10],
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

    print("OK: conexão real com o Serper concluída.")
    print("Consultas executadas: 1")
    print(f"Candidatos HTTPS do domínio premierleague.com: {len(candidates)}")
    print("Nenhum fato foi validado.")
    print("Redação, HTML e publicação permanecem bloqueados.")
    print("O valor de SERPER_API_KEY não foi exibido.")


if __name__ == "__main__":
    main()
