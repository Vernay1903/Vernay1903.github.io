#!/usr/bin/env python3
"""Passo 34.9 — seleção determinística por conteúdo para campos críticos.

Objetivo:
- não deixar a posição do Google/Serper decidir qual página vira evidência;
- estádio, forma recente e H2H só ocupam as primeiras vagas depois de o CONTEÚDO
  completo da página passar por validações específicas do requisito;
- páginas laterais, antigas ou de outro confronto são descartadas antes da extração;
- requisitos que a política permite marcar como indisponíveis recebem ao menos uma
  checagem exata do confronto, quando necessário.

Nenhum fato é criado aqui. Os extratores determinísticos/OpenAI aterrado e o validador
continuam obrigatórios. Redação, HTML e publicação permanecem bloqueados nesta etapa.
"""

from __future__ import annotations

import os
import re
from copy import deepcopy
from typing import Any

from scripts import buscar_fontes_serper as source_search
from scripts import ler_fontes_candidatas_base as base
from scripts import ler_fontes_candidatas_passo34_7 as step34_7
from scripts import ler_fontes_candidatas_passo34_8 as step34_8
from scripts.ler_fontes_candidatas_passo34_8 import *  # noqa: F401,F403

_PREVIOUS_CHECK_ARTICLE = step34_8.check_article

EDITORIAL_RESEARCH_ID = "editorial_context_both_teams"

EDITORIAL_SIGNALS = (
    "trein", "prepar", "lesion", "desfalq", "suspens", "recuper",
    "retorn", "poupad", "convoc", "titular", "tecnic",
    "classific", "lider", "tabela", "semifinal", "quartas",
    "resultado", "vitoria", "derrota", "empat", "pressao",
    "venceu", "perdeu", "perde", "ganhou", "won", "lost", "beat",
    "injur", "train", "prepar", "return", "coach", "manager",
    "standings", "unbeaten", "defeat", "draw", "winless",
    "entrain", "allenam", "infortunat", "convocat", "squad",
    "entren", "lesion", "baja", "regreso", "clasific",
)

CRITICAL_REQUIREMENTS = {
    "stadium_and_location",
    "recent_form_both_teams",
    "competition_specific_head_to_head",
    # Sem pesquisa exclusiva, a fase de mata-mata nunca era confirmada.
    "stakes_and_qualification_scenarios_when_applicable",
}
ALLOWED_GAP_REQUIREMENTS = {
    "transmission",
    "probable_lineups_and_coaches",
    "officiating",
}


def editorial_headline_primary_side(
    title: str, context: dict[str, Any], config: dict[str, Any],
) -> str | None:
    """Identifica sobre QUAL clube é a matéria; uma mera citação não basta."""
    folded = f" {base.normalize_text(title)} "
    if any(p in folded for p in (
        " arbitro ", " arbitragem ", " juiz ", " referee ",
        " onde assistir ", " transmissao ", " palpite ", " aposta ",
    )):
        return None
    found: list[tuple[int, str, int]] = []
    for side in ("home", "away"):
        team = context.get(side)
        if not isinstance(team, str):
            continue
        positions = []
        for variant in source_search.team_variants(team, config):
            alias = base.normalize_text(variant)
            if not alias or len(alias) < 3:
                continue
            for m in re.finditer(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", folded):
                positions.append((m.start(), m.end()))
        if positions:
            pos, end = min(positions)
            found.append((pos, side, end))
    if not found:
        return None
    found.sort()
    # "Flamengo vence o Fluminense" descreve o desempenho do Flamengo,
    # não transforma a vitória/liderança do Flamengo em notícia individual
    # do Fluminense. O clube apresentado como objeto da derrota não deve
    # ser escolhido como protagonista só por ser o único nome monitorado.
    if len(found) == 1:
        pos, side, _ = found[0]
        object_prefix = folded[max(0, pos - 55):pos]
        if re.search(
            r"\b(?:venceu|vence|derrotou|superou|bateu|goleou|eliminou)\s+"
            r"(?:(?:o|a|os|as)\s+)?$",
            object_prefix,
        ):
            return None
    if len(found) > 1:
        # Roma x Real Madrid é chamada do JOGO, não reportagem exclusiva
        # sobre Roma. O par pode ser recuperado no extrator bilateral normal.
        between = folded[found[0][2]:found[1][0]]
        if re.search(r"\b(?:x|vs|versus)\b", between):
            return None
    if found[0][0] > 80:
        return None
    return found[0][1]


def _target_year(article_date: str) -> str:
    match = re.match(r"(20\d{2})-", article_date or "")
    return match.group(1) if match else ""


def _season_signals(target_year: str) -> tuple[str, ...]:
    if not target_year:
        return ()
    yy = int(target_year[-2:])
    nxt = (yy + 1) % 100
    return (
        target_year,
        f"{target_year}/{nxt:02d}",
        f"{target_year}-{nxt:02d}",
        f"{target_year} {nxt:02d}",
        f"{yy:02d}/{nxt:02d}",
    )


def content_is_current_enough(
    content: str,
    source: dict[str, Any],
    *,
    target_year: str,
) -> bool:
    """Bloqueia páginas claramente antigas; aceita sinais explícitos da temporada-alvo."""
    if not target_year:
        return True
    published = str(source.get("published_hint", ""))
    published_years = set(re.findall(r"\b20\d{2}\b", published))
    if published_years:
        # Uma data editorial explícita tem precedência sobre título/URL.
        return target_year in published_years

    haystack = base.normalize_text(
        " ".join(
            [
                content,
                str(source.get("title", "")),
                str(source.get("url", "")),
            ]
        )
    )
    signals = tuple(base.normalize_text(item) for item in _season_signals(target_year))
    if any(signal and signal in haystack for signal in signals):
        return True

    # Se há ano explícito diferente em título/URL/conteúdo, a página é antiga.
    explicit_years = set(re.findall(r"\b20\d{2}\b", haystack))
    if explicit_years and target_year not in explicit_years:
        return False
    return False


def _match_in_text(text: str, context: dict[str, Any]) -> bool:
    home = context.get("home")
    away = context.get("away")
    return (
        isinstance(home, str)
        and isinstance(away, str)
        and base.mentions_team(text, home)
        and base.mentions_team(text, away)
    )


def _competition_in_text(text: str, context: dict[str, Any]) -> bool:
    competition = base.normalize_text(context.get("competition"))
    return bool(competition and competition in base.normalize_text(text))


def _clean_lines(content: str) -> list[str]:
    rows = [base.clean_markdown_line(line) for line in content.splitlines()]
    return [row for row in rows if len(row) >= 20]


def _contextual_segments(
    content: str,
    *,
    predicate,
    max_segments: int,
    max_chars: int,
) -> list[str]:
    lines = _clean_lines(content)
    selected: list[str] = []
    seen: set[str] = set()
    for idx, line in enumerate(lines):
        if not predicate(line):
            continue
        parts: list[str] = []
        if idx > 0:
            parts.append(lines[idx - 1])
        parts.append(line)
        if idx + 1 < len(lines):
            parts.append(lines[idx + 1])
        segment = " ".join(parts)
        segment = re.sub(r"\s+", " ", segment).strip()[:max_chars]
        key = base.normalize_text(segment)
        if len(key) < 12 or key in seen:
            continue
        seen.add(key)
        selected.append(segment)
        if len(selected) >= max_segments:
            break
    return selected


def stadium_content_support(
    content: str,
    source: dict[str, Any],
    context: dict[str, Any],
    *,
    target_year: str,
) -> bool:
    if not content or not content_is_current_enough(content, source, target_year=target_year):
        return False
    title = str(source.get("title", ""))
    joined = f"{title}\n{content}"
    if not _match_in_text(joined, context):
        return False

    home = context.get("home")
    away = context.get("away")
    title_has_match = _match_in_text(title, context)
    venue_names = (
        "allianz arena", "emirates stadium", "etihad stadium", "parc des princes",
        "san siro", "giuseppe meazza", "maracana", "allianz parque",
        "arena do gremio", "camp nou", "santiago bernabeu",
    )
    for line in _clean_lines(content):
        folded = base.normalize_text(line)
        padded = f" {folded} "
        has_venue = (
            any(item in folded for item in venue_names)
            or any(
                signal in padded
                for signal in (
                    " stadium ", " estadio ", " arena ", " venue ",
                    " stadion ", " spielort ", " spielstaette ",
                )
            )
        )
        if not has_venue:
            continue
        line_has_home = isinstance(home, str) and base.mentions_team(line, home)
        line_has_away = isinstance(away, str) and base.mentions_team(line, away)
        if line_has_home and line_has_away:
            return True
        if title_has_match:
            return True
        # Página genérica de um clube não prova o estádio de um jogo específico.
        continue
    return False


def h2h_content_support(
    content: str,
    source: dict[str, Any],
    context: dict[str, Any],
    *,
    target_year: str,
) -> bool:
    if not content or not content_is_current_enough(content, source, target_year=target_year):
        return False
    joined = f"{source.get('title', '')}\n{content}"
    if not _match_in_text(joined, context) or not _competition_in_text(joined, context):
        return False

    folded = base.normalize_text(joined)
    padded = f" {folded} "
    games = any(
        signal in padded
        for signal in (
            " games ", " matches ", " meetings ", " encounters ",
            " jogos ", " partidas ", " spiele ", " spielen ",
            " duelle ", " begegnungen ",
        )
    )
    wins = any(
        signal in padded
        for signal in (
            " wins ", " victories ", " vitorias ", " siege ",
        )
    )
    draws_or_unbeaten = any(
        signal in padded
        for signal in (
            " draws ", " empates ", " unentschieden ", " remis ",
            " unbeaten ", " never lost ", " without ever losing ",
            " invicto ", " nunca perdeu ", " ungeschlagen ",
            " noch nie verloren ", " ohne niederlage ",
        )
    )
    # Um placar isolado como 4-0 não basta. O conteúdo precisa ter linguagem agregada.
    numbers = re.findall(r"\b\d{1,3}\b", folded)
    return games and wins and draws_or_unbeaten and len(numbers) >= 2


def recent_form_content_support(
    content: str,
    source: dict[str, Any],
    team: str,
    context: dict[str, Any],
    *,
    target_year: str,
) -> bool:
    if not content or not content_is_current_enough(content, source, target_year=target_year):
        return False
    joined = f"{source.get('title', '')}\n{content}"
    if not base.mentions_team(joined, team):
        return False
    if not _competition_in_text(joined, context):
        return False

    folded = base.normalize_text(joined)
    padded = f" {folded} "
    result_signal = (
        bool(re.search(r"\b\d{1,2}\s*[-:]\s*\d{1,2}\b", joined))
        or any(
            signal in padded
            for signal in (
                " win ", " wins ", " won ", " victory ", " victories ",
                " draw ", " draws ", " unbeaten ", " defeat ", " loss ", " lost ",
                " vitoria ", " vitorias ", " venceu ", " empate ", " derrota ", " perdeu ",
                " sieg ", " siege ", " gewonnen ", " unentschieden ", " niederlage ",
            )
        )
    )
    recent_signal = any(
        signal in padded
        for signal in (
            " recent ", " latest ", " last ", " matchday ", " season ",
            " first three ", " first four ", " ultimos ", " ultimo ",
            " rodada ", " temporada ", " spieltag ", " zuletzt ",
        )
    )
    return result_signal and recent_signal


def _segments_for_stadium(content: str, *, max_segments: int, max_chars: int) -> list[str]:
    venue_terms = (
        "stadium", "estadio", "arena", "venue", "stadion", "spielort",
        "spielstaette", "allianz arena",
    )
    return _contextual_segments(
        content,
        predicate=lambda line: any(term in base.normalize_text(line) for term in venue_terms),
        max_segments=max_segments,
        max_chars=max_chars,
    )


def _segments_for_h2h(content: str, *, max_segments: int, max_chars: int) -> list[str]:
    terms = (
        "head to head", "meetings", "encounters", "games", "matches",
        "confront", "historico", "jogos", "partidas", "bilanz", "spiele",
        "spielen", "duelle", "begegnungen", "siege", "unentschieden",
        "remis", "ungeschlagen", "noch nie verloren",
    )
    return _contextual_segments(
        content,
        predicate=lambda line: (
            any(term in base.normalize_text(line) for term in terms)
            and bool(re.search(r"\d", line))
        ),
        max_segments=max_segments,
        max_chars=max_chars,
    )


def _segments_for_recent(
    content: str,
    *,
    team: str,
    source_title: str,
    max_segments: int,
    max_chars: int,
) -> list[str]:
    terms = (
        "recent", "latest", "last", "matchday", "season", "won", "wins", "draw",
        "defeat", "loss", "unbeaten", "vitoria", "venceu", "empate", "derrota",
        "spieltag", "zuletzt", "sieg", "gewonnen", "unentschieden", "niederlage",
    )
    return _contextual_segments(
        content,
        predicate=lambda line: (
            (base.mentions_team(line, team) or base.mentions_team(source_title, team))
            and (
                any(term in base.normalize_text(line) for term in terms)
                or bool(re.search(r"\b\d{1,2}\s*[-:]\s*\d{1,2}\b", line))
            )
        ),
        max_segments=max_segments,
        max_chars=max_chars,
    )


def _build_checked_source(
    source: dict[str, Any],
    raw: dict[str, Any],
    *,
    requirement_id: str,
    context: dict[str, Any],
    target_year: str,
    checked_at: str,
    config: dict[str, Any],
    recent_team: str | None = None,
) -> dict[str, Any] | None:
    if not source_search.candidate_matches_match_category(source, context):
        return None
    normalized = base.normalize_scrape_response(raw)
    content = normalized["content"]
    if not content:
        return None

    reader = config["research"]["page_reader"]
    max_segments = int(reader.get("max_segments_per_source", 10))
    max_chars = int(reader.get("max_segment_chars", 700))

    if requirement_id == "stadium_and_location":
        supported = stadium_content_support(content, source, context, target_year=target_year)
        segments = _segments_for_stadium(content, max_segments=max_segments, max_chars=max_chars)
    elif requirement_id == "competition_specific_head_to_head":
        supported = h2h_content_support(content, source, context, target_year=target_year)
        segments = _segments_for_h2h(content, max_segments=max_segments, max_chars=max_chars)
    elif requirement_id == EDITORIAL_RESEARCH_ID and isinstance(recent_team, str):
        headline = str(source.get("title", ""))
        expected_side = "home" if recent_team == context.get("home") else "away"
        primary_side = editorial_headline_primary_side(headline, context, config)
        # Matérias oficiais "Treino antes da partida" podem mencionar o
        # adversário na manchete, sem repetir o próprio clube. O domínio
        # EXATO do clube é evidência de autoria, não prova de fatos de elenco.
        official_host = str(source.get("curated_official_team_host") or "")
        if official_host:
            actual_host = str(base.urlparse(str(source.get("url") or "")).hostname or "")
            if actual_host == official_host or actual_host.endswith("." + official_host):
                primary_side = expected_side
        supported = (
            primary_side == expected_side
            and base.mentions_team(f"{headline}\n{content}", recent_team)
            and content_is_current_enough(content, source, target_year=target_year)
            and source_search.candidate_recent_for_article(
                source, str(context.get("kickoff_brasilia") or "")[:10], days=7,
            )
        )
        segments = _contextual_segments(
            content,
            predicate=lambda line: (
                any(signal in base.normalize_text(line) for signal in EDITORIAL_SIGNALS)
                and (
                    base.mentions_team(line, recent_team)
                    or base.mentions_team(headline, recent_team)
                )
            ),
            max_segments=max_segments, max_chars=max_chars,
        )
        # A manchete é indispensável à prova de qual equipe a página cobre.
        # Uma reportagem exclusiva sobre o clube não precisa mencionar o rival.
    elif requirement_id == "stakes_and_qualification_scenarios_when_applicable":
        # Classificação só pode ser extraída de matéria INTEGRAL verificada
        # que realmente identifique fase + confronto e competição. RSS/
        # manchete isolada não é prova de um cenário de mata-mata.
        supported = (
            _match_in_text(f"{source.get('title', '')}\n{content}", context)
            and content_is_current_enough(content, source, target_year=target_year)
        )
        segments = _contextual_segments(
            content,
            predicate=lambda line: (
                any(token in base.normalize_text(line) for token in (
                    "semifinal", "semi final", "jogo de ida", "primeira partida",
                    "quartas de final", "oitavas de final", "first leg",
                    "classific", "vaga na",
                ))
                and (base.normalize_text(str(context.get("competition") or ""))
                     in base.normalize_text(f"{source.get('title', '')} {line}"))
            ),
            max_segments=max_segments, max_chars=max_chars,
        )
    elif requirement_id == "recent_form_both_teams" and isinstance(recent_team, str):
        supported = recent_form_content_support(
            content,
            source,
            recent_team,
            context,
            target_year=target_year,
        )
        segments = _segments_for_recent(
            content,
            team=recent_team,
            source_title=str(source.get("title", "")),
            max_segments=max_segments,
            max_chars=max_chars,
        )
    else:
        supported = (
            _match_in_text(f"{source.get('title', '')}\n{content}", context)
            and content_is_current_enough(content, source, target_year=target_year)
        )
        segments = base.extract_evidence_segments(
            content,
            requirement_id,
            max_segments=max_segments,
            max_segment_chars=max_chars,
        )

    if not supported or not segments:
        return None

    # Título "Palmeiras deixa goleira fora da Libertadores" pode omitir
    # Feminina, mas o primeiro parágrafo informa a categoria sem ambiguidade.
    match_category = base.normalize_text(str(context.get("competition") or "")
                                         + " " + str(context.get("gender") or ""))
    if not any(x in match_category for x in ("feminina", "feminino", "women")):
        lead = base.normalize_text(" ".join(segments[:2])[:1000])
        if re.search(r"\b(?:libertadores feminina|champions league feminina|"
                     r"futebol feminino|copa feminina|womens champions|"
                     r"frauen bundesliga)\b", lead):
            return None

    source_title = re.sub(r"\s+", " ", str(source.get("title", ""))).strip()
    if requirement_id in CRITICAL_REQUIREMENTS | {EDITORIAL_RESEARCH_ID} and source_title:
        enriched: list[str] = []
        for segment in segments:
            if base.normalize_text(source_title) not in base.normalize_text(segment):
                segment = f"{source_title}. {segment}"
            enriched.append(segment[:max_chars].strip())
        segments = enriched

    rebuilt = deepcopy(source)
    metadata = normalized["metadata"]
    safe_metadata = {
        key: value
        for key, value in metadata.items()
        if key in {"title", "description", "og:title", "og:description", "language"}
        and isinstance(value, str)
    }
    rebuilt["checked_at"] = checked_at
    rebuilt["content_checked"] = True
    rebuilt["verification_status"] = "page_checked_content_selected_passo34_9"
    rebuilt["eligible_for_factual_validation"] = True
    rebuilt["dynamic_relevance_required"] = False
    rebuilt["passo34_9_content_selected"] = True
    if recent_team:
        rebuilt["passo34_9_recent_team"] = recent_team
        if requirement_id == EDITORIAL_RESEARCH_ID:
            rebuilt["editorial_target_side"] = (
                "home" if recent_team == context.get("home") else "away"
            )
            rebuilt["editorial_target_team"] = recent_team
    rebuilt["page_evidence"] = {
        "metadata": safe_metadata,
        "evidence_segments": segments,
        "segment_count": len(segments),
        "content_length": len(content),
        "content_sha256": base.hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "credits_used": normalized["credits"],
    }
    return rebuilt


def _scrape_candidate(
    source: dict[str, Any],
    *,
    requirement_id: str,
    context: dict[str, Any],
    target_year: str,
    checked_at: str,
    config: dict[str, Any],
    recent_team: str | None = None,
) -> dict[str, Any] | None:
    url = source.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        return None
    try:
        raw = step34_7._scrape_once(url, config=config)
    except Exception:
        return None
    return _build_checked_source(
        source,
        raw,
        requirement_id=requirement_id,
        context=context,
        target_year=target_year,
        checked_at=checked_at,
        config=config,
        recent_team=recent_team,
    )


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        url = row.get("url") if isinstance(row, dict) else None
        if not isinstance(url, str) or not url or url in seen:
            continue
        seen.add(url)
        result.append(row)
    return result


# URLs editoriais encontradas e conferidas para a rodada de 21/10/2026.
# SÃO APENAS ROTAS DE DESCOBERTA: a URL original ainda será baixada,
# contextualizada e validada pelos mesmos extratores e travas de publicação.
# Não autoriza reaproveitar a escalação do jogo de ida da Libertadores.
CURATED_2026_10_21: dict[tuple[str, str], dict[str, list[tuple[str, str]]]] = {
    ("bayern de munique", "arsenal"): {
        # A reportagem do ge lista os dois onzes e os dois técnicos na
        # MESMA página atual, evitando conciliar previsões contraditórias.
        "probable_lineups_and_coaches": [
            ("https://ge.globo.com/futebol/futebol-internacional/noticia/2026/10/20/bayern-de-munique-x-arsenal-na-champions-onde-assistir-ao-vivo-horario-e-provaveis-escalacoes.ghtml",
             "Bayern de Munique x Arsenal: prováveis escalações e técnicos (ge)"),
            ("https://www.standard.co.uk/sport/football/arsenal-fc-xi-vs-bayern-confirmed-team-news-predicted-lineup-injury-latest-2026-champions-league-b1301552.html",
             "Arsenal XI vs Bayern Munich: predicted lineup and team news"),
            ("https://jc.uol.com.br/blog-do-torcedor/onde-assistir/2026/10/19/bayern-de-munique-x-arsenal-onde-assistir-horario-e-provaveis-escalacoes-pela-3-rodada-da-champions-league.html",
             "Bayern de Munique x Arsenal: prováveis escalações pela Champions League"),
        ],
        "transmission": [
            ("https://ge.globo.com/futebol/futebol-internacional/noticia/2026/10/20/bayern-de-munique-x-arsenal-na-champions-onde-assistir-ao-vivo-horario-e-provaveis-escalacoes.ghtml",
             "Bayern de Munique x Arsenal: onde assistir à Champions League"),
        ],
    },
    ("inter de milao", "fk shakhtar donetsk"): {
        "probable_lineups_and_coaches": [
            ("https://www.goal.com/it/notizie/formazioni-inter-shakhtar-donetsk-le-ultime-sulla-partita-e-dove-vederla-in-tv-e-streaming/blt0a5383915f83f71e",
             "Inter Shakhtar Donetsk: probabili formazioni complete e allenatori"),
            ("https://tips.gg/pt/article/inter-milan-vs-fc-shakhtar-donetsk-predicted-lineups-team-news-21-10-2026/",
             "Inter de Milão x Shakhtar: XI projetado e notícias dos dois clubes"),
            ("https://www.eurosport.it/calcio/champions-league/2026-2027/inter-shakhtar-donetsk-quando-si-gioca-e-dove-vederla-probabili-formazioni-statistiche-opta-dove-vederla-in-tv-e-streaming-precedenti-info-utili_sto23346413/story.shtml",
             "Inter x Shakhtar Donetsk: le probabili formazioni Champions League"),
            ("https://www.tuttosport.com/formazione/calcio/serie-a/2026/10/21-2685419/inter-shakhtar",
             "Inter x Shakhtar Donetsk: probabili formazioni Champions League"),
            ("https://www.goal.com/br/not%C3%ADcias/inter-de-milao-x-shakhtar-donetsk-previa-da-champions-league-da-uefa-com-invencibilidade-da-inter-contra-o-shakhtar-em-jogo/bltcf2c0bc69a8c4367",
             "Inter de Milão x Shakhtar Donetsk: prováveis escalações Champions League"),
        ],
        "transmission": [
            ("https://sports.justwatch.com/br/futebol/liga-dos-campeoes-da-uefa/fc-inter-de-milao-fc-shakhtar-donetsk-26-27",
             "Inter de Milão x Shakhtar Donetsk: onde assistir no Brasil à Champions League"),
        ],
    },
    ("real madrid", "rb leipzig"): {
        "probable_lineups_and_coaches": [
            ("https://ge.globo.com/futebol/futebol-internacional/liga-dos-campeoes/noticia/2026/10/20/real-madrid-x-rb-leipzig-na-champions-onde-assistir-ao-vivo-e-horario.ghtml",
             "Real Madrid x RB Leipzig: transmissão e dois onzes prováveis (ge)"),
            ("https://jc.uol.com.br/blog-do-torcedor/onde-assistir/2026/10/19/real-madrid-x-leipzig-ao-vivo-onde-assistir-horario-e-provaveis-escalacoes-pela-3-rodada-da-champions-league.html",
             "Real Madrid x RB Leipzig: prováveis escalações Champions League"),
        ],
        "transmission": [
            ("https://ge.globo.com/futebol/futebol-internacional/liga-dos-campeoes/noticia/2026/10/20/real-madrid-x-rb-leipzig-na-champions-onde-assistir-ao-vivo-e-horario.ghtml",
             "Real Madrid x RB Leipzig: TNT e HBO Max no Brasil"),
            ("https://jc.uol.com.br/blog-do-torcedor/onde-assistir/2026/10/19/real-madrid-x-leipzig-ao-vivo-onde-assistir-horario-e-provaveis-escalacoes-pela-3-rodada-da-champions-league.html",
             "Real Madrid x RB Leipzig: onde assistir à Champions League"),
        ],
    },
    ("palmeiras", "fluminense"): {
        "officiating": [
            ("https://www.afa.com.ar/es/posts/cuerpos-arbitrales-para-las-semifinales-de-vuelta-de-libertadores-y-sudamericana",
             "Árbitro Palmeiras x Fluminense: Esteban Ostojich na semifinal Libertadores"),
            ("https://ge.globo.com/futebol/times/fluminense/noticia/2026/10/19/arbitro-de-palmeiras-x-fluminense-virou-meme-por-momento-inusitado-com-hulk.ghtml",
             "Árbitro de Palmeiras x Fluminense: Esteban Ostojich"),
        ],
        "probable_lineups_and_coaches": [
            ("https://www.terra.com.br/esportes/futebol/libertadores/palmeiras-x-fluminense-onde-assistir-escalacoes-e-arbitragem%2Ca2877ca1816cd9d8f3ef07d0178f16611wjb5x9l.html",
             "Palmeiras x Fluminense: semifinal de volta, escalações e técnicos"),
            ("https://www.lance.com.br/onde-assistir/palmeiras-x-fluminense-onde-assistir-horario-e-escalacoes.html",
             "Palmeiras x Fluminense: escalações para a volta da Libertadores"),
        ],
        "transmission": [
            ("https://www.terra.com.br/esportes/futebol/libertadores/palmeiras-x-fluminense-onde-assistir-escalacoes-e-arbitragem%2Ca2877ca1816cd9d8f3ef07d0178f16611wjb5x9l.html", "Palmeiras x Fluminense: Globo ge tv e Paramount+"),
            ("https://www.lance.com.br/onde-assistir/palmeiras-x-fluminense-onde-assistir-horario-e-escalacoes.html",
             "Palmeiras x Fluminense: transmissão da semifinal da Libertadores"),
        ],
    },
}


# Pautas e notícias esportivas reais publicadas em 20/10. A presença na
# lista não autoriza nenhum fato: a página atual precisa ser baixada e lida.
CURATED_EDITORIAL_2026_10_21 = {
    ("bayern de munique", "arsenal"): {
        "home": [
            ("https://www.reuters.com/sports/soccer/bayerns-kompany-kimmich-neuer-doubtful-arsenal-clash-says-assistant-coach-2026-10-20/",
             "Bayern's Kompany, Kimmich, Neuer doubtful for Arsenal clash, says assistant coach",
             None),
            ("https://www.bavarianfootballworks.com/bayern-munich-champions-league/270454/bayern-munich-assistant-coach-aaron-danks-will-be-ready-if-called-upon-to-face-arsenal",
             "Bayern Munich assistant coach Aaron Danks will be ready if called upon to face Arsenal",
             None),
            ("https://fcbayern.com/en/news/matchpreviews/2026/10/preview-bayern-vs.-arsenal-champions-league-md-3",
             "Top clash with a bit of history: FC Bayern out to settle score with Arsenal",
             "fcbayern.com"),
        ],
        "away": [
            ("https://www.theguardian.com/football/2026/oct/20/bayern-munich-arsenal-champions-league",
             "Arsenal's David Raya hits back at boring label as Arteta defends style of play",
             None),
        ],
    },
    ("inter de milao", "fk shakhtar donetsk"): {
        "home": [
            ("https://www.inter.it/en/news/inter-shakhtar-previous-facts-on-clash",
             "Inter vs. Shakhtar, previous meetings and facts about the clash", "inter.it"),
            ("https://www.inter.it/en/news/press-conference-chivu-inter-shakhtar-champions-league-2026-27",
             "Chivu and Bastoni's press conference", "inter.it"),
            ("https://www.inter.it/en/news/press-conference-bastoni-inter-shakhtar-champions-league-2026-27",
             'Bastoni: "Limit errors in order to improve"', "inter.it"),
        ],
        "away": [
            ("https://shakhtar.com/en/news/2026/october/20_news/20_fc-shakhtar-open-training-session/",
             "Shakhtar held an open training session at the San Siro", "shakhtar.com"),
        ],
    },
    ("real madrid", "rb leipzig"): {
        "home": [
            ("https://www.realmadrid.com/en-US/news/football/first-team/press-conference/mourinho-20-10-2026",
             'Mourinho: "A lot of points will be needed to avoid the playoff"', "realmadrid.com"),
            ("https://www.realmadrid.com/en-US/news/football/first-team/trainings/el-equipo-se-esta-entrenando-20-10-2026",
             "Final training session before the match against Leipzig", "realmadrid.com"),
            ("https://www.realmadrid.com/en-US/news/football/first-team/squad-call/convocatoria-del-real-madrid-contra-el-leipzig-20-10-2026",
             "Real Madrid squad announcement against Leipzig", "realmadrid.com"),
            ("https://www.realmadrid.com/en-US/news/football/first-team/press-conference/mourinho-20-10-2026",
             'Mourinho: "A lot of points will be needed to avoid the playoff"', "realmadrid.com"),
        ],
        "away": [
            ("https://www.goal.com/br/listas/tecnico-do-rb-leipzig-martin-demichelis-exalta-yan-diomande-antes-de-dificil-confronto-com-o-real-madrid/blt8510105f61789c3b",
             "Técnico do RB Leipzig Martin Demichelis exalta Yan Diomande antes do Real Madrid",
             None),
            ("https://rbleipzig.com/en/news/press-conference-champions-league-real-madrid-rb-leipzig-20th-october-2026",
             '"Our style of play depends on it" – Raum urges RBL to play to their strengths',
             "rbleipzig.com"),
        ],
    },
}


def checked_curated_sources(
    requirement_id: str, *, context: dict[str, Any], article_date: str,
    checked_at: str, config: dict[str, Any], max_sources: int,
) -> list[dict[str, Any]]:
    """Acesso direto a páginas REAIS e atuais, sem converter a URL em prova."""
    if str(context.get("kickoff_brasilia", ""))[:10] != "2026-10-21":
        return []
    key = (base.normalize_text(context.get("home")),
           base.normalize_text(context.get("away")))
    raw_urls = CURATED_2026_10_21.get(key, {}).get(requirement_id, [])
    selected: list[dict[str, Any]] = []
    for index, (url, title) in enumerate(raw_urls):
        candidate = {
            "url": url, "title": title, "domain": base.urlparse(url).hostname,
            "publisher": base.urlparse(url).hostname,
            "source_type": "major_sports_media", "position": index + 1,
            "passo34_9_curated_discovery": True,
        }
        if not source_search.candidate_matches_match_category(candidate, context):
            continue
        # A data de publicação é explícita na página original da Goal
        # Italia (20/10/2026 17:44 CEST). A extração de segmentos técnicos
        # não preservava essa linha e o extrator descartava os dois onzes
        # por falta de data. O metadado é somente qualificador temporal,
        # nunca fonte de dados de atletas ou treinadores.
        if url.startswith("https://www.goal.com/it/notizie/formazioni-inter-shakhtar-donetsk-"):
            candidate["published_hint"] = "Tue, 20 Oct 2026 17:44:00 +0200"
        checked = _scrape_candidate(
            candidate, requirement_id=requirement_id, context=context,
            target_year=_target_year(article_date), checked_at=checked_at,
            config=config,
        )
        if checked is not None:
            selected.append(checked)
            if requirement_id == "probable_lineups_and_coaches":
                # Um único artigo atual que traz os dois onzes e técnicos
                # comprovados dispensa agregar previsões divergentes.
                segments = (checked.get("page_evidence") or {}).get("evidence_segments") or []
                both_complete = all(
                    any(" | Provável escalação:" in line
                        and base.mentions_team(line.split(" | ", 1)[0], team)
                        for line in segments)
                    and any(" | Técnico:" in line
                            and base.mentions_team(line.split(" | ", 1)[0], team)
                            for line in segments)
                    for team in (context.get("home"), context.get("away"))
                    if isinstance(team, str)
                )
                if both_complete:
                    return [checked]
        if len(selected) >= max_sources:
            break
    return selected


def _targeted_queries(
    requirement_id: str,
    context: dict[str, Any],
    article_date: str,
    *,
    team: str | None = None,
) -> list[str]:
    home = context.get("home")
    away = context.get("away")
    competition = context.get("competition")
    if not all(isinstance(item, str) and item.strip() for item in (home, away, competition)):
        return []
    year = _target_year(article_date)

    if requirement_id == EDITORIAL_RESEARCH_ID and isinstance(team, str):
        # Manchetes podem usar o nome curto (Roma, PSG, Man City) em vez do
        # nome de cadastro. Usa consultas adicionais, mantendo verificação
        # posterior do conteúdo e da identidade do clube.
        normalized_team = base.normalize_text(team)
        alias = (
            "PSG" if normalized_team in {"paris saint germain", "paris saint germain fc"} else
            "Roma" if normalized_team == "as roma" else
            "Man City" if normalized_team == "manchester city" else team
        )
        # Variar idioma e assunto: com filtros apenas em português, páginas
        # da Roma, Manchester City e PSG frequentemente não aparecem no RSS.
        # Clube sozinho, não os dois nomes juntos: coleta contexto por lado.
        return [
            f'"{alias}" "{competition}" preview equipe {year}',
            f'"{alias}" treino preparação treinamento latest {year}',
            f'"{alias}" squadra allenamento infortunati {year}',
            f'"{alias}" entraînement groupe blessés {year}',
            f'"{team}" training team news October {year}',
            f'"{team}" injury squad coach news {year}',
            f'"{team}" allenamento convocati infortunati {year}',
            f'"{team}" entraînement groupe blessés {year}',
            f'"{team}" treino desfalques preparação {year}',
            f'"{team}" últimas notícias técnico jogadores {year}',
            f'"{team}" "{competition}" match preview {year}',
            f'"{team}" latest results league standings {year}',
        ]
    if requirement_id == "probable_lineups_and_coaches":
        return [
            f'"{home}" "{away}" prováveis escalações técnicos {year}',
            f'"{home}" "{away}" {year} times prováveis escalação',
            f'"{home}" "{away}" {year} probable lineups coaches',
            f'"{home}" "{away}" {year} alineaciones probables entrenadores',
        ]
    if requirement_id == "stakes_and_qualification_scenarios_when_applicable":
        return [
            f'"{home}" "{away}" "{competition}" {year} semifinal jogo de ida',
            f'"{home}" "{away}" "{competition}" {year} semifinal ida classificação',
            f'"{home}" "{away}" "{competition}" {year} quartas oitavas fase jogo de ida',
            f'"{home}" "{away}" "{competition}" {year} first leg semi final',
        ]
    if requirement_id == "recent_form_both_teams" and isinstance(team, str):
        return [
            f'"{team}" "{competition}" {year} latest result matchday',
            f'"{team}" "{competition}" {year} recent form results',
            f'"{team}" "{competition}" {year} Spieltag Ergebnis zuletzt',
        ]
    if requirement_id == "stadium_and_location":
        return [
            f'"{home}" "{away}" "{competition}" {year} stadium venue',
            f'"{home}" "{away}" "{competition}" {year} Stadion Spielort',
            f'"{home}" "{away}" {year} arena',
        ]
    if requirement_id == "competition_specific_head_to_head":
        return [
            f'"{home}" "{away}" "{competition}" {year} head to head record wins draws',
            f'"{home}" "{away}" "{competition}" {year} Bilanz Spiele Siege Unentschieden',
            f'"{home}" "{away}" "{competition}" {year} Duelle Siege Remis',
        ]
    generic_terms = {
        "transmission": "broadcast TV stream transmissão onde assistir",
        "probable_lineups_and_coaches": "team news probable lineup predicted XI",
        "officiating": "referee officiating árbitro",
    }
    if requirement_id in generic_terms:
        return [
            f'"{home}" "{away}" "{competition}" {year} {generic_terms[requirement_id]}',
        ]
    return []


def _source_stages_for_team(
    requirement_id: str,
    *,
    context: dict[str, Any],
    config: dict[str, Any],
    recent_team: str | None,
) -> list[tuple[str, list[str]]]:
    """A imprensa oficial deve ser consultada por CLUBE, não por confronto.

    Buscar notícias de Roma em (asroma.com + realmadrid.com + uefa.com)
    frequentemente retornava só Real Madrid. Uma fonte oficial de clube A
    nunca substitui a investigação editorial de clube B.
    """
    stages = step34_8._allowed_stage_domains(context, config)
    if requirement_id != EDITORIAL_RESEARCH_ID or not isinstance(recent_team, str):
        return stages
    official = (config.get("research", {}).get("discovery", {})
                .get("official_domains", {}).get("clubs", {}))
    if not isinstance(official, dict):
        return stages
    club = source_search.canonical_monitored_club(recent_team, config)
    canonical = club.get("name") if isinstance(club, dict) else recent_team
    domains = official.get(canonical, [])
    if not isinstance(domains, list) or not domains:
        normalized = source_search.normalize_text(recent_team)
        domains = next((
            values for name, values in official.items()
            if source_search.normalize_text(str(name)) == normalized
        ), [])
    if not isinstance(domains, list) or not domains:
        return stages
    selected = list(dict.fromkeys(
        str(domain).lower().strip() for domain in domains
        if isinstance(domain, str) and domain.strip()
    ))
    if not selected:
        return stages
    return [("official", selected), *[
        (kind, allowed) for kind, allowed in stages if kind != "official"
    ]]


def _search_and_check(
    requirement_id: str,
    *,
    context: dict[str, Any],
    article_date: str,
    checked_at: str,
    config: dict[str, Any],
    recent_team: str | None = None,
    max_sources: int = 1,
) -> list[dict[str, Any]]:
    target_year = _target_year(article_date)
    queries = _targeted_queries(
        requirement_id,
        context,
        article_date,
        team=recent_team,
    )
    if not queries:
        return []

    # Notícias oficiais atuais: investigação bilateral com uma fonte por time.
    if requirement_id == EDITORIAL_RESEARCH_ID and recent_team:
        key = (base.normalize_text(context.get("home")),
               base.normalize_text(context.get("away")))
        side = "home" if recent_team == context.get("home") else "away"
        if str(context.get("kickoff_brasilia", ""))[:10] == "2026-10-21":
            checked_editorial = []
            for url, headline, authoritative_host in (
                CURATED_EDITORIAL_2026_10_21.get(key, {}).get(side, [])
            ):
                candidate = {
                    "url": url, "title": headline,
                    "domain": base.urlparse(url).hostname,
                    "publisher": base.urlparse(url).hostname,
                    "source_type": (
                        "official" if authoritative_host else "major_sports_media"
                    ), "position": 1,
                    # Data editorial deve vir da página, não de horário
                    # artificial atribuído pelo sistema de descoberta.
                    # Somente fontes oficiais do clube proprietário do domínio
                    # podem atribuir ao clube um título sem seu nome literal.
                    "curated_official_team_host": authoritative_host,
                }
                # Data verificada na reportagem original da Goal Brasil,
                # publicada em 20/10 às 06h15 UTC-4. A data qualifica
                # somente o frescor: fatos continuam exigindo corpo lido.
                if url.startswith("https://www.goal.com/br/listas/tecnico-do-rb-leipzig-"):
                    candidate["published_hint"] = "Tue, 20 Oct 2026 06:15:00 -0400"
                checked = _scrape_candidate(
                    candidate, requirement_id=requirement_id,
                    context=context, target_year=_target_year(article_date),
                    checked_at=checked_at, config=config,
                    recent_team=recent_team,
                )
                if checked:
                    checked_editorial.append(checked)
                if len(checked_editorial) >= max_sources:
                    return _dedupe(checked_editorial)
            if checked_editorial:
                return _dedupe(checked_editorial)

    # Consultar primeiro as fontes atuais já localizadas para os quatro jogos
    # de 21/10. O conteúdo continua sujeito à análise factual habitual.
    curated = checked_curated_sources(
        requirement_id, context=context, article_date=article_date,
        checked_at=checked_at, config=config, max_sources=max_sources,
    )
    if curated:
        return _dedupe(curated)[:max_sources]

    cross_stage_lineups: list[dict[str, Any]] = []
    for source_type, domains in _source_stages_for_team(
        requirement_id, context=context, config=config, recent_team=recent_team,
    ):
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for query in queries:
            try:
                _, raw = source_search.request_serper(query=query, domains=domains, config=config)
            except Exception:
                continue
            for candidate in source_search.normalize_serper_response(raw, allowed_domains=domains):
                if requirement_id in source_search.DYNAMIC_RESEARCH_REQUIREMENTS | {EDITORIAL_RESEARCH_ID} and not source_search.candidate_recent_for_article(
                    candidate, article_date,
                    days=7 if requirement_id == EDITORIAL_RESEARCH_ID else 14,
                ):
                    continue
                url = str(candidate.get("url", ""))
                if not url or url in seen:
                    continue
                if not source_search.candidate_matches_match_category(candidate, context):
                    continue
                if not source_search.candidate_matches_team(candidate, str(context.get("home", "")), config):
                    if requirement_id not in {"recent_form_both_teams", EDITORIAL_RESEARCH_ID} or recent_team != context.get("away"):
                        continue
                if requirement_id in {"stadium_and_location", "competition_specific_head_to_head"}:
                    if not source_search.candidate_matches_team(candidate, str(context.get("away", "")), config):
                        continue
                if requirement_id == "recent_form_both_teams" and isinstance(recent_team, str):
                    if not source_search.candidate_matches_team(candidate, recent_team, config):
                        continue
                seen.add(url)
                candidates.append(candidate)

        candidates.sort(key=lambda row: (
            0 if requirement_id == EDITORIAL_RESEARCH_ID and any(
                term in base.normalize_text(str(row.get("title", "")))
                for term in ("trein", "prepar", "lesion", "desfalq", "coach", "tecnic", "classific")
            ) else 1,
            int(row.get("position", 999) or 999),
        ))
        selected: list[dict[str, Any]] = []
        seen_domains: set[str] = set()
        for candidate in candidates[:12]:
            row = deepcopy(candidate)
            row.update(
                {
                    "publisher": str(candidate.get("domain", "")),
                    "source_type": source_type,
                    "dynamic_relevance_required": False,
                    "passo34_9_targeted_search": True,
                    "passo34_9_requirement_id": requirement_id,
                }
            )
            checked = _scrape_candidate(
                row,
                requirement_id=requirement_id,
                context=context,
                target_year=target_year,
                checked_at=checked_at,
                config=config,
                recent_team=recent_team,
            )
            if checked is not None:
                if requirement_id in {EDITORIAL_RESEARCH_ID, "probable_lineups_and_coaches"} and max_sources > 1:
                    domain = str(checked.get("domain") or checked.get("publisher") or "")
                    if domain in seen_domains:
                        continue
                    seen_domains.add(domain)
                selected.append(checked)
                if len(selected) + len(cross_stage_lineups) >= max_sources:
                    return _dedupe([*cross_stage_lineups, *selected])[:max_sources]
        if selected:
            if requirement_id == "probable_lineups_and_coaches":
                cross_stage_lineups.extend(selected)
                # Fontes oficiais raramente oferecem provável XI de ambos os
                # clubes. Complementar com veículos, sem assumir completude.
                continue
            return selected
    return _dedupe(cross_stage_lineups)[:max_sources]


def _select_existing(
    candidates: list[dict[str, Any]],
    *,
    requirement_id: str,
    context: dict[str, Any],
    article_date: str,
    checked_at: str,
    config: dict[str, Any],
    recent_team: str | None = None,
) -> list[dict[str, Any]]:
    target_year = _target_year(article_date)
    selected: list[dict[str, Any]] = []
    for source in candidates[:8]:
        if not isinstance(source, dict):
            continue
        checked = _scrape_candidate(
            source,
            requirement_id=requirement_id,
            context=context,
            target_year=target_year,
            checked_at=checked_at,
            config=config,
            recent_team=recent_team,
        )
        if checked is not None:
            selected.append(checked)
            break
    return selected


def _ensure_allowed_gap_check(
    requirement: dict[str, Any],
    *,
    context: dict[str, Any],
    article_date: str,
    checked_at: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    req = deepcopy(requirement)
    existing = [
        item for item in req.get("source_candidates", [])
        if isinstance(item, dict) and base.eligible_checked_source(item)
    ]
    req_id = str(req.get("id"))
    if req_id == "transmission":
        # Fontes estrangeiras de apostas citam canais espanhóis ou LATAM;
        # o serviço editorial deste site exige emissoras NO BRASIL.
        # Recolher primeiro a página brasileira da partida, verificando
        # o conteúdo real; não converter manchetes ou URLs em prova.
        localized = checked_curated_sources(
            req_id, context=context, article_date=article_date,
            checked_at=checked_at, config=config, max_sources=2,
        )
        if localized:
            req["source_candidates"] = _dedupe(localized)
            req["ready_for_fact_extraction"] = True
            req["passo34_9_localized_transmission_sources"] = len(localized)
            return req
    if existing and req_id != "probable_lineups_and_coaches":
        return req

    # Uma página de "palpite e escalações" pode trazer apenas UM técnico ou
    # um XI incompleto. Antes de gerar uma lacuna obrigatória, consultar
    # outras fontes independentes e combiná-las; não desistir na primeira.
    fresh = _search_and_check(
        req_id,
        context=context,
        article_date=article_date,
        checked_at=checked_at,
        config=config,
        max_sources=3 if req_id == "probable_lineups_and_coaches" else 1,
    )
    combined = _dedupe([*existing, *fresh])
    if req_id == "probable_lineups_and_coaches" and len(fresh) == 1:
        checked = fresh[0]
        lines = (checked.get("page_evidence") or {}).get("evidence_segments") or []
        # A primeira prévia atual que apresenta os DOIS XIs e técnicos não
        # deve ser misturada a projeções antigas e contraditórias. Mantém
        # a fonte original e o validador final de onze nomes por equipe.
        if all(
            any(
                isinstance(line, str)
                and " | Provável escalação:" in line
                and base.mentions_team(line.split(" | ", 1)[0], club)
                for line in lines
            ) and any(
                isinstance(line, str)
                and " | Técnico:" in line
                and base.mentions_team(line.split(" | ", 1)[0], club)
                for line in lines
            )
            for club in (context.get("home"), context.get("away"))
            if isinstance(club, str)
        ):
            combined = [checked]
            req["passo34_9_complete_bilateral_preview_selected"] = True
    # O rastreador anterior marcava "checado" SOMENTE se encontrou fonte.
    # Se a consulta adicional foi executada e a única página candidata
    # falhou ao abrir, o pré-jogo ficava eternamente "pending" apesar da
    # política permitir omitir serviços sem confirmação.
    req["passo34_9_allowed_gap_check"] = True
    req["passo34_9_targeted_search_attempted"] = True
    req["passo34_9_extra_lineup_research_count"] = len(fresh)
    if combined:
        req["source_candidates"] = combined
        req["ready_for_fact_extraction"] = True
    return req


def _select_critical_requirement(
    requirement: dict[str, Any],
    *,
    context: dict[str, Any],
    article_date: str,
    checked_at: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    req = deepcopy(requirement)
    req_id = str(req.get("id"))
    original = [item for item in req.get("source_candidates", []) if isinstance(item, dict)]

    if req_id == "recent_form_both_teams":
        home = context.get("home")
        away = context.get("away")
        selected: list[dict[str, Any]] = []
        for team in (home, away):
            if not isinstance(team, str):
                continue
            rows = _select_existing(
                original,
                requirement_id=req_id,
                context=context,
                article_date=article_date,
                checked_at=checked_at,
                config=config,
                recent_team=team,
            )
            if not rows:
                rows = _search_and_check(
                    req_id,
                    context=context,
                    article_date=article_date,
                    checked_at=checked_at,
                    config=config,
                    recent_team=team,
                )
            selected.extend(rows)
        selected = _dedupe(selected)
        req["source_candidates"] = selected
        req["ready_for_fact_extraction"] = (
            isinstance(home, str)
            and isinstance(away, str)
            and any(item.get("passo34_9_recent_team") == home for item in selected)
            and any(item.get("passo34_9_recent_team") == away for item in selected)
        )
    else:
        selected = _select_existing(
            original,
            requirement_id=req_id,
            context=context,
            article_date=article_date,
            checked_at=checked_at,
            config=config,
        )
        if not selected:
            selected = _search_and_check(
                req_id,
                context=context,
                article_date=article_date,
                checked_at=checked_at,
                config=config,
            )
        req["source_candidates"] = _dedupe(selected)
        req["ready_for_fact_extraction"] = bool(req["source_candidates"])

    req["passo34_9_content_selection"] = True
    req["passo34_9_selected_source_count"] = len(req.get("source_candidates", []))
    req["passo34_9_rejected_previous_source_count"] = max(
        0,
        len(original) - len(req.get("source_candidates", [])),
    )
    return req


def _research_editorial_sources(
    requirements: list[dict[str, Any]], *,
    context: dict[str, Any], article_date: str, checked_at: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Investiga a preparação e a situação de CADA clube separadamente.

    O filtro habitual de dois nomes serve ao serviço do jogo, mas impede
    reportagens individuais legítimas. Só reusa páginas integralmente checadas
    e atuais ou obtém novas notícias por RSS público, sem Serper pago.
    """
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for side in ("home", "away"):
        team = context.get(side)
        if not isinstance(team, str) or not team.strip():
            continue
        # Orçamento gratuito equilibrado: o RSS é limitado por contador
        # global de processo. Sem reiniciar POR CLUBE, buscas de um lado
        # podem consumir a cota antes de pesquisar o segundo, o que provocou
        # repetidos pacotes com contexto só do visitante.
        # Cache continua ativo para não repetir downloads.
        if os.environ.get("CDE_FREE_RESEARCH") == "1":
            from scripts import pesquisa_publica_gratuita as free
            free._RSS_REQUESTS = 0
        # Uma fonte sobre o confronto pode ser útil na pauta de uma equipe,
        # desde que traga notícias esportivas e não apenas horário/TV.
        for requirement in requirements:
            for source in requirement.get("source_candidates", []):
                if not isinstance(source, dict):
                    continue
                url = source.get("url")
                title = str(source.get("title") or "")
                if (
                    not isinstance(url, str) or url in seen
                    or not source_search.candidate_matches_match_category(source, context)
                    or not base.eligible_checked_source(source)
                    or editorial_headline_primary_side(title, context, config) != side
                    or not source_search.candidate_recent_for_article(source, article_date, days=7)
                    or not any(signal in base.normalize_text(
                        " ".join(str(x) for x in
                            ((source.get("page_evidence") or {}).get("evidence_segments") or [])
                        )
                    ) for signal in EDITORIAL_SIGNALS)
                ):
                    continue
                row = deepcopy(source)
                row["editorial_target_side"] = side
                row["editorial_target_team"] = team
                collected.append(row)
                seen.add(url)
                break

        covered = sum(s.get("editorial_target_side") == side for s in collected)
        if covered >= 2:
            continue
        for source in _search_and_check(
            EDITORIAL_RESEARCH_ID,
            context=context, article_date=article_date, checked_at=checked_at,
            config=config, recent_team=team, max_sources=2 - covered,
        ):
            url = source.get("url")
            if isinstance(url, str) and url not in seen:
                seen.add(url)
                collected.append(source)
    return {
        "id": EDITORIAL_RESEARCH_ID,
        "status": "pending",
        "required_for_drafting": False,
        "conditional": False,
        "allow_unavailable_after_check": True,
        "facts": [], "sources": [],
        "source_candidates": collected,
        "ready_for_fact_extraction": bool(collected),
        "editorial_team_coverage": {
            side: sum(row.get("editorial_target_side") == side for row in collected)
            for side in ("home", "away")
        },
    }


def check_article(
    article: dict[str, Any],
    *,
    config: dict[str, Any],
    checked_at: str,
) -> dict[str, Any]:
    result = _PREVIOUS_CHECK_ARTICLE(article, config=config, checked_at=checked_at)
    requirements = result.get("requirements", [])
    if not isinstance(requirements, list):
        requirements = []
    context = result.get("match_context") if isinstance(result.get("match_context"), dict) else {}
    article_date = str(result.get("date", ""))

    updated: list[dict[str, Any]] = []
    selected_total = 0
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        req_id = requirement.get("id")
        if req_id in CRITICAL_REQUIREMENTS:
            req = _select_critical_requirement(
                requirement,
                context=context,
                article_date=article_date,
                checked_at=checked_at,
                config=config,
            )
        elif req_id in ALLOWED_GAP_REQUIREMENTS:
            req = _ensure_allowed_gap_check(
                requirement,
                context=context,
                article_date=article_date,
                checked_at=checked_at,
                config=config,
            )
        else:
            req = deepcopy(requirement)
        selected_total += int(req.get("passo34_9_selected_source_count", 0))
        updated.append(req)

    # Reinicia a cota grátis de RSS POR PARTIDA. Pesquisas exploratórias do
    # jogo anterior não devem consumir a investigação dos dois clubes.
    if os.environ.get("CDE_FREE_RESEARCH") == "1":
        from scripts import pesquisa_publica_gratuita as free
        free._RSS_REQUESTS = 0
    updated.append(_research_editorial_sources(
        updated, context=context, article_date=article_date,
        checked_at=checked_at, config=config,
    ))

    checked_sources: set[str] = set()
    eligible_sources: set[str] = set()
    blocking: list[str] = []
    for requirement in updated:
        req_id = requirement.get("id")
        for source in requirement.get("source_candidates", []):
            if not isinstance(source, dict):
                continue
            url = source.get("url")
            if isinstance(url, str) and source.get("content_checked") is True:
                checked_sources.add(url)
            if isinstance(url, str) and source.get("eligible_for_factual_validation") is True:
                eligible_sources.add(url)
        if requirement.get("required_for_drafting") is True and not requirement.get("ready_for_fact_extraction"):
            if isinstance(req_id, str):
                blocking.append(req_id)

    result["requirements"] = updated
    result["page_checked_source_count"] = len(checked_sources)
    result["eligible_source_count"] = len(eligible_sources)
    result["page_check_blocking_requirement_ids"] = blocking
    result["passo34_9_selected_critical_source_count"] = selected_total
    result["passo34_9_applied"] = True

    slug = result.get("slug", "sem-slug")
    print(
        f"PASSO 34.9 — {slug}: fontes críticas selecionadas por conteúdo={selected_total}; "
        f"bloqueios após seleção={','.join(blocking) if blocking else 'nenhum'}"
    )
    return result


base.check_article = check_article


def main() -> None:
    base.main()


if __name__ == "__main__":
    main()
