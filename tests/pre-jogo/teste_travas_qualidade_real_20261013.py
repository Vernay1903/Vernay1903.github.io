#!/usr/bin/env python3
"""Regressão da primeira matéria real da API: 960 palavras mas conteúdo reprovado."""
from __future__ import annotations
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.extrair_fatos_estruturados import source_current_for_match
from scripts.qualidade_editorial_pre_jogo import draft_quality_errors, category_and_third_club_errors
from scripts.montar_pacote_editorial import adjusted_service_headline

CONFIG=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
CTX={"home":"Fluminense","away":"Palmeiras","competition":"Libertadores",
     "competition_slug":"libertadores","kickoff_brasilia":"2026-10-14T21:30:00-03:00"}
CONTRACT={"match_context":CTX,"facts_by_requirement":[],"editorial_storyline":None}

def fake(title, opening):
    return {"url":"https://www.uol.com.br/esporte/futebol/ultimas-noticias/2026/10/13/exemplo.htm",
            "title":title,"published_hint":"Tue, 13 Oct 2026 12:00:00 GMT",
            "source_type":"major_sports_media",
            "page_evidence":{"metadata":{},"evidence_segments":[opening]}}

def check():
    youth=fake(
        "Fluminense derrota Maricá e dorme líder do Carioca Sub-20",
        "Fluminense derrota Maricá e assume a liderança do Carioca Sub-20."
    )
    assert not source_current_for_match(youth,CTX), "Sub-20 não pode virar notícia do profissional"
    senior=fake("Fluminense prepara elenco para semifinal da Libertadores",
                "O Fluminense treinou nesta terça-feira para a semifinal da Libertadores.")
    assert source_current_for_match(senior,CTX)

    youth_paragraph="<p>Fluminense derrotou o Maricá fora de casa e dormiu líder do Carioca Sub-20.</p>"
    assert category_and_third_club_errors(youth_paragraph, CONTRACT)
    third="<p>Na preparação da equipe, Saúl é titular no Flamengo, adversário do Fluminense.</p>"
    assert category_and_third_club_errors(third, CONTRACT)
    owned="<p>Paulinho é titular no Palmeiras antes da semifinal da Libertadores.</p>"
    assert not category_and_third_club_errors(owned, CONTRACT)

    meta="<p>No conjunto de informações fornecidas, o Fluminense tem foco na preparação.</p>"
    assert any("preenchimento" in x for x in draft_quality_errors(meta, CONTRACT))
    meta2="<p>Não há confrontos diretos disponíveis no pacote.</p>"
    assert any("preenchimento" in x for x in draft_quality_errors(meta2, CONTRACT))

    article={"match_context":CTX,
             "title":"Fluminense x Palmeiras na competição Libertadores: horário, prováveis escalações e transmissão",
             "excerpt":"Fluminense e Palmeiras se enfrentam na competição Libertadores; veja escalações e transmissão."}
    title,excerpt=adjusted_service_headline(article,{},config=CONFIG)
    assert "pela Libertadores" in title and "pela Libertadores" in excerpt, (title,excerpt)
    assert excerpt.startswith("As equipes se enfrentam nesta quarta-feira (14/10)")
    assert "prováveis escalações" not in title and "transmissão" not in title, title
    print("OK: texto real inadequado é bloqueado; título não promete serviços inexistentes.")
if __name__=="__main__":
    check()
