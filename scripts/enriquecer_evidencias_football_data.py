#!/usr/bin/env python3
"""Enriquece evidências checadas com dados gratuitos do football-data.org.

Escopo deliberadamente estreito:
- forma recente de cada equipe;
- H2H específico da competição.

Nunca fornece transmissão, escalações, arbitragem, estádio ou status final.
Nunca publica nada e grava somente em build/pre-jogo/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "pre-jogo.json"
BUILD = ROOT / "build" / "pre-jogo"


def fail(msg: str) -> None:
    raise SystemExit(f"ERRO: {msg}")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_json(endpoint: str, token: str, *, params: dict[str, str] | None = None) -> dict[str, Any]:
    base = "https://api.football-data.org/v4"
    url = base + endpoint
    if params:
        url += "?" + urlencode(params)
    req = Request(url, headers={"X-Auth-Token": token, "Accept": "application/json",
                                "User-Agent": "CorteDosEsportes/1.0"})
    try:
        with urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"football-data HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"football-data indisponível: {type(exc).__name__}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Resposta football-data inválida")
    return data


def outcome_for_team(match: dict[str, Any], team_id: int) -> str | None:
    home = match.get("homeTeam") or {}
    away = match.get("awayTeam") or {}
    score = (match.get("score") or {}).get("fullTime") or {}
    hg, ag = score.get("home"), score.get("away")
    if not isinstance(hg, int) or not isinstance(ag, int):
        return None
    if home.get("id") == team_id:
        gf, ga = hg, ag
    elif away.get("id") == team_id:
        gf, ga = ag, hg
    else:
        return None
    return "V" if gf > ga else "E" if gf == ga else "D"


def recent_form_segment(team_name: str, matches: list[dict[str, Any]], team_id: int) -> str | None:
    outcomes = [o for m in matches if (o := outcome_for_team(m, team_id)) is not None][:5]
    if not outcomes:
        return None
    wins, draws, losses = outcomes.count("V"), outcomes.count("E"), outcomes.count("D")
    n = len(outcomes)
    return (
        f"{team_name} — forma recente: nos últimos {n} jogos oficiais, "
        f"venceu {wins}, empatou {draws} e perdeu {losses}."
    )


def h2h_segment(home: str, away: str, competition: str, matches: list[dict[str, Any]],
                competition_code: str | None, home_id: int, away_id: int) -> str | None:
    relevant = []
    for match in matches:
        comp = match.get("competition") or {}
        if competition_code and comp.get("code") != competition_code:
            continue
        score = (match.get("score") or {}).get("fullTime") or {}
        if not isinstance(score.get("home"), int) or not isinstance(score.get("away"), int):
            continue
        relevant.append(match)
    if not relevant:
        return None
    home_wins = away_wins = draws = 0
    for match in relevant:
        hteam, ateam = match.get("homeTeam") or {}, match.get("awayTeam") or {}
        hg = match["score"]["fullTime"]["home"]
        ag = match["score"]["fullTime"]["away"]
        if hg == ag:
            draws += 1
        elif (hteam.get("id") == home_id and hg > ag) or (ateam.get("id") == home_id and ag > hg):
            home_wins += 1
        elif (hteam.get("id") == away_id and hg > ag) or (ateam.get("id") == away_id and ag > hg):
            away_wins += 1
        else:
            return None
    n = len(relevant)
    return (
        f"Retrospecto de {home} x {away} pela {competition}. "
        f"Jogos: {n}. Vitórias do {home}: {home_wins}. "
        f"Vitórias do {away}: {away_wins}. Empates: {draws}."
    )


def source(url: str, publisher: str, checked_at: str, segment: str) -> dict[str, Any]:
    return {
        "publisher": publisher,
        "url": url,
        "source_type": "structured_data_provider",
        "checked_at": checked_at,
        "content_checked": True,
        "eligible_for_factual_validation": True,
        "verification_status": "structured_provider_checked",
        "page_evidence": {
            "metadata": {"title": publisher},
            "evidence_segments": [segment],
            "segment_count": 1,
            "content_length": len(segment),
            "credits_used": 0,
        },
    }


def enrich_article(article: dict[str, Any], fixture: dict[str, Any], token: str,
                   checked_at: str, max_recent: int, max_h2h: int) -> dict[str, Any]:
    result = deepcopy(article)
    pdata = fixture.get("provider_data") or {}
    home_id, away_id, match_id = pdata.get("home_team_id"), pdata.get("away_team_id"), pdata.get("match_id")
    comp_code = pdata.get("competition_code")
    if not all(isinstance(x, int) for x in (home_id, away_id, match_id)):
        return result

    ctx = result.get("match_context") or {}
    home, away = str(ctx.get("home") or fixture.get("home")), str(ctx.get("away") or fixture.get("away"))
    competition = str(ctx.get("competition") or fixture.get("competition"))

    recent_sources: list[dict[str, Any]] = []
    for team_id, team_name in ((home_id, home), (away_id, away)):
        endpoint = f"/teams/{team_id}/matches"
        data = fetch_json(endpoint, token, params={"status": "FINISHED", "limit": str(max_recent)})
        matches = data.get("matches") if isinstance(data.get("matches"), list) else []
        segment = recent_form_segment(team_name, matches, team_id)
        if segment:
            recent_sources.append(source(
                f"https://api.football-data.org/v4{endpoint}?status=FINISHED&limit={max_recent}",
                "Football-Data.org", checked_at, segment
            ))

    h2h_sources: list[dict[str, Any]] = []
    endpoint = f"/matches/{match_id}/head2head"
    try:
        data = fetch_json(endpoint, token, params={"limit": str(max_h2h)})
        matches = data.get("matches") if isinstance(data.get("matches"), list) else []
        segment = h2h_segment(
            home, away, competition, matches,
            comp_code if isinstance(comp_code, str) else None,
            home_id, away_id,
        )
        if segment:
            h2h_sources.append(source(
                f"https://api.football-data.org/v4{endpoint}?limit={max_h2h}",
                "Football-Data.org", checked_at, segment
            ))
    except RuntimeError:
        # H2H ausente não pode derrubar a pesquisa restante.
        pass

    requirements = []
    for req in result.get("requirements", []):
        if not isinstance(req, dict):
            continue
        row = deepcopy(req)
        rid = row.get("id")
        if rid == "recent_form_both_teams" and recent_sources:
            existing = [x for x in row.get("source_candidates", []) if isinstance(x, dict)]
            row["source_candidates"] = recent_sources + existing
            row["ready_for_fact_extraction"] = True
            row["football_data_enriched"] = True
        elif rid == "competition_specific_head_to_head" and h2h_sources:
            existing = [x for x in row.get("source_candidates", []) if isinstance(x, dict)]
            row["source_candidates"] = h2h_sources + existing
            row["ready_for_fact_extraction"] = True
            row["football_data_enriched"] = True
        requirements.append(row)
    result["requirements"] = requirements
    result["football_data_editorial_enrichment"] = {
        "recent_form_sources": len(recent_sources),
        "h2h_sources": len(h2h_sources),
        "cost_usd": 0,
    }
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--checked", type=Path)
    ap.add_argument("--fixtures", type=Path, default=BUILD / "fixtures-normalizados.json")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
    if not token:
        fail("FOOTBALL_DATA_TOKEN ausente.")

    config = load(CONFIG)
    support = config.get("fixtures_provider", {}).get("editorial_fact_support", {})
    if support.get("enabled") is not True:
        fail("Suporte editorial Football-Data desativado.")
    target = args.date
    checked_path = args.checked or BUILD / f"paginas-checadas-{target}.json"
    checked = load(checked_path)
    fixtures_manifest = load(args.fixtures)
    if checked.get("target_date") != target or fixtures_manifest.get("target_date") != target:
        fail("Data-alvo divergente.")

    fixtures = fixtures_manifest.get("fixtures", [])
    by_id = {str(x.get("id")): x for x in fixtures if isinstance(x, dict) and x.get("id") is not None}
    checked_at = datetime.now(ZoneInfo(config["timezone"])).isoformat()
    max_recent = int(support.get("max_recent_matches", 5))
    max_h2h = int(support.get("max_h2h_matches", 50))

    enriched = []
    for article in checked.get("articles", []):
        fixture = by_id.get(str(article.get("fixture_id")))
        if not fixture:
            enriched.append(article)
            continue
        enriched.append(enrich_article(article, fixture, token, checked_at, max_recent, max_h2h))

    out = deepcopy(checked)
    out["articles"] = enriched
    out["football_data_editorial_enrichment_applied"] = True
    out["football_data_editorial_enrichment_cost_usd"] = 0
    checked_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("OK: forma recente/H2H enriquecidos via Football-Data sem custo adicional.")
    print("Nenhuma transmissão, escalação, arbitragem, estádio ou status final foi inferido.")


if __name__ == "__main__":
    main()
