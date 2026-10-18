#!/usr/bin/env python3
"""Título editorial fixo e compromisso obrigatório de serviços comprovados."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import montar_pacote_editorial as editorial

config = json.loads((ROOT / "config/pre-jogo.json").read_text(encoding="utf-8"))
title = "Flamengo x Grêmio: veja escalações, destaques e onde assistir"
missing = {
    "transmission": {"status": "unavailable_after_check", "facts": []},
    "probable_lineups_and_coaches": {"status": "unavailable_after_check", "facts": []},
}
errors = editorial.approved_headline_errors(title, missing, config=config)
assert "required_transmission_not_verified" in errors
assert "required_probable_lineups_not_verified" in errors
for bad in (
    "Flamengo x Grêmio pelo Brasileirão: horário",
    "Flamengo x Grêmio pelo Brasileirão: horário e transmissão",
    "Flamengo x Grêmio: veja horário e escalações",
    "Flamengo x Grêmio: veja escalações e onde assistir",
):
    assert "titulo_fora_do_modelo_fixo" in editorial.approved_headline_errors(
        bad, missing, config=config,
    ), bad
assert "titulo_fora_do_modelo_fixo" in editorial.approved_headline_errors(
    "Título genérico: horário", missing, config=config,
)
assert "titulo_fora_do_modelo_fixo" not in errors
print("OK: modelo fixo impede manchete de horário e promete apenas serviços verificados.")
