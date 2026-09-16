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
        if not isinstance(source_type, str) or not source_type.startswith("official"):
            continue
        if not isinstance(url, str) or not url.startswith("https://"):
            continue
        rank = 0 if source_type == "official_competition" else 1
        ranked.append((rank, url))
    return [url for _rank, url in sorted(ranked)]


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
