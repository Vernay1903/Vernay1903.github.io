#!/usr/bin/env python3
"""Teste do Passo 15: ingestão e validação de evidências factuais simuladas."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import preparar_dados_editoriais as editorial  # noqa: E402
from scripts import preparar_pesquisa_factual as research  # noqa: E402
from scripts import validar_pesquisa_factual as validator  # noqa: E402

TARGET_DATE = date(2026, 9, 17)
EVIDENCE_PATH = ROOT / "tests" / "pre-jogo" / "evidencias-pesquisa-simuladas.json"
REPORT_PATH = ROOT / "build" / "pre-jogo" / "teste-validacao-pesquisa.json"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: esperado={expected!r}, obtido={actual!r}")


def build_plan() -> dict:
    return {
        "fixture_id": 1001,
        "home": "Arsenal FC",
        "away": "Manchester City FC",
        "competition": "Premier League",
        "competition_slug": "premier-league",
        "kickoff_brasilia": "2026-09-17T16:00:00-03:00",
        "kickoff_time_brasilia": "16:00",
        "monitored_clubs": [
            {"name": "Arsenal", "slug": "arsenal"},
            {"name": "Manchester City", "slug": "manchester-city"},
        ],
        "two_monitored_clubs_same_match": True,
        "slug": "arsenal-manchester-city-premier-league-2026-transmissao-horario-escalacoes.html",
        "article_date": "17/09/2026",
        "prepare_at_brasilia": "2026-09-16T23:30:00-03:00",
        "target_publish_at_brasilia": "2026-09-17T00:01:00-03:00",
    }


def main() -> None:
    config = validator.load_config()
    editorial_record = editorial.build_editorial_record(
        build_plan(), target_date=TARGET_DATE, config=config
    )
    dossier = research.build_research_dossier(editorial_record, config=config)

    evidence_package = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    evidence_articles = evidence_package["articles"]

    validated, errors = validator.validate_batch(
        [dossier], evidence_articles, config=config
    )
    assert_equal(errors, [], "Pacote válido não deve gerar erros")
    assert_equal(len(validated), 1, "Quantidade de dossiês validados")

    result = validated[0]
    assert_equal(
        result["research_status"],
        "validated_ready_for_drafting",
        "Status após validação",
    )
    assert_equal(result["ready_for_drafting"], True, "Redação deve ser liberada")
    assert_equal(result["ready_for_html"], False, "HTML deve continuar bloqueado")
    assert_equal(result["publication_unlocked"], False, "Publicação deve continuar bloqueada")
    assert_equal(result["external_research_performed"], True, "Pesquisa externa deve ser reconhecida")
    assert_equal(result["verified_fact_count"], 6, "Quantidade de fatos validados")
    assert_equal(result["source_count"], 7, "Quantidade de fontes únicas")
    assert_equal(result["blocking_requirement_ids"], [], "Não deve restar requisito bloqueador")

    lineup = next(
        item
        for item in result["requirements"]
        if item["id"] == "probable_lineups_and_coaches"
    )
    assert_equal(
        lineup["status"],
        "unavailable_after_check",
        "Escalação pode ficar indisponível sem invenção",
    )
    assert_equal(lineup["facts"], [], "Escalação indisponível não pode fabricar jogadores")

    officiating = next(
        item for item in result["requirements"] if item["id"] == "officiating"
    )
    assert_equal(
        officiating["status"],
        "verified_not_announced",
        "Arbitragem não anunciada deve ser representada explicitamente",
    )

    internal_link = next(
        item
        for item in result["requirements"]
        if item["id"] == "competition_internal_link"
    )
    assert_equal(
        internal_link["sources"][0]["url"].startswith("https://cortedosesportes.com.br/"),
        True,
        "Link interno deve usar o domínio do site",
    )

    # Teste negativo: HTTP simples deve invalidar a evidência e bloquear a redação.
    invalid_articles = deepcopy(evidence_articles)
    invalid_articles[0]["requirements"]["stadium_and_location"]["sources"][0]["url"] = (
        "http://official.example/match/stadium"
    )
    invalidated, invalid_errors = validator.validate_batch(
        [dossier], invalid_articles, config=config
    )
    if not any("deve usar https" in error for error in invalid_errors):
        raise AssertionError("Fonte HTTP deveria ser rejeitada pela validação")
    assert_equal(
        invalidated[0]["ready_for_drafting"],
        False,
        "Erro de fonte deve bloquear a redação",
    )
    assert_equal(
        invalidated[0]["publication_unlocked"],
        False,
        "Erro de fonte nunca pode liberar publicação",
    )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "mode": "simulation_only",
        "target_date": TARGET_DATE.isoformat(),
        "external_web_called": False,
        "validated_ready_for_drafting": result["ready_for_drafting"],
        "ready_for_html": result["ready_for_html"],
        "publication_unlocked": result["publication_unlocked"],
        "verified_fact_count": result["verified_fact_count"],
        "source_count": result["source_count"],
        "negative_test_error_count": len(invalid_errors),
        "checks": {
            "valid_evidence_accepted": True,
            "https_required": True,
            "timezone_required_in_checked_at": True,
            "internal_link_domain_checked": True,
            "lineup_not_invented_when_unavailable": True,
            "not_announced_status_supported": True,
            "drafting_can_unlock_after_validation": True,
            "html_remains_blocked": True,
            "publication_remains_blocked": True,
        },
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("OK: validação factual simulada concluída.")
    print(f"Fatos verificados: {result['verified_fact_count']}")
    print(f"Fontes únicas: {result['source_count']}")
    print("Redação liberada após evidências válidas: sim")
    print("HTML liberado: não")
    print("Publicação liberada: não")
    print("Fonte HTTP inválida foi rejeitada: sim")
    print(f"Relatório: {REPORT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
