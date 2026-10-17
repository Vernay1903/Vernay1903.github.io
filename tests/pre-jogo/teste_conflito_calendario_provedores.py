#!/usr/bin/env python3
"""Regressão: conflito de provedores bloqueia só o confronto, nunca vira dia vazio."""
import json
import sys
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import coletar_competicoes_pre_jogo as calendar
from scripts import identificar_jogos as selection
from scripts import registrar_preparo_vazio_pre_jogo as empty

config = json.loads((ROOT / "config/pre-jogo.json").read_text(encoding="utf-8"))
target = date(2026, 10, 17)
tz = ZoneInfo("America/Sao_Paulo")
index = selection.build_club_index(config)


def game(identity, home, away, kickoff, provider="football-data.org", comp="brasileirao"):
    return dict(id=identity, home=home, away=away, competition="Brasileirão",
                competition_slug=comp, kickoff=kickoff, status="scheduled",
                official=True, first_team=True, friendly=False, provider=provider)


def selected(records):
    return selection.identify(records, target_date=target, timezone=tz, club_index=index)


def main():
    primary = game(1, "Flamengo", "Grêmio", "2026-10-17T16:00:00-03:00")
    agreeing = game("espn-1", "CR Flamengo", "Grêmio", "2026-10-17T19:00:00Z", "espn")
    merged = calendar.merge([primary], [agreeing], config)
    assert len(merged) == 1 and merged[0]["supplemental_fixture"] == agreeing
    good, ignored = selected(merged)
    assert len(good) == 1 and not ignored

    primary = game(2, "Flamengo", "Grêmio", "2026-10-17T16:00:00-03:00")
    opposite_time = game("espn-2", "Flamengo", "Grêmio", "2026-10-17T17:00:00-03:00", "espn")
    merged = calendar.merge([primary], [opposite_time], config)
    assert len(merged) == 2 and all(r["status"] == "schedule_conflict" for r in merged)
    good, ignored = selected(merged)
    assert not good and len(ignored) == 2
    assert all(x["reason"] == "calendar_conflict" for x in ignored)

    # Mesmo clube e competição NÃO implica mesmo jogo.
    other = game("espn-3", "Flamengo", "Palmeiras", "2026-10-17T16:00:00-03:00", "espn")
    merged = calendar.merge([game(3, "Flamengo", "Grêmio", "2026-10-17T16:00:00-03:00")], [other], config)
    assert len(merged) == 2 and all(r["status"] == "schedule_conflict" for r in merged)

    # Outra partida sem conflito continua disponível; nenhum fato divergente passa.
    healthy = game(4, "Barcelona", "Real Madrid", "2026-10-17T18:00:00-03:00", comp="la-liga")
    good, ignored = selected(merged + [healthy])
    assert len(good) == 1 and good[0]["home"] == "Barcelona"
    assert len(ignored) == 2

    report = {"target_date": target.isoformat(), "selected_count": 0,
              "matches": [], "ignored": ignored, "calendar_conflict_count": 2}
    planning = {"target_date": target.isoformat(), "planned_count": 0,
                "planned": [], "skipped_count": 0, "skipped": []}
    try:
        empty.build_empty_manifest(report, planning, target=target.isoformat(), source_sha="a"*40)
    except ValueError as exc:
        assert "NÃO dia sem jogos" in str(exc)
    else:
        raise AssertionError("Divergência foi mascarada como dia sem jogos")

    # Status externo inválido nunca é aceito como partida elegível.
    bad = game(5, "Arsenal", "Chelsea", "2026-10-17T18:00:00-03:00", comp="premier-league")
    bad["status"] = "unknown"
    good, ignored = selected([bad])
    assert not good and ignored[0]["reason"] == "unverified_status_unknown"
    print("OK: calendários concordantes, conflitos, confronto distinto, dia vazio e status não verificado.")


if __name__ == "__main__":
    main()
