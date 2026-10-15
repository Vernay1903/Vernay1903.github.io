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

def meaningful_team_news(raw: str) -> bool:
    """Uma chamada SEO sobre escalações não é notícia de preparação."""
    value = fold(raw.split(": ", 1)[-1])
    if len(value.split()) < 8:
        return False
    fake_or_vague = (
        r"escalacao desfalques e mais do jogo",
        r"nao tem confirmacoes?",
        r"sem confirmacao",
        r"nao foi divulgad",
        r"informacoes devem ser adicionadas",
        r"com informacoes sobre",
        r"acompanhamento ao vivo",
        r"onde assistir",
    )
    if any(re.search(p, value) for p in fake_or_vague):
        return False
    return bool(re.search(
        r"\b(?:fraturou|lesionad[oa]|lesao|suspens[ao]|suspensao|expuls[ao]|desfalqu\w*|"
        r"retorn\w*|voltou|recuper\w*|poupad\w*|fora|ausen\w*|"
        r"reavaliad\w*|convocad\w*|estre\w*|mudan\w*|"
        r"injur\w*|ruled out|suspended)\b", value,
    ))


def meaningful_sporting_context(raw: str) -> bool:
    value = fold(raw)
    if len(value.split()) < 10:
        return False
    # Falha real de 15/10/2026: arquibancada/ingressos passaram por
    # 'situação esportiva'. Serviço de estádio não é pauta sobre o elenco.
    if re.search(
        r"\b(?:arquibancad\w*|credenciament\w*|ingress\w*|"
        r"setores? da torcida|distribuicao de torcedores|"
        r"acesso ao estadio|bilheteria)\b", value,
    ):
        return False
    # A ficha da partida ("se enfrentam na semifinal nesta quinta")
    # não é novidade competitiva nem contextualização substancial.
    has_development = re.search(
        r"\b(?:lideranc\w*|lider|rebaixament\w*|zona de|pontos?|tabela|"
        r"posicao|classific\w*|eliminad\w*|vantag\w*|"
        r"vitori\w*|derrot\w*|empat\w*|invict\w*|"
        r"trein\w*|prepar\w*|desfalqu\w*|suspens\w*|"
        r"retorn\w*|lesion\w*|recuper\w*|convoc\w*|"
        r"gols?|marcou|hat trick|standings|unbeaten|"
        r"qualified|advanced|training|injured)\b", value,
    )
    if not has_development:
        return False
    if (
        re.search(r"\b(?:se enfrentam|disputam|acontece|esta marcado|sera disputad\w*)\b", value)
        and not re.search(
            r"\b(?:venceu|perdeu|empatou|conquistou|pontos?|lider|tabela|"
            r"suspens\w*|retorn\w*|trein\w*|classificou|avancou|"
            r"jogos anteriores|placar agregado)\b", value,
        )
    ):
        return False
    return bool(re.search(
        r"\b(?:lideranca|lider|rebaixamento|queda|zona|classificacao|vaga|"
        r"semifinal|final|estreia|primeiro classico|pontos|tabela|"
        r"treinamento|treinou|preparacao|desfalqu\w*|"
        r"recuperacao|lesionado|retornou|convocado|"
        r"derrota|empatou|vitoria|invicto|venceu|perdeu|perde|ganhou|won|lost|beat|"
        r"training|trained|entrain\w*|allenam\w*|infortunat\w*|"
        r"prepar\w*|lesion\w*|convocat\w*|standings|unbeaten|"
        r"injured|returned|marcou|hat trick)\b",
        value,
    ))


def source_depth_errors(package: dict[str, Any]) -> list[str]:
    """O padrão aprovado exige NOTÍCIA do jogo, não um resumo de 10 placares.

    A liberação automática exige contexto editorial particular dos dois clubes
    e no mínimo três fatos substantivos distintos. Informações de serviço,
    H2H, últimos cinco placares e nomes de escalação não contam como pauta.
    """
    available = facts(package)
    home_news = [v for k,v in available.items()
                 if k.startswith("home_team_news_") and meaningful_team_news(v)]
    away_news = [v for k,v in available.items()
                 if k.startswith("away_team_news_") and meaningful_team_news(v)]
    home_stakes = [v for k,v in available.items()
                   if k.startswith("home_stakes_") and meaningful_sporting_context(v)]
    away_stakes = [v for k,v in available.items()
                   if k.startswith("away_stakes_") and meaningful_sporting_context(v)]
    common_stakes = [v for k,v in available.items()
                     if (k.startswith(("stakes_", "qualification_", "upcoming_fixture_"))
                         or k in {"competitive_context", "standings_context", "qualification_scenario"})
                     and meaningful_sporting_context(v)]
    home = home_news + home_stakes
    away = away_news + away_stakes
    total = home + away + common_stakes
    # Dois campos verificados podem representar a MESMA notícia reescrita.
    # Não contar duas versões da mesma suspensão/retorno como duas pautas.
    unique_stories: list[set[str]] = []
    for story in total:
        tokens = {t for t in fold(story.split(":", 1)[-1]).split()
                  if len(t) >= 4 and t not in STOP}
        repeated = any(
            len(tokens & previous) >= 10
            and len(tokens & previous) / max(1, min(len(tokens), len(previous))) >= .72
            for previous in unique_stories
        )
        if not repeated:
            unique_stories.append(tokens)
    # Não exigir lesão ou suspensão para justificar uma matéria: times sem
    # desfalques também podem render jornalismo substantivo. Três fatos
    # competitivos *verificados*, com contexto de ambos os clubes, bastam.
    # Placar agregado, H2H e serviço continuam excluídos da contagem.
    if home and away and len(unique_stories) >= 3 and (
        home_news or away_news or (home_stakes and away_stakes)
    ):
        return []
    return [
        "profundidade editorial insuficiente: faltam três fatos atuais específicos "
        "e verificados, cobrindo os dois times e sua preparação ou situação competitiva. "
        "Resultados, H2H, escalações e serviço NÃO substituem reportagem."
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

def repeated_stat_summaries_errors(body_html: str) -> list[str]:
    """Bloqueia o mesmo V/E/D em dois parágrafos, mesmo com derrota singular."""
    numbers = {
        "um": "1", "uma": "1", "dois": "2", "duas": "2",
        "tres": "3", "quatro": "4", "cinco": "5", "seis": "6",
        "sete": "7", "oito": "8", "nove": "9", "dez": "10",
    }
    seen: set[tuple[tuple[str, str], ...]] = set()
    for paragraph in paragraphs(body_html):
        tokens = re.findall(
            r"\b(\d+|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez)"
            r"\s+(vitorias?|empates?|derrotas?)\b",
            paragraph,
        )
        current: dict[str, str] = {}
        observed: set[tuple[tuple[str, str], ...]] = set()
        for value, category in tokens:
            singular = category.rstrip("s")
            if singular in current:
                current = {}
            current[singular] = numbers.get(value, value)
            if len(current) == 3:
                observed.add(tuple(sorted(current.items())))
                current = {}
        if seen & observed:
            return ["o mesmo balanço de vitórias, empates e derrotas é repetido em seções diferentes"]
        seen.update(observed)
    return []


def unrelated_story_errors(body_html: str, contract: dict[str, Any]) -> list[str]:
    """Impede o desvio visto na matéria real: Neymar/Santos em Palmeiras x Flu."""
    context = contract.get("match_context") or {}
    participating = {
        fold(str(context.get("home") or "")),
        fold(str(context.get("away") or "")),
    }
    for paragraph in paragraphs(body_html):
        # Neymar não é assunto da partida entre Palmeiras e Fluminense;
        # a reportagem agregadora do Santos não é notícia dos dois elencos.
        if "neymar" in paragraph and "santos" in paragraph and not (
            "santos" in participating or "neymar" in participating
        ):
            return ["parágrafo sobre Neymar e Santos não contextualiza as equipes da partida"]
    return []


def repeated_preparation_hook_errors(body_html: str, contract: dict[str, Any]) -> list[str]:
    """Exige aprofundamento, não repetir 'poupou titulares' em cinco blocos."""
    context = contract.get("match_context") or {}
    rows = paragraphs(body_html)
    for side in ("home", "away"):
        team = fold(str(context.get(side) or ""))
        if not team:
            continue
        hits = sum(
            1 for row in rows
            if team in row and re.search(
                r"\b(?:time misto|formacao alternativa|time alternativo|"
                r"poupar titulares|poupou titulares|poupando titulares|"
                r"preservar titulares|preservou titulares)\b",
                row,
            )
        )
        if hits >= 4:
            return ["a mesma decisão de poupar titulares é recontada em muitos parágrafos"]
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
    r"\b(?:o|esse|este) contrato (?:nao )?(?:forne[cs]\w*|inform\w*|apresent\w*|inclu\w*|contem|traz|permite afirmar)\b",
    r"\ba noticia de elenco e (?:igualmente )?direta\b",
    r"\bsaiba mais sobre este confronto e acompanhe\b",
    r"\bacompanhe todas as informacoes da partida em tempo real\b",
    r"\ba informacao de elenco.{0,130}\bacompanhamento\b",
    r"\bo retrospecto disponivel.{0,70}\breune um jogo\b",
    r"\bo historico especifico do confronto faz parte do contexto\b",
    r"\besse e mais um capitulo\b",
    r"\bo duelo coloca frente a frente\b.{0,75}\bdois times\b",
    r"\bde acordo com os dados fornecidos\b",
    r"\bno recorte considerado\b",
    r"\bno conjunto de informacoes fornecidas\b",
    r"\b(?:os|nos) (?:dados|fatos|resultados) fornecidos\b",
    r"\bnos resultados fornecidos\b",
    r"\bna amostra apresentada\b",
    r"\ba amostra serve\b",
    r"\bno pacote\b",
    r"\bprincipais pontos individuais verificados\b",
    r"\b(?:no contrato|contrato da partida|contrato editorial|contrato apresentado)\b",
    r"\b(?:o compromisso desta materia|este texto tem como compromisso)\b",
    # Regressões de linguagem vazia observadas em 15/10/2026.
    r"\bo resultado da partida de ida dara o primeiro contorno\b",
    r"\bsera definido no conjunto da eliminatoria\b",
    r"\besse e o limite da amostra direta disponivel\b",
    r"\bo encontro tambem pode ser acompanhado dentro da historia\b",
    r"\buma eliminatoria de alto peso na competicao\b",
    r"\bo mando (?:argentino|brasileiro) sera o primeiro elemento\b",
)

def redundant_recent_calendar_errors(body_html: str) -> list[str]:
    """Detecta o calendário recente copiado na abertura e novamente na análise."""
    normalized=fold(body_html)
    matches=re.findall(
        r"\b\d{1,2} de (?:janeiro|fevereiro|marco|abril|maio|junho|"
        r"julho|agosto|setembro|outubro|novembro|dezembro)\b",
        normalized,
    )
    duplicates={key for key in matches if matches.count(key)>1}
    if len(duplicates)>=3:
        return ["resultados recentes recontados em mais de uma seção; datas de jogos repetidas"]
    return []


def unsupported_stakes_closing_errors(body_html: str, contract: dict[str, Any]) -> list[str]:
    headings=[fold(h) for h in HEADINGS.findall(body_html)]
    if any(h.startswith(("o que esta em jogo","desdobramentos da rodada")) for h in headings):
        verified=facts(contract)
        real_stakes=any(
            k.startswith(("home_stakes_", "away_stakes_", "stakes_", "qualification_"))
            or k in {"standings_context","competitive_context","qualification_scenario"}
            for k in verified
        )
        if not real_stakes:
            return ["seção O que está em jogo repete serviço/placares sem fato competitivo comprovado"]
    return []


def rivalry_context_errors(body_html: str, contract: dict[str, Any]) -> list[str]:
    """Rejeita o erro real de 11/10: quatro rivalidades publicadas sem contexto."""
    context = contract.get("match_context") or {}
    rivalry = (contract.get("editorial_storyline")
               or (context.get("editorial_rivalry") if isinstance(context, dict) else None))
    if not isinstance(rivalry, dict):
        return []
    name = str(rivalry.get("rivalry_name") or rivalry.get("name") or "").strip()
    background = str(rivalry.get("established_background") or rivalry.get("background") or "")
    if not name:
        return []
    errors = []
    first_heading = HEADINGS.search(body_html)
    opening = body_html[:first_heading.start()] if first_heading else body_html
    kind = str(rivalry.get("rivalry_kind") or rivalry.get("kind") or "").casefold()
    if kind.startswith("rivalidade"):
        home = fold(str(context.get("display_home") or context.get("home") or ""))
        away = fold(str(context.get("display_away") or context.get("away") or ""))
        opening_ok = ("rivalidade" in fold(opening)
                      and home in fold(opening) and away in fold(opening))
        whole_ok = "rivalidade" in fold(body_html) and home in fold(body_html) and away in fold(body_html)
    else:
        opening_ok = fold(name) in fold(opening)
        whole_ok = fold(name) in fold(body_html)
    if not opening_ok:
        errors.append(f"abertura não identifica o clássico/rivalidade {name}")
    if not whole_ok:
        errors.append(f"o texto não contextualiza a rivalidade {name}")
    if not any(marker in fold(body_html) for marker in ("classico","rivalidade","derby","derbi","duelo historico")):
        errors.append("rivalidade mencionada sem contextualização jornalística")
    # O texto não pode simplesmente virar um histórico de clubes: as travas de
    # notícia atual e repetição continuam sendo avaliadas separadamente.
    return errors


def category_and_third_club_errors(body_html: str, contract: dict[str, Any]) -> list[str]:
    """Bloqueia mistura de categorias e titulares de clubes fora da pauta."""
    context = contract.get("match_context") or {}
    competition = fold(" ".join(str(context.get(key) or "") for key in
                               ("competition", "category", "age_group")))
    text = fold(body_html)
    youth_marker = r"\b(?:sub|u|under) (?:15|17|18|19|20|21|23)\b"
    if not re.search(youth_marker, competition) and re.search(youth_marker, text):
        return ["resultado ou elenco de categoria de base misturado ao pré-jogo profissional"]
    home = fold(str(context.get("display_home") or context.get("home") or ""))
    away = fold(str(context.get("display_away") or context.get("away") or ""))
    for item in re.finditer(
        r"\b(?:e|foi|sera|esta) titular (?:no|na|pelo|pela) ([a-z][a-z0-9]*)\b",
        text,
    ):
        other = item.group(1)
        if other not in ("clube", "time", "confronto", "duelo") and other not in home.split() and other not in away.split():
            return ["titular de terceiro clube apresentado como contexto do pré-jogo"]
    return []


def dense_fixture_enumeration_errors(body_html: str) -> list[str]:
    """Cinco jogos com cinco datas no mesmo parágrafo não são análise."""
    date_pattern = (
        r"\b\d{1,2} de (?:janeiro|fevereiro|marco|abril|maio|junho|"
        r"julho|agosto|setembro|outubro|novembro|dezembro)\b"
    )
    for paragraph in paragraphs(body_html):
        if len(re.findall(date_pattern, paragraph)) >= 4:
            return ["cronologia extensa de placares e datas substitui reportagem sobre a partida atual"]
    return []


def editorial_development_errors(body_html: str) -> list[str]:
    """Bloqueia matéria que alcança 700 palavras só por listas e parágrafos rasos.

    Medida conservadora de UX: o modelo LDU aprovado possui muitos blocos
    argumentativos completos; a publicação original Estudiantes x Flamengo
    tinha somente oito parágrafos minimamente desenvolvidos. Sem um mínimo
    de desenvolvimento NÃO há reportagem, mesmo com serviços corretos.
    """
    words = len(fold(body_html).split())
    if words < 650:
        return []  # textos curtos já falham em outras validações
    developed = 0
    for paragraph in PARAGRAPHS.findall(body_html):
        content = fold(paragraph)
        if HEADINGS.fullmatch("<p>" + paragraph + "</p>"):
            continue
        if len(content.split()) >= 45:
            developed += 1
    if developed < 9:
        return [
            "profundidade narrativa insuficiente: menos de nove parágrafos "
            "com desenvolvimento jornalístico; não substituir reportagem "
            "por ficha de serviço, cronologia ou repetição do lide"
        ]
    return []


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
    # Cabeçalhos da primeira versão de Estudiantes x Flamengo serviam apenas
    # para repetir a ficha do jogo. O modelo aprovado usa títulos com pauta.
    if any(h in {"contexto do confronto", "horario e local da partida",
                 "subtitulo especifico a definir",
                 "contexto competitivo da partida subtitulo especifico a definir"}
           for h in headings):
        errors.append("subtítulo genérico/de serviço repetido: criar título jornalístico baseado em fato novo verificado")
    if any(h in {"dados do confronto", "informacoes principais", "resumo do encontro",
                 "fechamento", "servico do jogo", "ultimas linhas antes da partida"}
           for h in headings):
        errors.append("subtítulos de repetição/fechamento artificial")
    if "onde assistir" in headings and ("dados do confronto" in headings or "servico do jogo" in headings):
        errors.append("serviço repetido em seções diferentes")
    errors.extend(editorial_development_errors(body_html))
    errors.extend(category_and_third_club_errors(body_html, contract))
    errors.extend(repeated_lineup_errors(body_html, contract))
    errors.extend(dense_fixture_enumeration_errors(body_html))
    errors.extend(near_duplicate_errors(body_html))
    errors.extend(repeated_stat_summaries_errors(body_html))
    errors.extend(repeated_preparation_hook_errors(body_html, contract))
    errors.extend(unrelated_story_errors(body_html, contract))
    errors.extend(rivalry_context_errors(body_html, contract))
    errors.extend(redundant_recent_calendar_errors(body_html))
    errors.extend(unsupported_stakes_closing_errors(body_html, contract))
    return list(dict.fromkeys(errors))
