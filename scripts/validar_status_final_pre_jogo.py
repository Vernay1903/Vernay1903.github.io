#!/usr/bin/env python3
"""Validação final de status antes da publicação de um pré-jogo.

Lê apenas fontes oficiais registradas no snapshot interno de evidências e usa
Serper Scrape para confirmar que a partida continua anunciada. Qualquer indicação
explícita de adiamento, cancelamento ou suspensão bloqueia a publicação.

As fontes continuam exclusivamente internas; este script não altera conteúdo
editorial e grava apenas um relatório em build/pre-jogo/.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import ler_fontes_candidatas as reader  # noqa: E402
from scripts import buscar_fixtures_football_data as fixtures_api  # noqa: E402

DEFAULT_REPORT = ROOT / "build" / "pre-jogo" / "status-final.json"
STOPWORDS = {"de", "da", "do", "das", "dos", "del", "the", "club", "clube", "fc", "cf", "cd", "csd"}
BLOCK_PATTERNS = (
    "adiado",
    "adiada",
    "cancelado",
    "cancelada",
    "suspenso",
    "suspensa",
    "suspendido",
    "suspendida",
    "aplazado",
    "aplazada",
    "pospuesto",
    "pospuesta",
    "reprogramado",
    "reprogramada",
    "postponed",
    "cancelled",
    "canceled",
    "suspended",
)
NEGATIVE_SAFE_PHRASES = (
    "nao foi adiado",
    "nao esta adiado",
    "nao foi cancelado",
    "nao esta cancelado",
    "not postponed",
    "not cancelled",
    "not canceled",
    "no fue aplazado",
    "no fue cancelado",
)
MONTHS_PT = {
    1: "janeiro", 2: "fevereiro", 3: "marco", 4: "abril", 5: "maio", 6: "junho",
    7: "julho", 8: "agosto", 9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}
MONTHS_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
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


def fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())


def team_tokens(name: str) -> list[str]:
    return [
        token for token in re.findall(r"[a-z0-9]+", fold(name))
        if len(token) >= 3 and token not in STOPWORDS
    ]


def has_team(content: str, name: str) -> bool:
    tokens = team_tokens(name)
    if not tokens:
        return False
    normalized = fold(content)
    # Um nome composto precisa ter ao menos um token distintivo; para Flamengo,
    # o próprio nome é suficiente. Isso tolera abreviações editoriais oficiais.
    return any(token in normalized for token in tokens)


def schedule_markers(date_br: str, kickoff: str | None, stadium: str | None) -> list[str]:
    try:
        parsed = datetime.strptime(date_br, "%d/%m/%Y")
    except ValueError:
        fail(f"Data inválida no snapshot: {date_br}")

    day = parsed.day
    month = parsed.month
    markers = [
        date_br,
        f"{day:02d}/{month:02d}",
        f"{day}/{month}",
        f"{day} de {MONTHS_PT[month]}",
        f"{day} {MONTHS_PT[month]}",
        f"{day} de {MONTHS_ES[month]}",
        f"{day} {MONTHS_ES[month]}",
    ]
    if isinstance(kickoff, str) and kickoff.strip():
        markers.extend([kickoff.strip(), kickoff.strip().replace(":", "h")])
    if isinstance(stadium, str) and stadium.strip():
        markers.append(stadium.strip())
    return [fold(item) for item in markers if item]


def cancellation_hits(content: str) -> list[str]:
    normalized = fold(content)
    for phrase in NEGATIVE_SAFE_PHRASES:
        normalized = normalized.replace(phrase, " ")
    return sorted({pattern for pattern in BLOCK_PATTERNS if pattern in normalized})


def official_urls(evidence: dict[str, Any]) -> list[str]:
    rows = evidence.get("evidence")
    if not isinstance(rows, list):
        fail("Snapshot interno sem array evidence.")

    ranked: list[tuple[int, str]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        source_type = item.get("source_type")
        url = item.get("url")
        if not isinstance(source_type, str) or source_type == "official_fixture_data" or not source_type.startswith("official"):
            continue
        if not isinstance(url, str) or not url.startswith("https://"):
            continue
        rank = 0 if source_type == "official_competition" else 1
        ranked.append((rank, url))
    return [url for _rank, url in sorted(ranked)]


def verify_official_fixture(
    fixture: dict[str, Any],
    match: dict[str, Any],
) -> dict[str, Any]:
    """Checagem final por ID, data, horário, equipes, competição e status da API.

    A partida ter sido listada no preparo NÃO é suficiente: a chamada é atual,
    independente do snapshot e impede publicar jogo iniciado ou reagendado.
    """
    token = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
    if not token:
        fail("FOOTBALL_DATA_TOKEN ausente no check final gratuito.")
    match_id = fixture.get("match_id")
    if not isinstance(match_id, int) or match_id <= 0:
        fail("ID da partida oficial inválido.")
    data, _ = fixtures_api.request_json(
        base_url="https://api.football-data.org/v4",
        endpoint=f"/matches/{match_id}",
        auth_header="X-Auth-Token",
        token=token,
        params={},
    )
    if data.get("id") != match_id:
        fail("Football-Data devolveu outra partida.")
    home = data.get("homeTeam")
    away = data.get("awayTeam")
    comp = data.get("competition")
    if not isinstance(home, dict) or not isinstance(away, dict) or not isinstance(comp, dict):
        fail("Football-Data retornou equipes/competição inválidas.")
    if (
        home.get("id") != fixture.get("home_team_id")
        or away.get("id") != fixture.get("away_team_id")
        or comp.get("code") != fixture.get("competition_code")
    ):
        fail("Equipes ou competição mudaram em relação ao preparo.")
    if data.get("status") not in {"SCHEDULED", "TIMED"}:
        fail("Partida não está oficialmente agendada: " + str(data.get("status"))[:30])
    raw = data.get("utcDate")
    if not isinstance(raw, str) or not raw:
        fail("Partida oficial sem horário UTC.")
    try:
        current = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        prepared = datetime.fromisoformat(str(fixture.get("utc_date", "")).replace("Z", "+00:00"))
        expected_date = datetime.strptime(match["date"], "%d/%m/%Y").date()
    except (TypeError, ValueError, KeyError):
        fail("Data ou horário do snapshot inválido.")
    if current.tzinfo is None or prepared.tzinfo is None or current != prepared:
        fail("Horário oficial alterado após o preparo; matéria bloqueada para revisão.")
    local = current.astimezone(ZoneInfo("America/Sao_Paulo"))
    if local.date() != expected_date or local.strftime("%H:%M") != match.get("kickoff_brasilia"):
        fail("Data/hora oficial não coincide com a matéria.")
    if datetime.now(ZoneInfo("America/Sao_Paulo")) >= local:
        fail("Jogo já começou; matéria pré-jogo não será publicada.")
    return {
        "step": 33,
        "mode": "final_official_status_check",
        "match": {
            "home": match["home"],
            "away": match["away"],
            "date": match["date"],
            "kickoff_brasilia": match.get("kickoff_brasilia"),
        },
        "official_source_confirmed": True,
        "official_provider": "football-data.org",
        "postponed_cancelled_or_suspended": False,
        "publication_status_gate_passed": True,
        "sources_internal_only": True,
        "attempts": [{"source_type": "official_fixture_data", "read_ok": True,
                      "match_id": match_id, "status": data["status"]}],
    }


def validate_status(evidence: dict[str, Any], *, execute: bool) -> dict[str, Any]:
    if not execute:
        fail("Validação externa bloqueada. Use --execute explicitamente.")

    policy = evidence.get("article_source_policy")
    if not isinstance(policy, dict) or policy.get("internal_only") is not True:
        fail("Snapshot não preserva a política de fontes internas.")
    if policy.get("send_sources_to_model") is not False or policy.get("show_sources_in_article") is not False:
        fail("Snapshot permitiria vazamento de fonte para a matéria.")

    match = evidence.get("match")
    if not isinstance(match, dict):
        fail("Snapshot sem objeto match.")
    home = match.get("home")
    away = match.get("away")
    date_br = match.get("date")
    kickoff = match.get("kickoff_brasilia")
    stadium = match.get("stadium")
    if not all(isinstance(value, str) and value.strip() for value in (home, away, date_br)):
        fail("Snapshot sem mandante, visitante ou data válidos.")

    fixture_rows = [
        row for row in evidence.get("evidence", [])
        if isinstance(row, dict) and row.get("source_type") == "official_fixture_data"
    ]
    if fixture_rows:
        if len(fixture_rows) != 1:
            fail("Snapshot com IDs oficiais conflitantes.")
        return verify_official_fixture(fixture_rows[0], match)

    urls = official_urls(evidence)
    if not urls:
        fail("Nenhuma fonte oficial registrada para a validação final.")

    config = reader.load_config()
    markers = schedule_markers(date_br, kickoff if isinstance(kickoff, str) else None, stadium if isinstance(stadium, str) else None)
    attempts: list[dict[str, Any]] = []

    for url in urls:
        try:
            raw = reader.request_serper_scrape(url, config=config, timeout=30, retries=1)
            normalized = reader.normalize_scrape_response(raw)
            content = normalized.get("content", "")
        except Exception as exc:  # noqa: BLE001 - registrar e tentar a próxima fonte oficial
            attempts.append({"source_type": "official", "read_ok": False, "error": type(exc).__name__})
            continue

        if not isinstance(content, str) or len(content.strip()) < 200:
            attempts.append({"source_type": "official", "read_ok": False, "error": "conteudo_insuficiente"})
            continue

        hits = cancellation_hits(content)
        home_ok = has_team(content, home)
        away_ok = has_team(content, away)
        folded = fold(content)
        schedule_ok = any(marker in folded for marker in markers)

        attempts.append(
            {
                "source_type": "official",
                "read_ok": True,
                "home_found": home_ok,
                "away_found": away_ok,
                "schedule_marker_found": schedule_ok,
                "blocking_status_markers": hits,
            }
        )

        if hits:
            fail(
                "Fonte oficial contém indicação de adiamento/cancelamento/suspensão: "
                + ", ".join(hits)
            )
        if home_ok and away_ok and schedule_ok:
            return {
                "step": 33,
                "mode": "final_official_status_check",
                "match": {"home": home, "away": away, "date": date_br, "kickoff_brasilia": kickoff},
                "official_source_confirmed": True,
                "postponed_cancelled_or_suspended": False,
                "publication_status_gate_passed": True,
                "sources_internal_only": True,
                "attempts": attempts,
            }

    fail("Nenhuma fonte oficial pôde confirmar a partida e seu marcador de agenda no check final.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida status oficial final antes de publicar pré-jogo.")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    evidence = load_json(args.evidence)
    if not isinstance(evidence, dict):
        fail("Snapshot de evidências inválido.")

    report = validate_status(evidence, execute=args.execute)
    allowed = (ROOT / "build" / "pre-jogo").resolve()
    output = args.report.resolve()
    try:
        output.relative_to(allowed)
    except ValueError:
        fail("Relatório final só pode ser gravado em build/pre-jogo/.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("OK: fonte oficial confirmou a partida no check final.")
    print("Indicação de adiamento/cancelamento/suspensão: não")
    print("Fontes usadas no check: internas")
    print("Porta de status para publicação: aprovada")


if __name__ == "__main__":
    main()
