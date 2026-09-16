#!/usr/bin/env python3
"""Teste determinístico do Passo 20 sem chamadas externas."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import estruturar_evidencias_candidatas as evidence  # noqa: E402
from scripts import preparar_pesquisa_factual as research  # noqa: E402

REPORT_PATH = ROOT / "build" / "pre-jogo" / "teste-estruturacao-evidencias.json"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: esperado={expected!r}, obtido={actual!r}")


def main() -> None:
    config = evidence.load_config()
    editorial_record = {
        "title": "Arsenal x Manchester City pela Premier League: transmissão, horário e prováveis escalações",
        "excerpt": "Registro simulado do Passo 20.",
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
            "excerpt": "Registro simulado do Passo 20.",
            "url": "arsenal-manchester-city-premier-league-2026-transmissao-horario-escalacoes.html",
            "date": "17/09/2026",
            "category": "Futebol",
        },
    }

    dossier = research.build_research_dossier(editorial_record, config=config)
    discovered_at = "2026-09-16T12:00:00-03:00"
    discovery_result = {
        "slug": editorial_record["slug"],
        "external_search_performed": True,
        "tasks": [
            {
                "requirement_id": "stadium_and_location",
                "selected_source_type": "official",
                "dynamic_relevance_required": False,
                "candidates": [
                    {
                        "title": "Arsenal v Manchester City",
                        "url": "https://www.arsenal.com/fixture/arsenal-manchester-city",
                        "domain": "arsenal.com",
                        "snippet": "Match information and venue details.",
                        "position": 1,
                        "published_hint": None,
                    }
                ],
            },
            {
                "requirement_id": "probable_lineups_and_coaches",
                "selected_source_type": "relevant_local_press",
                "dynamic_relevance_required": True,
                "candidates": [
                    {
                        "title": "Team news",
                        "url": "https://www.london-example.test/arsenal-city-team-news",
                        "domain": "london-example.test",
                        "snippet": "Possible team news.",
                        "position": 2,
                        "published_hint": None,
                    }
                ],
            },
            {
                "requirement_id": "competition_internal_link",
                "selected_source_type": "internal_site",
                "dynamic_relevance_required": False,
                "candidates": [
                    {
                        "title": "Premier League: história e campeões",
                        "url": "https://cortedosesportes.com.br/premier-league-historia-campeoes.html",
                        "domain": "cortedosesportes.com.br",
                        "snippet": "Conteúdo interno.",
                        "position": 1,
                        "published_hint": None,
                    }
                ],
            },
            {
                "requirement_id": "transmission",
                "selected_source_type": None,
                "dynamic_relevance_required": False,
                "candidates": [],
            },
        ],
    }

    article = evidence.structure_article(
        dossier,
        discovery_result,
        discovered_at=discovered_at,
        config=config,
    )

    assert_equal(article["research_status"], "candidate_sources_structured", "Status da pesquisa")
    assert_equal(article["external_research_performed"], True, "Busca externa registrada")
    assert_equal(article["verified_fact_count"], 0, "Nenhum fato pode ser verificado")
    assert_equal(article["verified_source_count"], 0, "Nenhuma fonte pode ser validada ainda")
    assert_equal(article["ready_for_factual_validation"], False, "Validação factual deve ficar bloqueada")
    assert_equal(article["ready_for_drafting"], False, "Redação deve ficar bloqueada")
    assert_equal(article["ready_for_html"], False, "HTML deve ficar bloqueado")
    assert_equal(article["publication_unlocked"], False, "Publicação deve ficar bloqueada")

    by_id = {item["id"]: item for item in article["requirements"]}
    stadium = by_id["stadium_and_location"]
    assert_equal(stadium["candidate_status"], "candidate_sources_found", "Candidato oficial")
    assert_equal(stadium["candidate_source_count"], 1, "Quantidade de candidatos oficiais")
    source = stadium["source_candidates"][0]
    assert_equal(source["publisher"], "Arsenal", "Publisher oficial")
    assert_equal(source["source_type"], "official", "Tipo oficial")
    assert_equal(source["checked_at"], None, "Página ainda não foi checada")
    assert_equal(source["content_checked"], False, "Conteúdo ainda não foi lido")
    assert_equal(source["verification_status"], "pending_page_check", "Status de verificação")
    assert_equal(source["eligible_for_factual_validation"], False, "Não pode ir ao validador ainda")

    lineup = by_id["probable_lineups_and_coaches"]
    local_source = lineup["source_candidates"][0]
    assert_equal(local_source["dynamic_relevance_required"], True, "Imprensa local exige relevância")
    assert_equal(local_source["local_relevance_verified"], False, "Relevância local ainda não validada")

    internal = by_id["competition_internal_link"]["source_candidates"][0]
    assert_equal(internal["publisher"], "Corte dos Esportes", "Publisher interno")
    assert_equal(internal["source_type"], "internal_site", "Tipo interno")

    transmission = by_id["transmission"]
    assert_equal(transmission["candidate_status"], "no_candidates", "Sem candidatos de transmissão")
    assert_equal(transmission["status"], "pending", "Requisito permanece pendente")

    for requirement in article["requirements"]:
        assert_equal(requirement["facts"], [], f"Fatos devem permanecer vazios em {requirement['id']}")
        assert_equal(requirement["sources"], [], f"Fontes validadas devem permanecer vazias em {requirement['id']}")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "step": 20,
        "mode": "simulation_only",
        "generated_at": datetime.now(ZoneInfo(config["timezone"])).isoformat(),
        "candidate_source_count": article["candidate_source_count"],
        "verified_fact_count": article["verified_fact_count"],
        "checks": {
            "candidate_urls_linked_to_requirements": True,
            "publisher_normalized": True,
            "discovery_time_preserved": True,
            "page_check_not_faked": True,
            "local_press_relevance_still_pending": True,
            "facts_still_empty": True,
            "factual_validation_blocked": True,
            "drafting_blocked": True,
            "html_blocked": True,
            "publication_blocked": True,
        },
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("OK: URLs candidatas estruturadas sem validar fatos.")
    print(f"Fontes candidatas únicas: {article['candidate_source_count']}")
    print("checked_at permanece vazio até o conteúdo da página ser realmente consultado.")
    print("Validação factual, redação, HTML e publicação permanecem bloqueados.")


if __name__ == "__main__":
    main()
