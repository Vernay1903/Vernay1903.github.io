#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import extrair_fatos_estruturados as facts
from scripts import estruturar_evidencias_candidatas as struct


def base_requirement(req_id: str, config: dict) -> dict:
    policy = config["research"]["requirement_policy"][req_id]
    return {
        "id": req_id,
        "required_for_drafting": bool(policy.get("required_for_drafting")),
        "conditional": bool(policy.get("conditional")),
        "allow_unavailable_after_check": bool(policy.get("allow_unavailable_after_check")),
        "status": "pending",
        "facts": [],
        "sources": [],
        "source_candidates": [],
    }


def checked_source() -> dict:
    return {
        "publisher": "Veículo local relevante",
        "url": "https://example.com/bayern-union-2026",
        "source_type": "relevant_local_press",
        "checked_at": "2026-09-18T10:00:00-03:00",
        "content_checked": True,
        "eligible_for_factual_validation": True,
        "title": "Bayern de Munique x Union Berlin - Bundesliga",
        "page_evidence": {
            "metadata": {},
            "evidence_segments": [
                (
                    "Bayern de Munique x Union Berlin - Bundesliga. "
                    "O Bayern de Munique venceu quatro de seus últimos cinco jogos em todas as competições, "
                    "com um empate. Sua partida mais recente foi uma vitória por 5 a 0. "
                    "O Union Berlin venceu um de seus últimos cinco jogos, empatou um e perdeu três. "
                    "Seu resultado mais recente foi a derrota por 3 a 1 para o Schalke na Bundesliga."
                ),
                (
                    "Bayern de Munique x Union Berlin - Bundesliga. Retrospecto do confronto. "
                    "Nos últimos cinco confrontos diretos, o Bayern venceu três, "
                    "com um empate e uma vitória do Union Berlin."
                ),
            ],
            "segment_count": 2,
        },
    }


def main() -> None:
    config = facts.load_config()
    context = {
        "home": "Bayern de Munique",
        "away": "1. FC Union Berlin",
        "competition": "Bundesliga",
        "competition_slug": "bundesliga",
    }
    source = checked_source()

    structured = struct.structure_article(
        {
            "title": "Bayern x Union",
            "slug": "bayern-union.html",
            "date": "18/09/2026",
            "fixture_id": 123,
            "match_context": context,
            "requirements": [],
            "editorial_input": {
                "excerpt": "Excerpt obrigatório preservado.",
                "noticias_entry": {
                    "title": "Bayern x Union",
                    "excerpt": "Excerpt obrigatório preservado.",
                    "url": "bayern-union.html",
                    "date": "18/09/2026",
                    "category": "Futebol",
                },
            },
        },
        None,
        discovered_at="2026-09-18T10:00:00-03:00",
        config=config,
    )
    assert structured["excerpt"] == "Excerpt obrigatório preservado."
    assert structured["noticias_entry"]["excerpt"] == "Excerpt obrigatório preservado."

    recent_req = base_requirement("recent_form_both_teams", config)
    h2h_req = base_requirement("competition_specific_head_to_head", config)
    h2h_req["source_candidates"] = [source]

    augmented = facts.augment_requirements_with_final_cross_evidence(
        [recent_req, h2h_req],
        match_context=context,
        config=config,
    )
    recent_aug = next(item for item in augmented if item["id"] == "recent_form_both_teams")
    assert recent_aug.get("passo34_11_reused_source_count") == 1
    assert len(recent_aug["source_candidates"]) == 1

    recent_result = facts.extract_recent_form_requirement(
        recent_aug,
        match_context=context,
        config=config,
    )
    assert recent_result["status"] == "verified", recent_result
    fields = {item["field"] for item in recent_result["facts"]}
    assert fields == {"home_recent_form", "away_recent_form"}, fields
    recent_text = {item["field"]: item["text"] for item in recent_result["facts"]}
    assert "quatro de seus últimos cinco jogos" in recent_text["home_recent_form"], recent_text
    assert "venceu um de seus últimos cinco jogos" in recent_text["away_recent_form"], recent_text
    assert "Retrospecto do confronto" not in recent_text["home_recent_form"], recent_text
    assert "confrontos diretos" not in recent_text["away_recent_form"], recent_text

    h2h_result = facts.extract_h2h_requirement(
        h2h_req,
        match_context=context,
        config=config,
    )
    assert h2h_result["status"] == "verified", h2h_result
    values = {
        item["field"]: item["text"]
        for item in h2h_result["facts"]
    }
    assert "5 jogos" in values["h2h_games"]
    assert values["h2h_home_wins"].endswith("3.")
    assert values["h2h_away_wins"].endswith("1.")
    assert values["h2h_draws"].endswith("1.")

    parsed = facts.natural_h2h_counts(
        source["page_evidence"]["evidence_segments"][1],
        home=context["home"],
        away=context["away"],
        config=config,
    )
    assert parsed == {
        "h2h_games": 5,
        "h2h_home_wins": 3,
        "h2h_away_wins": 1,
        "h2h_draws": 1,
    }

    print("OK: Passo 34.11 resolve forma recente bilateral e H2H natural com a evidência real do caso Bayern x Union.")


if __name__ == "__main__":
    main()
