#!/usr/bin/env python3
"""Sem APIs: impede manchetes que prometem serviços ausentes e corpo incompleto."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import montar_pacote_editorial as editorial
from scripts import validar_rascunho_pre_jogo as draft

def field(name, value):
    return {"field": name, "text": value}

def verified(id_, fields):
    return {"id": id_, "status": "verified", "conflict_detected": False,
            "facts": fields}

def main():
    config=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
    title="Equipe A x Equipe B: transmissão, horário e prováveis escalações"
    excerpt="Confira arbitragem, escalações e onde assistir."
    absent={
       "transmission":{"id":"transmission","status":"unavailable_after_check","facts":[]},
       "probable_lineups_and_coaches":{"id":"probable_lineups_and_coaches","status":"unavailable_after_check","facts":[]},
       "officiating":{"id":"officiating","status":"unavailable_after_check","facts":[]},
    }
    gaps=editorial.verified_promised_service_gaps(absent,title=title,excerpt=excerpt,config=config)
    assert any("transmission" in x for x in gaps),gaps
    assert any("lineups" in x for x in gaps),gaps
    assert any("officiating" in x for x in gaps),gaps
    a=[f"Jogador Alfa {i}" for i in range(1,12)]
    b=[f"Jogador Beta {i}" for i in range(1,12)]
    full={
      "transmission":verified("transmission",[field("transmission","Transmissão: Canal Exemplo.")]),
      "probable_lineups_and_coaches":verified("probable_lineups_and_coaches",[
        field("home_lineup","Provável escalação do Equipe A: "+"; ".join(a)+"."),
        field("home_coach","Técnico do Equipe A: Técnico Alfa."),
        field("away_lineup","Provável escalação do Equipe B: "+"; ".join(b)+"."),
        field("away_coach","Técnico do Equipe B: Técnico Beta."),
      ]),
      "officiating":verified("officiating",[field("referee","Árbitro: Árbitro Gama.")]),
    }
    assert editorial.verified_promised_service_gaps(full,title=title,excerpt=excerpt,config=config)==[]
    shorter=json.loads(json.dumps(full))
    shorter["probable_lineups_and_coaches"]["facts"][0]["text"]="Provável escalação do Equipe A: "+ "; ".join(a[:8])+"."
    gaps=editorial.verified_promised_service_gaps(shorter,title=title,excerpt=excerpt,config=config)
    assert "promised_home_lineup_less_than_11_names" in gaps,gaps

    # Regressão de 07/10/2026: escalações jornalísticas usam "e" antes do 11º nome.
    natural=json.loads(json.dumps(full))
    natural["probable_lineups_and_coaches"]["facts"][0]["text"]="Provável escalação do Equipe A: "+ "; ".join(a[:10])+" e "+a[10]+"."
    natural["probable_lineups_and_coaches"]["facts"][2]["text"]="Provável escalação do Equipe B: "+ ", ".join(b[:10])+" e "+b[10]+"."
    assert editorial.verified_promised_service_gaps(natural,title=title,excerpt=excerpt,config=config)==[]

    # Arbitragem só é obrigatória quando a chamada realmente a promete.
    excerpt_sem_arbitragem="Confira transmissão, prováveis escalações e informações do confronto."
    sem_arbitragem=json.loads(json.dumps(natural))
    sem_arbitragem["officiating"]={"id":"officiating","status":"unavailable_after_check","facts":[],"allow_unavailable_after_check":True}
    gaps=editorial.verified_promised_service_gaps(
        sem_arbitragem,title=title,excerpt=excerpt_sem_arbitragem,config=config
    )
    assert not any("officiating" in x or "referee" in x for x in gaps),gaps

    contract={
       "title":title,"excerpt":excerpt,
       "facts_by_requirement":list(full.values())
    }
    good=(
      "<p><strong>Prováveis escalações e arbitragem</strong></p>"
      "<ul><li><strong>Provável Equipe A:</strong> "+"; ".join(a)+".</li>"
      "<li><strong>Provável Equipe B:</strong> "+"; ".join(b)+".</li>"
      "<li><strong>Técnico:</strong> Técnico Alfa.</li>"
      "<li><strong>Técnico:</strong> Técnico Beta.</li>"
      "<li><strong>Árbitro:</strong> Árbitro Gama.</li></ul>"
      "<p><strong>Onde assistir</strong></p>"
      "<p>Transmissão: Canal Exemplo.</p>"
    )
    assert draft.required_service_body_errors(good,contract)==[]

    natural_contract={
       "title":title,
       "excerpt":excerpt_sem_arbitragem,
       "facts_by_requirement":list(sem_arbitragem.values())
    }
    natural_body=(
      "<p><strong>Prováveis escalações</strong></p>"
      "<ul><li><strong>Provável Equipe A:</strong> "+"; ".join(a[:10])+" e "+a[10]+".</li>"
      "<li><strong>Provável Equipe B:</strong> "+", ".join(b[:10])+" e "+b[10]+".</li>"
      "<li><strong>Técnico:</strong> Técnico Alfa.</li>"
      "<li><strong>Técnico:</strong> Técnico Beta.</li></ul>"
      "<p><strong>Onde assistir</strong></p><p>Transmissão: Canal Exemplo.</p>"
    )
    assert draft.required_service_body_errors(natural_body,natural_contract)==[]

    no_lineups="<p><strong>Momento recente</strong></p><p>O retrospecto tem dois jogos.</p>"
    bad=draft.required_service_body_errors(no_lineups,contract)
    assert any("escalação" in x for x in bad),bad
    assert any("transmissão" in x for x in bad),bad
    assert any("arbitragem" in x for x in bad),bad
    body_missing_b=good.replace("; ".join(b),"Sem definição de atletas")
    assert any("away_lineup" in x for x in draft.required_service_body_errors(body_missing_b,contract))
    print("OK: chamada sem informação bloqueada; rascunho exige os nomes, transmissão, técnicos e árbitro.")


if __name__ == "__main__":
    main()
