#!/usr/bin/env python3
"""Manchete com notícia de terceiro clube não deve ser exportada ao redator."""
from __future__ import annotations
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.extrair_fatos_estruturados import extract_individual_team_context
CONFIG=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
CTX={"home":"Fluminense","away":"Palmeiras","competition":"Libertadores",
     "competition_slug":"libertadores","kickoff_brasilia":"2026-10-14T21:30:00-03:00"}

def check():
    headline="Saúl é titular no Flamengo, enquanto Fluminense tem time misto; escalações"
    source={
       "url":"https://www.uol.com.br/esporte/futebol/ultimas-noticias/2026/10/11/saul-e-titular.htm",
       "title":headline,"publisher":"UOL","source_type":"major_sports_media",
       "published_hint":"Sun, 11 Oct 2026 12:46:00 GMT",
       "checked_at":"2026-10-13T12:20:00-03:00",
       "content_checked":True,"eligible_for_factual_validation":True,
       "editorial_target_side":"home","editorial_target_team":"Fluminense",
       "page_evidence":{"metadata":{"description":"Escalações do Fla-Flu pela 30ª rodada do Campeonato Brasileiro"},
                        "evidence_segments":[
                            headline,
                            headline+" Flamengo e Fluminense estão escalados para o clássico. "
                                     "Já o Flu, com foco na semifinal da Copa Libertadores, "
                                     "terá um time misto para poupar titulares.",
                            "Pelo lado do Fluminense, o técnico Marcão optou por escalar um time "
                            "alternativo, poupando titulares para o duelo com Palmeiras pela Libertadores."
                        ]}
    }
    result=extract_individual_team_context(
        [{"id":"editorial_context_both_teams","source_candidates":[source]}],
        match_context=CTX,config=CONFIG,
    )
    assert result is not None and result["status"]=="verified",result
    values=" ".join(f["text"] for f in result["facts"])
    assert "Saúl" not in values and "Flamengo" not in values,values
    assert "Flu" in values or "Fluminense" in values,values
    assert any("semifinal" in f["text"] for f in result["facts"]),values
    print("OK: título da notícia não vira fato obrigatório; preparação do Flu é mantida.")

if __name__=="__main__":
    check()
