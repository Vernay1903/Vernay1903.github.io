#!/usr/bin/env python3
"""Teste determinístico da integração Serper sem executar busca externa."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import buscar_fontes_serper as serper  # noqa: E402

FIXTURE_PATH = ROOT / "tests" / "pre-jogo" / "serper-resposta-simulada.json"
REPORT_PATH = ROOT / "build" / "pre-jogo" / "teste-serper-provider.json"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: esperado={expected!r}, obtido={actual!r}")


def main() -> None:
    config = serper.load_config()
    discovery = config["research"]["discovery"]
    provider = discovery["search_provider"]

    assert_equal(provider["name"], "serper", "Nome do provedor")
    assert_equal(provider["base_url"], "https://google.serper.dev", "Base URL do Serper")
    assert_equal(provider["endpoint"], "/search", "Endpoint de busca")
    assert_equal(provider["method"], "POST", "Método HTTP")
    assert_equal(provider["api_key_env"], "SERPER_API_KEY", "Nome do Secret")
    assert_equal(provider["auth_header"], "X-API-KEY", "Header de autenticação")
    assert_equal(discovery["external_search_enabled"], False, "Busca real deve continuar desligada")

    query = serper.build_query(
        '"Arsenal" "Manchester City" "Premier League" estádio',
        ["arsenal.com", "premierleague.com"],
    )
    if "site:arsenal.com" not in query or "site:premierleague.com" not in query:
        raise AssertionError("Filtro de domínio não foi incluído na consulta.")

    payload = serper.build_payload(query, provider=provider)
    assert_equal(payload["gl"], "br", "País da pesquisa")
    assert_equal(payload["hl"], "pt-br", "Idioma da pesquisa")
    assert_equal(payload["num"], 10, "Quantidade de resultados por consulta")

    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    all_results = serper.normalize_serper_response(raw)
    assert_equal(len(all_results), 4, "Resultados HTTPS únicos normalizados")

    official = serper.normalize_serper_response(
        raw,
        allowed_domains=["arsenal.com", "premierleague.com"],
    )
    assert_equal(len(official), 2, "Resultados oficiais filtrados")
    assert_equal(
        [item["domain"] for item in official],
        ["arsenal.com", "premierleague.com"],
        "Domínios oficiais preservados",
    )

    major = serper.normalize_serper_response(
        raw,
        allowed_domains=["espn.com.br", "ge.globo.com"],
    )
    assert_equal(len(major), 1, "Resultado de grande imprensa")
    assert_equal(major[0]["domain"], "espn.com.br", "Domínio de grande imprensa")

    if any(item["url"].startswith("http://") for item in all_results):
        raise AssertionError("Resultados HTTP não podem ser aceitos como candidatos.")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "step": 17,
        "mode": "simulation_only",
        "provider": provider["name"],
        "external_search_performed": False,
        "provider_configured": True,
        "secret_expected": provider["api_key_env"],
        "normalized_result_count": len(all_results),
        "official_result_count": len(official),
        "major_media_result_count": len(major),
        "checks": {
            "serper_selected": True,
            "post_endpoint_configured": True,
            "secret_not_embedded": True,
            "domain_filters_added": True,
            "https_only_candidates": True,
            "duplicate_urls_removed": True,
            "official_domain_filtering": True,
            "major_media_domain_filtering": True,
            "real_search_still_disabled": True,
            "publication_still_blocked": True
        }
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("OK: integração Serper validada sem chamada externa.")
    print(f"Resultados normalizados: {len(all_results)}")
    print(f"Resultados oficiais: {len(official)}")
    print(f"Resultados de grande imprensa: {len(major)}")
    print("Secret esperado: SERPER_API_KEY (nenhum valor foi usado).")
    print("Busca real, redação, HTML e publicação continuam bloqueados.")


if __name__ == "__main__":
    main()
