#!/usr/bin/env python3
"""Entrada estável do leitor factual; Passo 34.9 vive em módulo separado."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import ler_fontes_candidatas_passo34_9 as _impl  # noqa: E402
from scripts.ler_fontes_candidatas_passo34_9 import *  # noqa: E402,F401,F403


if __name__ == "__main__":
    _impl.main()
