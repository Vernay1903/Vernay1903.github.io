#!/usr/bin/env python3
"""Regressão de 11/10/2026: quatro prévias publicadas sem reconhecer seus clássicos.

Usa os HTMLs reais como prova NEGATIVA. Não edita matérias publicadas e não
consome tokens da API. A referência LDU x Palmeiras permanece a régua.
"""
from pathlib import Path
import json
import re
import sys
from datetime import date

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import preparar_dados_editoriais as data
from scripts import qualidade_editorial_pre_jogo as quality
from scripts import validar_rascunho_pre_jogo as validate
from scripts.contexto_classicos_pre_jogo import find_rivalry
from scripts.planejar_coleta_fontes import query_variants
from scripts import preparar_redacao_pre_jogo as draft_prep

config=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
fixtures=[
    ("Grêmio","SC Internacional","Gre-Nal",
     "gremio-sc-internacional-brasileirao-2026-transmissao-horario-escalacoes.html"),
    ("Flamengo","Fluminense FC","Fla-Flu",
     "flamengo-fluminense-fc-brasileirao-2026-transmissao-horario-escalacoes.html"),
    ("Palmeiras","SC Corinthians Paulista","Derby Paulista",
     "palmeiras-sc-corinthians-paulista-brasileirao-2026-transmissao-horario-escalacoes.html"),
    ("Liverpool FC","Manchester City","Liverpool x Manchester City",
     "liverpool-fc-manchester-city-premier-league-2026-transmissao-horario-escalacoes.html"),
]

def article(html):
    m=re.search(r'<article id="articleBody"[^>]*>(.*?)</article>',html,re.S)
    assert m, "template sem <article>"
    return m.group(1)

def main():
    for home,away,nickname,slug in fixtures:
        plan={"home":home,"away":away,"article_date":"11/10/2026",
              "kickoff_time_brasilia":"17:30","competition_slug":(
                  "premier-league" if "liverpool" in slug else "brasileirao"),
              "slug":slug}
        record=data.build_editorial_record(plan,target_date=date(2026,10,11),config=config)
        rivalry=record["match_context"]["editorial_rivalry"]
        assert rivalry and rivalry["name"]==nickname,(home,away,rivalry)
        assert nickname in record["excerpt"] if nickname in {"Gre-Nal","Fla-Flu","Derby Paulista"} else "rivalidade" not in record["excerpt"]
        queries=query_variants("probable_lineups_and_coaches",record["match_context"],"11/10/2026")
        assert any(nickname in item for item in queries),(nickname,queries)
        assert any("desfalques" in item for item in queries)
        body=article((ROOT/slug).read_text(encoding="utf-8"))
        contract={"match_context":record["match_context"],"facts_by_requirement":[]}
        problems=quality.rivalry_context_errors(body,contract)
        assert problems,(nickname,"o texto reprovado não pode ser aprovado")
        assert any("abertura" in x for x in problems),(nickname,problems)

        if rivalry["kind"].startswith("rivalidade"):
            first=f"<p>{record['match_context']['display_home']} e {record['match_context']['display_away']} se enfrentam, e a rivalidade entre os clubes acrescenta contexto ao compromisso de hoje.</p>"
        else:
            first=f"<p>O {nickname} coloca frente a frente {record['match_context']['display_home']} e {record['match_context']['display_away']} em mais um capítulo desse clássico.</p>"
        improved=first+"<p><strong>Como chegam as equipes</strong></p><p>O preparo precisa de notícias atuais.</p>"
        assert not quality.rivalry_context_errors(improved,contract),(nickname,quality.rivalry_context_errors(improved,contract))
        assert not any("abertura sem identidade" in x for x in validate.editorial_style_errors(improved,contract))
        # Não aceitar só apelido num subtítulo sem que a abertura fale do clássico.
        misplaced="<p>Os dois times se enfrentam hoje.</p><p><strong>"+nickname+": contexto</strong></p><p>O confronto será disputado.</p>"
        assert quality.rivalry_context_errors(misplaced,contract)
    assert not find_rivalry("Liverpool","Everton")["name"] == find_rivalry("Liverpool","Manchester City")["name"]
    # O gerador do contrato precisa escolher notícias atuais antes dos placares.
    synthetic={
       "slug":"flamengo-fluminense-fc-brasileirao-2026-transmissao-horario-escalacoes.html",
       "title":"Flamengo x Fluminense pelo Brasileirão: horário",
       "excerpt":"Fla-Flu no Maracanã.",
       "date":"11/10/2026",
       "match_context":{
           "home":"Flamengo","away":"Fluminense FC",
           "display_home":"Flamengo","display_away":"Fluminense",
           "editorial_rivalry":find_rivalry("Flamengo","Fluminense"),
           "competition":"Brasileirão","competition_slug":"brasileirao",
       },
       "facts_by_requirement":[
           {"id":"facts","status":"verified","facts":[
              {"field":"home_team_news_1","text":"Notícia verificada: o jogador A retorna depois de cumprir suspensão."},
              {"field":"away_team_news_1","text":"Notícia verificada: o jogador B fica fora por lesão no tornozelo."},
              {"field":"home_recent_matches","text":"Placar 1 x 0."},
              {"field":"away_recent_matches","text":"Placar 2 x 0."},
           ]}
       ],
       "competition_internal_link":{
           "url":"https://cortedosesportes.com.br/brasileirao-historia-campeoes.html",
           "anchor_hint":"história do Brasileirão",
           "competition_slug":"brasileirao",
       },
       "ready_for_drafting":True,
       "ready_for_html":False,
       "publication_unlocked":False,
       "provenance_available_to_drafter":False,
    }
    contract=draft_prep.build_contract(synthetic,config=config)
    hierarchy=contract["editorial_fact_hierarchy"]
    assert hierarchy["opening_hook_fields"]==[
       "home_team_news_1","away_team_news_1"],hierarchy
    assert "home_recent_matches" not in hierarchy["opening_hook_fields"]
    assert contract["editorial_storyline"]["rivalry_name"]=="Fla-Flu"
    assert contract["editorial_section_plan"][0].startswith("Fla-Flu")
    assert find_rivalry("Flamengo","Palmeiras") is None
    print("OK: quatro partidas reais de 11/10 bloqueadas por falta de rivalidade;")
    print("OK: texto contextual passa e apelido jogado no subtítulo não burla a abertura.")

if __name__=="__main__":
    main()
