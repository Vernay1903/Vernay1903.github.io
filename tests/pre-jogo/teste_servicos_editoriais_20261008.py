#!/usr/bin/env python3
"""Regressão de 08/10: não publicar seções vazias, repetição ou títulos de serviço sem fatos."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import validar_rascunho_pre_jogo as editorial
from scripts import preparar_redacao_pre_jogo as prepare

def main():
    cfg = prepare.load_config()
    no_service = {
        "title": "Santos FC x Flamengo pelo Brasileirão: horário e informações do jogo",
        "excerpt": "Veja o horário do confronto.",
        "facts_by_requirement": [
            {"id": "probable_lineups_and_coaches", "status": "unavailable_after_check", "facts": []},
            {"id": "transmission", "status": "unavailable_after_check", "facts": []},
        ],
    }
    bad = (
        "<p><strong>Prováveis escalações</strong></p>"
        "<p>As escalações prováveis não integram as informações disponíveis; não há nomes de jogadores ou técnicos a apresentar.</p>"
        "<p><strong>Onde assistir</strong></p>"
        "<p>O jogo começa às 19h30, na Vila Belmiro.</p>"
    )
    errors = editorial.required_service_body_errors(bad, no_service)
    assert any("transmissão verificada" in x for x in errors), errors
    assert any("jogadores e técnicos verificados" in x for x in errors), errors
    errors = editorial.editorial_style_errors(bad, no_service)
    assert any("seção vazia" in x for x in errors), errors

    assert editorial.required_service_body_errors(
        "<p><strong>Contexto da partida</strong></p><p>Confronto válido pelo campeonato.</p>",
        no_service,
    ) == []

    from teste_redacao_controlada import clean_package, valid_body
    contract = prepare.build_contract(clean_package(), config=cfg)
    draft = {
        "slug": contract["slug"],
        "body_html": valid_body(),
        "fact_fields_used": contract["required_fact_fields"],
    }
    _, base_errors = editorial.validate_draft(draft, contract, config=cfg)
    assert not base_errors, base_errors

    for section in ("Resumo do encontro", "Últimas linhas antes da partida", "Informações principais", "Fechamento"):
        altered = dict(draft, body_html=draft["body_html"] + f"<p><strong>{section}</strong></p><p>Arsenal e Manchester City se enfrentam pela Premier League.</p>")
        _, errors = editorial.validate_draft(altered, contract, config=cfg)
        assert any("subtítulo genérico repetitivo" in x for x in errors), (section, errors)
    # Regresso do texto real de 08/10: escalação inteira duplicada no corpo.
    repeated = dict(draft, body_html=draft["body_html"] +
        "<p>Raya; Timber; Saliba; Gabriel; Calafiori; Rice; Odegaard; Saka; Eze; Martinelli; Gyokeres.</p>")
    _, errors = editorial.validate_draft(repeated, contract, config=cfg)
    assert any("escalação completa repetida" in x for x in errors), errors

    duplicated_service = dict(draft, body_html=draft["body_html"] +
        "<p>ESPN e Disney+ estão na transmissão. ESPN e Disney+ mostram o jogo. ESPN e Disney+ transmitem a partida.</p>")
    _, errors = editorial.validate_draft(duplicated_service, contract, config=cfg)
    assert any("plataformas de transmissão repetidas" in x for x in errors), errors

    teaser = dict(draft, body_html=draft["body_html"] +
        "<p>A informação de elenco apresenta acompanhamento de jogo ao vivo com escalações e desfalques.</p>")
    _, errors = editorial.validate_draft(teaser, contract, config=cfg)
    assert any("descrição promocional" in x for x in errors), errors

    print("OK: regressões editoriais de 08/10 bloqueiam matéria incompleta; exemplo aprovado permanece válido.")

if __name__ == "__main__":
    main()
