#!/usr/bin/env python3
"""Contexto extra: desfalques/retornos verificados sem inferir a equipe ausente."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import extrair_fatos_estruturados as facts
from scripts import planejar_coleta_fontes as planner
from scripts import buscar_fontes_serper as search

def source(segments):
    return {
      "publisher":"Veículo teste","url":"https://example.com/preview",
      "source_type":"major_sports_media","checked_at":"2026-09-26T10:00:00-03:00",
      "content_checked":True,"eligible_for_factual_validation":True,
      "title":"Manchester City x Sunderland AFC: Premier League 2026",
      "page_evidence":{"metadata":{"title":"Manchester City x Sunderland AFC 2026"},
                       "evidence_segments":segments},
    }

def main():
    config=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
    assert "team_news_and_availability" in config["editorial"]["research_requirements"]
    assert config["research"]["requirement_policy"]["team_news_and_availability"]["required_for_drafting"] is False
    context={"home":"Manchester City","away":"Sunderland AFC","competition":"Premier League",
             "competition_slug":"premier-league","kickoff_brasilia":"2026-09-27T15:00:00-03:00"}
    queries=planner.query_variants("team_news_and_availability",context,"27/09/2026")
    assert len(queries)>=3 and any("desfalques" in q for q in queries)
    expanded=search.expanded_queries("team_news_and_availability",queries,context,"27/09/2026")
    assert any("team news" in q for q in expanded)

    req={"id":"team_news_and_availability","required_for_drafting":False,"conditional":True,
         "allow_unavailable_after_check":True,
         "source_candidates":[source([
           "Manchester City terá o retorno de Rodri após recuperação de lesão para o jogo contra o Sunderland AFC.",
           "Sunderland AFC não contará com Jogador Teste, suspenso, diante do Manchester City.",
         ])]}
    result=facts.extract_team_news_requirement(req,match_context=context,config=config)
    assert result["status"]=="verified",result
    fields={x["field"]:x["text"] for x in result["facts"]}
    assert "Rodri" in fields["home_team_news"] and "suspenso" in fields["away_team_news"]

    one=json.loads(json.dumps(req))
    one["source_candidates"]=[source([
      "Manchester City terá o retorno de Rodri após recuperação de lesão contra o Sunderland AFC."
    ])]
    partial=facts.extract_team_news_requirement(one,match_context=context,config=config)
    assert partial["status"]=="verified"
    assert [x["field"] for x in partial["facts"]]==["home_team_news"]

    unrelated=json.loads(json.dumps(req))
    unrelated["source_candidates"]=[source([
      "Manchester City terá retorno importante no próximo compromisso."
    ])]
    pending=facts.extract_team_news_requirement(unrelated,match_context=context,config=config)
    assert pending["status"]=="pending"
    print("OK: team news opcional só entra quando explicitamente sustentado pela página do confronto.")

if __name__=="__main__":
    main()
