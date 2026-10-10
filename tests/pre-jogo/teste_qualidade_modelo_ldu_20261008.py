#!/usr/bin/env python3
"""Benchmark editorial: referência aprovada passa, textos reais ruins são reprovados."""
from __future__ import annotations
import re
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import qualidade_editorial_pre_jogo as quality

def body(slug):
    page = (ROOT / slug).read_text(encoding="utf-8")
    article = re.search(r'<article id="articleBody"[\s\S]*?</article>', page)
    assert article, f"HTML sem articleBody: {slug}"
    return article.group(0)

def mk(fields):
    return {"facts_by_requirement": [{"id": "context", "status": "verified",
                                      "facts": [{"field": f, "text": text} for f, text in fields.items()]}]}

def main():
    shallow = mk({"home_recent_form": "O time ganhou três jogos.",
                  "away_recent_form": "O rival ganhou dois jogos.",
                  "competition_h2h": "Dois encontros.",
                  "transmission": "TV Globo."})
    assert quality.source_depth_errors(shallow), "placares e serviço não bastam"
    full = mk({
        **{k: v for k, v in quality.facts(shallow).items()},
        "home_team_news_1": "O Palmeiras terá o retorno do meio-campista após suspensão e mexe no setor central da equipe.",
        "away_team_news_1": "O Bahia tem um retorno importante no ataque após o jogador cumprir suspensão no confronto anterior.",
    })
    assert quality.source_depth_errors(full) == [], "dois fatos concretos sustentam a pesquisa"
    reference = body("ldu-x-palmeiras-libertadores-onde-assistir-horario-escalacoes.html")
    assert quality.draft_quality_errors(reference, {"facts_by_requirement": []}) == [], "modelo aprovado não pode ser reprovado"
    bad_santos = body("santos-fc-flamengo-brasileirao-2026-transmissao-horario-escalacoes.html")
    assert quality.draft_quality_errors(bad_santos, shallow), "prévia fragmentada passou"
    # O HTML publicado pelo editor pode ter sido revisado desde 08/10.
    # O teste de repeticao deve usar um caso imutavel, nao reprovar uma materia
    # atualizada por ela manter o mesmo slug.
    repetitive = (
        "O time da casa chega ao confronto para defender sua campanha no campeonato "
        "e pretende manter a regularidade diante da torcida, enquanto o adversario "
        "busca melhorar sua posicao na tabela depois dos ultimos resultados. "
        "O duelo exige atencao nos setores de defesa e meio campo, mas a equipe "
        "ainda trabalha para definir suas principais alternativas de ataque."
    )
    bad_palmeiras = f"<p>{repetitive}</p><p>{repetitive}</p>"
    assert quality.draft_quality_errors(bad_palmeiras, shallow), "texto com paragrafo duplicado passou"
    assert "saiba mais" not in quality.fold(reference)
    print("OK: modelo LDU aprovado; previa fragmentada e repeticao sintetica bloqueadas; profundidade obrigatoria.")

if __name__ == "__main__":
    main()
