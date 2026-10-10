#!/usr/bin/env python3
"""Modelo aprovado com notícia independente de escalações ou dados ricos de jogos."""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import extrair_fatos_estruturados as extract
from scripts import qualidade_editorial_pre_jogo as quality

def req(id_, facts):
    return {"id":id_, "status":"verified",
            "facts":[{"field":key,"text":text} for key,text in facts.items()]}

def checked_source(sentence, url="https://trivela.com.br/onde-assistir/jogo-2026/"):
    return {
      "publisher":"Trivela", "url":url, "source_type":"major_sports_media",
      "checked_at":"2026-10-10T14:30:00-03:00", "content_checked":True,
      "eligible_for_factual_validation":True,
      "title":"Liverpool x Manchester City pela Premier League",
      "page_evidence":{"evidence_segments":[sentence]},
    }

def main():
    config=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
    context={"home":"Liverpool FC","away":"Manchester City","competition":"Premier League"}
    news=(
      "Liverpool FC enfrenta o Manchester City pela Premier League. "
      "O Manchester City informou que seu atacante está fora do jogo por lesão. "
      "No Liverpool FC, o goleiro está suspenso e não jogará."
    )
    clean=extract.extract_separate_team_news(
      [{"id":"probable_lineups_and_coaches",
        "source_candidates":[checked_source(news)]}],
      match_context=context,config=config)
    assert clean and clean["status"]=="verified", "notícias precisam sobreviver sem os 22 jogadores"
    fields={fact["field"] for fact in clean["facts"]}
    assert fields=={"home_team_news_1","away_team_news_1"}, fields
    assert clean["sources"] and clean["structured_fact_count"]==2
    assert quality.source_depth_errors({"facts_by_requirement":[clean]})==[]

    # Menções de apenas um clube ou fontes não verificadas não autorizam notícias.
    assert extract.extract_separate_team_news(
        [{"id":"probable_lineups_and_coaches","source_candidates":[
          checked_source("Liverpool FC pode jogar hoje. Arsenal lesionado.")]}],
        match_context=context,config=config) is None

    games_h="; ".join(
      f"{10+i:02d}/09/2026: Liverpool {i} x {i+1} Visitante"
      for i in range(1,6))
    games_a="; ".join(
      f"{10+i:02d}/09/2026: Manchester City {i+1} x {i} Visitante"
      for i in range(1,6))
    fact_pack={"facts_by_requirement":[req("recent_form_both_teams",{
       "home_recent_form":"Forma recente de Liverpool: duas vitórias e três empates.",
       "away_recent_form":"Forma recente de Manchester City: cinco vitórias.",
       "home_recent_matches":"Resultados recentes: "+games_h,
       "away_recent_matches":"Resultados recentes: "+games_a,
    }),req("competition_specific_head_to_head",{
       "h2h_games":"Histórico nos últimos onze jogos: 11.",
       "h2h_home_wins":"Vitórias do mandante: 3.",
       "h2h_away_wins":"Vitórias do visitante: 4.",
       "h2h_draws":"Empates: 4.",
    }),req("stadium_and_location",{"stadium":"Jogo em Anfield."})]}
    assert quality.source_depth_errors(fact_pack)==[], "dez resultados + H2H validado são pauta utilizável"
    fact_pack["facts_by_requirement"][0]["facts"][2]["text"]="Últimos cinco jogos: duas vitórias e três empates"
    assert quality.source_depth_errors(fact_pack), "balanços sem placares não podem liberar o redator"
    print("OK: notícia contextual preservada sem escalações; prévia factual rica liberada; pauta rasa bloqueada.")

if __name__=="__main__":main()
