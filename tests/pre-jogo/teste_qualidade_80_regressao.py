#!/usr/bin/env python3
"""Impede aprovação automática dos defeitos reais observados na amostra de 14/10."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"tests"/"pre-jogo"))
from scripts.qualidade_editorial_pre_jogo import (
    repeated_stat_summaries_errors, unrelated_story_errors, draft_quality_errors,
)
from scripts.preparar_redacao_pre_jogo import build_contract, load_config
from scripts.redigir_pre_jogo_openai import output_schema
from teste_redacao_controlada import clean_package
from scripts.extrair_fatos_estruturados import source_current_for_match

def check():
    context={"home":"Fluminense","away":"Palmeiras","competition":"Libertadores"}
    body=(
        "<p>Em dez partidas contra brasileiros em mata-matas da Libertadores, "
        "o Fluminense soma cinco vitórias, três derrotas e dois empates. "
        "A semifinal é o próximo compromisso do clube carioca no Maracanã.</p>"
        "<p><strong>Como chega o Fluminense</strong></p>"
        "<p>O Fluminense tem cinco vitórias, três derrotas e dois empates em dez "
        "partidas contra brasileiros em mata-matas da Libertadores. "
        "Esta repetição não deve ser autorizada pelo nosso portal de esportes.</p>"
        "<p><strong>Como chega o Palmeiras</strong></p>"
        "<p>Neymar criticou o gramado do Santos após sair lesionado "
        "na Copa do Brasil contra o Palmeiras. Esse assunto não altera "
        "a preparação do elenco palmeirense para a semifinal da Libertadores.</p>"
    )
    assert repeated_stat_summaries_errors(body), "Retrospecto duplicado passou."
    assert unrelated_story_errors(body,{"match_context":context}), "Neymar/Santos passou."
    assert len(draft_quality_errors(body,{"match_context":context,"facts_by_requirement":[]}))>=2

    match={"home":"Fluminense","away":"Palmeiras","competition":"Libertadores",
           "competition_slug":"libertadores",
           "kickoff_brasilia":"2026-10-14T21:30:00-03:00"}
    generic={"title":"Palmeiras news",
             "url":"https://www.goal.com/en/team/palmeiras/news/b9d2xcvxxcw",
             "published_hint":"Tue, 13 Oct 2026 12:00:00 GMT",
             "page_evidence":{"metadata":{},"evidence_segments":[
               "Palmeiras news. Neymar nets penalty brace for Santos against Flamengo."]}}
    assert not source_current_for_match(generic,match)
    match_news={"title":"Paulinho treina com elenco do Palmeiras",
                "url":"https://www.lance.com.br/palmeiras/paulinho-treina-2026.html",
                "published_hint":"Tue, 13 Oct 2026 12:00:00 GMT",
                "page_evidence":{"metadata":{},"evidence_segments":[
                  "Paulinho treinou com o elenco do Palmeiras antes da semifinal."]}}
    assert source_current_for_match(match_news,match)
    package=clean_package()
    for row in package["facts_by_requirement"]:
        if row["id"]=="recent_form_both_teams":
            row["facts"].extend([
               {"field":"home_recent_matches","text":"Resultados recentes do Arsenal verificados."},
               {"field":"away_recent_matches","text":"Resultados recentes do Manchester City verificados."},
            ])
    contract=build_contract(package,config=load_config())
    required=set(contract["required_fact_fields"])
    allowed=set(contract["allowed_fact_fields"])
    assert required.issubset(allowed)
    assert "home_recent_matches" in allowed and "home_recent_matches" not in required
    assert "away_recent_matches" in allowed and "away_recent_matches" not in required
    assert "stadium" in required and "transmission" in required
    schema=output_schema(contract)["properties"]["fact_fields_used"]
    assert "home_recent_matches" in schema["items"]["enum"]
    assert schema["minItems"] < schema["maxItems"]
    assert contract["output_contract"]["maximum_words"] == 1400
    print("OK: artigo com assunto paralelo e estatísticas repetidas é barrado; fatos extras são opcionais.")

if __name__=="__main__":
    check()
