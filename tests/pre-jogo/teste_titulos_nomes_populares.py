#!/usr/bin/env python3
"""Proíbe nomes cartoriais e chamadas genéricas nos pré-jogos automáticos."""
import json
import sys
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import preparar_dados_editoriais as data
from scripts import montar_pacote_editorial as package
from scripts import preparar_redacao_pre_jogo as drafting

config=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))


def record(home, away, *, slug="teste-liverpool-manchester-city-premier-league-2026-transmissao-horario-escalacoes.html"):
    return data.build_editorial_record({
       "home":home,"away":away,"slug":slug,"article_date":"11/10/2026",
       "kickoff_time_brasilia":"12:30","competition_slug":"premier-league"
    },target_date=date(2026,10,11),config=config)


def test():
    variants={
       "Liverpool FC":"Liverpool",
       "Clube de Regatas do Flamengo":"Flamengo",
       "CR Flamengo":"Flamengo",
       "Fluminense FC":"Fluminense",
       "SC Internacional":"Internacional",
       "SC Corinthians Paulista":"Corinthians",
       "FC Barcelona":"Barcelona",
       "Real Madrid CF":"Real Madrid",
       "FC Augsburg":"Augsburg",
       "AC Milan":"Milan",
    }
    for raw,expected in variants.items():
        assert data.common_editorial_name(raw, config)==expected,(raw,expected)
    article=record("Liverpool FC","Manchester City")
    assert article["title"] == "Liverpool x Manchester City pela Premier League: horário, prováveis escalações e transmissão"
    assert "informações do" not in article["excerpt"]
    assert "FC" not in article["title"]
    assert article["match_context"]["home"]=="Liverpool FC", "pesquisa não pode perder identificador do provedor"
    assert article["match_context"]["display_home"]=="Liverpool"
    title,excerpt=package.adjusted_service_headline(article,{},config=config)
    assert title=="Liverpool x Manchester City pela Premier League: horário"
    assert "informações do" not in title+excerpt
    transmission={"id":"transmission","status":"verified","facts":[
       {"field":"transmission","text":"Transmissão: ESPN."}]}
    t,e=package.adjusted_service_headline(article,{"transmission":transmission},config=config)
    assert t.endswith(": horário e transmissão"),t
    lineup={"id":"probable_lineups_and_coaches","status":"verified","facts":[
       {"field":"home_lineup","text":"Liverpool: "+"; ".join("Jogador "+str(i) for i in range(1,12))},
       {"field":"away_lineup","text":"Manchester City: "+"; ".join("Atleta "+str(i) for i in range(1,12))},
       {"field":"home_coach","text":"Técnico do Liverpool: Exemplo A"},
       {"field":"away_coach","text":"Técnico do Manchester City: Exemplo B"}]}
    t,e=package.adjusted_service_headline(article,{"transmission":transmission,"probable_lineups_and_coaches":lineup},config=config)
    assert t=="Liverpool x Manchester City pela Premier League: horário, prováveis escalações e transmissão",t
    assert "informações do" not in e
    # A fonte não mudou: apenas nomes exibidos e chamadas condicionais.
    flamengo=record("Clube de Regatas do Flamengo","Fluminense FC")
    assert flamengo["title"].startswith("Flamengo x Fluminense ")
    assert flamengo["match_context"]["home"]=="Flamengo"
    assert flamengo["match_context"]["away"]=="Fluminense FC"
    print("OK: nomes populares em títulos; serviços apenas se verificados; pesquisa com nomes originais.")


if __name__=="__main__":
    test()
