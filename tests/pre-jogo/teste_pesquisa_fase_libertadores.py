#!/usr/bin/env python3
"""Regressão: pesquisa dedicada só aceita fase explícita na página checada."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import ler_fontes_candidatas_passo34_9 as research
from scripts.extrair_fatos_estruturados import verified_knockout_first_leg_segment

RID = "stakes_and_qualification_scenarios_when_applicable"
CTX = {"home": "Fluminense", "away": "Palmeiras",
       "competition": "Libertadores", "competition_slug": "libertadores",
       "kickoff_brasilia": "2026-10-14T21:30:00-03:00"}
CONFIG = {"research": {"page_reader": {
    "max_segments_per_source": 10, "max_segment_chars": 700}}}

def check():
    assert RID in research.CRITICAL_REQUIREMENTS
    queries = research._targeted_queries(RID, CTX, "2026-10-14")
    assert len(queries) >= 3
    assert all("Fluminense" in q and "Palmeiras" in q for q in queries)
    assert any("semifinal" in q for q in queries)
    candidate = {
        "url": "https://example.com/partida/fase",
        "title": "Fluminense x Palmeiras: ida da semifinal da Libertadores",
        "published_hint": "Mon, 12 Oct 2026 09:00:00 GMT",
        "source_type": "sports_news",
    }
    content = (
        "Fluminense e Palmeiras disputam nesta quarta-feira a primeira partida "
        "da semifinal da Libertadores, jogo de ida da disputa pela vaga na final."
    )
    row = research._build_checked_source(
        candidate, {"text": content}, requirement_id=RID,
        context=CTX, target_year="2026", checked_at="2026-10-13T10:20:00-03:00",
        config=CONFIG,
    )
    assert row and row["content_checked"] is True, row
    segment = row["page_evidence"]["evidence_segments"][0]
    value = verified_knockout_first_leg_segment(segment, CTX, {})
    assert value and "jogo de ida da semifinal" in value, segment
    not_phase = research._build_checked_source(
        candidate, {"text": "Fluminense recebe o Palmeiras em uma partida de futebol."},
        requirement_id=RID, context=CTX, target_year="2026",
        checked_at="2026-10-13T10:20:00-03:00", config=CONFIG,
    )
    assert not_phase is None, "Título SEO isolado não comprova fase do jogo"
    print("OK: pesquisa específica comprova fase em texto integral; rejeita falta de evidência.")

if __name__ == "__main__":
    check()
