#!/usr/bin/env python3
"""Regressão: cenário eliminatório não pode bloquear a 2ª rodada da fase de liga,
mas jamais liberar jogos de mata-mata ou fase/rodada não verificadas.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.extrair_fatos_estruturados import resolve_allowed_gap


def main() -> None:
    config = json.loads((ROOT / "config/pre-jogo.json").read_text(encoding="utf-8"))
    req = {
        "id": "stakes_and_qualification_scenarios_when_applicable",
        "status": "pending", "facts": [], "sources": [],
        "candidate_status": "no_candidates", "candidate_source_count": 0,
    }
    valid = resolve_allowed_gap(
        req, competition_slug="champions-league", competition_stage="LEAGUE_STAGE",
        competition_matchday=2, config=config,
    )
    assert valid["status"] == "not_applicable" and not valid["facts"], valid
    assert req["status"] == "pending", "Não modificar evidência recebida"

    for stage, matchday in [
        ("LAST_16", 2), ("QUARTER_FINALS", 1), (None, 2),
        ("LEAGUE_STAGE", None), ("LEAGUE_STAGE", 8), ("LEAGUE_STAGE", True),
    ]:
        unresolved = resolve_allowed_gap(
            req, competition_slug="champions-league", competition_stage=stage,
            competition_matchday=matchday, config=config,
        )
        assert unresolved["status"] == "pending", (stage, matchday, unresolved)

    national = resolve_allowed_gap(req, competition_slug="brasileirao", config=config)
    assert national["status"] == "not_applicable"
    print("OK: 2ª rodada comprovada da fase de liga não bloqueia; mata-mata e fase desconhecida permanecem seguros.")


if __name__ == "__main__":
    main()
