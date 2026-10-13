#!/usr/bin/env python3
"""A coleta gratuita precisa pesquisar AMBOS os clubes independentemente."""
from __future__ import annotations
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts import ler_fontes_candidatas_passo34_9 as research
from scripts import pesquisa_publica_gratuita as free

CTX = {"home": "AS Roma", "away": "Real Madrid", "competition": "Champions League",
       "kickoff_brasilia": "2026-10-14T16:00:00-03:00"}
REQ = [{"id": "stadium_and_location", "source_candidates": []}]

def run() -> None:
    for club in ("AS Roma", "Real Madrid"):
        searches = research._targeted_queries(
            research.EDITORIAL_RESEARCH_ID, CTX, "2026-10-14", team=club,
        )
        assert len(searches) >= 6
        assert any("allenamento" in x for x in searches)
        assert any("entraînement" in x for x in searches)
        assert all(club in x for x in searches)

    observed = []
    def mock_search(requirement_id, *, recent_team, **kwargs):
        observed.append((recent_team, free._RSS_REQUESTS))
        # Simula toda a cota consumida pela pesquisa do primeiro clube.
        free._RSS_REQUESTS = 60
        return []

    with patch.dict(os.environ, {"CDE_FREE_RESEARCH": "1"}), patch.object(
        research, "_search_and_check", side_effect=mock_search,
    ):
        free._RSS_REQUESTS = 59
        result = research._research_editorial_sources(
            REQ, context=CTX, article_date="2026-10-14",
            checked_at="2026-10-13T10:12:00-03:00", config={},
        )

    assert observed == [("AS Roma", 0), ("Real Madrid", 0)], observed
    assert result["editorial_team_coverage"] == {"home": 0, "away": 0}
    print("OK: buscas multilíngues independentes com cota gratuita por clube.")

if __name__ == "__main__":
    run()
