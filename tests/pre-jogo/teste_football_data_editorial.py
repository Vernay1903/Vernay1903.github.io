#!/usr/bin/env python3
"""Regressão dos fatos gratuitos vindos do football-data.org."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import enriquecer_evidencias_football_data as fd

def m(hid,aid,hg,ag,code="PL"):
    return {"homeTeam":{"id":hid,"name":"Home FC"},"awayTeam":{"id":aid,"name":"Away FC"},
            "score":{"fullTime":{"home":hg,"away":ag}},"competition":{"code":code}}

def main():
    rows=[m(1,9,2,0),m(8,1,1,1),m(1,7,0,1),m(6,1,0,3),m(1,5,4,2)]
    seg=fd.recent_form_segment("Arsenal",rows,1)
    assert seg and "venceu 3" in seg and "empatou 1" in seg and "perdeu 1" in seg, seg

    h2h=[m(1,2,2,0),m(2,1,1,1),m(1,2,0,3),m(1,2,1,1),m(1,2,5,0,"CL")]
    h=fd.h2h_segment("Arsenal","Manchester City","Premier League",h2h,"PL",1,2)
    assert h and "Jogos: 4" in h and "Arsenal: 1" in h and "Manchester City: 1" in h and "Empates: 2" in h, h
    assert fd.h2h_segment("Arsenal","Manchester City","Premier League",[m(1,2,2,0,"CL")],"PL",1,2) is None
    src=fd.source("https://api.football-data.org/v4/test","Football-Data.org","2026-09-19T10:00:00-03:00",h)
    assert src["source_type"]=="structured_data_provider"
    assert src["eligible_for_factual_validation"] is True
    assert src["page_evidence"]["credits_used"]==0
    print("OK: Football-Data só cria forma/H2H determinísticos e gratuitos.")

if __name__=="__main__":
    main()
