#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import ler_fontes_candidatas_passo34_9 as reader


def src(title: str, *, published: str | None = None) -> dict:
    return {
        "title": title,
        "url": "https://fcbayern.com/test-2026",
        "published_hint": published,
        "source_type": "official",
    }


def main() -> None:
    assert callable(reader.step34_7._scrape_once)
    assert callable(reader.step34_8._allowed_stage_domains)
    assert reader._PREVIOUS_CHECK_ARTICLE is reader.step34_8.check_article

    context = {
        "home": "FC Bayern München",
        "away": "1. FC Union Berlin",
        "competition": "Bundesliga",
        "competition_slug": "bundesliga",
    }

    stadium_text = (
        "FC Bayern München empfängt 1. FC Union Berlin am 18. September 2026.\n"
        "Das Bundesliga-Spiel findet in der Allianz Arena statt."
    )
    assert reader.stadium_content_support(
        stadium_text,
        src("FC Bayern München vs 1. FC Union Berlin | Bundesliga 2026/27"),
        context,
        target_year="2026",
    ) is True

    old_stadium = (
        "FC Bayern München empfängt 1. FC Union Berlin im Jahr 2024.\n"
        "Das Bundesliga-Spiel findet in der Allianz Arena statt."
    )
    assert reader.stadium_content_support(
        old_stadium,
        src("Bayern gegen Union 2024", published="2024-03-01"),
        context,
        target_year="2026",
    ) is False

    current_union = (
        "1. FC Union Berlin spielt in der Bundesliga-Saison 2026/27.\n"
        "Zuletzt gewann Union Berlin am 3. Spieltag mit 2:1."
    )
    assert reader.recent_form_content_support(
        current_union,
        src("Union Berlin: letzter Bundesliga-Sieg 2026/27"),
        "1. FC Union Berlin",
        context,
        target_year="2026",
    ) is True

    stale_side_match = (
        "Borussia Dortmund besiegte 1. FC Union Berlin am 10. Februar 2024 mit 2:0.\n"
        "Bundesliga Matchday report."
    )
    assert reader.recent_form_content_support(
        stale_side_match,
        src("Dortmund vs Union Berlin 2024", published="2024-02-10"),
        "1. FC Union Berlin",
        context,
        target_year="2026",
    ) is False

    aggregate = (
        "FC Bayern München und 1. FC Union Berlin treffen in der Bundesliga 2026/27 aufeinander.\n"
        "In 14 Bundesliga-Spielen gab es 9 Siege für Bayern und 5 Unentschieden; Bayern ist ungeschlagen."
    )
    assert reader.h2h_content_support(
        aggregate,
        src("Bayern vs Union: Bundesliga-Bilanz 2026"),
        context,
        target_year="2026",
    ) is True

    isolated = (
        "FC Bayern München gewann 2026 in der Bundesliga 4:0 gegen 1. FC Union Berlin. "
        "Previous meeting."
    )
    assert reader.h2h_content_support(
        isolated,
        src("Bayern 4-0 Union | Bundesliga 2026"),
        context,
        target_year="2026",
    ) is False

    stadium_segments = reader._segments_for_stadium(
        stadium_text,
        max_segments=10,
        max_chars=700,
    )
    assert stadium_segments
    assert any("Allianz Arena" in item for item in stadium_segments)

    h2h_segments = reader._segments_for_h2h(
        aggregate,
        max_segments=10,
        max_chars=700,
    )
    assert h2h_segments
    assert any("14" in item and "9" in item and "5" in item for item in h2h_segments)

    print("OK: Passo 34.9 rejeita fonte antiga/lateral e só seleciona conteúdo crítico suportado.")


if __name__ == "__main__":
    main()
