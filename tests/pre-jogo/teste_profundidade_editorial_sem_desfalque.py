#!/usr/bin/env python3
"""Trava editorial aceita notícia competitiva real sem inventar lesões."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.qualidade_editorial_pre_jogo import source_depth_errors


def requirement(*rows):
    return {"id": "editorial_match_stakes", "status": "verified",
            "facts": [{"field": field, "text": text} for field, text in rows]}


def main() -> None:
    # Cenário fictício testável; textos representam fatos previamente validados.
    home = ("home_stakes_1", "Equipe A iniciou a tabela com seis pontos e lidera a competição após duas rodadas concluídas.")
    away = ("away_stakes_1", "Equipe B aparece na zona de classificação com três pontos e busca avançar mais posições na tabela.")
    common = ("competitive_context", "A disputa pela liderança e pelas vagas na próxima fase depende da pontuação acumulada ao longo da competição.")
    good = {"facts_by_requirement": [requirement(home, away, common)]}
    assert source_depth_errors(good) == [], source_depth_errors(good)

    insufficient = {"facts_by_requirement": [requirement(home, away)]}
    assert source_depth_errors(insufficient), "Dois fatos não bastam para notícia densa."

    one_sided = {"facts_by_requirement": [requirement(
        home, common, ("home_stakes_2", "Equipe A busca ampliar seus pontos na tabela e manter a liderança isolada após a rodada.")
    )]}
    assert source_depth_errors(one_sided), "Não publicar reportagem sem contexto do adversário."

    score_only = {"facts_by_requirement": [requirement(
        ("home_recent_form", "Dois triunfos no torneio."),
        ("away_recent_form", "Um empate no torneio."),
        ("h2h_games", "Retrospecto: quatro jogos.")
    )]}
    assert source_depth_errors(score_only), "Resultados de serviço não são pauta."
    print("OK: contextos verificados bilaterais bastam sem lesões; fatos pobres continuam bloqueados.")


if __name__ == "__main__":
    main()
