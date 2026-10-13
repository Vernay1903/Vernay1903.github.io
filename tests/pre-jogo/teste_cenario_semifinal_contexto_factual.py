#!/usr/bin/env python3
"""Regressão do bloqueio real da semifinal Fluminense x Palmeiras (14/10/2026).

Dados sintéticos reproduzem trechos de páginas checadas; nenhuma chamada externa,
publicação ou redator é executado.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.extrair_fatos_estruturados import (
    extract_separate_competitive_context,
    extract_stakes_requirement,
    include_checked_first_leg_sources,
    source_current_for_match,
    verified_knockout_first_leg_segment,
)

CONFIG = json.loads((ROOT / "config/pre-jogo.json").read_text(encoding="utf-8"))
CTX = {
    "home": "Fluminense",
    "away": "Palmeiras",
    "competition": "Libertadores",
    "competition_slug": "libertadores",
    "kickoff_brasilia": "2026-10-14T21:30:00-03:00",
}

def source(segment: str, title: str, pub: str = "Wed, 07 Oct 2026 17:22:00 GMT"):
    return {
        "url": "https://www.terra.com.br/esportes/futebol/semifinal-fluminense-palmeiras.html",
        "title": title, "published_hint": pub,
        "source_type": "major_sports_media",
        "publisher": "Terra",
        "checked_at": "2026-10-13T08:17:32-03:00",
        "content_checked": True, "eligible_for_factual_validation": True,
        "page_evidence": {"metadata": {}, "evidence_segments": [segment]},
    }


def main():
    explicit = (
        "Facundo Tello será o árbitro de Fluminense x Palmeiras, dia 14, às 21h30, "
        "no Maracanã, pela ida da semifinal da Copa Libertadores da América."
    )
    candidate = source(explicit, "Facundo Tello apita Fluminense x Palmeiras")
    assert source_current_for_match(candidate, CTX), "Data RSS recente já basta para comprovar atualidade"
    assert verified_knockout_first_leg_segment(explicit, CTX, CONFIG) == (
        "Fluminense e Palmeiras disputam o jogo de ida da semifinal da Libertadores"
    )
    staged = include_checked_first_leg_sources([
        {"id": "probable_lineups_and_coaches", "source_candidates": [candidate]},
        {"id": "stakes_and_qualification_scenarios_when_applicable",
         "source_candidates": [], "status": "pending", "facts": [], "sources": [],
         "required_for_drafting": True, "conditional": True,
         "allow_unavailable_after_check": False},
    ], match_context=CTX, config=CONFIG)
    req = staged[1]
    assert len(req["source_candidates"]) == 1, "Reusar apenas conteúdo já lido"
    result = extract_stakes_requirement(req, match_context=CTX, config=CONFIG)
    assert result["status"] == "verified", result.get("validator_errors", result)
    assert len(result["facts"]) == 1
    assert "jogo de ida da semifinal" in result["facts"][0]["text"]

    old = source(explicit, "Facundo Tello apita Fluminense x Palmeiras",
                 pub="Wed, 07 Oct 2020 17:22:00 GMT")
    assert not source_current_for_match(old, CTX)
    assert not include_checked_first_leg_sources([
        {"id":"stakes_and_qualification_scenarios_when_applicable", "source_candidates":[]},
        {"id":"probable_lineups_and_coaches","source_candidates":[old]},
    ], match_context=CTX, config=CONFIG)[0]["source_candidates"]

    # Histórico de arbitragem não é situação competitiva do Palmeiras.
    historical = (
        "Tello comandou a final brasileira entre Atlético-MG e Botafogo e a "
        "semifinal entre LDU e Palmeiras em 2025."
    )
    referee_source = source(historical, "Árbitro de Fluminense x Palmeiras já apitou duas Copas",
                            pub="Mon, 12 Oct 2026 12:37:00 GMT")
    assert extract_separate_competitive_context([
        {"id":"probable_lineups_and_coaches", "source_candidates":[referee_source]},
    ], match_context=CTX, config=CONFIG) is None

    # Nem semifinal de outro ano nem jogo de volta é prova de primeira perna atual.
    for irrelevant in (
        "LDU e Palmeiras se enfrentaram pela ida da semifinal da Libertadores em 2025.",
        "Fluminense e Palmeiras disputam a volta da semifinal da Libertadores em 2026.",
        "Fluminense enfrenta Flamengo pela ida da semifinal da Libertadores em 2026.",
    ):
        assert verified_knockout_first_leg_segment(irrelevant, CTX, CONFIG) is None

    print("OK: ida de semifinal verificada; árbitro/histórico antigo não viram contexto competitivo.")


if __name__ == "__main__":
    main()
