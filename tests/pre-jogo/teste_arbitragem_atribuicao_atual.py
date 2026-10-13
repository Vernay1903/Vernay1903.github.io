#!/usr/bin/env python3
"""Regressões contra erro factual de árbitro e atribuição do adversário."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.extrair_fatos_estruturados import (
    current_referee_assignment,
    include_current_referee_sources,
    extract_officiating_requirement,
    extract_separate_competitive_context,
)
from scripts.qualidade_editorial_pre_jogo import meaningful_sporting_context
CFG = json.loads((ROOT / "config/pre-jogo.json").read_text(encoding="utf-8"))
CTX = {
    "home": "Fluminense", "away": "Palmeiras", "competition":"Libertadores",
    "competition_slug":"libertadores", "kickoff_brasilia":"2026-10-14T21:30:00-03:00",
}


def item(title, paragraph, slug):
    return {
        "title":title,"url":"https://www.terra.com.br/esportes/futebol/"+slug,
        "publisher":"Terra","source_type":"major_sports_media",
        "published_hint":"Mon, 12 Oct 2026 12:37:00 GMT",
        "checked_at":"2026-10-13T09:49:04-03:00",
        "content_checked":True,"eligible_for_factual_validation":True,
        "page_evidence":{"metadata":{},"evidence_segments":[paragraph]},
    }


def main():
    new = (
        "Facundo Tello será o árbitro de Fluminense x Palmeiras pela semifinal "
        "da Copa Libertadores da América em 14 de outubro de 2026."
    )
    old = (
        "A matéria lembra a arbitragem: Nazareno Jorge Arasa do jogo entre "
        "Fluminense e Palmeiras de 2025."
    )
    assert current_referee_assignment(new,CTX,CFG) == "Facundo Tello"
    assert current_referee_assignment(old,CTX,CFG) is None

    assignment = item("Facundo Tello apita Fluminense x Palmeiras",new,"tello-2026.html")
    history = item("Arbitragem: histórico de Fluminense x Palmeiras",old,"arbitragem-antiga.html")
    reqs = include_current_referee_sources([
        {"id":"stadium_and_location","source_candidates":[assignment]},
        {"id":"officiating","source_candidates":[history], "status":"pending",
         "facts":[],"sources":[],"required_for_drafting":True,
         "conditional":False,"allow_unavailable_after_check":True},
    ], match_context=CTX, config=CFG)
    assert any(s["url"] == assignment["url"] for s in reqs[1]["source_candidates"])
    result = extract_officiating_requirement(reqs[1],match_context=CTX,config=CFG)
    assert result["status"] == "verified",result
    assert result["facts"][0]["text"] == "Árbitro: Facundo Tello."

    other_side = (
        "O treinador, porém, será novamente desfalque na partida de ida "
        "da semifinal da Libertadores, contra o Fluminense, no Maracanã."
    )
    offside = item("Palmeiras inicia preparação para o Fluminense",
                   other_side,"palmeiras-coach-2026.html")
    context = extract_separate_competitive_context(
        [{"id":"probable_lineups_and_coaches","source_candidates":[offside]}],
        match_context=CTX, config=CFG,
    )
    assert context is None or all(
        not f["field"].startswith("home_stakes_") for f in context["facts"]
    ),"Fluminense é objeto de 'contra o'; o fato pertence ao Palmeiras"
    assert meaningful_sporting_context(
        "Savarino marcou três vezes e conseguiu seu primeiro hat-trick "
        "com a camisa do Fluminense na vitória sobre o Coritiba."
    )
    print("OK: árbitro atual sem nome de histórico; adversário não vira protagonista.")


if __name__ == "__main__":
    main()
