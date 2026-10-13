#!/usr/bin/env python3
"""Não usar matérias históricas como fatos atuais de elenco ou classificação."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.extrair_fatos_estruturados import source_current_for_match


def row(date: str, title: str, url: str = "https://exemplo.com/jogo") -> dict:
    return {
        "url": url, "title": title, "published_hint": date,
        "source_type": "major_sports_media",
        "page_evidence": {
            "metadata": {"og:title": title},
            "evidence_segments": ["Manchester City e PSG na Champions League 2026: Enzo Maresca analisa a rodada."],
        },
    }


def main() -> None:
    champions = {
        "kickoff_brasilia": "2026-10-14T16:00:00-03:00",
        "competition_slug": "champions-league",
    }
    title = "Manchester City x PSG na Champions League"
    assert not source_current_for_match(row("Mon, 03 May 2021 12:01:00 GMT", title), champions)
    assert not source_current_for_match(row("Mon, 23 Feb 2026 16:33:00 GMT", title), champions)
    assert not source_current_for_match(row("Fri, 14 Aug 2026 15:19:00 GMT", title), champions)
    assert not source_current_for_match(row("Mon, 21 Sep 2026 16:25:00 GMT", title), champions)
    assert source_current_for_match(row("Mon, 12 Oct 2026 23:54:00 GMT", title), champions)
    assert not source_current_for_match(row("Mon, 23 Nov 2026 15:19:00 GMT", title), champions)
    assert not source_current_for_match(row("ontem", title), champions)

    # Fontes do Brasileiro não podem fundamentar "situação de Libertadores".
    libertadores = {
        "kickoff_brasilia": "2026-10-14T21:30:00-03:00",
        "competition_slug": "libertadores",
    }
    recent = "Mon, 12 Oct 2026 12:37:00 GMT"
    assert not source_current_for_match(
        row(recent, "Fluminense x Palmeiras pelo Campeonato Brasileiro"), libertadores)
    assert source_current_for_match(
        row(recent, "Fluminense x Palmeiras na semifinal da Libertadores"), libertadores)

    # Sem data do feed, uma data antiga em qualquer ano não comprova atualidade.
    undated = row("", title)
    undated["page_evidence"]["evidence_segments"] = [
        "Manchester City x PSG, nesta terça-feira (4), vaga na final de 2021."
    ]
    assert not source_current_for_match(undated, champions)
    print("OK: rejeitados 2021, fevereiro/agosto/setembro, competições distintas e páginas sem data atual.")


if __name__ == "__main__":
    main()
