#!/usr/bin/env python3
"""HTML de quatro seções substantivas é válido; três não."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.montar_preview_html_pre_jogo import section_records

def main():
    four="".join(
        f"<p><strong>Seção {i}</strong></p><p>Conteúdo jornalístico factual, verificado e independente {i}.</p>"
        for i in range(4)
    )
    assert len(section_records(four))==4
    try:
        section_records(four.rsplit("<p><strong>Seção 3",1)[0])
    except SystemExit:
        pass
    else:
        raise AssertionError("Três seções não devem passar")
    print("OK: prévia aceita quatro seções, não inventa quinta.")
if __name__=="__main__":
    main()
