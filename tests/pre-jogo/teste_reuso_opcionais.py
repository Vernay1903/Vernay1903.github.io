#!/usr/bin/env python3
"""Reuso de página atual do jogo para registrar lacunas opcionais sem inventar fatos."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import ler_fontes_candidatas_base as base

def main():
    src={
      "url":"https://example.com/preview","title":"Olympique de Marseille x PSG - Ligue 1 2026",
      "source_type":"major_sports_media","content_checked":True,
      "eligible_for_factual_validation":True,"checked_at":"2026-09-19T12:00:00-03:00",
      "page_evidence":{"metadata":{},"evidence_segments":[
          "Olympique de Marseille x PSG pela Ligue 1 em 20 de setembro de 2026."
      ]}
    }
    ctx={"home":"Olympique de Marseille","away":"PSG","competition":"Ligue 1",
         "kickoff_brasilia":"2026-09-20T15:45:00-03:00"}
    reqs=[
      {"id":"stadium_and_location","source_candidates":[src]},
      {"id":"transmission","source_candidates":[]},
      {"id":"probable_lineups_and_coaches","source_candidates":[]},
      {"id":"officiating","source_candidates":[]},
    ]
    out,count=base.reuse_checked_sources_across_requirements(reqs,context=ctx)
    by={r["id"]:r for r in out}
    assert count==3,count
    for rid in ("transmission","probable_lineups_and_coaches","officiating"):
        rows=by[rid]["source_candidates"]
        assert len(rows)==1 and rows[0]["url"]==src["url"],(rid,rows)
        assert rows[0]["passo34_6_cross_requirement_reuse"] is True

    bad={**src,"title":"PSG x Lyon - Ligue 1 2026",
         "page_evidence":{"metadata":{},"evidence_segments":["PSG x Lyon pela Ligue 1 em 2026."]}}
    out2,count2=base.reuse_checked_sources_across_requirements(
      [{"id":"stadium_and_location","source_candidates":[bad]},
       {"id":"officiating","source_candidates":[]}],context=ctx)
    assert count2==0 and out2[1]["source_candidates"]==[]
    print("OK: página atual do mesmo jogo pode fechar lacuna opcional; outro confronto não.")

if __name__=="__main__":
    main()
