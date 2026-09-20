#!/usr/bin/env python3
"""Complementa forma recente e H2H com resultados reais da Football-Data gratuita.

Não inventa placares, não altera fatos já validados, não cria matérias nem publica.
Conta somente jogos FINISHED e, para H2H, somente partidas retornadas pela API
na MESMA competição. Toda soma pode ser refeita a partir dos jogos registrados.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts import validar_pesquisa_factual as factual_validator

BUILD = ROOT / "build" / "pre-jogo"
API = "https://api.football-data.org/v4"
TZ = ZoneInfo("America/Sao_Paulo")
MIN_FORM_GAMES = 2


def require(condition: bool, message: str) -> None:
    if not condition: raise ValueError(message)


def api_json(endpoint: str, token: str) -> dict:
    require(endpoint.startswith("/"), "endpoint inválido")
    req = Request(API + endpoint, headers={"X-Auth-Token": token, "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=25) as resp:
                content = json.loads(resp.read(800_000).decode("utf-8"))
            require(isinstance(content, dict), "Resposta da API não é objeto.")
            return content
        except HTTPError as exc:
            if exc.code != 429 or attempt == 2: raise
            time.sleep(7 * (attempt + 1))
    raise ValueError("Falha no provedor de resultados.")


def score_for(match: dict, team_id: int) -> tuple[str, str] | None:
    if match.get("status") != "FINISHED": return None
    home, away = match.get("homeTeam"), match.get("awayTeam")
    if not isinstance(home, dict) or not isinstance(away, dict): return None
    if home.get("id") == team_id: side = "home"
    elif away.get("id") == team_id: side = "away"
    else: return None
    full = match.get("score", {}).get("fullTime")
    if not isinstance(full, dict): return None
    h, a = full.get("home"), full.get("away")
    if type(h) is not int or type(a) is not int or min(h, a) < 0: return None
    goals, conceded = (h,a) if side == "home" else (a,h)
    name = "Vitória" if goals > conceded else "Empate" if goals == conceded else "Derrota"
    return name, f"{goals}-{conceded}"


def latest_form(data: dict, team_id: int, cutoff: datetime) -> str | None:
    rows = data.get("matches", [])
    require(isinstance(rows, list), "API sem lista de jogos")
    dated = []
    for row in rows:
        if not isinstance(row, dict): continue
        try:
            d = datetime.fromisoformat(str(row["utcDate"]).replace("Z", "+00:00"))
        except (ValueError, KeyError): continue
        if d >= cutoff or d > datetime.now(d.tzinfo): continue
        score = score_for(row, team_id)
        if score: dated.append((d, score))
    dated.sort(reverse=True, key=lambda item: item[0])
    latest = dated[:5]
    if len(latest) < MIN_FORM_GAMES: return None
    outcomes = [item[1][0] for item in latest]
    wins = outcomes.count("Vitória")
    draws = outcomes.count("Empate")
    losses = outcomes.count("Derrota")
    return (f"nos últimos {len(latest)} jogos concluídos registrados, "
            f"{wins} {'vitória' if wins == 1 else 'vitórias'}, "
            f"{draws} {'empate' if draws == 1 else 'empates'} e "
            f"{losses} {'derrota' if losses == 1 else 'derrotas'}")



def recent_match_details(data: dict, team_id: int, cutoff: datetime) -> str | None:
    """Resultados individuais da MESMA lista gratuita usada para a forma recente.

    Nunca atribui gol a jogador, nunca cria adversário quando o provedor omite
    seu nome e nunca contabiliza partidas futuras, sem placar ou não encerradas.
    """
    matches = data.get("matches", [])
    require(isinstance(matches, list), "API sem lista de jogos")
    dated: list[tuple[datetime, str]] = []
    for row in matches:
        if not isinstance(row, dict):
            continue
        try:
            when = datetime.fromisoformat(str(row["utcDate"]).replace("Z", "+00:00"))
        except (ValueError, KeyError):
            continue
        if when >= cutoff or when > datetime.now(when.tzinfo):
            continue
        if score_for(row, team_id) is None:
            continue
        home, away = row.get("homeTeam"), row.get("awayTeam")
        if not isinstance(home, dict) or not isinstance(away, dict):
            continue
        if team_id not in {home.get("id"), away.get("id")}:
            continue
        home_name = home.get("shortName") or home.get("name")
        away_name = away.get("shortName") or away.get("name")
        score = row.get("score", {}).get("fullTime", {})
        hg, ag = score.get("home"), score.get("away")
        if not all(isinstance(n, str) and n.strip() for n in (home_name, away_name)):
            continue
        if any(";" in n or "\\n" in n for n in (home_name, away_name)):
            continue
        comp = row.get("competition")
        comp_name = comp.get("name") if isinstance(comp, dict) else None
        comp_suffix = f" ({comp_name})" if isinstance(comp_name, str) and comp_name.strip() else ""
        moment = when.astimezone(TZ).strftime("%d/%m/%Y")
        dated.append((
            when, f"{moment}: {home_name} {hg} x {ag} {away_name}{comp_suffix}"
        ))
    dated.sort(key=lambda item: item[0], reverse=True)
    last = [description for _date, description in dated[:5]]
    return "; ".join(last) if len(last) >= MIN_FORM_GAMES else None


def head_to_head(data: dict, home_id: int, away_id: int, comp_code: str, cutoff: datetime) -> tuple[int,int,int,int] | None:
    rows = data.get("matches", [])
    require(isinstance(rows, list), "API sem lista de confrontos")
    count,hw,aw,draw = 0,0,0,0
    for row in rows:
        if not isinstance(row, dict): continue
        try: d = datetime.fromisoformat(str(row["utcDate"]).replace("Z","+00:00"))
        except (ValueError, KeyError): continue
        if d >= cutoff or d > datetime.now(d.tzinfo) or row.get("competition", {}).get("code") != comp_code: continue
        left,right = row.get("homeTeam",{}).get("id"),row.get("awayTeam",{}).get("id")
        if {left,right} != {home_id,away_id}: continue
        result = score_for(row, home_id)
        if result is None: continue
        count += 1
        if result[0] == "Vitória": hw += 1
        elif result[0] == "Derrota": aw += 1
        else: draw += 1
    if count == 0 or count != hw+aw+draw: return None
    return count,hw,aw,draw


def validated_update(req: dict, facts: list[dict], urls: list[str], now: str, config: dict) -> dict:
    if req.get("status") == "verified" or req.get("conflict_detected") is True: return req
    evidence = {"status": "verified", "facts": facts,
        "sources": [{"publisher":"football-data.org","url":url,
                     "source_type":"structured_data_provider","checked_at":now}
                    for url in sorted(set(urls))], "notes":None}
    validated, errors = factual_validator.validate_requirement_evidence(req,evidence,config=config)
    if errors: raise ValueError("Evidência Football-Data não passou no validador: " + "; ".join(errors))
    validated["fact_extraction_status"] = "validated_structured_api"
    validated["structured_fact_count"] = len(facts)
    validated["validator_accepted"] = True
    validated["conflict_detected"] = False
    validated["internal_provenance_only"] = True
    return validated


def enrich(article: dict, fixture: dict, query, now: str, config: dict) -> dict:
    result = deepcopy(article)
    ctx = article.get("match_context",{})
    src = fixture.get("provider_data",{})
    home_id,away_id = src.get("home_team_id"),src.get("away_team_id")
    match_id,code = src.get("match_id"),src.get("competition_code")
    if not all(type(value) is int and value>0 for value in (home_id,away_id,match_id)):
        return result
    if not isinstance(code,str) or not code: return result
    if ctx.get("competition_slug") != fixture.get("competition_slug"): return result
    try: cutoff = datetime.fromisoformat(fixture["kickoff"].replace("Z","+00:00"))
    except (KeyError,ValueError): return result
    now_dt = datetime.now(TZ)
    if cutoff.astimezone(TZ) <= now_dt: return result

    requirements = result.get("requirements",[])
    if not isinstance(requirements,list): return result
    needed = {r.get("id") for r in requirements if isinstance(r,dict) and
              r.get("status") != "verified" and r.get("conflict_detected") is not True}
    if not needed.intersection({"recent_form_both_teams","competition_specific_head_to_head"}):
        return result

    home=ctx.get("home");away=ctx.get("away");competition=ctx.get("competition")
    if not all(isinstance(x,str) and x.strip() for x in (home,away,competition)): return result

    supplements={}
    if "recent_form_both_teams" in needed:
        home_url = f"{API}/teams/{home_id}/matches?status=FINISHED&limit=5"
        away_url = f"{API}/teams/{away_id}/matches?status=FINISHED&limit=5"
        home_data=query(f"/teams/{home_id}/matches?status=FINISHED&limit=5")
        away_data=query(f"/teams/{away_id}/matches?status=FINISHED&limit=5")
        home_form=latest_form(home_data,home_id,cutoff)
        away_form=latest_form(away_data,away_id,cutoff)
        if home_form and away_form:
            facts=[
              {"field":"home_recent_form","text":f"Forma recente do {home}: {home_form}."},
              {"field":"away_recent_form","text":f"Forma recente do {away}: {away_form}."},
            ]
            home_details=recent_match_details(home_data,home_id,cutoff)
            away_details=recent_match_details(away_data,away_id,cutoff)
            if home_details:
                facts.append({"field":"home_recent_matches","text":f"Resultados recentes do {home}, com datas e placares registrados: {home_details}."})
            if away_details:
                facts.append({"field":"away_recent_matches","text":f"Resultados recentes do {away}, com datas e placares registrados: {away_details}."})
            supplements["recent_form_both_teams"]=(facts,[home_url,away_url])
    if "competition_specific_head_to_head" in needed:
        endpoint=f"/matches/{match_id}/head2head?limit=15"
        sample=head_to_head(query(endpoint),home_id,away_id,code,cutoff)
        if sample:
            n,hw,aw,draw=sample
            qualifier=f"no recorte de {n} confrontos anteriores registrados na {competition}"
            supplements["competition_specific_head_to_head"]=(
                [{"field":"h2h_games","text":f"Retrospecto {qualifier}: {n} jogos."},
                 {"field":"h2h_home_wins","text":f"Vitórias do {home} {qualifier}: {hw}."},
                 {"field":"h2h_away_wins","text":f"Vitórias do {away} {qualifier}: {aw}."},
                 {"field":"h2h_draws","text":f"Empates {qualifier}: {draw}."}],
                [API+endpoint])

    updated=[]
    for req in requirements:
        if not isinstance(req,dict) or req.get("id") not in supplements:
            updated.append(req)
        else:
            facts,urls=supplements[req["id"]]
            updated.append(validated_update(req,facts,urls,now,config))
    result["requirements"]=updated
    result["structured_fact_count"]=sum(len(r.get("facts",[])) for r in updated if isinstance(r,dict))
    result["validator_accepted_requirement_ids"]=[r["id"] for r in updated if isinstance(r,dict) and r.get("status")=="verified"]
    result["free_structured_supplement_applied"]=True
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date",required=True)
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--force",action="store_true")
    args=parser.parse_args()
    if not args.execute: raise SystemExit("Sem --execute não há consulta externa.")
    token=os.environ.get("FOOTBALL_DATA_TOKEN","").strip()
    if not token: raise SystemExit("FOOTBALL_DATA_TOKEN ausente.")
    if os.environ.get("CDE_FREE_RESEARCH") != "1": raise SystemExit("Modo gratuito obrigatório.")
    path=BUILD/f"fatos-estruturados-{args.date}.json"
    if not path.exists(): raise SystemExit("Manifesto factual ausente.")
    config=json.loads((ROOT/"config"/"pre-jogo.json").read_text(encoding="utf-8"))
    data=json.loads(path.read_text(encoding="utf-8"))
    fixtures=json.loads((BUILD/"fixtures-normalizados.json").read_text(encoding="utf-8"))
    if data.get("target_date") != args.date or fixtures.get("target_date") != args.date:
        raise SystemExit("Data-alvo divergente.")
    by_id={str(f.get("id")):f for f in fixtures.get("fixtures",[]) if isinstance(f,dict)}
    checked=datetime.now(TZ).isoformat()
    cache={}
    last_request=[0.0]
    def query(endpoint):
        if endpoint not in cache:
            delay=6.2-(time.monotonic()-last_request[0])
            if delay>0 and last_request[0]: time.sleep(delay)
            response=api_json(endpoint,token)
            last_request[0]=time.monotonic()
            cache[endpoint]=response
        return cache[endpoint]
    new=[]
    for article in data.get("articles",[]):
        if not isinstance(article,dict): continue
        fixture=by_id.get(str(article.get("fixture_id")))
        new.append(enrich(article,fixture,query,checked,config) if fixture else article)
    data["articles"]=new
    data["free_structured_supplement"]=True
    data["structured_fact_count"]=sum(a.get("structured_fact_count",0) for a in new)
    if not args.force: raise SystemExit("É obrigatório --force para substituir somente arquivo de build.")
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Football-Data: reforço factual gratuito sem publicação.")
    for a in new:
        fields=[r["id"] for r in a.get("requirements",[]) if isinstance(r,dict) and
                r.get("fact_extraction_status")=="validated_structured_api"]
        print(a.get("slug"),"campos reforçados=",fields)

if __name__=="__main__":
    main()
