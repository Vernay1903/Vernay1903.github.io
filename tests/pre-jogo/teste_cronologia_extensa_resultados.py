#!/usr/bin/env python3
"""Bloqueia cronologia de cinco jogos da amostra real e preserva duas referências."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.qualidade_editorial_pre_jogo import dense_fixture_enumeration_errors
def main():
    long=("<p>Nos cinco jogos mais recentes, o Fluminense ganhou por 3 a 1 em 27 de maio, "
          "empatou em 11 de agosto, empatou novamente em 18 de agosto, venceu em "
          "8 de setembro e perdeu em 15 de setembro.</p>")
    assert dense_fixture_enumeration_errors(long)
    brief=("<p>Nos cinco jogos recentes, o Fluminense soma duas vitórias, dois empates "
           "e uma derrota; venceu em 8 de setembro e perdeu em 15 de setembro.</p>")
    assert not dense_fixture_enumeration_errors(brief)
    print("OK: rejeita cronologia de cinco datas, preserva síntese com dois jogos.")
if __name__=="__main__":
    main()
