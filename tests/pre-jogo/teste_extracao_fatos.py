#!/usr/bin/env python3
"""Teste determinístico do Passo 22 sem internet."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import extrair_fatos_estruturados as extractor  # noqa: E402
from scripts import preparar_pesquisa_factual as research  # noqa: E402
from scripts import validar_politica_editorial as editorial_policy  # noqa: E402

OUTPUT = ROOT / "build" / "pre-jogo" / "teste-extracao-fatos.json"


def source(url: str, publisher: str, segment: str) -> dict:
    return {
        "publisher": publisher,
        "url": url,
        "source_type": "official",
        "domain": url.split("/")[2],
        "title": "Arsenal v Manchester City - Premier League",
        "checked_at": "2026-09-16T12:00:00-03:00",
        "content_checked": True,
        "verification_status": "page_checked_pending_fact_extraction",
        "eligible_for_factual_validation": True,
        "page_evidence": {
            "metadata": {"title": "Arsenal v Manchester City - Premier League"},
            "evidence_segments": [segment],
            "segment_count": 1,
            "content_length": len(segment),
            "content_sha256": "simulado",
            "credits_used": 1,
        },
    }


def main() -> None:
    config = extractor.load_config()
    base = research.build_requirement("stadium_and_location", config=config)
    match_context = {
        "home": "Arsenal",
        "away": "Manchester City",
        "competition": "Premier League",
    }

    agreeing = dict(base)
    agreeing["source_candidates"] = [
        source(
            "https://www.arsenal.com/example-match",
            "Arsenal",
            "Arsenal host Manchester City in the Premier League, with the match played at Emirates Stadium.",
        ),
        source(
            "https://www.premierleague.com/example-match",
            "Premier League",
            "Arsenal v Manchester City will be played at Emirates Stadium in this Premier League fixture.",
        ),
    ]
    accepted = extractor.extract_requirement(
        agreeing,
        match_context=match_context,
        config=config,
    )
    assert accepted["validator_accepted"] is True
    assert accepted["status"] == "verified"
    assert accepted["structured_fact_count"] == 1
    assert accepted["facts"][0]["field"] == "stadium"
    assert "Emirates Stadium" in accepted["facts"][0]["text"]
    assert accepted["conflict_detected"] is False

    conflicting = dict(base)
    conflicting["source_candidates"] = [
        source(
            "https://www.arsenal.com/example-match",
            "Arsenal",
            "Arsenal host Manchester City in the Premier League, with the match played at Emirates Stadium.",
        ),
        source(
            "https://www.premierleague.com/example-match",
            "Premier League",
            "Arsenal v Manchester City will be played at Etihad Stadium in this Premier League fixture.",
        ),
    ]
    blocked = extractor.extract_requirement(
        conflicting,
        match_context=match_context,
        config=config,
    )
    assert blocked["validator_accepted"] is False
    assert blocked["status"] == "pending"
    assert blocked["conflict_detected"] is True
    assert blocked["fact_extraction_status"] == "conflict_blocked"
    assert not blocked["facts"]

    direct_body = (
        "<p><strong>Onde será o jogo</strong></p>"
        "<p>A partida será disputada no Emirates Stadium.</p>"
        "<p>A transmissão terá definição no serviço oficial da competição.</p>"
    )
    forbidden_body = (
        "<p><strong>Onde será o jogo</strong></p>"
        "<p>Segundo o site do Arsenal, a partida será disputada no Emirates Stadium.</p>"
    )
    assert editorial_policy.validate_body_policy(direct_body, config) == []
    forbidden_errors = editorial_policy.validate_body_policy(forbidden_body, config)
    assert forbidden_errors

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "step": 22,
        "agreement_case": {
            "validator_accepted": accepted["validator_accepted"],
            "status": accepted["status"],
            "facts": accepted["facts"],
            "source_count": len(accepted["sources"]),
        },
        "conflict_case": {
            "validator_accepted": blocked["validator_accepted"],
            "status": blocked["status"],
            "conflict_detected": blocked["conflict_detected"],
            "conflicts": blocked["conflicts"],
        },
        "editorial_source_policy": {
            "direct_fact_allowed": True,
            "source_attribution_rejected": True,
            "forbidden_example_error_count": len(forbidden_errors),
        },
        "ready_for_drafting": False,
        "ready_for_html": False,
        "publication_unlocked": False,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("OK: extração estruturada, conflito e política editorial validados.")
    print("Caso concordante: fato de estádio aceito pelo validador factual.")
    print("Caso conflitante: promoção bloqueada.")
    print("Atribuição de fonte no corpo: bloqueada.")
    print("Redação, HTML e publicação permanecem bloqueados.")


if __name__ == "__main__":
    main()
