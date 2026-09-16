#!/usr/bin/env python3
"""
Busca partidas no football-data.org e gera uma lista normalizada para
scripts/identificar_jogos.py.

Segurança:
- o token é lido somente da variável de ambiente FOOTBALL_DATA_TOKEN;
- o token nunca é gravado no repositório;
- o script NÃO publica matéria;
- o script NÃO altera noticias.json, sitemap.xml ou HTML publicado;
- a saída padrão fica em build/pre-jogo/fixtures-normalizados.json.

Observação de cobertura:
O plano Free do football-data.org cobre as principais ligas nacionais dos
10 clubes monitorados e a Champions League. Copas nacionais e Libertadores
precisam de uma fonte complementar em outra etapa.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
DEFAULT_OUTPUT = ROOT / "build" / "pre-jogo" / "fixtures-normalizados.json"

RETRYABLE_HTTP = {429, 500, 502, 503, 504}
STATUS_MAP = {
    "SCHEDULED": "scheduled",
    "TIMED": "scheduled",
    "LIVE": "live",
    "IN_PLAY": "in_play",
    "PAUSED": "paused",
    "FINISHED": "finished",
    "POSTPONED": "postponed",
    "SUSPENDED": "suspended",
    "CANCELLED": "cancelled",
    "CANCELED": "cancelled",
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

    provider = config.get("fixtures_provider")
    if not isinstance(provider, dict):
        fail('Configuração "fixtures_provider" ausente ou inválida.')
    if provider.get("name") != "football-data.org":
        fail('O provedor configurado deve ser "football-data.org".')
    if provider.get("query_mode") != "date_range":
        fail('O modo de consulta deve permanecer "date_range".')
    if provider.get("auth_header") != "X-Auth-Token":
        fail('O header de autenticação deve permanecer "X-Auth-Token".')
    if provider.get("editorial_timezone") != config.get("timezone"):
        fail("O timezone editorial do provedor deve coincidir com o timezone geral.")

    codes = provider.get("free_competition_codes")
    if not isinstance(codes, list) or not codes or not all(isinstance(x, str) for x in codes):
        fail("fixtures_provider.free_competition_codes inválido.")

    competition_slugs = provider.get("competition_slugs")
    if not isinstance(competition_slugs, dict):
        fail("fixtures_provider.competition_slugs inválido.")
    missing_slugs = [code for code in codes if code not in competition_slugs]
    if missing_slugs:
        fail("Faltam slugs de competição para: " + ", ".join(missing_slugs))

    monitored = config.get("monitored_clubs")
    if not isinstance(monitored, list) or len(monitored) != 10:
        fail("A configuração deve conter exatamente os 10 clubes monitorados.")

    return config


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def build_monitored_index(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for club in config["monitored_clubs"]:
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
        for candidate in [name, slug.replace("-", " "), *aliases]:
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


def parse_target_date(raw: str | None, tz: ZoneInfo) -> date:
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            fail("--date deve usar o formato YYYY-MM-DD.")
    return datetime.now(tz).date() + timedelta(days=1)


def get_token(provider: dict[str, Any]) -> str:
    env_name = provider.get("api_key_env")
    if not isinstance(env_name, str) or not env_name.strip():
        fail("fixtures_provider.api_key_env inválido.")
    token = os.getenv(env_name.strip())
    if not token or not token.strip():
        fail(
            f"Variável de ambiente {env_name} não definida. "
            "O token não deve ser gravado no repositório."
        )
    return token.strip()


def request_json(
    *,
    base_url: str,
    endpoint: str,
    auth_header: str,
    token: str,
    params: dict[str, str],
    attempts: int = 3,
) -> tuple[dict[str, Any], dict[str, str]]:
    query = urlencode(params)
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}?{query}"
    headers = {
        auth_header: token,
        "Accept": "application/json",
        "User-Agent": "CorteDosEsportes-PreJogo/1.0",
    }

    last_error = "erro desconhecido"
    for attempt in range(1, attempts + 1):
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw)
                if not isinstance(data, dict):
                    fail("Resposta inesperada do football-data.org: JSON raiz não é objeto.")

                rate = {
                    "requests_available_minute": response.headers.get(
                        "X-Requests-Available-Minute", ""
                    ),
                    "request_counter_reset": response.headers.get(
                        "X-RequestCounter-Reset", ""
                    ),
                }
                return data, rate

        except HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            retry_after = exc.headers.get("X-RequestCounter-Reset") if exc.headers else None
            if exc.code not in RETRYABLE_HTTP or attempt == attempts:
                try:
                    body = exc.read().decode("utf-8", errors="replace")[:500]
                except Exception:
                    body = ""
                fail(f"Falha no football-data.org: {last_error}. {body}".strip())
            try:
                wait_seconds = max(1, int(retry_after)) if retry_after else 3
            except ValueError:
                wait_seconds = 3
            time.sleep(min(wait_seconds, 30))

        except (URLError, TimeoutError) as exc:
            last_error = str(exc)
            if attempt == attempts:
                fail(f"Falha de rede ao acessar football-data.org: {last_error}")
            time.sleep(3)

        except json.JSONDecodeError:
            fail("O football-data.org retornou conteúdo que não é JSON válido.")

    fail(f"Falha no football-data.org: {last_error}")


def parse_utc_date(value: Any) -> datetime | None:
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
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_status(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "unknown"
    upper = value.strip().upper()
    if upper in STATUS_MAP:
        return STATUS_MAP[upper]
    return normalize_name(value).replace(" ", "_") or "unknown"


def team_name(team: Any) -> str | None:
    if not isinstance(team, dict):
        return None
    for key in ("name", "shortName", "tla"):
        value = team.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def normalize_match(
    item: dict[str, Any],
    *,
    target_date: date,
    tz: ZoneInfo,
    monitored_index: dict[str, dict[str, str]],
    competition_slugs: dict[str, str],
) -> dict[str, Any] | None:
    home_obj = item.get("homeTeam")
    away_obj = item.get("awayTeam")
    competition = item.get("competition")
    if not isinstance(home_obj, dict) or not isinstance(away_obj, dict):
        return None
    if not isinstance(competition, dict):
        return None

    home = team_name(home_obj)
    away = team_name(away_obj)
    if not home or not away:
        return None

    home_monitored = monitored_index.get(normalize_name(home))
    away_monitored = monitored_index.get(normalize_name(away))
    if home_monitored is None and away_monitored is None:
        return None

    utc_kickoff = parse_utc_date(item.get("utcDate"))
    if utc_kickoff is None:
        return None
    kickoff_local = utc_kickoff.astimezone(tz)
    if kickoff_local.date() != target_date:
        return None

    competition_name = competition.get("name")
    competition_code = competition.get("code")
    if not isinstance(competition_name, str) or not competition_name.strip():
        return None
    if not isinstance(competition_code, str) or not competition_code.strip():
        return None

    competition_code = competition_code.strip()
    competition_slug = competition_slugs.get(competition_code)
    if not isinstance(competition_slug, str) or not competition_slug:
        return None

    status = normalize_status(item.get("status"))

    return {
        "id": item.get("id"),
        "home": home,
        "away": away,
        "competition": competition_name.strip(),
        "competition_slug": competition_slug,
        "kickoff": kickoff_local.isoformat(),
        "status": status,
        "official": True,
        "first_team": True,
        "friendly": False,
        "provider": "football-data.org",
        "provider_data": {
            "match_id": item.get("id"),
            "utc_date": item.get("utcDate"),
            "competition_id": competition.get("id"),
            "competition_code": competition_code,
            "competition_type": competition.get("type"),
            "matchday": item.get("matchday"),
            "stage": item.get("stage"),
            "group": item.get("group"),
            "last_updated": item.get("lastUpdated"),
            "home_team_id": home_obj.get("id"),
            "away_team_id": away_obj.get("id"),
            "matched_home_monitor": home_monitored,
            "matched_away_monitor": away_monitored,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Busca partidas do dia seguinte no football-data.org e normaliza "
            "os jogos dos 10 clubes monitorados."
        )
    )
    parser.add_argument(
        "--date",
        help="Data-alvo YYYY-MM-DD. Se omitida, usa amanhã em America/Sao_Paulo.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Arquivo de saída. Padrão: build/pre-jogo/fixtures-normalizados.json",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite substituir somente o JSON normalizado no diretório de build.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    provider = config["fixtures_provider"]
    tz = ZoneInfo(config["timezone"])
    target_date = parse_target_date(args.date, tz)
    token = get_token(provider)
    monitored_index = build_monitored_index(config)

    codes = provider["free_competition_codes"]
    competition_slugs = provider["competition_slugs"]

    # O dia editorial em Brasília vai de 03:00 UTC até 02:59 UTC do dia seguinte.
    # Consultamos dois dias UTC em uma única chamada e filtramos localmente depois.
    query_date_from = target_date
    query_date_to = target_date + timedelta(days=1)

    params = {
        "competitions": ",".join(codes),
        "dateFrom": query_date_from.isoformat(),
        "dateTo": query_date_to.isoformat(),
    }

    data, rate = request_json(
        base_url=str(provider["base_url"]),
        endpoint=str(provider["endpoint"]),
        auth_header=str(provider["auth_header"]),
        token=token,
        params=params,
    )

    matches = data.get("matches")
    if not isinstance(matches, list):
        message = data.get("message")
        if isinstance(message, str) and message.strip():
            fail("football-data.org retornou erro: " + message.strip())
        fail('Resposta do football-data.org sem array "matches".')

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for item in matches:
        if not isinstance(item, dict):
            continue
        record = normalize_match(
            item,
            target_date=target_date,
            tz=tz,
            monitored_index=monitored_index,
            competition_slugs=competition_slugs,
        )
        if record is None:
            continue

        match_id = record.get("id")
        dedupe_key = str(match_id) if match_id is not None else (
            f'{record["home"]}|{record["away"]}|{record["kickoff"]}'
        )
        if dedupe_key in seen_ids:
            continue
        seen_ids.add(dedupe_key)
        normalized.append(record)

    normalized.sort(key=lambda item: (item["kickoff"], item["home"], item["away"]))

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.force:
        fail(
            f"O arquivo já existe: {output}. "
            "Use --force somente para substituir este arquivo de build."
        )

    result = {
        "provider": "football-data.org",
        "generated_at": datetime.now(tz).isoformat(),
        "target_date": target_date.isoformat(),
        "timezone": config["timezone"],
        "query": {
            "date_from": query_date_from.isoformat(),
            "date_to": query_date_to.isoformat(),
            "competitions": codes,
        },
        "rate_limit": rate,
        "source_match_count": len(matches),
        "normalized_count": len(normalized),
        "attribution": provider.get("attribution"),
        "fixtures": normalized,
    }

    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"OK: fixtures normalizados para {target_date.isoformat()}.")
    print(f"Partidas recebidas da API: {len(matches)}")
    print(f"Partidas dos clubes monitorados: {len(normalized)}")
    for fixture in normalized:
        kickoff = datetime.fromisoformat(fixture["kickoff"])
        print(
            f'- {kickoff.strftime("%H:%M")} | {fixture["home"]} x {fixture["away"]} '
            f'| {fixture["competition"]}'
        )
    print(
        f"Arquivo: {output.relative_to(ROOT) if output.is_relative_to(ROOT) else output}"
    )
    print("Nenhuma matéria ou arquivo publicado foi alterado.")


if __name__ == "__main__":
    main()
