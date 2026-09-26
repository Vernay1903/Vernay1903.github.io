#!/usr/bin/env python3
"""Registra lotes sem matéria sem pesquisar ou chamar OpenAI.

Modos:
- no_games: nenhum dos 10 clubes tem partida elegível;
- no_new_articles: há partida elegível, mas todas foram barradas no planejamento
  por duplicidade/colisão e não existe matéria nova a pesquisar/redigir.
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


def _base_manifest(*, target: str, source_sha: str) -> dict:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", target):
        raise ValueError("Data-alvo inválida.")
    datetime.strptime(target, "%Y-%m-%d")
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


def _validate_dates(games: dict, plans: dict, target: str) -> None:
    if games.get("target_date") != target or plans.get("target_date") != target:
        raise ValueError("Data dos relatórios não corresponde à data-alvo.")


def build_empty_manifest(games: dict, plans: dict, *, target: str, source_sha: str) -> dict:
    _validate_dates(games, plans, target)
    if games.get("selected_count") != 0 or games.get("matches") != []:
        raise ValueError("Há jogo elegível: lote sem jogos não autorizado.")
    if plans.get("planned_count") != 0 or plans.get("planned") != []:
        raise ValueError("Há matéria planejada: lote sem jogos não autorizado.")
    if plans.get("skipped_count") != 0 or plans.get("skipped") != []:
        raise ValueError("Há partidas descartadas: não confundir com dia sem jogos.")
    result = _base_manifest(target=target, source_sha=source_sha)
    result["no_eligible_matches"] = True
    result["no_new_articles"] = False
    result["planning_skipped_count"] = 0
    return result


def build_no_new_articles_manifest(
    games: dict, plans: dict, *, target: str, source_sha: str
) -> dict:
    _validate_dates(games, plans, target)
    matches = games.get("matches")
    selected = games.get("selected_count")
    if type(selected) is not int or selected <= 0 or not isinstance(matches, list) or not matches:
        raise ValueError("Modo sem matéria nova exige ao menos uma partida elegível.")
    if plans.get("planned_count") != 0 or plans.get("planned") != []:
        raise ValueError("Há matéria planejada: pesquisa/redação ainda é necessária.")
    skipped = plans.get("skipped")
    skipped_count = plans.get("skipped_count")
    if (
        type(skipped_count) is not int or skipped_count <= 0
        or not isinstance(skipped, list) or len(skipped) != skipped_count
    ):
        raise ValueError("Sem matéria planejada, o motivo de descarte precisa estar registrado.")
    result = _base_manifest(target=target, source_sha=source_sha)
    result["no_eligible_matches"] = False
    result["no_new_articles"] = True
    result["planning_skipped_count"] = skipped_count
    result["planning_skip_reasons"] = sorted({
        str(reason)
        for item in skipped if isinstance(item, dict)
        for reason in item.get("reasons", [])
        if isinstance(reason, str) and reason.strip()
    })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--source-main-sha", required=True)
    parser.add_argument("--kind", choices=("no_games", "no_new_articles"), default="no_games")
    parser.add_argument("--output-dir", type=Path, default=BUILD / "automatico")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    games = json.loads((BUILD / f"jogos-{args.date}.json").read_text(encoding="utf-8"))
    plans = json.loads((BUILD / f"planos-{args.date}.json").read_text(encoding="utf-8"))
    builder = build_empty_manifest if args.kind == "no_games" else build_no_new_articles_manifest
    manifest = builder(games, plans, target=args.date, source_sha=args.source_main_sha)

    output = args.output_dir.resolve()
    if output != (BUILD / "automatico").resolve():
        raise SystemExit("ERRO: lote sem matéria somente no diretório automático de build/.")
    if output.exists() and not args.force and any(output.iterdir()):
        raise SystemExit("ERRO: saída automática existente; use --force.")
    if output.exists() and args.force:
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.kind == "no_games":
        print(f"SEM JOGOS ELEGÍVEIS em {args.date}: lote vazio registrado e validado.")
    else:
        print(
            f"SEM MATÉRIAS NOVAS em {args.date}: "
            f"{manifest['planning_skipped_count']} confronto(s) já barrado(s) no planejamento."
        )
    print("Pesquisa RSS: não; OpenAI: não; Serper: não; publicação: não.")


if __name__ == "__main__":
    main()
