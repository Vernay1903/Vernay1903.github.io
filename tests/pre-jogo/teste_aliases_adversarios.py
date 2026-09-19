#!/usr/bin/env python3
"""Regressão das variantes de nomes vindas do provedor."""
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import extrair_fatos_estruturados as facts
from scripts import buscar_fontes_serper as search

def main():
    config=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
    cases=[
        ("RB Bragantino","Red Bull Bragantino"),
        ("RB Bragantino","Bragantino"),
        ("Club Atlético de Madrid","Atlético de Madrid"),
        ("Club Atlético de Madrid","Atletico Madrid"),
        ("Olympique de Marseille","Marseille"),
    ]
    for provider_name, page_name in cases:
        aliases=facts.unmonitored_team_aliases(provider_name)
        assert any(facts.normalize_text(page_name)==facts.normalize_text(a) for a in aliases), (provider_name,aliases)
        assert facts.mentions_team(f"Prévia: {page_name} entra em campo amanhã.",provider_name,config)
    assert "red bull bragantino" in search.team_variants("RB Bragantino",config)
    assert "atletico madrid" in search.team_variants("Club Atlético de Madrid",config)
    assert "marseille" in search.team_variants("Olympique de Marseille",config)
    assert not facts.mentions_team("Prévia do Real Betis amanhã.","RB Bragantino",config)
    assert not facts.mentions_team("Prévia do Lyon amanhã.","Olympique de Marseille",config)
    print("OK: aliases conservadores reconhecem os três adversários sem ampliar para clubes diferentes.")

if __name__=="__main__":
    main()
