#!/usr/bin/env python3
"""Notícias factuais sobre clube não exigem substantivos vitória/derrota."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.ler_fontes_candidatas_passo34_9 import EDITORIAL_SIGNALS
from scripts.extrair_fatos_estruturados import EDITORIAL_TEAM_SIGNALS, normalize_text
from scripts.qualidade_editorial_pre_jogo import meaningful_sporting_context

def check():
    sentences = [
        "Fluminense perdeu para o Flamengo no Maracanã e iniciou a semana em busca de recuperação no Campeonato Brasileiro.",
        "Roma venceu seu último compromisso e retomou a preparação para o duelo de quarta-feira pela Champions League.",
        "Manchester City lost its latest match before returning to training for the next Champions League fixture.",
    ]
    for sentence in sentences:
        folded = normalize_text(sentence)
        assert any(s in folded for s in EDITORIAL_SIGNALS), sentence
        assert re.search(EDITORIAL_TEAM_SIGNALS, folded), sentence
        assert meaningful_sporting_context(sentence), sentence

    service = "Fluminense x Palmeiras: veja onde assistir ao vivo nesta quarta-feira e prováveis escalações"
    assert not any(s in normalize_text(service) for s in (
        "venceu", "perdeu", "perde", "ganhou", "won", "lost", "beat"
    ))
    print("OK: reconhece vitórias e derrotas concretas; serviço de jogo não vira pauta.")

if __name__ == "__main__":
    check()
