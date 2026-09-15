#!/usr/bin/env python3
"""
Busca na API-Football as partidas da data-alvo e gera uma entrada normalizada
para scripts/identificar_jogos.py.

Segurança:
- a chave nunca é gravada em arquivo;
- a chave é lida somente da variável de ambiente API_FOOTBALL_KEY;
- o script NÃO publica matéria;
- o script NÃO altera noticias.json, sitemap.xml ou HTML publicado;
- a saída padrão fica em build/pre-jogo/fixtures-normalizados.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
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
    "NS": "scheduled",
    "TBD": "scheduled",
    "PST": "postponed",
    "CANC": "cancelled",
    "ABD": "abandoned",
    "SUSP": "suspended",
    "INT": "interrupted",
    "FT": "finished",
    "AET": "finished",
    "PEN": "finished",
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
    if provider.get("name") != "api-football":
        fail('O provedor configurado deve ser "api-football".')
    if provider.get("query_mode") != "date":
        fail('O modo de consulta deve permanecer "date".')
    if provider.get("timezone") != config.get("timezone"):
        fail("O timezone do provedor deve ser igual ao timezone editorial.")

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


def slugify(value: str) -> str:
    normalized = normalize_name(value)
    slug = normalized.replace(" ", "-")
    return slug or "competicao"


def build_monitored_index(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for club in config["monitored_clubs"]:
        if not isinstance(club, dict):
            fail("Há um clube inválido em monitored_clubs.")
        name = club.get("name")
        slug = club.get("slug")
        aliases = club.get("aliases", [])
        if not isinstance(name, str) or not isinstance(slug, str):
            fail("Clube monitorado sem name/slug válido.")
        if not isinstance(aliases, list) or not all(isinstance(x, str) for x in aliases):
            fail(f"Aliases inválidos para {name}.")

        canonical = {"name": name, "slug": slug}
        for candidate in [name, slug.replace("-", " "), *aliases]:
            key = normalize_name(candidate)
            if key:
                index[key] = canonical
    return index


def parse_target_date(raw: str | None, timezone: ZoneInfo) -> date:
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            fail("--date deve usar o formato YYYY-MM-DD.")
    return datetime.now(timezone).date() + timedelta(days=1)


def get_api_key(provider: dict[str, Any]) -> str:
    env_name = provider.get("api_key_env")
    if not isinstance(env_name, str) or not env_name.strip():
        fail("fixtures_provider.api_key_env inválido.")
    value = os.getenv(env_name.strip())
    if not value or not value.strip():
        fail(
            f"Variável de ambiente {env_name} não definida. "
            "A chave da API não deve ser gravada no repositório."
        )
    return value.strip()


def api_request(
    *,
    base_url: str,
    endpoint: str,
    api_key: str,
    params: dict[str, str],
    attempts: int = 2,
) -> tuple[dict[str, Any], dict[str, str]]:
    query = urlencode(params)
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}?{query}"
    headers = {
        "x-apisports-key": api_key,
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
                quota = {
                    "daily_limit": response.headers.get("x-ratelimit-requests-limit", ""),
                    "daily_remaining": response.headers.get("x-ratelimit-requests-remaining", ""),
                    "minute_limit": response.headers.get("X-RateLimit-Limit", ""),
                    "minute_remaining": response.headers.get("X-RateLimit-Remaining", ""),
                }
                if not isinstance(data, dict):
                    fail("Resposta inesperada da API-Football: JSON raiz não é objeto.")
                return data, quota
        except HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code not in RETRYABLE_HTTP or attempt == attempts:
                try:
                    body = exc.read().decode("utf-8", errors="replace")[:500]
                except Exception:
                    body = ""
                fail(f"Falha na API-Football: {last_error}. {body}".strip())
        except (URLError, TimeoutError) as exc:
            last_error = str(exc)
            if attempt == attempts:
                fail(f"Falha de rede ao acessar API-Football: {last_error}")
        except json.JSONDecodeError:
            fail("A API-Football retornou conteúdo que não é JSON válido.")

        time.sleep(2)

    fail(f"Falha na API-Football: {last_error}")


def api_errors(data: dict[str, Any]) -> list[str]:
    errors = data.get("errors")
    if not errors:
        return []
    if isinstance(errors, dict):
        return [f"{key}: {value}" for key, value in errors.items()]
    if isinstance(errors, list):
        return [str(item) for item in errors]
    return [str(errors)]


def is_friendly_competition(name: str, patterns: list[str]) -> bool:
    normalized = normalize_name(name)
    return any(normalize_name(pattern) in normalized for pattern in patterns if pattern.strip())


def normalize_fixture(
    item: dict[str, Any],
    *,
    monitored_index: dict[str, dict[str, str]],
    friendly_patterns: list[str],
) -> dict[str, Any] | None:
    fixture = item.get("fixture")
    league = item.get("league")
    teams = item.get("teams")
    if not isinstance(fixture, dict) or not isinstance(league, dict) or not isinstance(teams, dict):
        return None

    home = teams.get("home")
    away = teams.get("away")
    if not isinstance(home, dict) or not isinstance(away, dict):
        return None

    home_name = home.get("name")
    away_name = away.get("name")
    if not isinstance(home_name, str) or not isinstance(away_name, str):
        return None

    home_monitored = monitored_index.get(normalize_name(home_name))
    away_monitored = monitored_index.get(normalize_name(away_name))
    if home_monitored is None and away_monitored is None:
        return None

    league_name = league.get("name")
    if not isinstance(league_name, str) or not league_name.strip():
        return None

    friendly = is_friendly_competition(league_name, friendly_patterns)

    status_obj = fixture.get("status")
    status_short = ""
    status_long = ""
    if isinstance(status_obj, dict):
        if isinstance(status_obj.get("short"), str):
            status_short = status_obj["short"].strip().upper()
        if isinstance(status_obj.get("long"), str):
            status_long = status_obj["long"].strip()

    normalized_status = STATUS_MAP.get(status_short)
    if not normalized_status:
        normalized_status = normalize_name(status_long).replace(" ", "_") or status_short.casefold() or "unknown"

    kickoff = fixture.get("date")
    if not isinstance(kickoff, str) or not kickoff.strip():
        return None

    venue = fixture.get("venue") if isinstance(fixture.get("venue"), dict) else {}

    return {
        "id": fixture.get("id"),
        "home": home_name.strip(),
        "away": away_name.strip(),
        "competition": league_name.strip(),
        "competition_slug": slugify(league_name),
        "kickoff": kickoff.strip(),
        "status": normalized_status,
        "official": not friendly,
        "first_team": True,
        "friendly": friendly,
        "provider": "api-football",
        "provider_data": {
            "fixture_id": fixture.get("id"),
            "status_short": status_short,
            "status_long": status_long,
            "league_id": league.get("id"),
            "league_country": league.get("country"),
            "league_season": league.get("season"),
            "round": league.get("round"),
            "home_team_id": home.get("id"),
            "away_team_id": away.get("id"),
            "venue_id": venue.get("id"),
            "venue_name": venue.get("name"),
            "venue_city": venue.get("city"),
            "referee": fixture.get("referee"),
            "matched_home_monitor": home_monitored,
            "matched_away_monitor": away_monitored,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Busca fixtures do dia seguinte na API-Football e normaliza a saída."
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
    timezone = ZoneInfo(config["timezone"])
    target_date = parse_target_date(args.date, timezone)
    api_key = get_api_key(provider)
    monitored_index = build_monitored_index(config)

    patterns = provider.get("friendly_name_patterns", [])
    if not isinstance(patterns, list) or not all(isinstance(x, str) for x in patterns):
        fail("fixtures_provider.friendly_name_patterns inválido.")

    params = {
        "date": target_date.isoformat(),
        "timezone": config["timezone"],
    }

    data, quota = api_request(
        base_url=str(provider["base_url"]),
        endpoint=str(provider["endpoint"]),
        api_key=api_key,
        params=params,
    )

    errors = api_errors(data)
    if errors:
        fail("API-Football retornou erros: " + " | ".join(errors))

    response = data.get("response")
    if not isinstance(response, list):
        fail('Resposta da API-Football sem array "response".')

    paging = data.get("paging") if isinstance(data.get("paging"), dict) else {}
    total_pages = paging.get("total", 1)
    current_page = paging.get("current", 1)
    if isinstance(total_pages, int) and isinstance(current_page, int) and total_pages > current_page:
        all_response = list(response)
        for page in range(current_page + 1, total_pages + 1):
            page_params = dict(params)
            page_params["page"] = str(page)
            page_data, page_quota = api_request(
                base_url=str(provider["base_url"]),
                endpoint=str(provider["endpoint"]),
                api_key=api_key,
                params=page_params,
            )
            page_errors = api_errors(page_data)
            if page_errors:
                fail("API-Football retornou erros na paginação: " + " | ".join(page_errors))
            page_response = page_data.get("response")
            if not isinstance(page_response, list):
                fail("Página adicional da API-Football sem array response.")
            all_response.extend(page_response)
            quota = page_quota
        response = all_response

    fixtures: list[dict[str, Any]] = []
    for item in response:
        if not isinstance(item, dict):
            continue
        normalized = normalize_fixture(
            item,
            monitored_index=monitored_index,
            friendly_patterns=patterns,
        )
        if normalized is not None:
            fixtures.append(normalized)

    fixtures.sort(key=lambda x: (str(x.get("kickoff", "")), str(x.get("home", ""))))

    destination = args.output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not args.force:
        fail(
            f"A saída já existe: {destination}. "
            "Use --force somente para substituir este arquivo de build."
        )

    result = {
        "provider": "api-football",
        "generated_at": datetime.now(timezone).isoformat(),
        "target_date": target_date.isoformat(),
        "timezone": config["timezone"],
        "api_results_received": len(response),
        "normalized_monitored_fixtures": len(fixtures),
        "quota": quota,
        "fixtures": fixtures,
    }

    destination.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"OK: API-Football consultada para {target_date.isoformat()}.")
    print(f"Partidas recebidas da API: {len(response)}")
    print(f"Partidas envolvendo clubes monitorados: {len(fixtures)}")
    for fixture in fixtures:
        print(
            f'- {fixture["kickoff"]} | {fixture["home"]} x {fixture["away"]} '
            f'| {fixture["competition"]} | status={fixture["status"]} '
            f'| friendly={fixture["friendly"]}'
        )
    if quota.get("daily_remaining"):
        print(f'Requisições restantes no dia: {quota["daily_remaining"]}')
    print(f"Arquivo: {destination.relative_to(ROOT) if destination.is_relative_to(ROOT) else destination}")
    print("Nenhuma matéria ou arquivo publicado foi alterado.")


if __name__ == "__main__":
    main()
