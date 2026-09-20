#!/usr/bin/env python3
"""Teste offline: pesquisa esportiva recebe placares e escalações reais lidas do HTML."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import enriquecer_fatos_football_data as fd
from scripts import ler_fontes_candidatas_base as reader
from scripts import extrair_fatos_estruturados as facts
from scripts import buscar_fontes_serper as discover

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
    queries=discover.expanded_queries("probable_lineups_and_coaches",[
        '"Manchester City" "Sunderland AFC" provável escalação 20/09/2026'
    ],{"home":"Manchester City","away":"Sunderland AFC","competition":"Premier League"},"20/09/2026")
    assert any("2026" in q and "team news" in q for q in queries),queries
    assert any("desfalques" in q for q in queries)

    names_a=[f"Jogador Alfa{i}" for i in range(1,12)]
    names_b=[f"Jogador Beta{i}" for i in range(1,12)]
    content=(
      "Manchester City x Sunderland AFC pela Premier League, em 20/09/2026\n"
      "Provável Manchester City:\n"
      + "\n".join(names_a)
      + "\nTécnico: Exemplo Alfa\n"
      + "Provável Sunderland AFC:\n"
      + "\n".join(names_b)
      + "\nTécnico: Exemplo Beta"
    )
    segments=reader.extract_evidence_segments(
        content,"probable_lineups_and_coaches",max_segments=10,max_segment_chars=700
    )
    assert any("Provável Manchester City:" in s and names_a[-1] in s for s in segments),segments
    assert any("Provável Sunderland AFC:" in s and names_b[-1] in s for s in segments),segments

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
    assert names_a[0] in seen["home_lineup"] and names_a[-1] in seen["home_lineup"]
    assert names_b[0] in seen["away_lineup"] and names_b[-1] in seen["away_lineup"]
    assert not any("Jogador Gama" in str(x) for x in claims)
    print("OK: detalhes reais gratuitos, busca de 2026 e dois times com 11 nomes de HTML.")


if __name__=="__main__":
    main()
