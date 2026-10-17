#!/usr/bin/env python3
"""Regressão editorial: não exigir serviços ausentes em títulos que não os prometem."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import montar_pacote_editorial as editorial

config = json.loads((ROOT / "config/pre-jogo.json").read_text(encoding="utf-8"))
missing = {
    "transmission": {"status": "unavailable_after_check", "facts": []},
    "probable_lineups_and_coaches": {"status": "unavailable_after_check", "facts": []},
}
prefix = "Flamengo x Grêmio pelo Brasileirão: "
assert editorial.approved_headline_errors(prefix + "horário", missing, config=config) == []
assert "required_transmission_not_verified" in editorial.approved_headline_errors(
    prefix + "horário e transmissão", missing, config=config
)
assert "required_probable_lineups_not_verified" in editorial.approved_headline_errors(
    prefix + "horário e prováveis escalações", missing, config=config
)
both = editorial.approved_headline_errors(
    prefix + "horário, prováveis escalações e transmissão", missing, config=config
)
assert {"required_transmission_not_verified", "required_probable_lineups_not_verified"} <= set(both)
assert "incomplete_approved_headline" in editorial.approved_headline_errors(
    "Título genérico: horário", missing, config=config
)
print("OK: promessa editorial condicional exige somente serviços verificados.")
