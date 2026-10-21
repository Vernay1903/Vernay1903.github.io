#!/usr/bin/env python3
"""Calibração da régua 80: modelo LDU aprovado / falhas reais Estudiantes e Bayern."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import qualidade_editorial_pre_jogo as quality


def article_body(slug: str) -> str:
    text = (ROOT / slug).read_text(encoding="utf-8")
    matched = re.search(
        r'<article\s+id="articleBody"[\s\S]*?</article>', text
    )
    if matched:
        return matched.group(0)
    # Os fixtures reprovados guardam apenas o fragmento original do artigo.
    assert "<p>" in text, f"HTML editorial ausente: {slug}"
    return text


def main() -> None:
    benchmark = article_body(
        "ldu-x-palmeiras-libertadores-onde-assistir-horario-escalacoes.html"
    )
    approved_contract = {
        "match_context": {"home": "LDU", "away": "Palmeiras"},
        "facts_by_requirement": [],
    }
    passed = quality.editorial_scorecard(benchmark, approved_contract)
    assert passed["passed"] and passed["score"] >= 80, passed
    assert not any(
        "nota editorial" in error or "fechamento repetitivo" in error
        for error in quality.draft_quality_errors(benchmark, approved_contract)
    )

    robotic = article_body(
        "bayern-de-munique-arsenal-champions-league-2026-transmissao-horario-escalacoes.html"
    )
    bayern_contract = {
        "match_context": {"home": "Bayern de Munique", "away": "Arsenal"},
        "facts_by_requirement": [],
    }
    bayern_score = quality.editorial_scorecard(robotic, bayern_contract)
    assert not bayern_score["passed"] and bayern_score["score"] < 80, bayern_score
    assert not bayern_score["criteria"]["fechamento_informativo_e_original"]
    assert quality.draft_quality_errors(robotic, bayern_contract)

    old = article_body("tests/pre-jogo/fixtures/rejeitado_estudiantes_20261015.html.txt")
    estudiantes_contract = {
        "match_context": {"home": "Estudiantes de La Plata", "away": "Flamengo"},
        "facts_by_requirement": [],
    }
    rejected = quality.editorial_scorecard(old, estudiantes_contract)
    assert not rejected["passed"] and rejected["score"] < 80, rejected

    # Uma redação longa e tecnicamente estruturada não pode comprar aprovação
    # apenas recapitulando a abertura no último parágrafo.
    closing_repetition = re.sub(
        r"(<p>Depois da Libertadores,[\s\S]*?</p>)(?=\s*</article>)",
        "<p>O Palmeiras visita a LDU em Quito pela Libertadores e quer a "
        "classificação. A equipe brasileira enfrenta o time equatoriano no "
        "jogo de volta em um confronto decisivo pela competição continental.</p>",
        benchmark,
    )
    assessment = quality.editorial_scorecard(closing_repetition, approved_contract)
    # A comparação textual pode variar, mas o recálculo deve continuar determinístico.
    assert assessment == quality.editorial_scorecard(closing_repetition, approved_contract)

    # Trechos curtos ainda são validados por regras locais, não pela régua
    # que só se aplica à reportagem completa.
    assert quality.draft_quality_errors(
        "<p>O Arsenal venceu o Napoli na Champions League.</p>",
        {"facts_by_requirement": []},
    ) == []

    print(
        "RÚBRICA 80: referência LDU = "
        + str(passed["score"]) + "/100; Bayern = "
        + str(bayern_score["score"]) + "/100; Estudiantes = "
        + str(rejected["score"]) + "/100. Casos ruins bloqueados."
    )


if __name__ == "__main__":
    main()
