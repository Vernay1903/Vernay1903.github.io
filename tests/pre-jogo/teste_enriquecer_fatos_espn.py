#!/usr/bin/env python3
"""Sem rede: regressão do complemento estruturado ESPN para pré-jogo."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import enriquecer_fatos_espn as espn


def event(eid, home, away, hg, ag, days, code="bra.1", venue=None):
    when = datetime.now(timezone.utc) - timedelta(days=days)
    comp = {
        "date": when.isoformat(),
        "status": {"type": {"name": "STATUS_FULL_TIME", "completed": True}},
        "competitors": [
            {"homeAway": "home", "team": {"id": str(home), "displayName": f"Time {home}"}, "score": str(hg)},
            {"homeAway": "away", "team": {"id": str(away), "displayName": f"Time {away}"}, "score": str(ag)},
        ],
    }
    if venue:
        comp["venue"] = {"fullName": venue}
    return {"id": str(eid), "date": when.isoformat(), "league": {"slug": code, "name": "Brasileirão"}, "competitions": [comp]}


def main():
    config = json.loads((ROOT / "config/pre-jogo.json").read_text(encoding="utf-8"))
    home, away = "2029", "9967"
    kickoff = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    home_events = [
        event(1, home, away, 2, 0, 150),
        event(2, home, 111, 3, 1, 10),
        event(3, 222, home, 1, 1, 20),
        event(4, home, 333, 0, 1, 30),
    ]
    away_events = [
        event(5, away, 444, 1, 0, 9),
        event(6, 555, away, 2, 2, 19),
        event(7, away, 666, 0, 1, 29),
    ]
    summary = {
        "header": {
            "id": "999",
            "league": {"slug": "bra.1"},
            "competitions": [{
                "date": kickoff,
                "competitors": [
                    {"homeAway": "home", "team": {"id": home}},
                    {"homeAway": "away", "team": {"id": away}},
                ],
            }],
        },
        "gameInfo": {"venue": {"fullName": "Arena Exata"}},
    }
    article = {
        "slug": "palmeiras-bahia.html",
        "fixture_id": "espn-999",
        "match_context": {"home": "Palmeiras", "away": "Bahia", "competition": "Brasileirão", "competition_slug": "brasileirao"},
        "requirements": [
            {"id": "stadium_and_location", "status": "verified", "facts": [{"field": "stadium", "text": "A partida será disputada no estádio errado."}], "sources": [], "conflict_detected": False, "required_for_drafting": True, "conditional": False, "allow_unavailable_after_check": False},
            {"id": "recent_form_both_teams", "status": "pending", "facts": [], "sources": [], "conflict_detected": False, "required_for_drafting": True, "conditional": False, "allow_unavailable_after_check": False},
            {"id": "competition_specific_head_to_head", "status": "unavailable_after_check", "facts": [], "sources": [], "conflict_detected": False, "required_for_drafting": True, "conditional": False, "allow_unavailable_after_check": True},
        ],
    }
    fixture = {
        "id": "espn-999", "provider": "espn", "kickoff": kickoff, "competition_slug": "brasileirao",
        "provider_data": {"match_id": "999", "competition_code": "bra.1", "home_team_id": home, "away_team_id": away},
    }
    urls = {
        f"{espn.BASE}/bra.1/summary?event=999": summary,
        f"{espn.BASE}/all/teams/{home}/schedule?fixture=true": {"team": {"id": home}, "events": home_events},
        f"{espn.BASE}/all/teams/{away}/schedule?fixture=true": {"team": {"id": away}, "events": away_events},
    }
    result = espn.enrich(article, fixture, lambda url: urls[url], datetime.now(timezone.utc).isoformat(), config)
    req = {r["id"]: r for r in result["requirements"]}
    assert req["stadium_and_location"]["facts"][0]["text"] == "A partida será disputada no Arena Exata."
    assert req["recent_form_both_teams"]["status"] == "verified"
    assert {f["field"] for f in req["recent_form_both_teams"]["facts"]} >= {"home_recent_form", "away_recent_form"}
    assert req["competition_specific_head_to_head"]["status"] == "verified"
    assert req["competition_specific_head_to_head"]["facts"][0]["text"].endswith("1 jogos.")
    fixed = json.loads(json.dumps(article))
    fixed["requirements"][0]["editorial_stadium_override"] = True
    fixed_result = espn.enrich(fixed, fixture, lambda url: urls[url], datetime.now(timezone.utc).isoformat(), config)
    assert "estádio errado" in fixed_result["requirements"][0]["facts"][0]["text"]

    # Quando Football-Data é o provedor principal, o calendário ESPN suplementar
    # ainda deve corrigir estádio e completar dados estruturados.
    primary = {
        "id": 123,
        "provider": "football-data.org",
        "kickoff": kickoff,
        "supplemental_fixture": fixture,
    }
    supplemental_result = espn.enrich(
        article, primary, lambda url: urls[url], datetime.now(timezone.utc).isoformat(), config
    )
    supplemental_req = {r["id"]: r for r in supplemental_result["requirements"]}
    assert supplemental_req["stadium_and_location"]["facts"][0]["text"] == "A partida será disputada no Arena Exata."
    assert supplemental_req["recent_form_both_teams"]["status"] == "verified"
    print("OK: ESPN complementa estádio exato, forma recente e H2H sem sobrescrever estádio fixo editorial.")


if __name__ == "__main__":
    main()
