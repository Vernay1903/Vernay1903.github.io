#!/usr/bin/env python3
"""Teste determinístico da camada de redação controlada do Passo 25.

Não chama modelo externo. Simula uma resposta de redator para validar o contrato,
as travas editoriais e a permanência do rascunho somente em build/.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import preparar_redacao_pre_jogo as prepare  # noqa: E402
from scripts import validar_rascunho_pre_jogo as validate  # noqa: E402

OUTPUT = ROOT / "build" / "pre-jogo" / "teste-redacao-controlada.json"
DRAFT_OUTPUT = ROOT / "build" / "pre-jogo" / "rascunhos-teste" / "arsenal-manchester-city-premier-league-2026-transmissao-horario-escalacoes.json"


def clean_package() -> dict:
    return {
        "step": 24,
        "title": "Arsenal x Manchester City pela Premier League: transmissão, horário e prováveis escalações",
        "excerpt": "Arsenal e Manchester City se enfrentam pela Premier League em Londres.",
        "date": "17/09/2026",
        "slug": "arsenal-manchester-city-premier-league-2026-transmissao-horario-escalacoes.html",
        "match_context": {
            "home": "Arsenal",
            "away": "Manchester City",
            "competition": "Premier League",
            "competition_slug": "premier-league",
            "kickoff_time_brasilia": "16:00",
        },
        "facts_by_requirement": [
            {
                "id": "stadium_and_location",
                "status": "verified",
                "resolved": True,
                "facts": [{"field": "stadium", "text": "A partida será disputada no Emirates Stadium."}],
            },
            {
                "id": "transmission",
                "status": "verified",
                "resolved": True,
                "facts": [{"field": "transmission", "text": "A transmissão será de ESPN e Disney+."}],
            },
            {
                "id": "probable_lineups_and_coaches",
                "status": "verified",
                "resolved": True,
                "facts": [
                    {"field": "home_lineup", "text": "Arsenal: Raya; Timber; Saliba; Gabriel; Calafiori; Rice; Odegaard; Saka; Eze; Martinelli; Gyokeres."},
                    {"field": "home_coach", "text": "Técnico do Arsenal: Mikel Arteta."},
                    {"field": "away_lineup", "text": "Manchester City: Donnarumma; Lewis; Dias; Gvardiol; Ait-Nouri; Rodri; Reijnders; Foden; Cherki; Doku; Haaland."},
                    {"field": "away_coach", "text": "Técnico do Manchester City: Pep Guardiola."},
                ],
            },
            {
                "id": "officiating",
                "status": "verified",
                "resolved": True,
                "facts": [{"field": "referee", "text": "Michael Oliver será o árbitro da partida."}],
            },
            {
                "id": "recent_form_both_teams",
                "status": "verified",
                "resolved": True,
                "facts": [
                    {"field": "home_recent_form", "text": "O Arsenal soma três vitórias nos últimos cinco jogos."},
                    {"field": "away_recent_form", "text": "O Manchester City venceu quatro dos últimos cinco jogos."},
                ],
            },
            {
                "id": "competition_specific_head_to_head",
                "status": "verified",
                "resolved": True,
                "facts": [
                    {"field": "games", "text": "Foram 20 confrontos pela Premier League no recorte considerado."},
                    {"field": "home_wins", "text": "O Arsenal venceu sete."},
                    {"field": "away_wins", "text": "O Manchester City venceu dez."},
                    {"field": "draws", "text": "Houve três empates."},
                ],
            },
            {
                "id": "stakes_and_qualification_scenarios_when_applicable",
                "status": "verified",
                "resolved": True,
                "facts": [{"field": "stakes", "text": "Os três pontos têm impacto direto na disputa pelas primeiras posições."}],
            },
        ],
        "competition_internal_link": {
            "competition_slug": "premier-league",
            "url": "https://cortedosesportes.com.br/premier-league-historia-campeoes.html",
            "anchor_hint": "história da Premier League",
        },
        "resolution_status": {},
        "unresolved_required_requirement_ids": [],
        "editorial_constraints": {
            "minimum_words": 700,
            "subtitles_in_strong": True,
            "internal_link_required": True,
            "research_sources_must_not_be_cited": True,
            "research_process_must_not_be_mentioned": True,
            "write_verified_facts_directly": True,
        },
        "ready_for_drafting": True,
        "ready_for_html": False,
        "publication_unlocked": False,
        "provenance_available_to_drafter": False,
    }


def valid_body() -> str:
    link = "https://cortedosesportes.com.br/premier-league-historia-campeoes.html"
    intro = (
        "<p>Arsenal e Manchester City se enfrentam pela Premier League em um duelo que reúne dois dos principais clubes ingleses. "
        "A partida será disputada no Emirates Stadium e terá transmissão de ESPN e Disney+. O encontro coloca frente a frente equipes "
        "que chegam com campanhas recentes fortes e com necessidade de somar pontos na disputa pelas primeiras posições. O horário em "
        "Brasília é 16h, e o confronto concentra atenção tanto pelo momento dos times quanto pelo histórico recente entre eles.</p>"
    )
    context = (
        "<p><strong>O que está em jogo</strong></p>"
        "<p>Os três pontos têm impacto direto na disputa pelas primeiras posições. Isso aumenta o peso de cada escolha desde o início, "
        "porque um confronto entre adversários desse nível pode alterar a leitura da rodada e a sequência imediata de ambos. O Arsenal "
        "atua diante de sua torcida, enquanto o Manchester City chega para um compromisso fora de casa que exige equilíbrio entre controle "
        "da posse, proteção defensiva e capacidade de aproveitar os espaços. O cenário favorece uma partida em que detalhes podem ganhar "
        "importância, especialmente se o placar permanecer equilibrado por boa parte do jogo.</p>"
        "<p>O duelo também se encaixa em uma competição cuja trajetória ajuda a explicar o peso desses encontros. A "
        f"<a href=\"{link}\">história da Premier League</a> reúne diferentes ciclos de domínio, rivalidades e mudanças de força entre os clubes. "
        "Nesse contexto, Arsenal e Manchester City entram em campo com a responsabilidade de transformar o bom momento recente em resultado "
        "e evitar que um rival direto ganhe terreno na tabela.</p>"
    )
    form = (
        "<p><strong>Como chega o Arsenal</strong></p>"
        "<p>O Arsenal soma três vitórias nos últimos cinco jogos. A sequência mostra uma equipe capaz de manter competitividade mesmo em um "
        "trecho exigente do calendário. Jogando no Emirates Stadium, o time busca aproveitar o ambiente favorável para impor ritmo desde os "
        "primeiros minutos. A provável formação mantém peças importantes em todos os setores e oferece alternativas para circular a bola, "
        "pressionar a saída adversária e acelerar quando houver espaço pelos lados.</p>"
        "<p>A presença de jogadores técnicos no meio permite ao Arsenal variar a construção, enquanto os atacantes dão profundidade para não "
        "deixar a equipe presa apenas à troca de passes. O desafio será equilibrar agressividade e proteção, porque avançar muitos jogadores "
        "ao mesmo tempo pode abrir corredores para as transições do Manchester City. Mikel Arteta aparece como o técnico responsável por "
        "organizar essa combinação entre pressão, circulação e segurança sem transformar o jogo em uma sequência de ataques desordenados.</p>"
        "<p><strong>Como chega o Manchester City</strong></p>"
        "<p>O Manchester City venceu quatro dos últimos cinco jogos e chega com uma sequência recente ligeiramente superior. O desempenho "
        "reforça a necessidade de o Arsenal controlar os momentos em que o rival consegue instalar sua posse no campo ofensivo. Pep Guardiola "
        "tem à disposição uma provável formação com qualidade para trabalhar por dentro e também ameaçar em velocidade, o que obriga o time "
        "da casa a manter distâncias curtas entre defesa, meio-campo e ataque.</p>"
        "<p>Para o City, administrar o ritmo pode ser tão importante quanto acelerar. Uma partida fora de casa contra um adversário direto "
        "costuma exigir paciência para não oferecer contra-ataques em perdas de bola simples. Ao mesmo tempo, a equipe precisa encontrar "
        "maneiras de aproximar seus jogadores mais criativos da área. A forma recente indica confiança, mas o confronto exige eficiência para "
        "transformar controle territorial em chances claras.</p>"
    )
    lineups = (
        "<p><strong>Prováveis escalações e arbitragem</strong></p>"
        "<p>As formações abaixo são prováveis e podem sofrer alterações até a confirmação oficial de cada equipe.</p>"
        "<ul>"
        "<li><strong>Arsenal:</strong> Raya; Timber; Saliba; Gabriel; Calafiori; Rice; Odegaard; Saka; Eze; Martinelli; Gyokeres.</li>"
        "<li><strong>Técnico:</strong> Mikel Arteta.</li>"
        "</ul>"
        "<ul>"
        "<li><strong>Manchester City:</strong> Donnarumma; Lewis; Dias; Gvardiol; Ait-Nouri; Rodri; Reijnders; Foden; Cherki; Doku; Haaland.</li>"
        "<li><strong>Técnico:</strong> Pep Guardiola.</li>"
        "</ul>"
        "<p>Michael Oliver será o árbitro da partida. A definição da arbitragem completa o quadro de serviço do confronto, que reúne duas "
        "equipes acostumadas a jogos de grande intensidade e que precisam controlar também o aspecto disciplinar para não perder jogadores "
        "em momentos decisivos.</p>"
    )
    h2h = (
        "<p><strong>Histórico do confronto pela Premier League</strong></p>"
        "<p>No recorte considerado pela competição, o retrospecto mostra vantagem do Manchester City, mas também registra vitórias do Arsenal "
        "e empates suficientes para reforçar que o confronto não deve ser tratado como automático. Os números abaixo se referem apenas à "
        "Premier League.</p>"
        "<ul>"
        "<li>Jogos: 20.</li>"
        "<li>Vitórias do Arsenal: 7.</li>"
        "<li>Vitórias do Manchester City: 10.</li>"
        "<li>Empates: 3.</li>"
        "</ul>"
        "<p>O recorte ajuda a dimensionar a rivalidade competitiva recente entre os clubes sem misturar partidas de outras competições. Para "
        "o jogo atual, o histórico funciona como contexto, enquanto a forma recente e as escolhas de escalação tendem a pesar mais diretamente "
        "na maneira como a partida será disputada.</p>"
    )
    watch = (
        "<p><strong>Onde assistir</strong></p>"
        "<p>A transmissão será de ESPN e Disney+. Para quem acompanha a rodada no Brasil, a informação concentra o serviço principal junto do "
        "horário de 16h de Brasília e do local da partida, o Emirates Stadium. Como se trata de um confronto com impacto nas primeiras posições, "
        "a expectativa é de atenção elevada durante toda a partida, principalmente se a diferença no placar permanecer mínima.</p>"
        "<p>O jogo reúne elementos suficientes para exigir paciência dos dois lados. O Arsenal tentará aproveitar o mando e sua sequência de "
        "resultados, enquanto o Manchester City chega respaldado por quatro vitórias nos últimos cinco compromissos. A provável composição dos "
        "times sugere qualidade técnica em todos os setores, mas a execução coletiva será decisiva para transformar nomes em vantagem real.</p>"
    )
    finish = (
        "<p><strong>Duelo pode pesar na sequência da temporada</strong></p>"
        "<p>Arsenal e Manchester City entram em campo com objetivos que se cruzam diretamente. Uma vitória fortalece a posição na parte de cima "
        "e, ao mesmo tempo, impede que um concorrente some três pontos. Esse efeito duplo aumenta o valor do confronto, sobretudo em uma liga "
        "na qual as margens entre os principais clubes podem se tornar pequenas ao longo da temporada.</p>"
        "<p>O cenário aponta para um duelo em que controle emocional, precisão na saída de bola, capacidade de pressionar e eficiência nas áreas "
        "terão peso considerável. O Arsenal conta com o mando e três vitórias nos últimos cinco jogos; o Manchester City chega com quatro vitórias "
        "no mesmo recorte. Entre essas tendências, o resultado será definido pelo que cada equipe conseguir executar no Emirates Stadium durante "
        "os noventa minutos.</p>"
    )
    filler = "".join(
        "<p>Em partidas desse nível, o equilíbrio entre iniciativa e cautela costuma orientar as decisões. Quem conseguir proteger melhor a bola, "
        "reduzir erros em zonas perigosas e manter organização depois de perder a posse terá condições de sustentar períodos maiores de domínio. "
        "A intensidade também pode mudar ao longo do confronto, exigindo leitura rápida para alternar pressão, circulação e ataques mais verticais "
        "sem abandonar a estrutura defensiva. Essa combinação ajuda a explicar por que um jogo entre Arsenal e Manchester City pode mudar de "
        "característica várias vezes antes do apito final.</p>"
        for _ in range(4)
    )
    return intro + context + form + lineups + h2h + watch + finish + filler


def main() -> None:
    config = prepare.load_config()
    contract = prepare.build_contract(clean_package(), config=config)

    required_fields = contract["required_fact_fields"]
    valid = {
        "slug": contract["slug"],
        "body_html": valid_body(),
        "fact_fields_used": required_fields,
    }
    checked, errors = validate.validate_draft(valid, contract, config=config)
    assert errors == []
    assert checked["draft_validated"] is True
    assert checked["word_count"] >= 700
    assert checked["strong_subheading_count"] >= 5
    assert checked["internal_link_count"] == 1
    assert checked["ready_for_html"] is False
    assert checked["publication_unlocked"] is False

    DRAFT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DRAFT_OUTPUT.write_text(json.dumps(checked, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    short = deepcopy(valid)
    short["body_html"] = "<p><strong>Jogo</strong></p><p>Arsenal x Manchester City.</p>"
    _short_checked, short_errors = validate.validate_draft(short, contract, config=config)
    assert any("mínimo exigido" in item for item in short_errors)

    attribution = deepcopy(valid)
    attribution["body_html"] = valid["body_html"].replace(
        "A partida será disputada no Emirates Stadium",
        "Segundo o site X, a partida será disputada no Emirates Stadium",
        1,
    )
    _attr_checked, attr_errors = validate.validate_draft(attribution, contract, config=config)
    assert any("atribuição" in item for item in attr_errors)

    external_link = deepcopy(valid)
    external_link["body_html"] = valid["body_html"].replace(
        "<p><strong>Onde assistir</strong></p>",
        '<p><a href="https://example.com/noticia">Outro link</a></p><p><strong>Onde assistir</strong></p>',
        1,
    )
    _link_checked, link_errors = validate.validate_draft(external_link, contract, config=config)
    assert any("exatamente um link" in item for item in link_errors)

    missing_field = deepcopy(valid)
    missing_field["fact_fields_used"] = required_fields[:-1]
    _field_checked, field_errors = validate.validate_draft(missing_field, contract, config=config)
    assert any("campos factuais" in item for item in field_errors)

    report = {
        "step": 25,
        "mode": "simulated_writer_contract_test",
        "drafting_provider_connected": contract["drafting_provider_connected"],
        "clean_input_only": True,
        "provenance_available_to_drafter": False,
        "valid_draft_word_count": checked["word_count"],
        "valid_draft_subheading_count": checked["strong_subheading_count"],
        "valid_draft_internal_link_count": checked["internal_link_count"],
        "short_draft_blocked": bool(short_errors),
        "source_attribution_blocked": bool(attr_errors),
        "external_link_blocked": bool(link_errors),
        "missing_fact_field_blocked": bool(field_errors),
        "semantic_factual_review_still_required": True,
        "ready_for_html": False,
        "publication_unlocked": False,
        "sample_draft": str(DRAFT_OUTPUT.relative_to(ROOT)),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("OK: contrato e validador de redação do Passo 25 aprovados.")
    print(f"Rascunho simulado válido: {checked['word_count']} palavras.")
    print("Rascunho curto: bloqueado.")
    print("Atribuição de fonte: bloqueada.")
    print("Link externo: bloqueado.")
    print("Campo factual omitido: bloqueado.")
    print("Provedor real de redação conectado: não.")
    print("HTML e publicação permanecem bloqueados.")


if __name__ == "__main__":
    main()
