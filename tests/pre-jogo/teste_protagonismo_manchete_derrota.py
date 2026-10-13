#!/usr/bin/env python3
"""Não atribuir liderança do Flamengo ao Fluminense em notícia do Fla-Flu."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.ler_fontes_candidatas_passo34_9 import editorial_headline_primary_side
CONFIG=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
CTX={"home":"Fluminense","away":"Palmeiras","competition":"Libertadores","competition_slug":"libertadores"}
def check():
    assert editorial_headline_primary_side(
        "Carrascal decide, Flamengo vence o Fluminense e segue líder do Brasileiro",
        CTX,CONFIG,
    ) is None
    assert editorial_headline_primary_side(
        "Fluminense perdeu o Fla-Flu e terá titulares poupados para a semifinal",
        CTX,CONFIG,
    )=="home"
    assert editorial_headline_primary_side(
        "Saúl é titular no Flamengo, enquanto Fluminense tem time misto; escalações",
        CTX,CONFIG,
    )=="home"
    print("OK: não atribui título de vitória de terceiro clube ao time derrotado.")
if __name__=="__main__":
    check()
