#!/usr/bin/env python3
"""Notícia sobre Cano enfrentando Palmeiras não é desfalque do Palmeiras."""
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.extrair_fatos_estruturados import extract_optional_team_news_claims
CONFIG=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
CTX={"home":"Fluminense","away":"Palmeiras","competition":"Libertadores",
     "competition_slug":"libertadores","kickoff_brasilia":"2026-10-14T21:30:00-03:00"}
def source(body):
    return {"url":"https://www.terra.com.br/esportes/2026/10/13/fluminense-palmeiras.html",
      "title":"Fluminense x Palmeiras: notícias dos elencos para a semifinal",
      "published_hint":"Tue, 13 Oct 2026 12:00:00 GMT",
      "source_type":"major_sports_media","content_checked":True,
      "eligible_for_factual_validation":True,
      "page_evidence":{"metadata":{},"evidence_segments":body}}
def extract(items):
    return extract_optional_team_news_claims(
      {"id":"probable_lineups_and_coaches","source_candidates":items},
      match_context=CTX,config=CONFIG,max_per_team=3)
def check():
    canoe=source([
      "Para enfrentar o Palmeiras, Germán Cano é dúvida, pois está em transição física."
    ])
    assert not any(c["field"].startswith("away") for c in extract([canoe]))
    contextual=source([
      "O Tricolor avançou à semifinal da Libertadores depois de eliminar o Platense. "
      "Para enfrentar o Palmeiras, Germán Cano é dúvida, pois está em transição física."
    ])
    linked=extract([contextual])
    assert any(c["field"].startswith("home") and "Cano" in c["value"] for c in linked),linked
    assert not any(c["field"].startswith("away") and "Cano" in c["value"] for c in linked),linked
    supported=source([
      "O Palmeiras confirma que Paulinho está lesionado e desfalca a equipe alviverde na semifinal."
    ])
    got=extract([supported])
    assert any(c["field"].startswith("away") for c in got),got
    assert all("Cano" not in c["value"] for c in got)
    print("OK: jogador do adversário não recebe o clube errado nas notícias do elenco.")
if __name__=="__main__":
    check()
