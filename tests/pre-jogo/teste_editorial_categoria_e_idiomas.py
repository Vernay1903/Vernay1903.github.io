#!/usr/bin/env python3
"""Reproduz perdas reais de contexto e evita importar notícia feminina."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import buscar_fontes_serper as discovery
from scripts.extrair_fatos_estruturados import (
    extract_individual_team_context, source_current_for_match,
)

cfg=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
ctx={"home":"Fluminense","away":"Palmeiras","competition":"Libertadores",
     "competition_slug":"libertadores","kickoff_brasilia":"2026-10-14T21:30:00-03:00"}
def src(title,seg,url,side="home"):
    return {
      "url":url,"title":title,"publisher":"UOL",
      "source_type":"major_sports_media","checked_at":"2026-10-13T10:38:52-03:00",
      "published_hint":"Sat, 10 Oct 2026 17:00:00 GMT",
      "content_checked":True,"eligible_for_factual_validation":True,
      "editorial_target_side":side,
      "editorial_target_team":ctx[side],
      "page_evidence":{"metadata":{},"evidence_segments":[seg]}
    }
def test():
    feminine=src(
      "Palmeiras deixa Kate Tapia fora da Libertadores Feminina",
      "O Palmeiras anunciou a goleira Kate Tapia fora da Libertadores Feminina por questões disciplinares.",
      "https://www.terra.com.br/esportes/palmeiras/2026/libertadores-feminina-kate-tapia.html",
      side="away",
    )
    assert not discovery.candidate_matches_match_category(feminine,ctx)
    assert not source_current_for_match(feminine,ctx)
    assert not extract_individual_team_context([{
       "id":"editorial_context_both_teams","source_candidates":[feminine],
    }],match_context=ctx,config=cfg)
    male=src(
      "Flamengo vence Fluminense no Maracanã em clássico",
      "O Fluminense, que poupou alguns titulares de olho na semifinal da Copa Libertadores, parou nos 51 pontos, mas segue na terceira colocação do Brasileirão.",
      "https://www.uol.com.br/esporte/futebol/ultimas-noticias/2026/10/11/flamengo-vence-fluminense.htm",
    )
    assert source_current_for_match(male,ctx)
    evidence=extract_individual_team_context([{
      "id":"editorial_context_both_teams","source_candidates":[male]
    }],match_context=ctx,config=cfg)
    assert evidence and evidence["status"]=="verified", evidence
    assert any(f["field"].startswith("home_stakes_") for f in evidence["facts"])
    french=src(
      "Le PSG prépare son prochain match avec plusieurs titulaires",
      "Le PSG a repris l'entraînement collectif et son entraîneur prépare une nouvelle organisation avant la Ligue des champions.",
      "https://www.lequipe.fr/Football/2026/10/12/psg-entrainement.html",
      side="away",
    )
    assert source_current_for_match(french,ctx)
    print("OK: editorial identifica Fluminense; bloqueia categoria feminina e reconhece francês.")

if __name__=="__main__":
    test()
