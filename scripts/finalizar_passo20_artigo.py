"""Passo 20: correcoes automáticas de unidades reprovadas, com duas revisoes independentes."""
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
from editorial_pos_jogo import prepare as prepare_editorial,validate
from revisar_pos_jogo import patch_request,apply_patch,review_request,validate_review,merge_reviews
from redigir_pos_jogo_openai import response_object
from empacotar_redacao_pos_jogo import package_reviewed

FID="espn-401882819"
SOURCE_RUN="41484419472"
SOURCE=ROOT/"build/pos-jogo/passo20-failed"
DEST=ROOT/"build/pos-jogo/passo20-conclusao"
TZ=ZoneInfo("America/Sao_Paulo")
def read(path):return json.loads(path.read_text(encoding="utf-8"))
def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def sha(obj):
    return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def spent(state):
    return sum((Decimal(c["charged_usd"]) for m in state["months"].values()
                for c in m.get("calls",[]) if c.get("fixture_id")==FID),Decimal(0))
def main():
    if not SOURCE.is_dir() or DEST.exists():raise ValueError("Arquivo original ou diretorio de saida invalido")
    links=read(ROOT/"auditoria/pos-jogo/links-autorizados-piloto.json")
    facts=read(SOURCE/"fatos.json");narrative=read(SOURCE/"narrativa.json")
    package=read(SOURCE/"pacote.json")
    article=read(SOURCE/"redacao/artigo.json")
    previous=read(SOURCE/"redacao/metadata.json")
    prior_review=read(SOURCE/"redacao/revisao-4.json")
    if (facts.get("fixture_id")!=FID or narrative.get("fixture_id")!=FID or
        previous.get("fixture_id")!=FID or previous.get("semantic_review_passed") is not False):
        raise ValueError("Arquivo nao representa o rascunho reprovado correto")
    if package!=prepare_editorial(facts,narrative,links):
        raise ValueError("Apuracao e pacote de fontes nao conferem")
    if previous.get("article_sha256")!=sha(article) or previous.get("package_sha256")!=sha(package):
        raise ValueError("Checksum original nao confere")
    issues=validate_review(prior_review,package,article)
    if not issues:raise ValueError("Revisao arquivada nao apresenta as pendencias esperadas")
    remote=RemoteState();job=remote.data["jobs"].get(FID,{})
    if (job.get("status")!="blocked" or job.get("final_step20_run_id")!=SOURCE_RUN or
        job.get("second_step20_retry_started")):raise ValueError("Estado da recuperacao divergente")
    prior_cost=spent(remote.data)
    if prior_cost>=Decimal("0.10"):raise ValueError("Sem saldo de US$ 0,10 no jogo")
    cfg=read(ROOT/"config/operacao-pos-jogo.json")
    if cfg.get("publication_enabled") is not False or Decimal(cfg["per_article_cap_usd"])!=Decimal("0.10"):
        raise ValueError("Publicacao ou teto alterados")
    if not Path("current-main/noticias.json").is_file() or not Path("current-main/sitemap.xml").is_file():
        raise ValueError("Destinos atuais nao lidos")
    DEST.mkdir(parents=True)
    for f in ("fatos.json","narrativa.json","pacote.json"):shutil.copy2(SOURCE/f,DEST/f)
    out=DEST/"redacao";out.mkdir()
    record={"step":20,"run_id":os.environ.get("GITHUB_RUN_ID"),"source_run_id":SOURCE_RUN,
            "mode":"targeted_model_patches_full_independent_review",
            "fixture_id":FID,"publication_enabled":False,"status":"running",
            "before_cost_usd":str(prior_cost),"started_at":datetime.now(TZ).isoformat(),
            "attempts":[]}
    job.update(status="running",second_step20_retry_started=True,second_step20_run_id=record["run_id"])
    remote.save()
    cfg["max_paid_calls_per_fixture"]=int(job.get("api_calls",0))+10
    caller=BudgetCaller(remote,FID,config=cfg)
    providers=read(ROOT/"config/redacao-pos-jogo.json")
    provider=providers["provider"];patch_provider=providers.get("patch_provider",provider)
    calls=[]
    def paid(payload,stage):
        result=caller(payload)
        calls.append({"stage":stage,"usage":result.get("usage"),"response_id":result.get("id")})
        save(out/"chamadas.json",calls)
        return response_object(result)
    try:
        for attempt in range(1,4):
            current=validate(article,package["allowed_internal_urls"])
            request=patch_request(package,article,issues,patch_provider)
            user=json.loads(request["input"][1]["content"])
            desired=650
            user["word_budget"]["minimum_words_in_replaced_body_units"]=max(
                user["word_budget"]["minimum_words_in_replaced_body_units"],
                desired-user["word_budget"]["unchanged_body_words"])
            user["word_budget"]["preferred_words_in_replaced_body_units"]=max(
                user["word_budget"]["preferred_words_in_replaced_body_units"],
                685-user["word_budget"]["unchanged_body_words"])
            request["input"][1]["content"]=json.dumps(user,ensure_ascii=False)
            request["input"][0]["content"] += (
                "\\nRevisao final do passo 20. O artigo como um todo deve ter entre 630 e "
                "760 palavras no CORPO depois da substituicao, com informacoes reais "
                "dos 19 fatos narrativos e dados dos jogos. Corrija as pendencias "
                "listadas, preserve a sequencia dos lances e evite repetir o mesmo "
                "lance em diferentes blocos. Nao invente estatisticas ou conclusoes "
                "para aumentar a extensao. Entregue apenas as unidades solicitadas."
            )
            patch=paid(request,"patch_"+str(attempt))
            save(out/"patch-"+str(attempt)+".json",patch)
            article=apply_patch(article,patch,issues)
            save(out/"artigo-"+str(attempt)+".json",article)
            check=validate(article,package["allowed_internal_urls"])
            if not check["format_passed"] or check["body_words"]<620:
                # Se a extensao ainda estiver insuficiente, apontar blocos explicitos
                # para aprofundamento factual, sem aprovar ou simular uma revisao.
                chosen=[i for i,b in enumerate(article["blocks"]) if b["type"]=="paragraph"]
                if not chosen:raise ValueError("Sem paragrafos para corrigir")
                ix=chosen[min(2,len(chosen)-1)]
                issues=["block_"+str(ix)+": Reestruture com fatos confirmados do pacote, "
                        "sem repetir lances; texto total precisa de pelo menos 630 palavras."]
                record["attempts"].append({"attempt":attempt,"status":"format_rejected","words":check["body_words"],"errors":check["errors"]})
                continue
            reviews=[]
            for n in (1,2):
                review=paid(review_request(package,article,provider),"review_"+str(attempt)+"_"+str(n))
                save(out/"revisao-"+str(attempt)+"-"+str(n)+".json",review)
                reviews.append(review)
            merged=merge_reviews(reviews,package,article)
            issues=validate_review(merged,package,article)
            record["attempts"].append({"attempt":attempt,"status":"rejected" if issues else "approved",
                                      "body_words":check["body_words"],"issues":issues})
            if issues:continue
            metadata={"model":patch_provider["model"],"review_model":provider["model"],
                      "patch_model":patch_provider["model"],"automatic_model_run":True,
                      "publication_enabled":False,"human_review_required":True,"fixture_id":FID,
                      "semantic_review_passed":True,"format_passed":True,
                      "written_at":datetime.now(timezone.utc).isoformat(),
                      "article_sha256":sha(article),"package_sha256":sha(package),"calls":calls}
            save(out/"artigo.json",article);save(out/"metadata.json",metadata);save(out/"validacao.json",check)
            report=package_reviewed(DEST,Path("current-main"),links)
            if (report.get("body_ad_count")!=3 or report.get("fixed_shell_unchanged") is not True
                or report.get("publication_enabled") is not False or
                not report.get("old_news_preserved") or not report.get("old_sitemap_preserved")):
                raise ValueError("Falha de pacote com anuncios, noticias ou sitemap")
            record.update(status="package_ready_pending_human_review",package=report)
            job.update(status="package_ready",package=report,
                       artifact_name="pos-jogo-passo20-conclusao-"+str(record["run_id"]),
                       review_run_url="https://github.com/Vernay1903/Vernay1903.github.io/actions/runs/"+str(record["run_id"]))
            break
        else:
            raise ValueError("Revisao completa nao aprovou o artigo apos correcoes limitadas")
    except Exception as exc:
        record.update(status="blocked",reason=str(exc));job["status"]="blocked"
        raise
    finally:
        after=spent(remote.data)
        record.update(after_cost_usd=str(after),additional_cost_usd=str(after-prior_cost),
                      finished_at=datetime.now(TZ).isoformat())
        if after>Decimal("0.10"):
            record["status"]="blocked_budget_violation";job["status"]="blocked"
        remote.save();save(DEST/"resultado.json",record)
        print(json.dumps(record,ensure_ascii=False),flush=True)

if __name__=="__main__":main()
