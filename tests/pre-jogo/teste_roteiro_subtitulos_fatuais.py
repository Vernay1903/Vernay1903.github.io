#!/usr/bin/env python3
"""A exigência de subtítulos deve corresponder a seções com fatos reais."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"tests"/"pre-jogo"))
from teste_redacao_controlada import clean_package
from scripts.preparar_redacao_pre_jogo import build_contract, load_config

def check():
    package=clean_package()
    package["facts_by_requirement"]=[
        r for r in package["facts_by_requirement"]
        if r["id"] not in (
            "competition_specific_head_to_head",
            "probable_lineups_and_coaches",
            "transmission",
        )
    ]
    recent=next(r for r in package["facts_by_requirement"]
                if r["id"]=="recent_form_both_teams")
    recent["facts"].extend([
        {"field":"home_recent_matches","text":"Arsenal venceu três das cinco partidas recentes da Premier League."},
        {"field":"away_recent_matches","text":"Manchester City venceu quatro das cinco partidas recentes da Premier League."},
    ])
    contract=build_contract(package,config=load_config())
    plan=contract["editorial_section_plan"]
    assert not any("Forma recente" in item for item in plan),plan
    assert len(plan)==2,plan  # Sem contexto confirmado, só existem dois assuntos seguros
    assert contract["output_contract"]["minimum_strong_subheadings"]==4

    recent["facts"]=[f for f in recent["facts"]
                     if f["field"] not in ("home_recent_matches","away_recent_matches")]
    short_contract=build_contract(package,config=load_config())
    short_plan=short_contract["editorial_section_plan"]
    assert len(short_plan)==2,short_plan
    assert short_contract["output_contract"]["minimum_strong_subheadings"]==4
    print("OK: roteiro não inventa contexto ou serviço; a exigência estrutural continua travada no validador.")

if __name__=="__main__":
    check()
