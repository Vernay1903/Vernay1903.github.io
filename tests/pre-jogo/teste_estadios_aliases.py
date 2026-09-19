#!/usr/bin/env python3
"""Normalização de nomes comerciais/históricos de estádios."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import extrair_fatos_estruturados as facts

def main():
    assert facts.canonical_venue("Estadio Jornalista Mário Filho")=="Maracanã"
    assert facts.canonical_venue("Wanda Metropolitano")=="Riyadh Air Metropolitano"
    assert facts.canonical_venue("CEPAC Vélodrome")=="Vélodrome"
    cases=[
      ("O confronto será disputado no Riyadh Air Metropolitano.", "Riyadh Air Metropolitano"),
      ("A partida será disputada no CEPAC Vélodrome.", "Vélodrome"),
      ("O confronto será disputado e o Maracanã recebe as equipes.", "Maracanã"),
    ]
    for text,expected in cases:
        found=facts.extract_venue_values(text)
        assert any(v==expected for v,_ in found),(text,found)
    print("OK: aliases de estádios convergem para nomes canônicos sem conflito.")

if __name__=="__main__":
    main()
