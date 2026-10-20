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

    # Regressões observadas na consulta REAL das duas APIs em 17/10/2026.
    # Horários idênticos e denominação jurídica diferente NÃO são conflito.
    equivalent = [
        ("Nottingham Forest FC", "Nottingham Forest"),
        ("EC Bahia", "Bahia"),
        ("Cruzeiro EC", "Cruzeiro"),
        ("Sevilla FC", "Sevilla"),
        ("Ipswich Town FC", "Ipswich Town"),
        ("RC Strasbourg Alsace", "Strasbourg"),
        ("Bologna FC 1909", "Bologna"),
        ("CA Paranaense", "Athletico Paranaense"),
        ("Real Betis Balompié", "Real Betis"),
    ]
    for i, (formal, short) in enumerate(equivalent, start=100):
        a = game(i, "Flamengo", formal, "2026-10-17T16:00:00-03:00")
        b = game(f"espn-{i}", "Flamengo", short, "2026-10-17T16:00:00-03:00", "espn")
        merged = calendar.merge([a], [b], config)
        assert len(merged) == 1 and merged[0].get("supplemental_fixture") == b, (formal, short)

    # Regressão real de 20/10: PAE AEK e AEK Athens identificam o mesmo clube.
    a = game(221, "Manchester City FC", "PAE AEK", "2026-10-20T16:00:00-03:00", comp="champions-league")
    b = game("espn-221", "Manchester City", "AEK Athens", "2026-10-20T16:00:00-03:00",
             "espn", comp="champions-league")
    merged = calendar.merge([a], [b], config)
    assert len(merged) == 1 and merged[0].get("supplemental_fixture") == b, merged

    # Regressão real 21/10: FK Shakhtar Donetsk é Shakhtar Donetsk.
    a = game(223, "FC Internazionale Milano", "FK Shakhtar Donetsk",
             "2026-10-21T16:00:00-03:00", comp="champions-league")
    b = game("espn-223", "Inter de Milão", "Shakhtar Donetsk",
             "2026-10-21T16:00:00-03:00", "espn", comp="champions-league")
    merged = calendar.merge([a], [b], config)
    assert len(merged) == 1 and merged[0].get("supplemental_fixture") == b, merged

    # Denominações equivalentes não podem ocultar um horário divergente real.
    a = game(222, "Barcelona", "Real Betis Balompié", "2026-10-17T13:30:00-03:00",
             comp="la-liga")
    b = game("espn-222", "Barcelona", "Real Betis", "2026-10-17T13:00:00-03:00",
             "espn", comp="la-liga")
    merged = calendar.merge([a], [b], config)
    assert len(merged) == 2 and all(x["status"] == "schedule_conflict" for x in merged)

    # Status externo inválido nunca é aceito como partida elegível.
    bad = game(5, "Arsenal", "Chelsea", "2026-10-17T18:00:00-03:00", comp="premier-league")
    bad["status"] = "unknown"
    good, ignored = selected([bad])
    assert not good and ignored[0]["reason"] == "unverified_status_unknown"
    print("OK: calendários concordantes, conflitos, confronto distinto, dia vazio e status não verificado.")


if __name__ == "__main__":
    main()
