"""Audita a coleta de futuros pré-jogos até a trava editorial, sem publicar."""
import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.recuperar_preparo_pre_jogo_automatico import command_plan, call, CONFIG, BUILD
from scripts.qualidade_editorial_pre_jogo import source_depth_errors

TZ = ZoneInfo("America/Sao_Paulo")


def pending_issues(packages: dict) -> list[dict]:
    """Pronto para redigir não significa pronto para cumprir o modelo editorial."""
    blocked = []
    for article in packages.get("articles", []):
        if not isinstance(article, dict):
            continue
        unresolved = article.get("unresolved_required_requirement_ids", [])
        depth_errors = source_depth_errors(article)
        if not article.get("ready_for_drafting") or unresolved or depth_errors:
            blocked.append({
                "slug": article.get("slug"),
                "unresolved": unresolved,
                "editorial_depth": depth_errors,
            })
    return blocked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        help="Data futura YYYY-MM-DD; padrão: amanhã em Brasília. Nunca testa partida já iniciada.",
    )
    args = parser.parse_args()
    today = datetime.now(TZ).date()
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            parser.error("--date deve usar YYYY-MM-DD")
    else:
        target_date = today + timedelta(days=1)
    if target_date <= today:
        raise SystemExit(
            "VALIDAÇÃO INCONCLUSIVA: a auditoria de pré-jogo exige data futura; "
            "partidas do dia podem já ter começado."
        )
    target = target_date.isoformat()
    print(f"AUDITORIA DE PRÉ-JOGO FUTURO: {target} (Brasília).", flush=True)
    original = CONFIG.read_bytes()
    try:
        cfg = json.loads(original)
        cfg["research"]["discovery"]["external_search_enabled"] = True
        for index, command in enumerate(command_plan(target)):
            if index == 6:
                CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
            if index == 12:
                CONFIG.write_bytes(original)
            call(*command)
            if index == 2:
                plan = json.loads((BUILD / f"planos-{target}.json").read_text())
                if not plan["planned_count"]:
                    print(
                        "::warning::VALIDAÇÃO INCONCLUSIVA: sem jogos elegíveis na data futura; "
                        "não foi possível comprovar o fluxo editorial.",
                        flush=True,
                    )
                    return
        packages = json.loads((BUILD / f"pacotes-editoriais-{target}.json").read_text())
        blocked = pending_issues(packages)
        if blocked:
            raise SystemExit(
                "PRÉ-JOGO FUTURO BLOQUEADO (fatos/qualidade): "
                + json.dumps(blocked, ensure_ascii=False)
            )
        print(
            "COLETA E PROFUNDIDADE EDITORIAL APROVADAS para pré-jogos futuros; "
            "redação e publicação NÃO foram executadas.",
            flush=True,
        )
    finally:
        CONFIG.write_bytes(original)


if __name__ == "__main__":
    main()
