#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import extrair_fatos_openai as grounded_extractor
from scripts import ler_fontes_candidatas_passo34_8 as reader


def source(segment: str) -> dict:
    return {
        "publisher": "FC Bayern",
        "url": "https://fcbayern.com/example",
        "source_type": "official",
        "checked_at": "2026-09-17T20:00:00-03:00",
        "content_checked": True,
        "eligible_for_factual_validation": True,
        "title": "FC Bayern München - 1. FC Union Berlin | Bundesliga",
        "page_evidence": {
            "metadata": {},
            "evidence_segments": [segment],
            "segment_count": 1,
        },
    }


def main() -> None:
    context = {
        "home": "FC Bayern München",
        "away": "1. FC Union Berlin",
        "competition": "Bundesliga",
        "competition_slug": "bundesliga",
    }

    stadium = source(
        "FC Bayern München empfängt 1. FC Union Berlin in der Allianz Arena "
        "am 4. Spieltag der Bundesliga."
    )
    assert reader.stadium_source_has_explicit_venue(stadium, context) is True

    aggregate = source(
        "In 14 Bundesliga-Spielen zwischen FC Bayern München und 1. FC Union Berlin "
        "gab es 9 Siege für Bayern und 5 Unentschieden; Bayern ist gegen Union ungeschlagen."
    )
    assert reader.h2h_source_has_aggregate_signals(aggregate, context) is True

    isolated = source(
        "Watch: FC Bayern München 4-0 1. FC Union Berlin - previous meeting in the Bundesliga."
    )
    assert reader.h2h_source_has_aggregate_signals(isolated, context) is False

    wrong_match = source(
        "Bayer Leverkusen gegen 1. FC Union Berlin in der Allianz Arena."
    )
    assert reader.stadium_source_has_explicit_venue(wrong_match, context) is False

    print("OK: Passo 34.8 mantém busca dirigida com suporte explícito de estádio e H2H agregado.")


if __name__ == "__main__":
    main()
