#!/usr/bin/env python3
"""Teste determinístico do planejamento de coleta de fontes do Passo 16."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import planejar_coleta_fontes as collector  # noqa: E402
from scripts import preparar_pesquisa_factual as research  # noqa: E402

REPORT_PATH = ROOT / "build" / "pre-jogo" / "teste-planejamento-coleta.json"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: esperado={expected!r}, obtido={actual!r}")


def main() -> None:
    config = collector.load_config()

    editorial_record = {
        "title": "Arsenal x Manchester City pela Premier League: transmissão, horário e prováveis escalações",
        "excerpt": "Registro simulado do Passo 16.",
        "date": "17/09/2026",
        "slug": "arsenal-manchester-city-premier-league-2026-transmissao-horario-escalacoes.html",
        "body_html": None,
        "body_html_status": "pending_research_and_drafting",
        "ready_for_html": False,
        "fixture_id": 1001,
        "match_context": {
            "home": "Arsenal",
            "away": "Manchester City",
            "competition": "Premier League",
            "competition_slug": "premier-league",
            "kickoff_brasilia": "2026-09-17T16:00:00-03:00",
            "kickoff_time_brasilia": "16:00",
            "prepare_at_brasilia": "2026-09-16T23:30:00-03:00",
            "target_publish_at_brasilia": "2026-09-17T00:01:00-03:00",
            "monitored_clubs": [
                {"name": "Arsenal", "slug": "arsenal"},
                {"name": "Manchester City", "slug": "manchester-city"},
            ],
            "two_monitored_clubs_same_match": True,
        },
        "research_requirements": list(config["editorial"]["research_requirements"]),
        "html_requirements": {
            "minimum_words": 700,
            "subtitles_in_strong": True,
            "internal_link_required": True,
            "category": "Futebol",
            "image_rotation": "deferred_until_html_generation",
        },
        "noticias_entry": {
            "title": "Arsenal x Manchester City pela Premier League: transmissão, horário e prováveis escalações",
            "excerpt": "Registro simulado do Passo 16.",
            "url": "arsenal-manchester-city-premier-league-2026-transmissao-horario-escalacoes.html",
            "date": "17/09/2026",
            "category": "Futebol",
        },
    }

    dossier = research.build_research_dossier(editorial_record, config=config)
    plan = collector.build_collection_plan(dossier, config=config)

    assert_equal(plan["external_search_enabled"], False, "Busca externa deve ficar desligada")
    assert_equal(plan["external_search_performed"], False, "Nenhuma busca pode ser executada")
    assert_equal(plan["search_provider"]["name"], "serper", "Serper deve ser o provedor escolhido")
    assert_equal(plan["search_provider"]["api_key_env"], "SERPER_API_KEY", "Secret esperado do Serper")
    assert_equal(plan["ready_for_drafting"], False, "Redação continua bloqueada")
    assert_equal(plan["ready_for_html"], False, "HTML continua bloqueado")
    assert_equal(plan["publication_unlocked"], False, "Publicação continua bloqueada")
    assert_equal(
        plan["source_priority"],
        ["official", "major_sports_media", "relevant_local_press"],
        "Prioridade de fontes",
    )
    assert_equal(len(plan["tasks"]), 9, "Quantidade de requisitos planejados")

    by_id = {item["requirement_id"]: item for item in plan["tasks"]}
    stadium = by_id["stadium_and_location"]
    assert_equal(
        [stage["source_type"] for stage in stadium["stages"]],
        ["official", "major_sports_media", "relevant_local_press"],
        "Ordem de fallback para estádio",
    )
    assert_equal(
        stadium["stages"][0]["domains"],
        ["arsenal.com", "mancity.com", "premierleague.com"],
        "Domínios oficiais do confronto",
    )
    assert_equal(
        stadium["stages"][1]["domains"],
        ["ge.globo.com", "espn.com.br"],
        "Domínios de grande imprensa",
    )
    assert_equal(
        stadium["stages"][2]["dynamic_relevance_required"],
        True,
        "Imprensa local deve exigir relevância dinâmica",
    )

    lineup = by_id["probable_lineups_and_coaches"]
    assert_equal(len(lineup["queries"]), 3, "Consultas de escalação devem cobrir jogo e cada time")

    internal = by_id["competition_internal_link"]
    assert_equal(len(internal["stages"]), 1, "Link interno deve usar uma única etapa")
    assert_equal(internal["stages"][0]["source_type"], "internal_site", "Tipo da fonte interna")
    assert_equal(
        internal["stages"][0]["domains"],
        ["cortedosesportes.com.br"],
        "Domínio do link interno",
    )
    if not internal["queries"][0].startswith("site:cortedosesportes.com.br"):
        raise AssertionError("Consulta do link interno deve ser restrita ao Corte dos Esportes.")

    for task in plan["tasks"]:
        assert_equal(task["execution_status"], "planned_not_executed", "Tarefa não pode ser executada")
        if not task["queries"]:
            raise AssertionError(f"Requisito sem consulta planejada: {task['requirement_id']}")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "step": 16,
        "mode": "simulation_only",
        "external_search_performed": False,
        "collection_status": plan["collection_status"],
        "task_count": len(plan["tasks"]),
        "provider_selected": plan["search_provider"]["name"],
        "official_domains": stadium["stages"][0]["domains"],
        "major_sports_media_domains": stadium["stages"][1]["domains"],
        "checks": {
            "official_sources_first": True,
            "major_media_second": True,
            "local_press_third_and_dynamic": True,
            "internal_link_scoped_to_site": True,
            "lineup_queries_cover_both_teams": True,
            "serper_selected_but_not_executed": True,
            "no_external_search": True,
            "drafting_blocked": True,
            "html_blocked": True,
            "publication_blocked": True,
        },
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("OK: planejamento de coleta de fontes validado sem busca externa.")
    print(f"Tarefas planejadas: {len(plan['tasks'])}")
    print("Ordem: fontes oficiais -> grandes veículos -> imprensa local relevante.")
    print("Provedor de busca selecionado: Serper (execução real ainda desligada).")
    print("Redação, HTML e publicação permanecem bloqueados.")


if __name__ == "__main__":
    main()
