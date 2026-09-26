#!/usr/bin/env python3
"""Lotes sem matéria não podem mascarar falhas, e não podem tocar no site."""
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import registrar_preparo_vazio_pre_jogo as empty
from scripts import aplicar_lote_pre_jogo_automatico as apply_batch

TARGET="2026-09-22"
SHA="a"*40

def records():
    return (
      {"target_date":TARGET,"selected_count":0,"matches":[],"input_count":0},
      {"target_date":TARGET,"planned_count":0,"planned":[],"skipped_count":0,"skipped":[]},
    )

def rejected(builder,games,plans):
    try:
        builder(games,plans,target=TARGET,source_sha=SHA)
    except ValueError:
        return
    raise AssertionError("Manifesto sem matéria foi aceito com dados incompatíveis.")

def main():
    games,plans=records()
    manifest=empty.build_empty_manifest(games,plans,target=TARGET,source_sha=SHA)
    assert manifest["no_eligible_matches"] is True and manifest["no_new_articles"] is False
    a,b=records(); a["selected_count"]=1; a["matches"]=[{"id":1}]
    rejected(empty.build_empty_manifest,a,b)

    games_dup={"target_date":TARGET,"selected_count":1,"matches":[{"id":9}],"input_count":1}
    plans_dup={"target_date":TARGET,"planned_count":0,"planned":[],"skipped_count":1,
               "skipped":[{"fixture_id":9,"reasons":["same_match_already_in_noticias"]}]}
    duplicate=empty.build_no_new_articles_manifest(games_dup,plans_dup,target=TARGET,source_sha=SHA)
    assert duplicate["no_eligible_matches"] is False and duplicate["no_new_articles"] is True
    assert duplicate["planning_skip_reasons"]==["same_match_already_in_noticias"]
    rejected(empty.build_no_new_articles_manifest,*records())

    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp); build=root/"build"/"pre-jogo"; build.mkdir(parents=True)
        (build/f"jogos-{TARGET}.json").write_text(json.dumps(games),encoding="utf-8")
        (build/f"planos-{TARGET}.json").write_text(json.dumps(plans),encoding="utf-8")
        with mock.patch.object(empty,"ROOT",root), mock.patch.object(empty,"BUILD",build), \
             mock.patch.object(sys,"argv",["script","--date",TARGET,"--source-main-sha",SHA,"--force"]):
            empty.main()
        assert json.loads((build/"automatico"/"manifest.json").read_text())["no_eligible_matches"] is True
        (build/f"jogos-{TARGET}.json").write_text(json.dumps(games_dup),encoding="utf-8")
        (build/f"planos-{TARGET}.json").write_text(json.dumps(plans_dup),encoding="utf-8")
        with mock.patch.object(sys,"argv",["script","--date",TARGET,"--source-main-sha",SHA,
                                           "--kind","no_new_articles","--force"]):
            empty.main()
        assert json.loads((build/"automatico"/"manifest.json").read_text())["no_new_articles"] is True
        assert not (root/"noticias.json").exists() and not (root/"agenda.json").exists()

    for sample in (manifest,duplicate):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            mf=folder/"manifest.json"; mf.write_text(json.dumps(sample),encoding="utf-8")
            approved=folder/"approved.txt"; approved.write_text("",encoding="utf-8")
            report_file=apply_batch.BUILD/"teste-aplicacao-lote-sem-materia.json"
            before_news=apply_batch.NOTICIAS.read_bytes(); before_sitemap=apply_batch.SITEMAP.read_bytes()
            with mock.patch.object(sys,"argv",["script","--manifest",str(mf),"--artifact-root",str(folder),
                "--approved",str(approved),"--previews-root",str(folder),"--report",str(report_file),"--dry-run"]):
                apply_batch.main()
            report=json.loads(report_file.read_text())
            assert report["selected_count"]==0 and report["changed_file_count"]==0
            assert apply_batch.NOTICIAS.read_bytes()==before_news and apply_batch.SITEMAP.read_bytes()==before_sitemap
            report_file.unlink()
    print("OK: dias sem jogos e jogos já descartados encerram sem pesquisa, OpenAI ou alteração do site.")

if __name__=="__main__":
    main()
