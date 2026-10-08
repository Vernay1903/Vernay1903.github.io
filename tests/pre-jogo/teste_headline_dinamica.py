#!/usr/bin/env python3
"""Regressão: chamada dinâmica e ausência opcional não podem bloquear pré-jogo."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import montar_pacote_editorial as pack
from scripts import extrair_fatos_estruturados as facts


def main():
    config=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
    article={
      "title":"Santos FC x Flamengo pelo Brasileirão: transmissão, horário e prováveis escalações",
      "excerpt":"Santos FC e Flamengo se enfrentam em 8 de outubro de 2026, às 19h30 (de Brasília), pelo Brasileirão; veja transmissão, prováveis escalações e informações do confronto.",
    }
    lineup_facts=[
      {"field":"home_lineup","text":"Santos FC: A; B; C; D; E; F; G; H; I; J e K."},
      {"field":"away_lineup","text":"Flamengo: L; M; N; O; P; Q; R; S; T; U e V."},
      {"field":"home_coach","text":"Técnico do Santos FC: Técnico A."},
      {"field":"away_coach","text":"Técnico do Flamengo: Técnico B."},
    ]
    reqs={
      "transmission":{"id":"transmission","status":"unavailable_after_check","facts":[]},
      "probable_lineups_and_coaches":{"id":"probable_lineups_and_coaches","status":"verified","facts":lineup_facts},
    }
    title,excerpt=pack.adjusted_service_headline(article,reqs,config=config)
    assert "transmissão" not in title.casefold()
    assert "prováveis escalações" in title.casefold()
    assert "transmissão" not in excerpt.casefold()
    reqs["probable_lineups_and_coaches"]={"id":"probable_lineups_and_coaches","status":"unavailable_after_check","facts":[]}
    title2,excerpt2=pack.adjusted_service_headline(article,reqs,config=config)
    assert "transmissão" not in title2.casefold() and "escala" not in title2.casefold()
    assert "horário" in title2.casefold() and "informações do jogo" in title2.casefold()
    assert "informações do confronto" in excerpt2.casefold()

    gap={
      "id":"transmission","status":"pending","facts":[],"sources":[],
      "candidate_status":"no_candidates","candidate_source_count":0,
      "allow_unavailable_after_check":True,"conflict_detected":False,
    }
    resolved=facts.resolve_allowed_gap(gap,competition_slug="brasileirao",config=config)
    assert resolved["status"]=="unavailable_after_check"
    assert resolved["validator_accepted"] is True
    print("OK: chamada remove serviços não verificados e ausência opcional pesquisada não bloqueia a matéria.")


if __name__=="__main__":
    main()
