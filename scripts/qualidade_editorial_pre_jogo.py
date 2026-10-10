#!/usr/bin/env python3
"""Trava editorial automática baseada na matéria LDU x Palmeiras aprovada.

Opera apenas sobre fatos validados e texto do rascunho: sem APIs, sem alterar
matérias publicadas, sem estimar fatos a partir do conhecimento do modelo.
"""
from __future__ import annotations

import html
import re
import unicodedata
from typing import Any

TAGS = re.compile(r"<[^>]+>")
HEADINGS = re.compile(r"<p\s*>\s*<strong\s*>(.*?)</strong>\s*</p\s*>", re.I | re.S)
PARAGRAPHS = re.compile(r"<p\b[^>]*>(.*?)</p\s*>", re.I | re.S)
STOP = {
    "a","o","as","os","de","da","do","das","dos","e","em","na","no",
    "nas","nos","para","por","com","um","uma","que","se","ao","aos",
    "pela","pelo","pelas","pelos","entre","sua","seu","seus","suas",
    "foi","sera","serao","estao","esta","depois","antes","mais","tambem",
}

def fold(raw: str) -> str:
    value = html.unescape(TAGS.sub(" ", raw or ""))
    value = "".join(c for c in unicodedata.normalize("NFKD", value)
                    if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-zA-Z0-9]+", " ", value.casefold()).split())

def facts(package: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for requirement in package.get("facts_by_requirement", []):
        if not isinstance(requirement, dict) or requirement.get("status") != "verified":
            continue
        for fact in requirement.get("facts", []):
            if isinstance(fact, dict) and isinstance(fact.get("field"), str) and isinstance(fact.get("text"), str):
                if fact["text"].strip():
                    result[fact["field"]] = fact["text"].strip()
    return result

def source_depth_errors(package: dict[str, Any]) -> list[str]:
    """Resultados, H2H, fichas de serviço e escalações NÃO sustentam 700 palavras.

    Precisa haver uma notícia de preparação específica para cada equipe, ou
    uma notícia concreta de um time e um cenário competitivo verificado.
    Nenhum campo ausente é preenchido automaticamente.
    """
    available = facts(package)
    home = [v for k, v in available.items()
            if k.startswith("home_team_news_") and len(fold(v).split()) >= 8]
    away = [v for k, v in available.items()
            if k.startswith("away_team_news_") and len(fold(v).split()) >= 8]
    sporting = [v for k, v in available.items()
                if (k.startswith(("stakes_", "qualification_", "upcoming_fixture_", "home_upcoming_", "away_upcoming_"))
                    or k in {"competitive_context", "standings_context", "qualification_scenario"})
                and len(fold(v).split()) >= 8]
    if (home and away) or (sporting and (home or away)) or len(sporting) >= 2:
        return []

    # Alternativa factual para rodadas sem entrevistas/preparação publicadas:
    # dez resultados com adversário/placar/data (cinco de cada lado) + H2H real.
    # Balanços agregados ou escalações isoladas NÃO liberam a redação.
    # A trava de 700 palavras, a ausência de invenção e o teste de repetição
    # continuam obrigatórios DEPOIS da geração.
    def detailed_games(field: str) -> int:
        value = available.get(field, "")
        return len(re.findall(r"\b\d{2}/\d{2}/\d{4}:\s*[^;]{3,110}?\s+\d+\s*[xX×-]\s*\d+", value))

    if (
        detailed_games("home_recent_matches") >= 5
        and detailed_games("away_recent_matches") >= 5
        and all(available.get(field) for field in (
            "home_recent_form", "away_recent_form", "h2h_games",
            "h2h_home_wins", "h2h_away_wins", "h2h_draws", "stadium",
        ))
    ):
        return []
    return [
        "profundidade factual insuficiente para o modelo LDU x Palmeiras: "
        "exige preparação verificada ou dez resultados individuais "
        "(cinco por equipe) com retrospecto validado; não completar lacunas "
        "com inferências ou repetição"
    ]

def paragraphs(body_html: str) -> list[str]:
    return [fold(x) for x in PARAGRAPHS.findall(body_html) if len(fold(x).split()) >= 23]

def near_duplicate_errors(body_html: str) -> list[str]:
    rows = paragraphs(body_html)
    groups = []
    for row in rows:
        tokens = [token for token in row.split() if len(token) >= 4 and token not in STOP]
        if len(tokens) >= 16:
            groups.append((row, set(tokens)))
    # Exige alto compartilhamento e muitos tokens; não penaliza nomes dos
    # clubes/competição que naturalmente reaparecem no texto.
    for i, (_, a) in enumerate(groups):
        for _, b in groups[i+1:]:
            overlap = a & b
            if len(overlap) >= 16 and len(overlap) / min(len(a), len(b)) >= .73:
                return ["parágrafos retomam praticamente os mesmos fatos com outras palavras"]
    return []

def repeated_lineup_errors(body_html: str, package: dict[str, Any]) -> list[str]:
    available = facts(package)
    sections = re.split(
        r"(?=<p\s*>\s*<strong\s*>[^<]+</strong>\s*</p\s*>)",
        body_html, flags=re.I,
    )
    for field in ("home_lineup", "away_lineup"):
        raw = available.get(field, "").split(":", 1)[-1].strip().rstrip(".")
        if not raw:
            continue
        names = [
            fold(re.sub(r"\([^)]*\)", "", name))
            for name in re.split(r"[;,]|\s+e\s+", raw, flags=re.I)
        ]
        names = [name for name in names if len(name) >= 4]
        if len(names) < 11:
            continue
        for section in sections:
            heading = HEADINGS.search(section)
            if heading and "escalac" in fold(heading.group(1)):
                continue
            # Repetir vários nomes numa análise contextual é normal; reproduzir
            # a escalação quase completa fora do bloco próprio não é.
            for row in PARAGRAPHS.findall(section):
                f = " " + fold(row) + " "
                used = sum(bool(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", f)) for name in names)
                if used >= 8:
                    return ["escalação quase completa repetida fora do bloco de escalações"]
    return []

ARTIFICIAL = (
    r"\bsaiba mais sobre este confronto e acompanhe\b",
    r"\bacompanhe todas as informacoes da partida em tempo real\b",
    r"\ba informacao de elenco.{0,130}\bacompanhamento\b",
    r"\bo retrospecto disponivel.{0,70}\breune um jogo\b",
    r"\bo historico especifico do confronto faz parte do contexto\b",
    r"\besse e mais um capitulo\b",
    r"\bo duelo coloca frente a frente\b.{0,75}\bdois times\b",
    r"\bde acordo com os dados fornecidos\b",
    r"\bno recorte considerado\b",
)

def draft_quality_errors(body_html: str, contract: dict[str, Any]) -> list[str]:
    """Trava extra, executada somente no lote automático antes da publicação."""
    errors: list[str] = []
    text = fold(body_html)
    for pattern in ARTIFICIAL:
        if re.search(pattern, text):
            errors.append("linguagem de preenchimento ou metadados de cobertura no texto")
            break
    headings = [fold(h) for h in HEADINGS.findall(body_html)]
    if len(headings) > 8:
        errors.append("matéria fragmentada em mais de oito subtítulos")
    if any(h in {"dados do confronto", "informacoes principais", "resumo do encontro",
                 "fechamento", "servico do jogo", "ultimas linhas antes da partida"}
           for h in headings):
        errors.append("subtítulos de repetição/fechamento artificial")
    if "onde assistir" in headings and ("dados do confronto" in headings or "servico do jogo" in headings):
        errors.append("serviço repetido em seções diferentes")
    errors.extend(repeated_lineup_errors(body_html, contract))
    errors.extend(near_duplicate_errors(body_html))
    return list(dict.fromkeys(errors))
