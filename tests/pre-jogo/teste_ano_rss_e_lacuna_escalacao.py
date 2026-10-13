#!/usr/bin/env python3
"""Reprodução da falha real de 14/10: RSS 2025 e XI não verificável."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import buscar_fontes_serper as search
from scripts import ler_fontes_candidatas_passo34_9 as research
from scripts.extrair_fatos_estruturados import resolve_allowed_gap
CONFIG=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
CTX={"home":"Fluminense","away":"Palmeiras",
     "competition":"Libertadores","competition_slug":"libertadores",
     "kickoff_brasilia":"2026-10-14T21:30:00-03:00"}

def check():
    stale={
      "url":"https://www.fluminense.com.br/noticia/copa-do-brasil-2025-ingressos",
      "title":"Copa do Brasil 2025: informações de ingressos Fluminense x Bahia",
      "published_hint":"Thu, 08 Oct 2026 17:00:00 GMT",
    }
    assert not search.candidate_recent_for_article(stale,"2026-10-14",days=7)
    recent={
      "url":"https://www.uol.com.br/esporte/futebol/2026/10/13/fluminense.htm",
      "title":"Fluminense poupa jogadores para semifinal da Libertadores 2026",
      "published_hint":"Tue, 13 Oct 2026 16:00:00 GMT",
    }
    assert search.candidate_recent_for_article(recent,"2026-10-14",days=7)
    candidate={"url":"https://www.msn.com/pt-br/noticias/escalacoes-2026",
       "title":"Fluminense x Palmeiras: palpite e escalações",
       "content_checked":False,"eligible_for_factual_validation":False}
    pending={"id":"probable_lineups_and_coaches","status":"pending",
       "source_candidates":[candidate],
       "candidate_status":"candidate_sources_found","candidate_source_count":1,
       "page_check_attempt_count":1,"page_check_success_count":0,
       "facts":[],"sources":[]}
    with patch.object(research,"_search_and_check",return_value=[]):
        checked=research._ensure_allowed_gap_check(
           pending,context=CTX,article_date="2026-10-14",
           checked_at="2026-10-13T13:00:00-03:00",config=CONFIG)
    assert checked.get("passo34_9_targeted_search_attempted") is True
    resolved=resolve_allowed_gap(checked,competition_slug="libertadores",config=CONFIG)
    assert resolved["status"]=="unavailable_after_check",resolved
    assert resolved["facts"]==[],resolved
    # Uma pesquisa não executada não autoriza omissão silenciosa.
    not_checked=resolve_allowed_gap(pending,competition_slug="libertadores",config=CONFIG)
    assert not_checked["status"] != "unavailable_after_check",not_checked
    print("OK: rejeita RSS 2025 e aceita indisponibilidade apenas após busca.")

if __name__=="__main__":
    check()
