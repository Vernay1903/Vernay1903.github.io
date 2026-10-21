#!/usr/bin/env python3
"""A narrativa do editor tem liberdade sem dispensar apuração e a nota >=80."""
from __future__ import annotations
import importlib.util
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import qualidade_editorial_pre_jogo as quality
from scripts import preparar_redacao_pre_jogo as prepare
from scripts import redigir_pre_jogo_openai as redactor

def main():
    fixture_path = ROOT / "tests/pre-jogo/teste_redacao_controlada.py"
    spec = importlib.util.spec_from_file_location("editor_fixture", fixture_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    contract = prepare.build_contract(module.clean_package(), config=prepare.load_config())
    assert contract["output_contract"]["minimum_strong_subheadings"] == 3
    prompt = redactor.user_payload(contract)
    assert "pauta OPCIONAL" in prompt or "apenas sugestões" in prompt, "Roteiro ainda obrigatório."
    instructions = redactor.system_instructions()
    assert "Escolha livremente assuntos, ordem e títulos" in instructions
    assert "não determina cabeçalhos" in instructions
    assert "PERSONALIDADE EDITORIAL PRIORITÁRIA" in instructions

    original = (ROOT / "ldu-x-palmeiras-libertadores-onde-assistir-horario-escalacoes.html").read_text()
    start = original.index('<article id="articleBody"')
    end = original.index("</article>", start) + len("</article>")
    approved = original[start:end]
    alternative = (
        approved
        .replace("Como chega o Palmeiras", "Palmeiras muda a defesa para a decisão")
        .replace("Como chega a LDU", "LDU preserva titulares antes do jogo em Quito")
    )
    model = {"match_context": {"home": "Palmeiras", "away": "LDU"}, "facts_by_requirement": []}
    score = quality.editorial_scorecard(alternative, model)
    assert score["score"] >= 80 and score["passed"], score
    assert not any("nota editorial" in x for x in quality.draft_quality_errors(alternative, model))
    assert quality.editorial_scorecard(approved, model)["passed"]
    print("OK: narrativa livre, títulos originais e nota >=80 preservados; fatos e serviços inalterados.")

if __name__ == "__main__":
    main()
