#!/usr/bin/env python3
"""Resume preparo de pré-jogo com bloqueio por matéria, sem derrubar lote misto."""
from __future__ import annotations
import json
from pathlib import Path

MANIFEST = Path("build/pre-jogo/automatico/manifest.json")


def avaliar_lote(data: dict) -> tuple[bool, str]:
    ready = data.get("prepared_count")
    blocked = data.get("skipped_count")
    if not isinstance(ready, int) or not isinstance(blocked, int) or ready < 0 or blocked < 0:
        return False, "ERRO: contagens do preparo inválidas."
    if ready != len(data.get("articles", [])) or blocked != len(data.get("skipped", [])):
        return False, "ERRO: contagens do preparo não conferem com os registros."
    if ready == 0 and blocked > 0:
        return False, "ERRO: nenhuma matéria pronta; as partidas foram bloqueadas."
    if ready > 0 and blocked > 0:
        return True, "AVISO: lote misto; matérias aprovadas seguem, partidas bloqueadas permanecem isoladas."
    return True, "OK: resumo do preparo concluído."


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print("PASSO 34 — PREPARO FINALIZADO")
    print(f"Data-alvo: {data['target_date']}")
    print(f"Matérias prontas: {data['prepared_count']}")
    print(f"Bloqueadas/puladas por segurança: {data['skipped_count']}")
    print("Publicação: não; o artifact aguardará a checagem final.")
    for item in data.get("skipped", []):
        print(f"BLOQUEIO: {item.get('slug')}: {item.get('unresolved', item.get('reason'))}")
    accepted, explanation = avaliar_lote(data)
    print(explanation)
    if not accepted:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
