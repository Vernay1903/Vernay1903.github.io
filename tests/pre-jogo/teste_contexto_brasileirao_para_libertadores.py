#!/usr/bin/env python3
"""Notícia do Brasileiro só fundamenta PREPARAÇÃO explícita para Libertadores."""
from __future__ import annotations
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.extrair_fatos_estruturados import (
    source_current_for_match, extract_individual_team_context,
)
CONFIG=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
CTX={"home":"Fluminense","away":"Palmeiras","competition":"Libertadores",
     "competition_slug":"libertadores","kickoff_brasilia":"2026-10-14T21:30:00-03:00"}
def source(title,description,content,side="home",year=2026):
    team=CTX[side]
    return {
        "url":f"https://www.uol.com.br/esporte/futebol/ultimas-noticias/{year}/10/11/contexto.htm",
        "title":title,"publisher":"UOL","source_type":"major_sports_media",
        "published_hint":f"Sun, 11 Oct {year} 12:46:00 GMT",
        "checked_at":"2026-10-13T12:20:00-03:00",
        "content_checked":True,"eligible_for_factual_validation":True,
        "editorial_target_side":side,"editorial_target_team":team,
        "page_evidence":{"metadata":{"description":description},
                         "evidence_segments":[content]},
    }
def check():
    note=source(
        "Saúl é titular no Flamengo, enquanto Fluminense tem time misto; escalações",
        "Flamengo e Fluminense estão escalados para o clássico pela 30ª rodada do Campeonato Brasileiro",
        "Flamengo e Fluminense estão escalados para o clássico de domingo. "
        "Já o Flu, com foco na semifinal da Copa Libertadores, terá um time misto "
        "para poupar titulares importantes para o duelo com Palmeiras."
    )
    assert source_current_for_match(note,CTX), "Foco explícito na semifinal deve superar filtro Brasileiro"
    extracted=extract_individual_team_context(
        [{"id":"editorial_context_both_teams","source_candidates":[note]}],
        match_context=CTX,config=CONFIG)
    assert extracted and any(f["field"].startswith("home_stakes") for f in extracted["facts"]), extracted
    unrelated=source(
        "Flamengo se prepara para o Brasileirão",
        "Flamengo e Fluminense já têm compromissos no Campeonato Brasileiro",
        "Flamengo trabalha para a decisão do Brasileirão. No rodapé do site há "
        "notícias sobre a Libertadores e a competição brasileira."
    )
    assert not source_current_for_match(unrelated,CTX), "Rodapé não prova preparação do Fluminense"
    older=source(note["title"],note["page_evidence"]["metadata"]["description"],
                 note["page_evidence"]["evidence_segments"][0],year=2021)
    assert not source_current_for_match(older,CTX), "Fonte histórica deve continuar bloqueada"
    alternate=source(
        "Carrascal decide, Flamengo vence o Fluminense e segue líder do Brasileiro",
        "O Flamengo venceu o clássico e lidera o Campeonato Brasileiro",
        "Flamengo e Fluminense têm compromissos na Libertadores. "
        "Na quarta-feira (14), o Fluminense recebe o Palmeiras pelo jogo de ida "
        "da semifinal da Copa Libertadores."
    )
    assert source_current_for_match(alternate,CTX)
    print("OK: Brasileiro -> Libertadores somente com preparação explícita verificada.")
if __name__=="__main__":
    check()
