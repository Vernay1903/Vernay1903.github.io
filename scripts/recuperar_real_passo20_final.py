"""Recuperacao unica do passo 20: reutiliza fontes verificadas, revisa novamente e nunca publica."""
import copy
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path.cwd().resolve()
sys.path.insert(0,str(ROOT/"scripts"))
from estado_operacao_pos_jogo import RemoteState
from custos_pos_jogo import BudgetCaller
from editorial_pos_jogo import prepare as editorial_prepare
from redigir_pos_jogo_openai import generate
from empacotar_redacao_pos_jogo import package_reviewed

FID="espn-401882819"
SOURCE_RUN="41344947385"
SOURCE=ROOT/"build/pos-jogo/real-recuperacao20-original"
DEST=ROOT/"build/pos-jogo/passo20-recuperacao-final"
TZ=ZoneInfo("America/Sao_Paulo")
BUDGET_LIMIT=Decimal("0.10")

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def sha(obj):
    return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def fixture_cost(state):
    return sum((Decimal(c["charged_usd"]) for month in state["months"].values()
                for c in month.get("calls",[]) if c.get("fixture_id")==FID),Decimal("0"))

def main():
    if not SOURCE.is_dir() or DEST.exists():
        raise ValueError("Arquivo de origem ausente ou tentativa final duplicada")
    game=SOURCE/"execucao/2026-11-01"/FID
    links=read(ROOT/"auditoria/pos-jogo/links-autorizados-piloto.json")
    facts=read(game/"fatos.json")
    narrative=read(game/"narrativa.json")
    package=read(game/"pacote.json")
    prior=read(game/"redacao/metadata.json")
    if facts.get("fixture_id")!=FID or narrative.get("fixture_id")!=FID or prior.get("fixture_id")!=FID:
        raise ValueError("Identidade da partida divergente")
    if facts.get("match",{}).get("match_date")!="2026-11-01":
        raise ValueError("Data do jogo divergente")
    if not facts.get("ready_for_drafting") or not narrative.get("reviewed"):
        raise ValueError("Apuracao anterior sem revisao aprovada")
    if package!=editorial_prepare(facts,narrative,links):
        raise ValueError("Pacote arquivado difere das evidencias revisadas")
    if prior.get("package_sha256")!=sha(package) or prior.get("semantic_review_passed") is not False:
        raise ValueError("Estado do rascunho original divergente")
    current=Path("current-main")
    if not (current/"noticias.json").is_file() or not (current/"sitemap.xml").is_file():
        raise ValueError("Destinos atuais nao conferidos")
    remote=RemoteState()
    job=remote.data["jobs"].get(FID,{})
    if job.get("status")!="blocked" or job.get("source_recovery_run_id")!=SOURCE_RUN or job.get("final_step20_retry_started"):
        raise ValueError("Partida ja tratada ou recuperacao nao autorizada")
    before=fixture_cost(remote.data)
    if before>=BUDGET_LIMIT:
        raise ValueError("Teto de US$ 0,10 por partida ja consumido")
    cfg=read(ROOT/"config/operacao-pos-jogo.json")
    if cfg["publication_enabled"] is not False or cfg["per_article_cap_usd"]!="0.10":
        raise ValueError("Protecoes de publicacao ou orcamento alteradas")
    original=copy.deepcopy(job)
    DEST.mkdir(parents=True)
    for filename in ("fatos.json","narrativa.json","pacote.json"):
        shutil.copy2(game/filename,DEST/filename)
    record={"step":20,"source_run_id":SOURCE_RUN,"fixture_id":FID,
            "mode":"verified_archived_sources_rewrite","status":"running",
            "publication_enabled":False,"before_cost_usd":str(before),
            "old_job_status":original["status"],
            "started_at":datetime.now(TZ).isoformat(),
            "run_id":os.environ.get("GITHUB_RUN_ID")}
    job.update(status="running",final_step20_retry_started=True,final_step20_run_id=record["run_id"])
    remote.save()
    try:
        cfg["max_paid_calls_per_fixture"]=max(int(cfg["max_paid_calls_per_fixture"]),int(job.get("api_calls",0))+12)
        caller=BudgetCaller(remote,FID,config=cfg)
        meta=generate(package,DEST/"redacao",execute=True,caller=caller)
        if meta.get("semantic_review_passed") is not True or meta.get("format_passed") is not True:
            raise ValueError("Revisao nao aprovou a nova redacao")
        report=package_reviewed(DEST,current,links)
        if (report.get("body_ad_count")!=3 or report.get("fixed_shell_unchanged") is not True
            or not report.get("old_news_preserved") or not report.get("old_sitemap_preserved")
            or report.get("publication_enabled") is not False):
            raise ValueError("Pacote HTML/noticia/sitemap nao passou nas travas")
        if "sidebar" not in (DEST/"publicacao-teste"/report["filename"]).read_text().lower():
            raise ValueError("Sidebar ausente do modelo do HTML")
        record.update(status="package_ready_pending_human_review",
                      package=report,article_sha256=meta["article_sha256"])
        job.update(status="package_ready",package=report,
                   artifact_name="pos-jogo-passo20-final-"+str(record["run_id"]),
                   review_run_url="https://github.com/Vernay1903/Vernay1903.github.io/actions/runs/"+str(record["run_id"]))
    except Exception as exc:
        record.update(status="blocked",reason=str(exc))
        job["status"]="blocked"
        raise
    finally:
        after=fixture_cost(remote.data)
        record.update(after_cost_usd=str(after),additional_cost_usd=str(after-before),
                      finished_at=datetime.now(TZ).isoformat())
        if after>BUDGET_LIMIT:
            record["status"]="blocked_budget_violation"
            job["status"]="blocked"
        remote.save()
        save(DEST/"resultado.json",record)
        print(json.dumps(record,ensure_ascii=False),flush=True)
    if record["status"]!="package_ready_pending_human_review":
        raise ValueError("Pacote nao aprovado")

if __name__=="__main__":
    main()
