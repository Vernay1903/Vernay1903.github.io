#!/usr/bin/env python3
"""Teste offline: pesquisa esportiva recebe placares e escalações reais lidas do HTML."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import enriquecer_fatos_football_data as fd
from scripts import ler_fontes_candidatas_base as reader
from scripts import extrair_fatos_estruturados as facts
from scripts import buscar_fontes_serper as discover
from scripts import pesquisa_publica_gratuita as public

def game(date,h,a,hg,ag,status="FINISHED"):
    return {
      "utcDate":date.isoformat(),"status":status,
      "homeTeam":{"id":h,"name":"Manchester City FC" if h==65 else "Sunderland AFC",
                  "shortName":"Manchester City" if h==65 else "Sunderland"},
      "awayTeam":{"id":a,"name":"Manchester City FC" if a==65 else "Sunderland AFC",
                  "shortName":"Manchester City" if a==65 else "Sunderland"},
      "competition":{"code":"PL","name":"Premier League"},
      "score":{"fullTime":{"home":hg,"away":ag}},
    }

def main():
    config=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
    now=datetime.now(timezone.utc)
    cutoff=now+timedelta(days=10)
    rows=[game(now-timedelta(days=2),65,71,2,1),
          game(now-timedelta(days=3),71,65,0,3),
          game(now+timedelta(days=2),65,71,4,1)]
    details=fd.recent_match_details({"matches":rows},65,cutoff)
    assert "Manchester City 2 x 1 Sunderland" in details,details
    assert "Sunderland 0 x 3 Manchester City" in details,details
    assert "4 x 1" not in details
    assert fd.recent_match_details({"matches":[rows[0]]},65,cutoff) is None
    # Se uma matéria já tem V/E/D checados na imprensa, a API deve complementar
    # com placares reais sem gastar busca extra e sem apagar a evidência anterior.
    checked_at=datetime.now(timezone.utc).isoformat()
    verified={
      "id":"recent_form_both_teams","status":"verified","conflict_detected":False,
      "facts":[
        {"field":"home_recent_form","text":"Forma recente do Manchester City: 2 vitórias."},
        {"field":"away_recent_form","text":"Forma recente do Sunderland: 2 derrotas."},
      ],
      "sources":[{
        "publisher":"Imprensa teste","url":"https://example.com/form",
        "source_type":"major_sports_media","checked_at":checked_at,
      }],
    }
    assert fd.append_verified_recent_results(
      verified,[{"field":"home_recent_matches","text":"Resultados recentes: "+details+"."}],
      ["https://api.football-data.org/v4/teams/65/matches?status=FINISHED&limit=5"],
      checked_at,config,
    )["status"]=="verified"
    queries=discover.expanded_queries("probable_lineups_and_coaches",[
        '"Manchester City" "Sunderland AFC" provável escalação 20/09/2026'
    ],{"home":"Manchester City","away":"Sunderland AFC","competition":"Premier League"},"20/09/2026")
    assert any("2026" in q and "team news" in q for q in queries),queries
    assert any("desfalques" in q for q in queries)

    # RSS deve ler primeiro página da partida e não notícia lateral de um clube.
    candidates=[
      {"title":"Manchester City: training", "url":"https://example.com/city-training",
       "snippet":"Premier League 2026"},
      {"title":"Manchester City x Sunderland AFC preview 2026",
       "url":"https://example.com/man-city-sunderland-preview", "snippet":"Matchday"},
      {"title":"Manchester City x Sunderland AFC prováveis escalações 2026",
       "url":"https://example.com/man-city-sunderland-lineups", "snippet":"Escalações"},
    ]
    old=os.environ.get("CDE_FREE_RESEARCH")
    os.environ["CDE_FREE_RESEARCH"]="1"
    try:
        prioritized=discover.filter_results_for_requirement(
            "probable_lineups_and_coaches",candidates,
            context={"home":"Manchester City","away":"Sunderland AFC",
                     "kickoff_brasilia":"2026-09-27T15:00:00-03:00"},
            config=config,
        )
        assert len(prioritized)==2,prioritized
        assert prioritized[0]["url"].endswith("lineups"),prioritized
    finally:
        if old is None:
            os.environ.pop("CDE_FREE_RESEARCH",None)
        else:
            os.environ["CDE_FREE_RESEARCH"]=old

    names_a=[f"Jogador Alfa{i}" for i in range(1,12)]
    names_b=[f"Jogador Beta{i}" for i in range(1,12)]
    markup=(
      "<main><h1>Manchester City x Sunderland AFC pela Premier League, 20/09/2026</h1>"
      "<h2>Provável Manchester City:</h2><ul>"
      + "".join(f"<li>{name}</li>" for name in names_a)
      + "<li>Técnico: Exemplo Alfa</li></ul>"
      + "<h2>Provável Sunderland AFC:</h2><ul>"
      + "".join(f"<li>{name}</li>" for name in names_b)
      + "<li>Técnico: Exemplo Beta</li></ul></main>"
    )
    parser=public.TextExtractor()
    parser.feed(markup)
    parser.flush()
    for name in names_a+names_b:
        assert name in parser.lines,("HTML omitiu o atleta",name,parser.lines)
    content="\n".join(parser.lines)
    segments=reader.extract_evidence_segments(
        content,"probable_lineups_and_coaches",max_segments=10,max_segment_chars=700
    )
    assert any("Provável Manchester City:" in s and names_a[-1] in s for s in segments),segments
    assert any("Provável Sunderland AFC:" in s and names_b[-1] in s for s in segments),segments
    assert any("Provável Manchester City" in s and "Técnico: Exemplo Alfa" in s for s in segments)
    assert any("Provável Sunderland AFC" in s and "Técnico: Exemplo Beta" in s for s in segments)

    requirement={
      "id":"probable_lineups_and_coaches",
      "source_candidates":[{
        "title":"Manchester City x Sunderland AFC: Premier League 2026",
        "publisher":"Veículo esportivo teste",
        "source_type":"major_sports_media",
        "url":"https://example.com/editorial",
        "checked_at":"2026-09-20T00:00:00-03:00",
        "content_checked":True,"eligible_for_factual_validation":True,
        "page_evidence":{"metadata":{"title":"Manchester City x Sunderland AFC Premier League 2026"},
                         "evidence_segments":segments},
      }]
    }
    context={"home":"Manchester City","away":"Sunderland AFC","competition":"Premier League"}
    value=facts.extract_lineups_requirement(requirement,match_context=context,config=config)
    claims=value.get("extracted_claims",[])
    seen={p["field"]:p["value"] for p in claims}
    assert "home_lineup" in seen,seen
    assert "away_lineup" in seen,seen
    assert "home_coach" in seen and seen["home_coach"]=="Exemplo Alfa",seen
    assert "away_coach" in seen and seen["away_coach"]=="Exemplo Beta",seen
    assert value["status"] == "verified",value.get("validator_errors",value)
    assert names_a[0] in seen["home_lineup"] and names_a[-1] in seen["home_lineup"]
    assert names_b[0] in seen["away_lineup"] and names_b[-1] in seen["away_lineup"]
    assert not any("Jogador Gama" in str(x) for x in claims)
    print("OK: detalhes reais gratuitos, busca de 2026 e dois times com 11 nomes de HTML.")


if __name__=="__main__":
    main()
