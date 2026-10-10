#!/usr/bin/env python3
"""Valida que diagnóstico de pré-jogo não confunde pacote liberado com pauta suficiente."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.diagnosticar_coleta_pre_jogo import pending_issues


def package(slug, *, ready=True, unresolved=None, news=None):
    fields = [{"field": name, "text": content} for name, content in (news or {}).items()]
    return {
        "slug": slug,
        "ready_for_drafting": ready,
        "unresolved_required_requirement_ids": unresolved or [],
        "facts_by_requirement": [
            {"id": "probable_lineups_and_coaches", "status": "verified", "facts": fields}
        ],
    }


def main():
    approved = package("validado.html", news={
        "home_team_news_1": "O mandante confirmou nesta semana que o lateral voltou a treinar e está liberado para o confronto.",
        "away_team_news_1": "O visitante anunciou antes da viagem que o atacante está suspenso e não participará da próxima partida.",
    })
    assert pending_issues({"articles": [approved]}) == []
    shallow = package("superficial.html")
    issues = pending_issues({"articles": [shallow]})
    assert len(issues) == 1 and issues[0]["editorial_depth"]
    incomplete = package("incompleto.html", ready=False, unresolved=["recent_form_both_teams"])
    issues = pending_issues({"articles": [incomplete]})
    assert len(issues) == 1 and issues[0]["unresolved"] == ["recent_form_both_teams"]
    assert issues[0]["editorial_depth"]
    assert pending_issues({"articles": []}) == []
    print("OK: auditoria futura rejeita insuficiência factual e editorial sem abrir mão do modelo aprovado.")


if __name__ == "__main__":
    main()
