#!/usr/bin/env python3
# Reexecucao real controlada apos reparo da transmissao e da sintese editorial.
"""Proteção offline do serviço factual e do retry editorial, sem chamada OpenAI."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.redigir_pre_jogo_openai import (
    repair_verified_transmission, focused_revision_guidance,
)

def main():
    contract={
        "facts_by_requirement":[{
            "id":"transmission",
            "status":"verified",
            "facts":[{"field":"transmission","text":"Transmissão: Canal Exemplo e Plataforma Exemplo."}],
        }]
    }
    body=(
        "<p>Este jogo reúne dois clubes com contextos distintos já confirmados.</p>"
        "<p><strong>Momento dos clubes</strong></p>"
        "<p>O mandante e o visitante chegam ao confronto com preparação específica.</p>"
        "<p><strong>Desdobramento</strong></p>"
        "<p>A partida ocorre nesta rodada e encerra esta prévia.</p>"
    )
    draft={"body_html":body, "fact_fields_used":["home_recent_form"]}
    fixed=repair_verified_transmission(draft,contract)
    assert fixed and fixed is not draft and "Canal Exemplo e Plataforma Exemplo" in fixed["body_html"]
    assert "Onde assistir" in fixed["body_html"]
    assert fixed["body_html"].index("Onde assistir") < fixed["body_html"].index("A partida ocorre")
    assert "transmission" in fixed["fact_fields_used"]
    assert draft["body_html"] == body
    with_heading={"body_html":body.replace(
        "<p><strong>Desdobramento</strong></p>",
        "<p><strong>Onde assistir</strong></p><p><strong>Desdobramento</strong></p>"
    )}
    repaired=repair_verified_transmission(with_heading,contract)
    assert repaired and repaired["body_html"].count("Onde assistir") == 1
    assert repair_verified_transmission(draft,{"facts_by_requirement":[]}) is None
    guidance=focused_revision_guidance([
        "cronologia extensa de placares e datas substitui reportagem sobre a partida atual",
        "o mesmo balanço de vitórias, empates e derrotas é repetido em seções diferentes",
    ])
    assert "DOIS resultados" in guidance and "uma única vez por equipe" in guidance
    print("OK: serviço confirmado pode ser reparado sem inventar, e retry combate cronologia.")
if __name__=="__main__":
    main()
