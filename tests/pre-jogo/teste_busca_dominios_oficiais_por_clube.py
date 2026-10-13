#!/usr/bin/env python3
"""Notícias oficiais devem ser pesquisadas no site do clube correspondente."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.ler_fontes_candidatas_passo34_9 import (
    EDITORIAL_RESEARCH_ID, _source_stages_for_team,
)

CFG = json.loads((ROOT / "config/pre-jogo.json").read_text(encoding="utf-8"))

def check():
    for home, away, expected in (
        ("AS Roma", "Real Madrid", ("asroma.com", "realmadrid.com")),
        ("Manchester City", "PSG", ("mancity.com", "psg.fr")),
        ("Fluminense", "Palmeiras", ("fluminense.com.br", "palmeiras.com.br")),
    ):
        ctx = {"home": home, "away": away, "competition_slug": "libertadores"}
        for club, required in ((home, expected[0]), (away, expected[1])):
            stages = _source_stages_for_team(
                EDITORIAL_RESEARCH_ID, context=ctx, config=CFG,
                recent_team=club,
            )
            official = next((v for kind, v in stages if kind == "official"), [])
            assert official == [required], (club, official)
            assert any(kind == "major_sports_media" for kind, _ in stages)
        non_editorial = _source_stages_for_team(
            "officiating", context=ctx, config=CFG, recent_team=home,
        )
        official = next((v for kind, v in non_editorial if kind == "official"), [])
        assert set(expected).issubset(official)
    print("OK: pesquisa editorial oficial restrita a cada clube; serviço do jogo preservado.")

if __name__ == "__main__":
    check()
