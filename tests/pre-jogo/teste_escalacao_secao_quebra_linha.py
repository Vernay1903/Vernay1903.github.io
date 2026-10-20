#!/usr/bin/env python3
"""Escalações em linhas abaixo do cabeçalho precisam sobreviver à segmentação."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import ler_fontes_candidatas_base as base


def main():
    content = (
        "Palmeiras x Fluminense: semifinal de volta da Libertadores\\n"
        "Provável escalação do Palmeiras\\n"
        "Carlos Miguel; Murilo, Gustavo Gómez e Barboza; Giay, Marlon Freitas, "
        "Andreas Pereira, Lucas Evangelista e Piquerez; Arias e Flaco López. Técnico: Abel Ferreira.\\n"
        "Provável escalação do Fluminense\\n"
        "Fábio; Guga, Thiago Silva, Millán e Guilherme Arana; Nonato, Martinelli "
        "e Ganso; Canobbio, Savarino e Hulk. Técnico: Marcão.\\n"
    ).replace("\\n", "\n")
    rows = base.structured_lineup_windows(content, 700)
    assert any("Palmeiras | Provável escalação:" in x and "Flaco López" in x for x in rows), rows
    assert any("Fluminense | Provável escalação:" in x and "Hulk" in x for x in rows), rows
    assert any("Palmeiras | Técnico: Abel Ferreira" in x for x in rows), rows
    assert any("Fluminense | Técnico: Marcão" in x for x in rows), rows
    extracted = base.extract_evidence_segments(
        content, "probable_lineups_and_coaches",
        max_segments=10, max_segment_chars=700,
    )
    assert len(extracted) >= 4 and "Carlos Miguel" in " ".join(extracted)
    assert "Marcão" in " ".join(extracted)
    assert base.structured_lineup_windows("Provável escalação do Palmeiras\\n", 700) == []
    print("OK: titulares e treinadores preservados sem gerar nomes inexistentes.")


if __name__ == "__main__":
    main()
