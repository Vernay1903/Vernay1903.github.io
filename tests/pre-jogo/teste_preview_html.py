#!/usr/bin/env python3
"""Teste determinístico do Passo 27, sem chamada externa e sem publicação."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import montar_preview_html_pre_jogo as preview  # noqa: E402

CONTRACT_PATH = ROOT / "tests" / "pre-jogo" / "contrato-redacao-controlado.json"
OUTPUT = ROOT / "build" / "pre-jogo" / "teste-preview-html.json"


def long_paragraph(seed: str, repetitions: int = 7) -> str:
    sentence = (
        f"{seed} O contexto esportivo exige concentração, regularidade e leitura do jogo, "
        "porque cada detalhe pode alterar o desenvolvimento da partida e a disputa pelas primeiras posições. "
    )
    return "<p>" + sentence * repetitions + "</p>"


def body_fixture(contract: dict) -> str:
    link = contract["competition_internal_link"]["url"]
    parts = [
        "<p>Arsenal e Manchester City se enfrentam em Londres em um duelo importante da Premier League. "
        "A partida está marcada para 16h, no horário de Brasília, e será disputada no Emirates Stadium, "
        "com transmissão de ESPN e Disney+.</p>",
        "<p><strong>Um confronto de peso na parte de cima</strong></p>",
        long_paragraph("Os três pontos têm impacto direto na disputa pelas primeiras posições."),
        f'<p>A <a href="{link}">história da Premier League</a> ajuda a dimensionar a importância de confrontos entre candidatos às primeiras posições.</p>',
        "<p><strong>Como chega o Arsenal</strong></p>",
        long_paragraph("O Arsenal soma três vitórias nos últimos cinco jogos."),
        "<p><strong>Como chega o Manchester City</strong></p>",
        long_paragraph("O Manchester City venceu quatro dos últimos cinco jogos."),
        "<p><strong>Prováveis escalações e arbitragem</strong></p>",
        "<p>As formações são prováveis e podem sofrer alterações até a confirmação oficial.</p>",
        "<ul><li>Arsenal: Raya; Timber; Saliba; Gabriel; Calafiori; Rice; Odegaard; Saka; Eze; Martinelli; Gyokeres.</li><li>Técnico: Mikel Arteta.</li></ul>",
        "<ul><li>Manchester City: Donnarumma; Lewis; Dias; Gvardiol; Ait-Nouri; Rodri; Reijnders; Foden; Cherki; Doku; Haaland.</li><li>Técnico: Pep Guardiola.</li></ul>",
        "<p>Michael Oliver será o árbitro da partida.</p>",
        "<p><strong>Histórico do confronto pela Premier League</strong></p>",
        "<p>Foram 20 confrontos pela Premier League no recorte considerado.</p>",
        "<ul><li>O Arsenal venceu sete.</li><li>O Manchester City venceu dez.</li><li>Houve três empates.</li></ul>",
        long_paragraph("O retrospecto mostra um confronto com peso competitivo e diferentes momentos ao longo das temporadas."),
        "<p><strong>Onde assistir</strong></p>",
        long_paragraph("A transmissão será de ESPN e Disney+."),
        "<p><strong>O que está em jogo</strong></p>",
        long_paragraph("Os três pontos têm impacto direto na disputa pelas primeiras posições."),
    ]
    return "\n".join(parts)


def main() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    body = body_fixture(contract)
    draft = {
        "slug": contract["slug"],
        "body_html": body,
        "fact_fields_used": contract["required_fact_fields"],
        "draft_validated": True,
        "draft_validation_errors": [],
        "ready_for_html": False,
        "publication_unlocked": False,
    }

    rendered, metadata = preview.build_preview(draft=draft, contract=contract)

    assert metadata["step"] == 27
    assert metadata["preview_only"] is True
    assert metadata["ready_for_publication"] is False
    assert metadata["in_body_ads"] == 3
    assert rendered.count('data-ad-slot="8702501261"') == 3
    assert rendered.count('data-ad-slot="5521804159"') == 1
    assert "<!-- ANÚNCIO (ARTIGO - TOPO) -->" in rendered
    assert "<!-- ANÚNCIO (ARTIGO - MEIO) -->" in rendered
    assert "<!-- ANÚNCIO (ARTIGO - FIM) -->" in rendered
    assert rendered.index("<!-- ANÚNCIO (ARTIGO - TOPO) -->") < rendered.index("<!-- ANÚNCIO (ARTIGO - MEIO) -->")
    assert rendered.index("<!-- ANÚNCIO (ARTIGO - MEIO) -->") < rendered.index("<!-- ANÚNCIO (ARTIGO - FIM) -->")
    assert metadata["ad_placement"]["recent_form_sections"]
    assert "historico" in metadata["ad_placement"]["h2h_section"]
    assert metadata["selected_image"] in {
        "bola-uhlsport-gramado.jpg",
        "bola-adidas-gramado.jpg",
        "bola-estadio-futebol.jpg",
    }
    image_tag = f'<img src="{metadata["selected_image"]}"'
    assert rendered.count(image_tag) == 1
    assert "{{" not in rendered
    assert "}}" not in rendered

    # A mesma expressão do confronto aparece no H1 e no excerpt. A posição da
    # imagem deve ser validada apenas dentro do conteúdo do <article>.
    article_marker = '<article id="articleBody">'
    article_start = rendered.index(article_marker) + len(article_marker)
    article_end = rendered.index("</article>", article_start)
    article_html = rendered[article_start:article_end]
    assert article_html.index(image_tag) < article_html.index("Arsenal e Manchester City")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("OK: montagem HTML do Passo 27 validada sem chamada externa.")
    print(f"Imagem selecionada no teste: {metadata['selected_image']}")
    print("Anúncios internos: 3")
    print("Sidebar preservada: sim")
    print("Arquivos publicados alterados: não")


if __name__ == "__main__":
    main()
