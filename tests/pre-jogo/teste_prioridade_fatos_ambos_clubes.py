#!/usr/bin/env python3
"""Abertura e 'Como chega' precisam de informações distintas para cada equipe."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"tests"/"pre-jogo"))
from teste_redacao_controlada import clean_package
from scripts.preparar_redacao_pre_jogo import build_contract,load_config

def check():
    p=clean_package()
    p["facts_by_requirement"].append({
      "id":"editorial_individual_team_context","status":"verified",
      "facts":[
        {"field":"home_team_news_1",
         "text":"Arsenal terá o atacante Smith como dúvida depois de sentir lesão no treino."},
        {"field":"away_stakes_1",
         "text":"Manchester City trabalha a preparação para o próximo jogo."},
        {"field":"away_stakes_2",
         "text":"Manchester City terminou treino para clássico contra Liverpool."},
        {"field":"away_stakes_individual_1",
         "text":"Manchester City chega à semifinal de competição continental após retorno de artilheiro."},
      ]
    })
    contract=build_contract(p,config=load_config())
    hierarchy=contract["editorial_fact_hierarchy"]
    opening=hierarchy["opening_hook_fields"]
    assert "home_team_news_1" in opening,opening
    assert any(x.startswith("away_") for x in opening),opening
    away=hierarchy["away_specific_preparation_fields"]
    assert "away_stakes_individual_1" in away,away
    assert "away_stakes_2" not in away or away.index("away_stakes_2") > away.index("away_stakes_individual_1"),away
    print("OK: os dois clubes têm gancho e fatos distintos na hierarquia.")
if __name__=="__main__":
    check()
