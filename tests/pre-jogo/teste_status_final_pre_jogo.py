#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import validar_status_final_pre_jogo as status  # noqa: E402


def main() -> None:
    normal = "Flamengo recebe o Independiente del Valle em 17 de setembro, às 21:30, no Maracanã."
    assert status.has_team(normal, "Flamengo")
    assert status.has_team(normal, "Independiente del Valle")
    assert not status.cancellation_hits(normal)

    postponed = "Flamengo x Independiente del Valle foi adiado e será reprogramado."
    hits = status.cancellation_hits(postponed)
    assert "adiado" in hits
    assert "reprogramado" in hits

    safe_negative = "O confronto não foi adiado e segue marcado para 17 de setembro."
    assert not status.cancellation_hits(safe_negative)

    markers = status.schedule_markers("17/09/2026", "21:30", "Maracanã")
    assert "17/09/2026" in markers
    assert "17 de setembro" in markers
    assert "21:30" in markers
    assert "maracana" in markers

    print("OK: regras locais do check final de status validadas.")


if __name__ == "__main__":
    main()
