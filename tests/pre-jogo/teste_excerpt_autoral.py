#!/usr/bin/env python3
"""Excerpt escrito pelo redator, mas com validação factual e título imutável."""
from __future__ import annotations
import html
import importlib.util
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import preparar_redacao_pre_jogo as prep
from scripts import validar_rascunho_pre_jogo as validator
from scripts import redigir_pre_jogo_openai as writer
from scripts import montar_preview_html_pre_jogo as preview

def main():
    source = ROOT / "tests/pre-jogo/teste_redacao_controlada.py"
    spec = importlib.util.spec_from_file_location("fixture_excerpt", source)
    assert spec and spec.loader
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    cfg = prep.load_config()
    contract = prep.build_contract(fixture.clean_package(), config=cfg)
    schema = writer.output_schema(contract)
    assert "excerpt" in schema["required"], schema
    assert contract["title"] == fixture.clean_package()["title"]
    custom = (
        "As equipes se enfrentam nesta quinta-feira (17/09), pela Premier League. "
        "O Arsenal soma três vitórias nos últimos cinco jogos, enquanto o Manchester City venceu quatro."
    )
    draft = {
        "slug": contract["slug"],
        "excerpt": custom,
        "body_html": fixture.valid_body(),
        "fact_fields_used": contract["required_fact_fields"],
    }
    validated, errors = validator.validate_draft(draft, contract, config=cfg)
    assert errors == [], errors
    assert validated["excerpt"] == custom
    rendered, meta = preview.build_preview(draft=validated, contract=contract)
    assert html.escape(custom, quote=True) in rendered, "O excerpt editorial precisa constar no HTML."
    assert contract["title"] in rendered, "Título fixo não pode mudar."

    wrong = dict(draft, excerpt=custom + " O Arsenal venceu 999 partidas.")
    _, errors = validator.validate_draft(wrong, contract, config=cfg)
    assert any("número sem suporte" in e for e in errors), errors

    too_short = dict(draft, excerpt="As equipes se enfrentam.")
    _, errors = validator.validate_draft(too_short, contract, config=cfg)
    assert any("excerpt autoral" in e for e in errors), errors
    print("OK: excerpt livre no HTML, título fixo, datas e números sujeitos à validação.")


if __name__ == "__main__":
    main()
