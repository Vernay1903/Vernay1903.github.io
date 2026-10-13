#!/usr/bin/env python3
"""A redação não deve usar o contrato como fonte nem repetir gancho quatro vezes."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.qualidade_editorial_pre_jogo import (
    repeated_preparation_hook_errors,draft_quality_errors,
)
CONTRACT={"match_context":{"home":"Fluminense","away":"Palmeiras"},
          "facts_by_requirement":[]}
def check():
    meta="<p>O contrato da partida não apresenta uma provável escalação completa para este jogo decisivo.</p>"
    assert any("preenchimento" in x for x in draft_quality_errors(meta,CONTRACT))
    paragraphs="".join(
        "<p>O Fluminense optou por um time misto e por poupar titulares "
        "na disputa da semifinal da Copa Libertadores. A escolha exige "
        "preparação distinta de compromissos anteriores do clube.</p>"
        for _ in range(4)
    )
    assert repeated_preparation_hook_errors(paragraphs,CONTRACT)
    one="<p>O Fluminense poupou titulares para chegar à semifinal.</p>"
    assert not repeated_preparation_hook_errors(one,CONTRACT)
    print("OK: sem metalinguagem editorial e sem recontar quatro vezes o time misto.")
if __name__=="__main__":
    check()
