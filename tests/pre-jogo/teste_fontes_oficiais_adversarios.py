#!/usr/bin/env python3
"""A pesquisa oficial cobre adversários sem monitoramento próprio."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.ler_fontes_candidatas_passo34_8 import _allowed_stage_domains
CONFIG = json.loads((ROOT / "config/pre-jogo.json").read_text(encoding="utf-8"))

def check():
    cases = [
        ({"home": "AS Roma", "away": "Real Madrid", "competition_slug": "champions-league"},
         {"asroma.com", "realmadrid.com"}),
        ({"home": "Fluminense", "away": "Palmeiras", "competition_slug": "libertadores"},
         {"fluminense.com.br", "palmeiras.com.br"}),
        ({"home": "Manchester City", "away": "PSG", "competition_slug": "champions-league"},
         {"mancity.com", "psg.fr"}),
    ]
    for context, expected in cases:
        stages = _allowed_stage_domains(context, CONFIG)
        official = next((set(domains) for kind, domains in stages if kind == "official"), set())
        assert expected.issubset(official), (context, official)
    print("OK: pesquisa oficial encontra clubes monitorados e adversários não monitorados.")

if __name__ == "__main__":
    check()
