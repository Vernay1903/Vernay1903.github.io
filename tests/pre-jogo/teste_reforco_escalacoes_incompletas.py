#!/usr/bin/env python3
"""Pesquisa continua após uma única página parcial de escalações."""
from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import ler_fontes_candidatas_passo34_9 as research

RID="probable_lineups_and_coaches"
CTX={"home":"Fluminense","away":"Palmeiras","competition":"Libertadores",
     "competition_slug":"libertadores","kickoff_brasilia":"2026-10-14T21:30:00-03:00"}
def candidate(url):
    return {"url":url, "title":"Fluminense x Palmeiras prováveis escalações",
            "domain":url.split("/")[2], "position":1,
            "published_hint":"Mon, 12 Oct 2026 13:22:56 GMT",
            "content_checked":True,"eligible_for_factual_validation":True}
def run():
    queries=research._targeted_queries(RID,CTX,"2026-10-14")
    assert len(queries)>=4
    assert all("Fluminense" in q and "Palmeiras" in q for q in queries)
    first=candidate("https://www.msn.com/pt-br/pre-jogo")
    second=candidate("https://ge.globo.com/futebol/pre-jogo")
    third=candidate("https://www.uol.com.br/esporte/pre-jogo")
    req={"id":RID,"source_candidates":[first],"ready_for_fact_extraction":True}
    with patch.object(research,"_search_and_check",return_value=[first,second,third]) as search:
        out=research._ensure_allowed_gap_check(
            req,context=CTX,article_date="2026-10-14",
            checked_at="2026-10-13T11:15:00-03:00",config={},
        )
        assert search.call_args.kwargs["max_sources"]==3
    assert [x["url"] for x in out["source_candidates"]]==[
        first["url"],second["url"],third["url"]
    ]
    assert out["ready_for_fact_extraction"]
    # Um campo parcial não é automaticamente verificado por esse reforço;
    # a extração factual continua exigindo XI e técnico dos DOIS lados.
    assert out["id"]==RID
    with patch.object(research,"_search_and_check",return_value=[]):
        existing_only=research._ensure_allowed_gap_check(
            req,context=CTX,article_date="2026-10-14",
            checked_at="2026-10-13T11:15:00-03:00",config={},
        )
    assert existing_only["source_candidates"]==[first]
    # As quatro pautas de 21/10 têm URLs atuais identificadas de forma
    # determinística, mas a URL continua passando pelo leitor/validador.
    scheduled = [
        ("Bayern de Munique", "Arsenal"),
        ("Inter de Milão", "FK Shakhtar Donetsk"),
        ("Real Madrid", "RB Leipzig"),
        ("Palmeiras", "Fluminense"),
    ]
    for home, away in scheduled:
        context = {"home": home, "away": away,
                   "competition": "Libertadores" if home == "Palmeiras" else "Champions League",
                   "kickoff_brasilia": "2026-10-21T16:00:00-03:00"}
        with patch.object(research, "_scrape_candidate", side_effect=lambda row, **_kw: row) as scrape:
            curated = research.checked_curated_sources(
                RID, context=context, article_date="2026-10-21",
                checked_at="2026-10-20T20:00:00-03:00",
                config={}, max_sources=3,
            )
            assert curated and scrape.called, (home, away)
            assert all(x["url"].startswith("https://") for x in curated)
            assert all(x["passo34_9_curated_discovery"] is True for x in curated)
        context["kickoff_brasilia"] = "2026-10-22T16:00:00-03:00"
        with patch.object(research, "_scrape_candidate") as scrape:
            assert not research.checked_curated_sources(
                RID, context=context, article_date="2026-10-22",
                checked_at="2026-10-20T20:00:00-03:00",
                config={}, max_sources=3,
            )
            scrape.assert_not_called()
    # Duas equipes precisam receber reportagens recentes, por clube, sem
    # dependência do RSS. O teste não acessa rede nem valida fatos sintéticos.
    for home, away in (
        ("Inter de Milão", "FK Shakhtar Donetsk"),
        ("Real Madrid", "RB Leipzig"),
    ):
        ctx = {
            "home": home, "away": away, "competition": "Champions League",
            "kickoff_brasilia": "2026-10-21T16:00:00-03:00",
        }
        with patch.object(research, "_scrape_candidate",
                          side_effect=lambda row, **_kw: row) as scrape:
            for team in (home, away):
                rows = research._search_and_check(
                    research.EDITORIAL_RESEARCH_ID,
                    context=ctx, article_date="2026-10-21",
                    checked_at="2026-10-20T20:00:00-03:00",
                    config={}, recent_team=team, max_sources=2,
                )
                assert rows and scrape.called, (home, away, team)
                assert all(item["url"].startswith("https://") for item in rows)
                # A notícia oficial pode ter slug permanente sem ano;
                # a data do conteúdo segue obrigatória no leitor real.
    # O calendário já normaliza FK Shakhtar Donetsk para Shakhtar Donetsk.
    # Não deixar esta mudança de grafia perder TODAS as fontes de pesquisa.
    normalized_context = {
        "home": "Inter de Milão", "away": "Shakhtar Donetsk",
        "competition": "Champions League",
        "kickoff_brasilia": "2026-10-21T16:00:00-03:00",
    }
    assert research._fixture_curated_key(normalized_context) == (
        "inter de milao", "fk shakhtar donetsk"
    )
    with patch.object(research, "_scrape_candidate",
                      side_effect=lambda row, **_kw: row) as scrape:
        rows = research.checked_curated_sources(
            RID, context=normalized_context, article_date="2026-10-21",
            checked_at="2026-10-20T20:00:00-03:00",
            config={}, max_sources=3,
        )
        assert rows and scrape.called, rows
    print("OK: pesquisa complementar após fonte parcial e preservação de evidências existentes.")

if __name__=="__main__":
    run()
