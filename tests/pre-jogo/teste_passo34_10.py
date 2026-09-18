#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import extrair_fatos_openai as grounded
from scripts import ler_fontes_candidatas_passo34_10 as reader


def checked_source(title: str, segment: str) -> dict:
    return {
        "publisher": "Teste",
        "url": "https://example.com/bayern-union-2026",
        "domain": "example.com",
        "source_type": "major_sports_media",
        "published_hint": "2026-09-18",
        "content_checked": True,
        "eligible_for_factual_validation": True,
        "title": title,
        "page_evidence": {
            "metadata": {},
            "evidence_segments": [segment],
            "segment_count": 1,
        },
    }


def main() -> None:
    h2h_support = (
        "Nos últimos cinco confrontos diretos pela Bundesliga, o Bayern venceu três, "
        "com um empate e uma vitória do Union Berlin."
    )
    assert grounded.normalize_grounded_h2h_count("cinco", h2h_support) == "5"
    assert grounded.normalize_grounded_h2h_count("três", h2h_support) == "3"
    assert grounded.normalize_grounded_h2h_count("uma", h2h_support) == "1"
    assert grounded.normalize_grounded_h2h_count("um", h2h_support) == "1"
    assert grounded.normalize_grounded_h2h_count("sete", h2h_support) is None

    context = {
        "home": "FC Bayern München",
        "away": "1. FC Union Berlin",
        "competition": "Bundesliga",
        "competition_slug": "bundesliga",
    }

    current_stadium = checked_source(
        "FC Bayern München x 1. FC Union Berlin | Bundesliga 2026/27",
        "FC Bayern München recebe o 1. FC Union Berlin pela Bundesliga. "
        "O jogo será disputado na Allianz Arena em 18 de setembro de 2026.",
    )
    assert reader.stadium_source_is_current(
        current_stadium,
        context,
        target_year="2026",
    ) is True

    historical_venue = checked_source(
        "FC Bayern München x 1. FC Union Berlin | Bundesliga 2026/27",
        "No encontro mais recente, o Bayern venceu o Union Berlin por 4 a 0 "
        "na Allianz Arena em março de 2026.",
    )
    assert reader.stadium_source_is_current(
        historical_venue,
        context,
        target_year="2026",
    ) is False

    current_officiating = checked_source(
        "FC Bayern München x 1. FC Union Berlin | Bundesliga 2026/27",
        "FC Bayern München recebe o 1. FC Union Berlin pela Bundesliga em setembro de 2026. "
        "Schiedsrichter: Felix Zwayer.",
    )
    assert reader.officiating_source_is_current(
        current_officiating,
        context,
        target_year="2026",
    ) is True

    queries = reader._queries(
        "officiating",
        context,
        "2026-09-18",
    )
    assert any("Schiedsrichter" in item for item in queries)
    assert any("referee" in item for item in queries)

    article = {
        "requirements": [
            {
                "id": "competition_specific_head_to_head",
                "source_candidates": [
                    {
                        "source_type": "relevant_local_press",
                        "domain": "jornal-local.example",
                        "url": "https://jornal-local.example/bayern-union",
                    }
                ],
            }
        ]
    }
    assert reader._article_local_press_domains(article) == ["jornal-local.example"]

    print("OK: Passo 34.10 normaliza H2H literal e fecha estádio/arbitragem com contexto atual.")


if __name__ == "__main__":
    main()
