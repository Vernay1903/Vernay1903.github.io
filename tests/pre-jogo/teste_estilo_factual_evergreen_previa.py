#!/usr/bin/env python3
"""Regressão: estilo do editor de resultados adaptado a PRÉVIA, sem copiar fatos."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts import preparar_redacao_pre_jogo as preparo
from scripts import redigir_pre_jogo_openai as redator


def main() -> None:
    persona = redator.editorial_persona_instructions()
    instructions = redator.system_instructions()
    assert "REFERÊNCIA DO EDITOR — FACTUAL COM TOM EVERGREEN" in persona
    assert "TRADUÇÃO PARA PRÉVIA" in persona
    assert "ENFOQUE FACTUAL COM TOM EVERGREEN" in instructions
    assert "SEM narrar acontecimentos futuros" in instructions or (
        "NÃO descreva como ocorrido aquilo que só poderá acontecer" in instructions
    )
    assert "Não copie nomes, resultados, alegações" in instructions
    assert "editorial_section_plan não obriga blocos" in instructions
    # O artigo de resultado é uma REFERÊNCIA DE ESTILO, jamais base factual.
    assert "Declan Rice garantiu o 2 a 2" not in instructions
    assert "Eberechi Eze abriu o placar" not in instructions
    assert "The Guardian +1" not in instructions

    # Fatos reais de outro jogo não podem contaminar o próximo contrato.
    path = ROOT / "tests" / "pre-jogo" / "teste_redacao_controlada.py"
    spec = importlib.util.spec_from_file_location("fixture_previa_evergreen", path)
    assert spec is not None and spec.loader is not None
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    contract = preparo.build_contract(fixture.clean_package(), config=preparo.load_config())
    prompt = redator.user_payload(contract)
    assert "APLIQUE A REFERÊNCIA FACTUAL-EVERGREEN DO EDITOR" in prompt
    assert "situação atual dos clubes" in instructions
    assert "sem determinar cabeçalhos" in prompt
    assert "fact_fields_used" in redator.output_schema(contract)["required"]
    assert "excerpt" in redator.output_schema(contract)["required"]
    assert "minimum_strong_subheadings" in contract["output_contract"]
    assert contract["title"] == fixture.clean_package()["title"]
    assert (
        "config/persona-criador-de-materias-prejogo.txt"
        in preparo.EDITORIAL_BUILD_FILES
    )
    print("OK: tom factual-evergreen ativo, prévia no futuro, estilo livre, apuração e título fixo.")


if __name__ == "__main__":
    main()
