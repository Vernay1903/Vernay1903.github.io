#!/usr/bin/env python3
"""Teste imutável: proíbe a aprovação da matéria automática reprovada em 15/10."""
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import qualidade_editorial_pre_jogo as quality


def entry(field, text):
    return {"field": field, "text": text}


def main():
    # Os seguintes fatos vieram do contrato REAL da publicação de 15/10.
    # Arquibancadas não explicam o desempenho ou a preparação esportiva.
    bad = {"facts_by_requirement": [
        {"id": "editorial_match_stakes", "status": "verified", "facts": [
            entry("home_stakes_1", "Situação competitiva verificada do Estudiantes de La Plata: Por: Letícia Gerheim / Licenciado de Gávea News O Estudiantes pode mudar a distribuição das arquibancadas do Estádio Jorge Luis Hirschi para o jogo contra o Flamengo, pela semifinal da Libertadores"),
            entry("home_stakes_2", "Situação competitiva verificada do Estudiantes de La Plata: O confronto entre Estudiantes e Flamengo acontece nesta quinta-feira (15), às 21h30, em La Plata, pelo jogo de ida da semifinal da Libertadores"),
        ]},
        {"id":"editorial_preparation_news","status":"verified","facts":[
            entry("away_team_news_1", "Bruno Henrique e Emerson Royal tendem a retornar ao Flamengo, enquanto Jorginho cumpre suspensão por expulsão nas quartas de final."),
        ]},
        {"id":"stakes_and_qualification_scenarios_when_applicable","status":"verified","facts":[
            entry("qualification_scenario", "Estudiantes de La Plata e Flamengo disputam o jogo de ida da semifinal da Libertadores."),
        ]},
    ]}
    assert not quality.meaningful_sporting_context(bad["facts_by_requirement"][0]["facts"][0]["text"])
    assert not quality.meaningful_sporting_context(bad["facts_by_requirement"][0]["facts"][1]["text"])
    assert quality.source_depth_errors(bad), "O mesmo contrato fraco não pode ser aprovado novamente."
    fixture = ROOT/"tests/pre-jogo/fixtures/rejeitado_estudiantes_20261015.html.txt"
    rejected = fixture.read_text(encoding="utf-8")
    assert quality.draft_quality_errors(rejected, bad), (
        "O texto que o editor avaliou como ruim precisa ser reprovado em vez de publicado."
    )
    # Regressão das duas matérias automáticas de 21/10: não permitir
    # contagem zero nem texto "jogos registrados" no corpo publicável.
    robotic = (
        "<p>Nos últimos 2 jogos registrados nessa competição, "
        "1 vitória, 1 empate e 0 derrotas.</p>"
    )
    assert "linguagem de preenchimento ou metadados de cobertura no texto" in (
        quality.draft_quality_errors(robotic, {"facts_by_requirement": []})
    )
    assert any(re.search(
        expression, quality.fold("<p>Situação competitiva verificada do Arsenal</p>")
    ) for expression in quality.ARTIFICIAL)

    # Regressoes efetivamente observadas na matéria Bayern x Arsenal de 21/10.
    for frase in (
        "<p>O balanço recente é de duas vitórias, nenhum empate e nenhuma derrota.</p>",
        "<p>O retrospecto considerado reúne três encontros pela competição.</p>",
        "<p>A referência à história da Champions League ajuda a dimensionar a competição.</p>",
    ):
        assert "linguagem de preenchimento ou metadados de cobertura no texto" in (
            quality.draft_quality_errors(frase, {"facts_by_requirement": []})
        ), frase
    contexto = {"match_context": {"home": "Bayern de Munique", "away": "Arsenal"}}
    base = [
        "<p>O Bayern soma quatro pontos depois de dois jogos da fase de liga, "
        "com a equipe alemã agora voltada ao próximo adversário.</p>",
        "<p>Para o Bayern de Munique, quatro pontos em dois compromissos "
        "antecedem o jogo da terceira rodada da competição europeia.</p>",
        "<p>O Bayern chega com quatro pontos, enquanto os demais clubes "
        "se preparam para a rodada da Champions League.</p>",
        "<p>O Bayern encerra o retrospecto com quatro pontos na competição, "
        "depois de resultados que foram apresentados no começo da matéria.</p>",
    ]
    assert quality.repeated_team_points_errors("".join(base), contexto), (
        "A mesma pontuação repetida quatro vezes precisa ser reprovada."
    )
    assert not quality.repeated_team_points_errors("".join(base[:2]), contexto), (
        "Uma ou duas referências justificadas não podem bloquear a reportagem."
    )
    natural = "<p>O Arsenal venceu Napoli e Lille nas duas primeiras rodadas da Champions.</p>"
    assert quality.draft_quality_errors(natural, {"facts_by_requirement": []}) == [], natural

    approved = (ROOT/"ldu-x-palmeiras-libertadores-onde-assistir-horario-escalacoes.html").read_text(encoding="utf-8")
    reference = re.search(r'<article id="articleBody"[\s\S]*?</article>', approved)
    assert reference, "Modelo LDU x Palmeiras não encontrado."
    assert quality.draft_quality_errors(reference.group(0), {"facts_by_requirement": []}) == [], (
        "Nova trava não pode punir o modelo editorial aprovado."
    )
    print("OK: contrato/rascunho real de 15/10 reprovados; referência LDU aprovada preservada.")


if __name__=="__main__":
    main()
