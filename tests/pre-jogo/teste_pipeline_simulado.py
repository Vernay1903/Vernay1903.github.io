#!/usr/bin/env python3
"""Teste determinístico do pipeline de pré-jogo sem consultar nenhuma API externa."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import buscar_fixtures_football_data as provider  # noqa: E402
from scripts import identificar_jogos as identifier  # noqa: E402
from scripts import planejar_pre_jogos as planner  # noqa: E402

RAW_FIXTURE_PATH = ROOT / "tests" / "pre-jogo" / "football-data-resposta-simulada.json"
REPORT_PATH = ROOT / "build" / "pre-jogo" / "teste-simulado.json"
TARGET_DATE = date(2026, 9, 17)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: esperado={expected!r}, obtido={actual!r}")


def main() -> None:
    config = provider.load_config()
    assert_equal(len(config["monitored_clubs"]), 10, "Quantidade de clubes monitorados")

    raw = json.loads(RAW_FIXTURE_PATH.read_text(encoding="utf-8"))
    matches = raw.get("matches")
    if not isinstance(matches, list):
        raise AssertionError('Fixture simulado sem array "matches".')

    tz = ZoneInfo(config["timezone"])
    monitored_index = provider.build_monitored_index(config)
    competition_slugs = config["fixtures_provider"]["competition_slugs"]

    normalized = []
    normalization_results = []
    for item in matches:
        record = provider.normalize_match(
            item,
            target_date=TARGET_DATE,
            tz=tz,
            monitored_index=monitored_index,
            competition_slugs=competition_slugs,
        )
        normalization_results.append(
            {
                "raw_id": item.get("id"),
                "included": record is not None,
                "normalized": record,
            }
        )
        if record is not None:
            normalized.append(record)

    normalized_ids = [item["id"] for item in normalized]
    assert_equal(
        normalized_ids,
        [1001, 1002, 1003, 1006, 1007],
        "Partidas mantidas pela normalização",
    )

    # Confirma que a janela editorial usa Brasília, inclusive quando o UTC já virou o dia.
    real_barca = next(item for item in normalized if item["id"] == 1003)
    assert_equal(
        real_barca["kickoff"],
        "2026-09-17T22:30:00-03:00",
        "Conversão UTC -> America/Sao_Paulo",
    )

    # 1004 não envolve clube monitorado; 1005 cai em 16/09 no horário de Brasília.
    excluded_at_normalization = {
        item["raw_id"] for item in normalization_results if not item["included"]
    }
    assert_equal(
        excluded_at_normalization,
        {1004, 1005},
        "Exclusões na normalização",
    )

    # Acrescenta casos normalizados artificiais para exercitar as travas editoriais.
    test_fixtures = deepcopy(normalized)
    test_fixtures.extend(
        [
            {
                "id": 2001,
                "home": "Arsenal",
                "away": "Tottenham Hotspur",
                "competition": "Friendly",
                "competition_slug": "friendly",
                "kickoff": "2026-09-17T13:00:00-03:00",
                "status": "scheduled",
                "official": True,
                "first_team": True,
                "friendly": True,
            },
            {
                "id": 2002,
                "home": "Palmeiras",
                "away": "Santos",
                "competition": "Brasileirão",
                "competition_slug": "brasileirao",
                "kickoff": "2026-09-17T19:00:00-03:00",
                "status": "scheduled",
                "official": False,
                "first_team": True,
                "friendly": False,
            },
            {
                "id": 2003,
                "home": "Grêmio",
                "away": "Internacional",
                "competition": "Brasileirão",
                "competition_slug": "brasileirao",
                "kickoff": "2026-09-17T21:30:00-03:00",
                "status": "scheduled",
                "official": True,
                "first_team": False,
                "friendly": False,
            },
            # Duplicata proposital de Flamengo x Bahia para confirmar matéria única.
            deepcopy(next(item for item in normalized if item["id"] == 1002)),
        ]
    )

    club_index = identifier.build_club_index(config)
    selected, ignored = identifier.identify(
        test_fixtures,
        target_date=TARGET_DATE,
        timezone=tz,
        club_index=club_index,
    )

    selected_ids = [item["id"] for item in selected]
    assert_equal(selected_ids, [1001, 1002, 1003], "Partidas aprovadas pelo filtro final")

    selected_by_id = {item["id"]: item for item in selected}
    assert_equal(
        selected_by_id[1001]["two_monitored_clubs_same_match"],
        True,
        "Arsenal x Manchester City deve marcar dois clubes monitorados",
    )
    assert_equal(
        selected_by_id[1002]["two_monitored_clubs_same_match"],
        False,
        "Flamengo x Bahia deve marcar apenas um clube monitorado",
    )
    assert_equal(
        selected_by_id[1003]["two_monitored_clubs_same_match"],
        True,
        "Real Madrid x Barcelona deve marcar dois clubes monitorados",
    )

    ignored_reasons = [item["reason"] for item in ignored]
    required_reasons = {
        "status_postponed",
        "status_cancelled",
        "friendly",
        "not_official",
        "not_first_team",
        "duplicate_fixture",
    }
    missing = required_reasons.difference(ignored_reasons)
    if missing:
        raise AssertionError(
            "Travas não exercitadas ou não aplicadas: " + ", ".join(sorted(missing))
        )

    # Planejamento: simula uma matéria manual já existente para Flamengo x Bahia.
    # O planejador deve bloquear esse jogo mesmo que o slug antigo seja diferente.
    simulated_noticias = [
        {
            "title": "Flamengo x Bahia: onde assistir, horário e escalações",
            "excerpt": "Registro simulado apenas para teste de duplicidade.",
            "url": "flamengo-bahia-onde-assistir.html",
            "date": "17/09/2026",
            "category": "Futebol",
        }
    ]
    nonexistent_root = ROOT / "tests" / "pre-jogo" / "__sem_html_publicado__"
    planned, skipped = planner.plan_matches(
        selected,
        target_date=TARGET_DATE,
        config=config,
        noticias=simulated_noticias,
        root=nonexistent_root,
    )

    assert_equal([item["fixture_id"] for item in planned], [1001, 1003], "Planos liberados")
    assert_equal([item["fixture_id"] for item in skipped], [1002], "Plano bloqueado por duplicidade")
    assert_equal(
        planned[0]["slug"],
        "arsenal-manchester-city-premier-league-2026-transmissao-horario-escalacoes.html",
        "Slug Arsenal x Manchester City",
    )
    assert_equal(
        planned[1]["slug"],
        "real-madrid-barcelona-la-liga-2026-transmissao-horario-escalacoes.html",
        "Slug Real Madrid x Barcelona",
    )
    assert_equal(
        "same_match_already_in_noticias" in skipped[0]["reasons"],
        True,
        "Detecção de matéria já existente para o mesmo jogo",
    )
    assert_equal(
        planned[0]["prepare_at_brasilia"],
        "2026-09-16T23:30:00-03:00",
        "Horário de preparação",
    )
    assert_equal(
        planned[0]["target_publish_at_brasilia"],
        "2026-09-17T00:01:00-03:00",
        "Horário-alvo de publicação",
    )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "mode": "simulation_only",
        "external_api_called": False,
        "target_date": TARGET_DATE.isoformat(),
        "timezone": config["timezone"],
        "raw_match_count": len(matches),
        "normalized_count": len(normalized),
        "normalized_ids": normalized_ids,
        "selected_count": len(selected),
        "selected_matches": selected,
        "ignored_reasons": ignored_reasons,
        "planned_count": len(planned),
        "planned_articles": planned,
        "planning_skipped_count": len(skipped),
        "planning_skipped": skipped,
        "checks": {
            "ten_monitored_clubs": True,
            "utc_to_brasilia": True,
            "non_monitored_removed": True,
            "wrong_brasilia_date_removed": True,
            "postponed_removed": True,
            "cancelled_removed": True,
            "friendly_removed": True,
            "unofficial_removed": True,
            "non_first_team_removed": True,
            "duplicate_removed": True,
            "two_monitored_clubs_single_match": True,
            "slug_pattern": True,
            "existing_manual_article_blocks_duplicate": True,
            "prepare_time_2330": True,
            "publish_time_0001": True,
        },
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("OK: pipeline simulado validado sem chamada externa.")
    print(f"Fixtures brutos: {len(matches)}")
    print(f"Fixtures normalizados: {len(normalized)}")
    print(f"Jogos aprovados: {len(selected)}")
    for match in selected:
        clubs = ", ".join(club["name"] for club in match["monitored_clubs"])
        print(
            f'- {match["kickoff_time_brasilia"]} | {match["home"]} x {match["away"]} '
            f'| {match["competition"]} | monitorado: {clubs}'
        )
    print(f"Planos de matéria liberados: {len(planned)}")
    for item in planned:
        print(f'- PLANO | {item["home"]} x {item["away"]} | {item["slug"]}')
    for item in skipped:
        print(
            f'- BLOQUEADO | {item["home"]} x {item["away"]} | '
            f'{", ".join(item["reasons"])}'
        )
    print(f"Relatório: {REPORT_PATH.relative_to(ROOT)}")
    print("Nenhum token foi usado e nenhum arquivo publicado foi alterado.")


if __name__ == "__main__":
    main()
