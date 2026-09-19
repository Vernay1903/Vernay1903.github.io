#!/usr/bin/env python3
"""Regressão: estádio fixo é aplicado SOMENTE pelo mandante monitorado.

O cadastro do editor não é apresentado como fonte externa de confirmação.
Não faz requisições, não redige e não publica nada.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import extrair_fatos_estruturados as facts


def assert_stadium(article, config, stadium):
    req = {
        "id": "stadium_and_location",
        "status": "pending",
        "facts": [],
        "source_candidates": [],
    }
    out = facts.apply_fixed_home_stadium([req], article=article, config=config)[0]
    if stadium is None:
        assert out == req
        return
    assert out["status"] == "verified"
    assert out["facts"] == [
        {"field": "stadium", "text": f"A partida será disputada no {stadium}."}
    ]
    assert out["sources"] == []
    assert out["fact_extraction_status"] == "editorial_fixed_home_stadium"
    assert out["editorial_stadium_override"] is True
    assert out["notes"].endswith("não confirmado para este jogo.")


def main():
    config = json.loads((ROOT / "config" / "pre-jogo.json").read_text(encoding="utf-8"))
    fixed = config["fixed_home_stadium"]
    assert fixed["policy"] == "fixed_when_monitored_club_is_home_user_approved_2026_09_19"
    expected = {
        "Arsenal": "Emirates Stadium",
        "Manchester City": "Etihad Stadium",
        "PSG": "Parc des Princes",
        "Bayern de Munique": "Allianz Arena",
        "Inter de Milão": "San Siro",
        "Flamengo": "Maracanã",
        "Palmeiras": "Nubank Parque",
        "Grêmio": "Arena do Grêmio",
        "Barcelona": "Spotify Camp Nou",
        "Real Madrid": "Santiago Bernabéu",
    }
    assert fixed["stadiums"] == expected
    assert {c["name"] for c in config["monitored_clubs"]} == set(expected)

    for home, stadium in expected.items():
        assert_stadium(
            {"fixture_id": 991, "match_context": {"home": home, "away": "Outro clube"}},
            config, stadium,
        )

    # Equipe monitorada VISITANTE não pode impor seu próprio estádio.
    assert_stadium(
        {"fixture_id": 992, "match_context": {"home": "Atlético de Madrid", "away": "Real Madrid"}},
        config, None,
    )
    assert_stadium(
        {"fixture_id": 993, "match_context": {"home": "Marseille", "away": "PSG"}},
        config, None,
    )
    # Dois monitorados no mesmo jogo: somente o MANDANTE prevalece.
    assert_stadium(
        {"fixture_id": 994, "match_context": {"home": "Flamengo", "away": "Palmeiras"}},
        config, "Maracanã",
    )
    assert_stadium(
        {"fixture_id": 995, "match_context": {"home": "Palmeiras", "away": "Flamengo"}},
        config, "Nubank Parque",
    )
    assert_stadium(
        {"fixture_id": 996, "match_context": {"home": "Manchester City FC", "away": "Arsenal"}},
        config, "Etihad Stadium",
    )

    # Mesmo que a pesquisa falhe ou encontre um estádio divergente, o proprietário
    # decidiu que a configuração editorial fixa prevalece.
    req = {
        "id": "stadium_and_location",
        "status": "pending",
        "facts": [],
        "source_candidates": [],
        "conflict_detected": True,
        "conflicts": [{"field": "stadium", "values": ["Outro estádio"]}],
    }
    article = {"fixture_id": 123456, "match_context": {"home": "Flamengo", "away": "Santos"}}
    fixed_req = facts.apply_fixed_home_stadium([req], article=article, config=config)[0]
    assert fixed_req["conflict_detected"] is False
    assert fixed_req["facts"][0]["text"].endswith("Maracanã.")

    # Correção excepcional por ID NÃO modifica os demais jogos do mandante.
    config["fixed_home_stadium"]["exceptions_by_fixture_id"]["123456"] = "Estádio alternativo"
    assert_stadium(article, config, "Estádio alternativo")
    assert_stadium(
        {"fixture_id": 123457, "match_context": article["match_context"]},
        config, "Maracanã",
    )

    # Testa fluxo real do extrator até o pacote factual, sem web.
    a = facts.extract_article(
        {"slug": "teste.html", "fixture_id": 123457,
         "match_context": article["match_context"],
         "requirements": [req]},
        config=config,
    )
    assert a["requirements"][0]["status"] == "verified"
    assert a["requirements"][0]["facts"][0]["text"] == "A partida será disputada no Maracanã."
    assert a["structured_fact_count"] == 1
    assert "stadium_and_location" not in a["conflict_requirement_ids"]

    print("OK: 10 estádios fixos, mando, variantes, confrontos monitorados e exceções manuais.")


if __name__ == "__main__":
    main()
