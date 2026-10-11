#!/usr/bin/env python3
"""Recusa portais antigos, manchetes SEO e notícia inexistente; preserva fatos atuais."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import extrair_fatos_estruturados as extraction
from scripts import qualidade_editorial_pre_jogo as editorial
config=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
context={"home":"Flamengo","away":"Fluminense FC","competition":"Brasileirão",
         "competition_slug":"brasileirao","kickoff_brasilia":"2026-10-11T17:30:00-03:00"}

def src(url,title,segments,source_type="major_sports_media"):
    return {"url":url,"title":title,"publisher":"Teste","source_type":source_type,
      "checked_at":"2026-10-11T09:00:00-03:00","content_checked":True,
      "eligible_for_factual_validation":True,
      "page_evidence":{"metadata":{"og:title":title},"evidence_segments":segments}}
def rows(sources):
    return extraction.extract_optional_team_news_claims(
      {"id":"probable_lineups_and_coaches","source_candidates":sources},
      match_context=context,config=config,
    )

old=src("https://goal.com/br/pre-jogo-brasileirao-serie-a-2022","Fluminense x Flamengo: escalação, desfalques e mais do jogo do Brasileirão Série A 2022",
        ["O Fluminense tem três desfalques certos: Nino, Fred e Pineida estão machucados."])
assert not extraction.source_current_for_match(old,context)
assert rows([old])==[], "2022 checado em 2026 NÃO é atual"
model=src("https://goal.com/br/noticias/fluminense-x-flamengo","Fluminense x Flamengo pela Série A",
    ["Renato Gaucho não tem confirmações de desfalques por lesão ou suspensão no Flamengo até o momento, e a escalação provável ainda não foi divulgada."])
assert rows([model])==[], "ausência de informação não é notícia"
official=src("https://www.flamengo.com.br/noticias/futebol/flamengo-x-fluminense",
 "Flamengo x Fluminense: informação do clássico",
 ["O Flamengo terá dois reforços contra o Fluminense. Varela fica à disposição depois da seleção. Léo Ortiz também retorna após ausência familiar. Jorginho está suspenso após ser expulso no último jogo."],
 source_type="official")
claimed=rows([official])
assert claimed and all(x["field"].startswith("home_team_news_") for x in claimed),claimed
assert not editorial.source_depth_errors({"facts_by_requirement":[{"status":"verified","facts":[
  {"field":"home_team_news_1","text":"Fluminense x Flamengo: escalação, desfalques e mais do jogo do Brasileirão Série A 2022"},
  {"field":"away_team_news_1","text":"O Flamengo não tem confirmações de desfalques até o momento."},
]}]})==[], "genérico / histórico não pode liberar"
official_stakes=src("https://www.flamengo.com.br/noticias/futebol/flamengo-x-fluminense",
 "Flamengo x Fluminense: informações do clássico",
 ["O Flamengo busca manter a liderança do Brasileirão depois do empate de quinta-feira, quando jogou contra o Santos."],
 source_type="official")
stakes=extraction.extract_separate_competitive_context(
 [{"id":"probable_lineups_and_coaches","source_candidates":[official_stakes]}],
 match_context=context,config=config)
assert stakes is not None and any(x["field"]=="home_stakes_1" for x in stakes["facts"]),stakes
print("OK: rejeita 2022 e falsos desfalques; mantém notícias recentes do clube correto.")
