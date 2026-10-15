#!/usr/bin/env python3
"""Regressão 15/10: busca gratuita deve encontrar manchete curta e não priorizar ingresso."""
import json
import os
from pathlib import Path
from scripts import buscar_fontes_serper as search
from scripts import extrair_fatos_estruturados as facts

config = json.loads((Path(__file__).resolve().parents[2] / "config/pre-jogo.json").read_text(encoding="utf-8"))
ctx = {
    "home": "Estudiantes de La Plata",
    "away": "Flamengo",
    "competition": "Libertadores",
    "competition_slug": "libertadores",
    "kickoff_brasilia": "2026-10-15T21:30:00-03:00",
}
news = {
    "title": "Estudiantes x Flamengo: onde assistir ao vivo, horário e escalações",
    "url": "https://ge.globo.com/futebol/times/flamengo/noticia/2026/10/15/estudiantes-x-flamengo-onde-assistir-ao-vivo-horario-e-escalacoes.ghtml",
    "snippet": "Jogo de ida da semifinal da Libertadores: times disputam uma vaga na final",
    "domain": "ge.globo.com",
}
press = {
    "title": "Credenciamento para Flamengo x Estudiantes de La Plata",
    "url": "https://www.flamengo.com.br/noticias/credenciamento-flamengo-estudiantes",
    "snippet": "Credenciamento de jornalistas para o estádio",
    "domain": "flamengo.com.br",
}
assert "estudiantes" in search.team_variants(ctx["home"], config)
assert "Estudiantes" in facts.aliases_for_team(ctx["home"], config)
assert facts.mentions_team(news["title"], ctx["home"], config)
previous = os.environ.get("CDE_FREE_RESEARCH")
os.environ["CDE_FREE_RESEARCH"] = "1"
try:
    assert search.filter_results_for_requirement("transmission", [press], context=ctx, config=config) == []
    assert search.filter_results_for_requirement("probable_lineups_and_coaches", [news], context=ctx, config=config)
    assert search.filter_results_for_requirement("transmission", [news], context=ctx, config=config)
    assert search.filter_results_for_requirement("stakes_and_qualification_scenarios_when_applicable", [news], context=ctx, config=config)
finally:
    if previous is None:
        os.environ.pop("CDE_FREE_RESEARCH", None)
    else:
        os.environ["CDE_FREE_RESEARCH"] = previous
print("OK: titulares abreviados nas manchetes e busca com relevância factual comprovada.")
