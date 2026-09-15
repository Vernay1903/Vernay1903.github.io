#!/usr/bin/env python3
"""
Identifica jogos oficiais do dia seguinte envolvendo os clubes monitorados.

Este script NÃO consulta uma API externa, NÃO gera matéria e NÃO publica nada.
Ele recebe uma lista normalizada de partidas produzida por uma fonte de dados
futura e aplica somente as regras editoriais/técnicas já aprovadas.

Entrada aceita (array direto ou objeto com chave "fixtures"):
[
  {
    "id": "fixture-123",
    "home": "Palmeiras",
    "away": "Flamengo",
    "competition": "Brasileirão",
    "competition_slug": "brasileirao",
    "kickoff": "2026-09-16T21:30:00-03:00",
    "status": "scheduled",
    "official": true,
    "first_team": true,
    "friendly": false
  }
]

Por padrão, a data-alvo é amanhã em America/Sao_Paulo e o resultado é salvo
somente em build/pre-jogo/jogos-AAAA-MM-DD.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
DEFAULT_FIXTURES_PATH = ROOT / "build" / "pre-jogo" / "fixtures-normalizados.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo"

SKIP_STATUSES = {
    "postponed",
    "cancelled",
    "canceled",
}


def fail(message: str) -> NoReturn:
    print(f"ERRO: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"Arquivo não encontrado: {path}")
    except json.JSONDecodeError as exc:
        fail(f"JSON inválido em {path}: {exc}")


def load_config() -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    if not isinstance(config, dict):
        fail("config/pre-jogo.json deve conter um objeto JSON.")

    timezone_name = config.get("timezone")
    if timezone_name != "America/Sao_Paulo":
        fail('A configuração de timezone deve permanecer "America/Sao_Paulo".')

    monitored = config.get("monitored_clubs")
    if not isinstance(monitored, list) or len(monitored) != 10:
        fail("A configuração deve conter exatamente os 10 clubes monitorados.")

    scope = config.get("scope")
    if not isinstance(scope, dict):
        fail('Configuração "scope" ausente ou inválida.')
    if scope.get("official_first_team_only") is not True:
        fail("A automação deve permanecer limitada a jogos oficiais do time principal.")
    if scope.get("exclude_friendlies") is not True:
        fail("Amistosos devem permanecer excluídos.")
    if scope.get("if_two_monitored_clubs_same_match") != "single_article":
        fail("Confrontos entre dois clubes monitorados devem gerar uma única matéria.")
    if scope.get("if_postponed_or_cancelled") != "skip":
        fail("Jogos adiados ou cancelados devem permanecer fora da publicação.")

    return config


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def build_club_index(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    monitored = config["monitored_clubs"]

    for club in monitored:
        if not isinstance(club, dict):
            fail("Há um clube inválido em monitored_clubs.")
        name = club.get("name")
        slug = club.get("slug")
        aliases = club.get("aliases", [])
        if not isinstance(name, str) or not name.strip():
            fail("Todo clube monitorado precisa de name.")
        if not isinstance(slug, str) or not slug.strip():
            fail(f"Clube sem slug válido: {name}")
        if not isinstance(aliases, list) or not all(isinstance(x, str) for x in aliases):
            fail(f"Aliases inválidos para {name}.")

        canonical = {"name": name.strip(), "slug": slug.strip()}
        candidates = [name, slug.replace("-", " "), *aliases]
        for candidate in candidates:
            key = normalize_name(candidate)
            if not key:
                continue
            existing = index.get(key)
            if existing and existing != canonical:
                fail(
                    f'Alias ambíguo "{candidate}" entre '
                    f'{existing["name"]} e {canonical["name"]}.'
                )
            index[key] = canonical

    return index


def load_fixtures(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    if isinstance(data, dict):
        data = data.get("fixtures")
    if not isinstance(data, list):
        fail('A entrada deve ser um array ou um objeto com a chave "fixtures".')

    fixtures: list[dict[str, Any]] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            fail(f"Partida na posição {idx} não é um objeto JSON.")
        fixtures.append(item)
    return fixtures


def parse_target_date(raw: str | None, timezone: ZoneInfo) -> date:
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            fail("--date deve usar o formato YYYY-MM-DD.")
    return datetime.now(timezone).date() + timedelta(days=1)


def parse_kickoff(value: Any, timezone: ZoneInfo) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone)


def as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def normalized_status(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return normalize_name(value).replace(" ", "_")


def match_club(team_name: Any, club_index: dict[str, dict[str, str]]) -> dict[str, str] | None:
    if not isinstance(team_name, str) or not team_name.strip():
        return None
    return club_index.get(normalize_name(team_name))


def fixture_key(fixture: dict[str, Any], kickoff_local: datetime) -> str:
    fixture_id = fixture.get("id")
    if isinstance(fixture_id, (str, int)) and str(fixture_id).strip():
        return f"id:{str(fixture_id).strip()}"

    home = normalize_name(str(fixture.get("home", "")))
    away = normalize_name(str(fixture.get("away", "")))
    return f"composite:{home}|{away}|{kickoff_local.isoformat()}"


def ignored_entry(index: int, fixture: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "source_index": index,
        "id": fixture.get("id"),
        "home": fixture.get("home"),
        "away": fixture.get("away"),
        "reason": reason,
    }


def identify(
    fixtures: list[dict[str, Any]],
    *,
    target_date: date,
    timezone: ZoneInfo,
    club_index: dict[str, dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected_by_key: dict[str, dict[str, Any]] = {}
    ignored: list[dict[str, Any]] = []

    for idx, fixture in enumerate(fixtures):
        home = fixture.get("home")
        away = fixture.get("away")
        if not isinstance(home, str) or not home.strip() or not isinstance(away, str) or not away.strip():
            ignored.append(ignored_entry(idx, fixture, "home_or_away_missing"))
            continue

        kickoff_local = parse_kickoff(fixture.get("kickoff"), timezone)
        if kickoff_local is None:
            ignored.append(ignored_entry(idx, fixture, "kickoff_invalid_or_without_timezone"))
            continue
        if kickoff_local.date() != target_date:
            ignored.append(ignored_entry(idx, fixture, "outside_target_date"))
            continue

        home_club = match_club(home, club_index)
        away_club = match_club(away, club_index)
        monitored_clubs = [club for club in (home_club, away_club) if club is not None]
        if not monitored_clubs:
            ignored.append(ignored_entry(idx, fixture, "no_monitored_club"))
            continue

        official = as_bool(fixture.get("official"))
        first_team = as_bool(fixture.get("first_team"))
        friendly = as_bool(fixture.get("friendly"))

        if official is not True:
            reason = "not_official" if official is False else "official_flag_missing"
            ignored.append(ignored_entry(idx, fixture, reason))
            continue
        if first_team is not True:
            reason = "not_first_team" if first_team is False else "first_team_flag_missing"
            ignored.append(ignored_entry(idx, fixture, reason))
            continue
        if friendly is not False:
            reason = "friendly" if friendly is True else "friendly_flag_missing"
            ignored.append(ignored_entry(idx, fixture, reason))
            continue

        status = normalized_status(fixture.get("status"))
        if status in SKIP_STATUSES:
            ignored.append(ignored_entry(idx, fixture, f"status_{status}"))
            continue

        competition = fixture.get("competition")
        competition_slug = fixture.get("competition_slug")
        if not isinstance(competition, str) or not competition.strip():
            ignored.append(ignored_entry(idx, fixture, "competition_missing"))
            continue
        if not isinstance(competition_slug, str) or not competition_slug.strip():
            ignored.append(ignored_entry(idx, fixture, "competition_slug_missing"))
            continue

        monitored_unique: list[dict[str, str]] = []
        seen_slugs: set[str] = set()
        for club in monitored_clubs:
            if club["slug"] not in seen_slugs:
                monitored_unique.append(club)
                seen_slugs.add(club["slug"])

        key = fixture_key(fixture, kickoff_local)
        record = {
            "id": fixture.get("id"),
            "home": home.strip(),
            "away": away.strip(),
            "competition": competition.strip(),
            "competition_slug": competition_slug.strip(),
            "kickoff_brasilia": kickoff_local.isoformat(),
            "kickoff_time_brasilia": kickoff_local.strftime("%H:%M"),
            "status": fixture.get("status"),
            "monitored_clubs": monitored_unique,
            "two_monitored_clubs_same_match": len(monitored_unique) == 2,
        }

        if key not in selected_by_key:
            selected_by_key[key] = record
        else:
            # Duplicata da mesma partida na fonte: mantém apenas um registro.
            current = selected_by_key[key]
            merged = {club["slug"]: club for club in current["monitored_clubs"]}
            for club in monitored_unique:
                merged[club["slug"]] = club
            current["monitored_clubs"] = list(merged.values())
            current["two_monitored_clubs_same_match"] = len(current["monitored_clubs"]) == 2
            ignored.append(ignored_entry(idx, fixture, "duplicate_fixture"))

    selected = sorted(
        selected_by_key.values(),
        key=lambda item: (item["kickoff_brasilia"], item["home"], item["away"]),
    )
    return selected, ignored


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Filtra uma lista normalizada de partidas e identifica jogos oficiais "
            "dos 10 clubes monitorados na data-alvo."
        )
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=DEFAULT_FIXTURES_PATH,
        help="JSON normalizado de partidas. Padrão: build/pre-jogo/fixtures-normalizados.json",
    )
    parser.add_argument(
        "--date",
        help="Data-alvo YYYY-MM-DD. Se omitida, usa amanhã em America/Sao_Paulo.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Diretório de saída. Padrão: build/pre-jogo/",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite sobrescrever somente o relatório de identificação no build/.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    timezone = ZoneInfo(config["timezone"])
    target_date = parse_target_date(args.date, timezone)
    club_index = build_club_index(config)
    fixtures = load_fixtures(args.fixtures)

    selected, ignored = identify(
        fixtures,
        target_date=target_date,
        timezone=timezone,
        club_index=club_index,
    )

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"jogos-{target_date.isoformat()}.json"

    if destination.exists() and not args.force:
        fail(
            f"O relatório já existe: {destination}. "
            "Use --force somente para substituir este arquivo de build."
        )

    result = {
        "generated_at": datetime.now(timezone).isoformat(),
        "target_date": target_date.isoformat(),
        "timezone": config["timezone"],
        "source_file": str(args.fixtures),
        "input_count": len(fixtures),
        "selected_count": len(selected),
        "ignored_count": len(ignored),
        "matches": selected,
        "ignored": ignored,
    }

    destination.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"OK: identificação concluída para {target_date.isoformat()}.")
    print(f"Partidas recebidas: {len(fixtures)}")
    print(f"Partidas selecionadas: {len(selected)}")
    for match in selected:
        monitored = ", ".join(club["name"] for club in match["monitored_clubs"])
        print(
            f'- {match["kickoff_time_brasilia"]} | {match["home"]} x {match["away"]} '
            f'| {match["competition"]} | monitorado: {monitored}'
        )
    print(f"Relatório: {destination.relative_to(ROOT) if destination.is_relative_to(ROOT) else destination}")
    print("Nenhuma matéria ou arquivo publicado foi alterado.")


if __name__ == "__main__":
    main()
