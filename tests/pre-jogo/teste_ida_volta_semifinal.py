#!/usr/bin/env python3
"""Regressão factual: 14/10 ida, 21/10 volta não podem ser confundidas."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import extrair_fatos_estruturados as facts


def main():
    config = facts.load_config()
    context = {
        "home": "Palmeiras", "away": "Fluminense",
        "competition_slug": "libertadores",
        "kickoff_brasilia": "2026-10-21T21:30:00-03:00",
    }
    current = {"title": "Palmeiras x Fluminense: árbitro para semifinal da Libertadores"}
    current_segment = (
        "A Conmebol escolheu Esteban Ostojich para o confronto de volta "
        "entre Palmeiras e Fluminense, pela semifinal da Libertadores. "
        "A partida está marcada para a quarta-feira (21)."
    )
    second = facts.verified_knockout_second_leg_segment(
        current_segment, context, config, current,
    )
    assert second and "jogo de volta da semifinal" in second, second
    previous = {"title": "Fluminense x Palmeiras: ida da semifinal da Libertadores"}
    first_segment = (
        "Fluminense e Palmeiras disputam o jogo de ida da semifinal da "
        "Libertadores, nesta quarta-feira (14)."
    )
    assert facts.verified_knockout_first_leg_segment(
        first_segment, context, config, previous,
    ) is None
    assert facts.verified_knockout_second_leg_segment(
        first_segment, context, config, previous,
    ) is None
    print("OK: ida não informa fase da volta; volta identificada por fonte atual.")


if __name__ == "__main__":
    main()
