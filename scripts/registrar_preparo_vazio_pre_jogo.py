#!/usr/bin/env python3
"""Registra preparo vazio verificável quando não há jogo elegível dos 10 clubes.

Sem consulta de pesquisa, OpenAI, alterações de páginas ou publicação.
A declaração de dia sem jogos exige relatório de identificação e planejamento
da mesma data, com zero partidas elegíveis, zero planejadas e zero descartadas.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "pre-jogo"
TZ = ZoneInfo("America/Sao_Paulo")


def build_empty_manifest(
    games: dict,
    plans: dict,
    *,
    target: str,
    source_sha: str,
) -> dict:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", target):
        raise ValueError("Data-alvo inválida.")
    datetime.strptime(target, "%Y-%m-%d")
    if games.get("target_date") != target or plans.get("target_date") != target:
        raise ValueError("Data dos relatórios não corresponde à data-alvo.")
    if games.get("selected_count") != 0 or games.get("matches") != []:
        raise ValueError("Há jogo elegível: lote vazio não autorizado.")
    if plans.get("planned_count") != 0 or plans.get("planned") != []:
        raise ValueError("Há matéria planejada: lote vazio não autorizado.")
    if plans.get("skipped_count") != 0 or plans.get("skipped") != []:
        raise ValueError("Há partidas descartadas: não confundir com dia sem jogos.")
    if not re.fullmatch(r"[a-fA-F0-9]{40}", source_sha):
        raise ValueError("SHA do checkout inválido.")
    return {
        "step": 34,
        "mode": "automatic_preparation",
        "generated_at": datetime.now(TZ).isoformat(),
        "target_date": target,
        "timezone": "America/Sao_Paulo",
        "source_main_sha": source_sha,
        "monitored_club_count": 10,
        "no_eligible_matches": True,
        "planning_skipped_count": 0,
        "prepared_count": 0,
        "skipped_count": 0,
        "articles": [],
        "skipped": [],
        "grounded_fact_fallback_attempted": False,
        "grounded_fact_fallback_succeeded": True,
        "grounded_diagnostic_attempted": False,
        "grounded_diagnostic_succeeded": True,
        "grounded_diagnostic_file": None,
        "publication_unlocked": False,
        "requires_final_official_status_check": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--source-main-sha", required=True)
    parser.add_argument("--output-dir", type=Path, default=BUILD / "automatico")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    games_file = BUILD / f"jogos-{args.date}.json"
    plans_file = BUILD / f"planos-{args.date}.json"
    games = json.loads(games_file.read_text(encoding="utf-8"))
    plans = json.loads(plans_file.read_text(encoding="utf-8"))
    manifest = build_empty_manifest(
        games, plans, target=args.date, source_sha=args.source_main_sha,
    )
    output = args.output_dir.resolve()
    if output != (BUILD / "automatico").resolve():
        raise SystemExit("ERRO: saída de lote vazio somente no diretório automático de build/.")
    if output.exists() and not args.force and any(output.iterdir()):
        raise SystemExit("ERRO: saída automática existente; use --force.")
    if output.exists() and args.force:
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"SEM JOGOS ELEGÍVEIS em {args.date}: lote vazio registrado e validado.")
    print("Pesquisa RSS: não; OpenAI: não; Serper: não; publicação: não.")


if __name__ == "__main__":
    main()
