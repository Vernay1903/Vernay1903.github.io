#!/usr/bin/env python3
"""Teste determinístico dos extratores factuais seguros do Passo 23."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import extrair_fatos_estruturados as extractor  # noqa: E402
from scripts import preparar_pesquisa_factual as research  # noqa: E402

OUTPUT = ROOT / "build" / "pre-jogo" / "teste-extratores-multicampos.json"

MATCH_CONTEXT = {
    "home": "Arsenal",
    "away": "Manchester City",
    "competition": "Premier League",
}


def source(url: str, publisher: str, segments: list[str], source_type: str = "official") -> dict:
    return {
        "publisher": publisher,
        "url": url,
        "source_type": source_type,
        "domain": url.split("/")[2],
        "title": "Arsenal v Manchester City - Premier League",
        "checked_at": "2026-09-16T12:00:00-03:00",
        "content_checked": True,
        "verification_status": "page_checked_pending_fact_extraction",
        "eligible_for_factual_validation": True,
        "page_evidence": {
            "metadata": {"title": "Arsenal v Manchester City - Premier League"},
            "evidence_segments": segments,
            "segment_count": len(segments),
            "content_length": sum(len(item) for item in segments),
            "content_sha256": "simulado",
            "credits_used": 1,
        },
    }


def run_requirement(requirement_id: str, sources: list[dict]) -> dict:
    config = extractor.load_config()
    requirement = research.build_requirement(requirement_id, config=config)
    requirement["source_candidates"] = sources
    return extractor.extract_requirement(
        requirement,
        match_context=MATCH_CONTEXT,
        config=config,
    )


def main() -> None:
    config = extractor.load_config()
    assert extractor.ENABLED_EXTRACTORS == {
        "stadium_and_location",
        "transmission",
        "probable_lineups_and_coaches",
        "officiating",
        "recent_form_both_teams",
        "competition_specific_head_to_head",
        "stakes_and_qualification_scenarios_when_applicable",
    }

    transmission = run_requirement(
        "transmission",
        [source(
            "https://www.premierleague.com/example-transmission",
            "Premier League",
            ["Arsenal v Manchester City - Premier League | Transmissão: ESPN e Disney+"],
        )],
    )
    assert transmission["validator_accepted"] is True
    assert transmission["status"] == "verified"
    assert transmission["facts"][0]["field"] == "transmission"
    assert "ESPN" in transmission["facts"][0]["text"]

    transmission_conflict = run_requirement(
        "transmission",
        [
            source(
                "https://www.premierleague.com/example-transmission-a",
                "Premier League",
                ["Arsenal v Manchester City - Premier League | Transmissão: ESPN e Disney+"],
            ),
            source(
                "https://www.arsenal.com/example-transmission-b",
                "Arsenal",
                ["Arsenal v Manchester City - Premier League | Transmissão: TNT Sports"],
            ),
        ],
    )
    assert transmission_conflict["validator_accepted"] is False
    assert transmission_conflict["conflict_detected"] is True
    assert transmission_conflict["fact_extraction_status"] == "conflict_blocked"

    officiating = run_requirement(
        "officiating",
        [source(
            "https://www.premierleague.com/example-referee",
            "Premier League",
            ["Arsenal v Manchester City - Premier League | Árbitro: Michael Oliver"],
        )],
    )
    assert officiating["validator_accepted"] is True
    assert officiating["facts"][0]["field"] == "referee"
    assert "Michael Oliver" in officiating["facts"][0]["text"]

    lineups = run_requirement(
        "probable_lineups_and_coaches",
        [source(
            "https://www.premierleague.com/example-lineups",
            "Premier League",
            [
                "Arsenal — provável escalação: Raya; Timber; Saliba; Gabriel; Calafiori; Rice; Odegaard; Saka; Eze; Martinelli; Gyokeres",
                "Arsenal — técnico: Mikel Arteta",
                "Manchester City — provável escalação: Donnarumma; Lewis; Dias; Gvardiol; Ait-Nouri; Rodri; Reijnders; Foden; Cherki; Doku; Haaland",
                "Manchester City — técnico: Pep Guardiola",
            ],
        )],
    )
    assert lineups["validator_accepted"] is True
    assert lineups["status"] == "verified"
    assert {item["field"] for item in lineups["facts"]} == {
        "home_lineup", "home_coach", "away_lineup", "away_coach"
    }

    incomplete_lineups = run_requirement(
        "probable_lineups_and_coaches",
        [source(
            "https://www.arsenal.com/example-only-one-team",
            "Arsenal",
            [
                "Arsenal v Manchester City - Premier League",
                "Arsenal — provável escalação: Raya; Timber; Saliba; Gabriel; Calafiori; Rice; Odegaard; Saka; Eze; Martinelli; Gyokeres",
                "Arsenal — técnico: Mikel Arteta",
            ],
        )],
    )
    assert incomplete_lineups["validator_accepted"] is False
    assert incomplete_lineups["fact_extraction_status"] == "incomplete_structured_fact"
    assert "away_lineup" in incomplete_lineups["missing_fields"]

    recent_form = run_requirement(
        "recent_form_both_teams",
        [source(
            "https://www.premierleague.com/example-form",
            "Premier League",
            [
                "Arsenal — forma recente: V-V-E-V-D nos últimos cinco jogos",
                "Manchester City — forma recente: V-E-V-V-V nos últimos cinco jogos",
            ],
        )],
    )
    assert recent_form["validator_accepted"] is True
    assert {item["field"] for item in recent_form["facts"]} == {
        "home_recent_form", "away_recent_form"
    }

    h2h = run_requirement(
        "competition_specific_head_to_head",
        [source(
            "https://www.premierleague.com/example-h2h",
            "Premier League",
            [
                "Arsenal v Manchester City - Premier League",
                "Jogos: 20",
                "Vitórias Arsenal: 7",
                "Vitórias Manchester City: 10",
                "Empates: 3",
            ],
        )],
    )
    assert h2h["validator_accepted"] is True
    assert h2h["structured_fact_count"] == 4

    inconsistent_h2h = run_requirement(
        "competition_specific_head_to_head",
        [source(
            "https://www.premierleague.com/example-h2h-bad",
            "Premier League",
            [
                "Arsenal v Manchester City - Premier League",
                "Jogos: 20",
                "Vitórias Arsenal: 7",
                "Vitórias Manchester City: 10",
                "Empates: 4",
            ],
        )],
    )
    assert inconsistent_h2h["validator_accepted"] is False
    assert inconsistent_h2h["conflict_detected"] is True
    assert inconsistent_h2h["fact_extraction_status"] == "consistency_blocked"

    stakes = run_requirement(
        "stakes_and_qualification_scenarios_when_applicable",
        [source(
            "https://www.premierleague.com/example-stakes",
            "Premier League",
            [
                "Arsenal v Manchester City - Premier League | Cenário de classificação: uma vitória garante vaga na semifinal; em caso de empate no agregado, a decisão vai para os pênaltis"
            ],
        )],
    )
    assert stakes["validator_accepted"] is True
    assert stakes["facts"][0]["field"] == "qualification_scenario"

    attribution_blocked = run_requirement(
        "transmission",
        [source(
            "https://www.premierleague.com/example-attribution",
            "Premier League",
            ["Arsenal v Manchester City - Premier League | Transmissão: segundo o portal X, ESPN"],
        )],
    )
    assert attribution_blocked["validator_accepted"] is False
    assert attribution_blocked["fact_extraction_status"] == "incomplete_structured_fact"

    report = {
        "step": 23,
        "enabled_extractors": sorted(extractor.ENABLED_EXTRACTORS),
        "accepted_requirements": [
            "transmission",
            "officiating",
            "probable_lineups_and_coaches",
            "recent_form_both_teams",
            "competition_specific_head_to_head",
            "stakes_and_qualification_scenarios_when_applicable",
        ],
        "conflict_case_blocked": transmission_conflict["conflict_detected"],
        "incomplete_lineup_blocked": not incomplete_lineups["validator_accepted"],
        "inconsistent_h2h_blocked": not inconsistent_h2h["validator_accepted"],
        "attribution_language_blocked_from_fact": not attribution_blocked["validator_accepted"],
        "research_sources_internal_only": config["editorial"]["source_attribution_policy"]["research_sources_are_internal_only"],
        "ready_for_drafting": False,
        "ready_for_html": False,
        "publication_unlocked": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("OK: extratores factuais seguros do Passo 23 validados.")
    print("Transmissão, arbitragem, escalações, forma, H2H e cenário competitivo testados.")
    print("Conflito, incompletude, inconsistência e linguagem de atribuição bloqueiam promoção.")
    print("Redação, HTML e publicação permanecem bloqueados.")


if __name__ == "__main__":
    main()
