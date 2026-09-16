#!/usr/bin/env python3
"""Teste determinístico da leitura de fontes do Passo 21 sem chamada externa."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import estruturar_evidencias_candidatas as evidence  # noqa: E402
from scripts import ler_fontes_candidatas as reader  # noqa: E402
from scripts import preparar_pesquisa_factual as research  # noqa: E402

REPORT_PATH = ROOT / "build" / "pre-jogo" / "teste-leitura-fontes.json"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: esperado={expected!r}, obtido={actual!r}")


def main() -> None:
    config = reader.load_config()
    policy = config["editorial"]["source_attribution_policy"]
    assert_equal(policy["research_sources_are_internal_only"], True, "Fontes devem ser internas")
    assert_equal(policy["forbid_source_names_in_article_body"], True, "Nomes de fontes no corpo")
    assert_equal(policy["forbid_research_process_mentions"], True, "Menções à pesquisa")
    assert_equal(policy["write_verified_facts_directly"], True, "Fatos devem ser escritos diretamente")

    base_requirement = research.build_requirement("stadium_and_location", config=config)
    discovery_task = {
        "requirement_id": "stadium_and_location",
        "selected_source_type": "official",
        "dynamic_relevance_required": False,
        "candidates": [
            {
                "title": "Match preview Arsenal v Manchester City",
                "url": "https://www.arsenal.com/example-preview",
                "domain": "arsenal.com",
                "snippet": "Emirates Stadium hosts the Premier League match.",
                "position": 1,
                "published_hint": "Sep 17, 2026",
            }
        ],
    }
    structured = evidence.structure_requirement_from_discovery(
        base_requirement,
        discovery_task,
        discovered_at="2026-09-16T23:30:00-03:00",
        config=config,
    )

    raw_scrape = {
        "markdown": """
# Arsenal v Manchester City

The Premier League match will be played at Emirates Stadium in London.

Kick-off is scheduled for the evening and supporters are advised to arrive early.

Team news will be published closer to kick-off.
""",
        "metadata": {
            "title": "Arsenal v Manchester City | Match preview",
            "description": "Match preview for Arsenal v Manchester City at Emirates Stadium.",
            "language": "en",
        },
        "credits": 2,
    }

    candidate = structured["source_candidates"][0]
    checked = reader.apply_scrape_to_candidate(
        candidate,
        raw_scrape,
        requirement_id="stadium_and_location",
        checked_at="2026-09-16T23:40:00-03:00",
        config=config,
    )

    assert_equal(checked["content_checked"], True, "Conteúdo deve ser marcado como checado")
    assert_equal(
        checked["verification_status"],
        "page_checked_pending_fact_extraction",
        "Status após leitura",
    )
    assert_equal(
        checked["eligible_for_factual_validation"],
        True,
        "Fonte oficial lida deve ficar elegível para extração factual",
    )
    if not checked["page_evidence"]["evidence_segments"]:
        raise AssertionError("Leitura deve produzir segmentos de evidência.")
    if not any("Emirates Stadium" in item for item in checked["page_evidence"]["evidence_segments"]):
        raise AssertionError("Segmento relevante sobre o estádio não foi preservado.")

    local_candidate = deepcopy(candidate)
    local_candidate["source_type"] = "relevant_local_press"
    local_candidate["dynamic_relevance_required"] = True
    local_candidate["local_relevance_verified"] = False
    checked_local = reader.apply_scrape_to_candidate(
        local_candidate,
        raw_scrape,
        requirement_id="stadium_and_location",
        checked_at="2026-09-16T23:40:00-03:00",
        config=config,
    )
    assert_equal(
        checked_local["eligible_for_factual_validation"],
        False,
        "Imprensa local sem relevância validada não pode avançar",
    )

    checked_requirement = deepcopy(structured)
    checked_requirement["source_candidates"] = [checked]
    checked_requirement["page_check_attempt_count"] = 1
    checked_requirement["page_check_success_count"] = 1
    checked_requirement["ready_for_fact_extraction"] = True
    assert_equal(checked_requirement["facts"], [], "Leitura não pode criar fatos")
    assert_equal(checked_requirement["sources"], [], "Leitura não pode promover fonte a validada")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "step": 21,
        "mode": "simulation_only",
        "page_reader": config["research"]["page_reader"]["name"],
        "content_checked": checked["content_checked"],
        "segment_count": checked["page_evidence"]["segment_count"],
        "eligible_for_fact_extraction": checked["eligible_for_factual_validation"],
        "facts_created": 0,
        "validated_sources_created": 0,
        "local_source_without_relevance_blocked": True,
        "article_source_attribution_forbidden": True,
        "ready_for_drafting": False,
        "ready_for_html": False,
        "publication_unlocked": False,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("OK: leitura de fontes validada sem chamada externa.")
    print(f"Segmentos de evidência: {report['segment_count']}")
    print("Nenhum fato foi criado automaticamente.")
    print("Fontes de pesquisa permanecem internas e não podem ser citadas na matéria.")
    print("Redação, HTML e publicação continuam bloqueados.")


if __name__ == "__main__":
    main()
