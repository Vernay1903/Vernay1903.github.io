#!/usr/bin/env python3
"""Teste determinístico do Passo 27, sem chamada externa e sem publicação."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
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
        long_paragraph("O Arsenal venceu três de seus últimos cinco jogos."),
        "<p><strong>Como chega o Manchester City</strong></p>",
        long_paragraph("O Manchester City chega após quatro vitórias em cinco partidas."),
        "<p><strong>Prováveis escalações e arbitragem</strong></p>",
        "<p>As formações são prováveis e podem sofrer alterações até a confirmação oficial.</p>",
        "<ul><li>Provável Arsenal: Raya; Timber; Saliba; Gabriel; Calafiori; Rice; Odegaard; Saka; Eze; Martinelli; Gyokeres.</li><li>Técnico: Mikel Arteta.</li></ul>",
        "<ul><li>Provável Manchester City: Donnarumma; Lewis; Dias; Gvardiol; Ait-Nouri; Rodri; Reijnders; Foden; Cherki; Doku; Haaland.</li><li>Técnico: Pep Guardiola.</li></ul>",
        "<p>Michael Oliver será o árbitro da partida.</p>",
        "<p><strong>Histórico do confronto pela Premier League</strong></p>",
        "<p>Foram 20 confrontos pela Premier League no recorte considerado.</p>",
        "<ul><li>O Arsenal venceu sete.</li><li>O Manchester City venceu dez.</li><li>Houve três empates.</li></ul>",
        long_paragraph("O retrospecto mostra um confronto com peso competitivo e diferentes momentos ao longo das temporadas."),
        "<p><strong>Onde assistir</strong></p>",
        long_paragraph("A transmissão será de ESPN e Disney+."),
        "<p><strong>O que está em jogo</strong></p>",
        long_paragraph(
            "Os três pontos têm impacto direto na disputa pelas primeiras posições. "
            "O Arsenal soma três vitórias nos últimos cinco jogos. "
            "O Manchester City venceu quatro dos últimos cinco jogos."
        ),
    ]
    return "\n".join(parts)



def collision_regression(contract: dict) -> None:
    """Números da forma recente não podem ser confundidos com a seção de H2H."""
    local = deepcopy(contract)
    local["match_context"]["home"] = "Arsenal"
    local["match_context"]["away"] = "Manchester City"
    for group in local["facts_by_requirement"]:
        if group.get("id") == "recent_form_both_teams":
            group["facts"] = [
                {
                    "field": "home_recent_form",
                    "text": "Forma recente do Arsenal: Arsenal 3 2-1-0 7:2 +5 7.",
                },
                {
                    "field": "away_recent_form",
                    "text": "Forma recente do Manchester City: seven-match winless run.",
                },
            ]
        elif group.get("id") == "competition_specific_head_to_head":
            group["facts"] = [
                {"field": "h2h_games", "text": "Confrontos pela Premier League: 5 jogos."},
                {"field": "h2h_home_wins", "text": "Vitórias do Arsenal pela Premier League: 3."},
                {"field": "h2h_away_wins", "text": "Vitórias do Manchester City pela Premier League: 1."},
                {"field": "h2h_draws", "text": "Empates pela Premier League: 1."},
            ]

    body = "\n".join(
        [
            "<p>Abertura do confronto.</p>",
            "<p><strong>Data, horário e local</strong></p>",
            "<p>Arsenal x Manchester City pela Premier League.</p>",
            "<p><strong>Transmissão</strong></p>",
            "<p>Serviço do jogo.</p>",
            "<p><strong>Momento do Arsenal</strong></p>",
            "<p>Arsenal 3 2-1-0 7:2 +5 7.</p>",
            "<p><strong>Momento do Manchester City</strong></p>",
            "<p>Manchester City vive seven-match winless run.</p>",
            "<p><strong>Retrospecto de Arsenal x Manchester City na Premier League</strong></p>",
            "<p>Em cinco jogos, o Arsenal tem três vitórias, o Manchester City uma e houve um empate.</p>",
            "<ul><li>Jogos: 5</li><li>Arsenal: 3</li><li>Manchester City: 1</li><li>Empates: 1</li></ul>",
            "<p><strong>Prováveis escalações</strong></p>",
            "<p>Informações das equipes.</p>",
            "<p><strong>O que está em jogo</strong></p>",
            "<p>Conclusão.</p>",
        ]
    )
    points, metadata = preview.placement_points(body, local)
    assert len(set(points)) == 3, points
    assert points == sorted(points), points
    assert "momento do manchester city" in metadata["recent_form_sections"][-1]
    assert "retrospecto" in metadata["h2h_section"]


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
    assert all("como chega" in heading for heading in metadata["ad_placement"]["recent_form_sections"])
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

    collision_regression(contract)

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
