"""Passo 20: remover somente duas qualificacoes refutadas e revisar tudo novamente."""
import copy
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path.cwd().resolve()
sys.path.insert(0,str(ROOT/"scripts"))
from estado_operacao_pos_jogo import RemoteState
from custos_pos_jogo import BudgetCaller
from editorial_pos_jogo import prepare as editorial_prepare,validate
from revisar_pos_jogo import merge_reviews,validate_review,review_request
from redigir_pos_jogo_openai import response_object
from empacotar_redacao_pos_jogo import package_reviewed

FID="espn-401882819"
PREVIOUS_RUN="41486397895"
SOURCE=ROOT/"build/pos-jogo/passo20-terra"
DEST=ROOT/"build/pos-jogo/passo20-validado"
TZ=ZoneInfo("America/Sao_Paulo")

def read(path):return json.loads(path.read_text(encoding="utf-8"))
def save(path,datum):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(datum,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def digest(obj):return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def spent(data):
    return sum((Decimal(c["charged_usd"]) for m in data["months"].values() for c in m.get("calls",[]) if c.get("fixture_id")==FID),Decimal(0))

def main():
    if DEST.exists() or not SOURCE.is_dir():raise ValueError("Pacote original ausente ou tentativa repetida")
    links=read(ROOT/"auditoria/pos-jogo/links-autorizados-piloto.json")
    facts=read(SOURCE/"fatos.json");narrative=read(SOURCE/"narrativa.json")
    package=read(SOURCE/"pacote.json")
    article=read(SOURCE/"redacao/artigo-1.json")
    reviews=[read(SOURCE/("redacao/revisao-1-"+str(i)+".json")) for i in (1,2)]
    if facts.get("fixture_id")!=FID or narrative.get("fixture_id")!=FID:
        raise ValueError("Jogo incorreto")
    if editorial_prepare(facts,narrative,links)!=package:raise ValueError("Pacote diverge da apuracao")
    issues=validate_review(merge_reviews(reviews,package,article),package,article)
    if not issues or any(not i.startswith("block_7:") for i in issues):
        raise ValueError("Pareceres nao isolam a falha prevista no bloco 7")
    before=copy.deepcopy(article)
    old=article["blocks"][7]["text"]
    a="O terceiro gol teve origem em um escanteio do Real Madrid."
    b="O terceiro gol teve origem em uma jogada de escanteio."
    c=", sem chance para Agirrezabala"
    if old.count(a)!=1 or old.count(c)!=1 or article["blocks"][7]["type"]!="paragraph":
        raise ValueError("Trechos refutados nao coincidem com original")
    article["blocks"][7]["text"]=old.replace(a,b).replace(c,"")
    changes=[i for i,(x,y) in enumerate(zip(before["blocks"],article["blocks"])) if x!=y]
    if changes!=[7] or before["title"]!=article["title"] or before["excerpt"]!=article["excerpt"]:
        raise ValueError("Modificacao fora da unidade reprovada")
    validity=validate(article,package["allowed_internal_urls"])
    if not validity["format_passed"] or validity["body_words"]<600:raise ValueError("Extensao ou formato insuficiente")
    if not Path("current-main/noticias.json").is_file() or not Path("current-main/sitemap.xml").is_file():
        raise ValueError("Destinos atuais ausentes")
    remote=RemoteState();job=remote.data["jobs"].get(FID,{})
    if (job.get("status")!="blocked" or job.get("third_step20_retry_run_id")!=PREVIOUS_RUN
        or job.get("fourth_step20_started")):raise ValueError("Recuperacao anterior nao corresponde ao estado")
    before_cost=spent(remote.data)
    cfg=read(ROOT/"config/operacao-pos-jogo.json")
    if before_cost>=Decimal("0.10") or Decimal(cfg["per_article_cap_usd"])!=Decimal("0.10") or cfg["publication_enabled"] is not False:
        raise ValueError("Orcamento ou publicacao fora da politica")
    DEST.mkdir(parents=True)
    for filename in ("fatos.json","narrativa.json","pacote.json"):shutil.copy2(SOURCE/filename,DEST/filename)
    out=DEST/"redacao";out.mkdir()
    save(out/"artigo.json",article)
    save(out/"validacao.json",validity)
    record={"step":20,"status":"running","mode":"double_review_after_targeted_unsupported_claim_removal",
            "fixture_id":FID,"source_run_id":PREVIOUS_RUN,"run_id":os.environ.get("GITHUB_RUN_ID"),
            "publication_enabled":False,"body_words":validity["body_words"],
            "source_article_sha256":digest(before),"corrected_article_sha256":digest(article),
            "altered_blocks":[7],"original_issues":issues,"before_cost_usd":str(before_cost),
            "started_at":datetime.now(TZ).isoformat()}
    job.update(status="running",fourth_step20_started=True,fourth_step20_run_id=record["run_id"])
    remote.save()
    cfg["max_paid_calls_per_fixture"]=int(job.get("api_calls",0))+2
    caller=BudgetCaller(remote,FID,config=cfg)
    provider=read(ROOT/"config/redacao-pos-jogo.json")["provider"]
    responses=[]
    try:
        checks=[]
        for index in (1,2):
            response=caller(review_request(package,article,provider))
            review=response_object(response)
            save(out/("revisao-final-"+str(index)+".json"),review)
            checks.append(review)
            responses.append({"response_id":response.get("id"),"usage":response.get("usage")})
        problems=validate_review(merge_reviews(checks,package,article),package,article)
        if problems:raise ValueError("Revisao independente rejeitou: "+"; ".join(problems))
        meta={"model":"gpt-5.6-terra","review_model":provider["model"],
              "automatic_model_run":True,"correction_method":"deterministic_removal_of_double_reviewer_rejected_clauses",
              "human_review_required":True,"publication_enabled":False,"fixture_id":FID,
              "semantic_review_passed":True,"format_passed":True,
              "written_at":datetime.now(timezone.utc).isoformat(),
              "article_sha256":digest(article),"package_sha256":digest(package),"calls":responses}
        save(out/"metadata.json",meta)
        report=package_reviewed(DEST,Path("current-main"),links)
        if (report.get("body_ad_count")!=3 or not report.get("fixed_shell_unchanged") or
            not report.get("old_news_preserved") or not report.get("old_sitemap_preserved") or
            report.get("publication_enabled") is not False):
            raise ValueError("Pacote final nao preservou template, tres anuncios e indices")
        record.update(status="package_ready_pending_human_review",package=report)
        job.update(status="package_ready",package=report,
                   artifact_name="pos-jogo-passo20-validado-"+str(record["run_id"]),
                   review_run_url="https://github.com/Vernay1903/Vernay1903.github.io/actions/runs/"+str(record["run_id"]))
    except Exception as exc:
        record.update(status="blocked",reason=str(exc));job["status"]="blocked"
        raise
    finally:
        after_cost=spent(remote.data)
        record.update(after_cost_usd=str(after_cost),additional_cost_usd=str(after_cost-before_cost),
                      finished_at=datetime.now(TZ).isoformat())
        if after_cost>Decimal("0.10"):
            record["status"]="blocked_budget_violation";job["status"]="blocked"
        remote.save();save(DEST/"resultado.json",record)
        print(json.dumps(record,ensure_ascii=False),flush=True)

if __name__=="__main__":main()
