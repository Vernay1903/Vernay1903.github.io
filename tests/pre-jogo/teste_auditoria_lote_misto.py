#!/usr/bin/env python3
"""Jogo sem notícia não pode tornar inelegível outra pauta realmente aprovada."""
from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.diagnosticar_coleta_pre_jogo import assess_editorial_lot

def check():
    packages = {"articles": [
        {"slug": "jogo-verdadeiramente-apto.html", "ready_for_drafting": True,
         "unresolved_required_requirement_ids": []},
        {"slug": "jogo-com-contexto-insuficiente.html", "ready_for_drafting": True,
         "unresolved_required_requirement_ids": []},
        {"slug": "jogo-sem-fatos.html", "ready_for_drafting": False,
         "unresolved_required_requirement_ids": ["probable_lineups_and_coaches"]},
    ]}
    def depth(article):
        return ["faltam fatos atuais de ambos os clubes"] if article["slug"].startswith(
            "jogo-com-contexto"
        ) else []
    with patch("scripts.diagnosticar_coleta_pre_jogo.source_depth_errors", side_effect=depth):
        approved, blocked = assess_editorial_lot(packages)
        assert approved == 1, approved
        assert len(blocked) == 2
        assert blocked[0]["editorial_depth"], blocked
        assert blocked[1]["unresolved"], blocked
        only_blocked = {"articles": packages["articles"][1:]}
        assert assess_editorial_lot(only_blocked)[0] == 0
    print("OK: lote misto pode prosseguir apenas com pauta aprovada; zero aptas continua falha.")

if __name__ == "__main__":
    check()
