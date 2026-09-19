#!/usr/bin/env python3
"""Reuso factual do estádio exige página original, data e contexto do jogo."""
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import ler_fontes_candidatas_passo34_10 as reader

def main():
    checked=datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat()
    url="https://www.lance.com.br/futebol-nacional/flamengo-x-red-bull-bragantino-onde-assistir-horario-e-escalacoes.html"
    src={
      "url":url,"title":"Flamengo x RB Bragantino: onde assistir, horário e escalações",
      "source_type":"major_sports_media",
      "content_checked":True,"eligible_for_factual_validation":True,
      "checked_at":checked,"page_evidence":{"metadata":{},"evidence_segments":["Flamengo x RB Bragantino: transmissão."]}
    }
    ctx={"home":"Flamengo","away":"RB Bragantino","competition":"Brasileirão"}
    article={"date":"20/09/2026","match_context":ctx,"requirements":[
       {"id":"stadium_and_location","source_candidates":[]},
       {"id":"transmission","source_candidates":[src]}
    ]}
    config={"research":{"page_reader":{"max_segments_per_source":10,"max_segment_chars":700}}}
    fake={"markdown":("Flamengo x RB Bragantino pelo Brasileirão, domingo, 20 de setembro de 2026.\n"
                      "Ficha do jogo: local: Estádio Jornalista Mário Filho (Maracanã), Rio de Janeiro.\n"
                      "O Flamengo recebe o RB Bragantino no Maracanã."),
          "metadata":{"title":src["title"]},"credits":0}
    with patch.dict(os.environ,{"CDE_FREE_RESEARCH":"1"}), \
         patch.object(reader._step34_7,"_scrape_once",return_value=fake) as scrape:
        found=reader._reuse_original_pages(
          article,requirement_id="stadium_and_location",context=ctx,
          article_date="20/09/2026",checked_at=checked,config=config)
    assert len(found)==1,found
    assert found[0]["passo34_10_reused_original_page"] is True
    assert found[0]["page_evidence"]["credits_used"]==0
    assert any("Maracanã" in x for x in found[0]["page_evidence"]["evidence_segments"])
    assert scrape.call_count==1
    print("OK: estádio é reaproveitado de fonte original da partida sem busca/custo extra.")

if __name__=="__main__":
    main()
