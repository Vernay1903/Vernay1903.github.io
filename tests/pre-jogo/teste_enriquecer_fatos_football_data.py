#!/usr/bin/env python3
"""Sem rede/custos: regressão de forma e H2H do provedor estruturado."""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import enriquecer_fatos_football_data as fd


def game(h,a,hg,ag,code="PL",days=1):
    return {
        "status":"FINISHED","utcDate":(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(),
        "homeTeam":{"id":h},"awayTeam":{"id":a},
        "competition":{"code":code},
        "score":{"fullTime":{"home":hg,"away":ag}},
    }


def main():
    config=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
    home,away=65,71
    date=(datetime.now(timezone.utc)+timedelta(days=4)).isoformat()
    kickoff=datetime.fromisoformat(date)
    history=[
        game(home,away,3,0,days=180),
        game(away,home,1,1,days=220),
        game(home,away,1,0,code="FAC",days=270),
        game(home,away,2,1,days=-1),  # FUTURO NÃO PODE CONTAR
    ]
    assert fd.score_for(game(home,away,1,0),home)[0]=="Vitória"
    assert fd.score_for(game(home,away,1,0),away)[0]=="Derrota"
    assert fd.head_to_head({"matches":history},home,away,"PL",kickoff)==(2,1,0,1)
    assert fd.latest_form({"matches":[game(home,away,1,1),game(home,away,1,0)]},home,kickoff).endswith("1 vitória, 1 empate e 0 derrotas")
    reqs=[
      {"id":"recent_form_both_teams","status":"pending","conflict_detected":False},
      {"id":"competition_specific_head_to_head","status":"pending","conflict_detected":False},
      {"id":"transmission","status":"pending","conflict_detected":False},
    ]
    article={"slug":"teste.html","fixture_id":123,
             "match_context":{"home":"Manchester City","away":"Sunderland",
                              "competition":"Premier League","competition_slug":"premier-league"},
             "requirements":reqs}
    fixture={"id":123,"kickoff":date,"competition_slug":"premier-league",
             "provider_data":{"home_team_id":home,"away_team_id":away,
                              "match_id":123,"competition_code":"PL"}}
    requests=[]
    def query(endpoint):
        requests.append(endpoint)
        if "head2head" in endpoint:return {"matches":history}
        if "/65/" in endpoint:return {"matches":[game(home,away,2,1),game(home,away,1,1)]}
        return {"matches":[game(away,home,2,1),game(away,home,0,0)]}
    result=fd.enrich(article,fixture,query,datetime.now(timezone.utc).isoformat(),config)
    by_id={r["id"]:r for r in result["requirements"]}
    assert by_id["recent_form_both_teams"]["status"]=="verified"
    assert by_id["competition_specific_head_to_head"]["status"]=="verified"
    assert by_id["transmission"]["status"]=="pending"
    assert len(by_id["competition_specific_head_to_head"]["facts"])==4
    assert "recorte de 2" in by_id["competition_specific_head_to_head"]["facts"][0]["text"]
    assert len(requests)==3
    # Nunca substitui evidência conflitante ou já validada.
    article["requirements"][0]["conflict_detected"]=True
    article["requirements"][1]["status"]="verified"
    assert fd.enrich(article,fixture,query,datetime.now(timezone.utc).isoformat(),config)["requirements"]==article["requirements"]
    # Se o adversário não tem jogos suficientes, a pesquisa continua pendente.
    assert fd.latest_form({"matches":[game(home,away,2,1)]},home,kickoff) is None
    print("OK: Football-Data complementar só valida forma bilateral e H2H da competição no recorte disponível.")


if __name__=="__main__":
    main()
