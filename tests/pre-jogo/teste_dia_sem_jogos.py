#!/usr/bin/env python3
"""Dias sem jogos são sucesso sem custo; bloqueio editorial e duplicidade não são dias vazios."""
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


def rejected(games,plans):
    try:
        empty.build_empty_manifest(games,plans,target=TARGET,source_sha=SHA)
    except ValueError:
        return
    raise AssertionError("Lote sem jogos foi aceito com dados incompatíveis.")


def main():
    games,plans=records()
    manifest=empty.build_empty_manifest(games,plans,target=TARGET,source_sha=SHA)
    assert manifest["no_eligible_matches"] is True
    assert manifest["articles"] == [] and manifest["skipped"] == []
    assert manifest["prepared_count"] == 0 and manifest["skipped_count"] == 0
    assert manifest["publication_unlocked"] is False
    assert manifest["source_main_sha"] == SHA
    assert manifest["grounded_fact_fallback_attempted"] is False
    a,b=records()
    a["selected_count"]=1
    a["matches"]=[{"id":1}]
    rejected(a,b)
    a,b=records()
    b["planned_count"]=1
    b["planned"]=[{"id":1}]
    rejected(a,b)
    a,b=records()
    b["skipped_count"]=1
    b["skipped"]=[{"id":1,"reason":"duplicado"}]
    rejected(a,b)
    a,b=records()
    b["target_date"]="2026-09-21"
    rejected(a,b)
    a,b=records()
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        build=root/"build"/"pre-jogo"
        build.mkdir(parents=True)
        (build/f"jogos-{TARGET}.json").write_text(json.dumps(a),encoding="utf-8")
        (build/f"planos-{TARGET}.json").write_text(json.dumps(b),encoding="utf-8")
        with mock.patch.object(empty,"ROOT",root), mock.patch.object(empty,"BUILD",build), \
             mock.patch.object(sys,"argv",["script","--date",TARGET,"--source-main-sha",SHA,"--force"]):
            empty.main()
            got=json.loads((build/"automatico"/"manifest.json").read_text(encoding="utf-8"))
            assert got["no_eligible_matches"] is True
            assert list((build/"automatico").iterdir()) == [build/"automatico"/"manifest.json"]
            assert not (root/"noticias.json").exists()
            assert not (root/"agenda.json").exists()
            (build/f"jogos-{TARGET}.json").write_text(json.dumps({
                "target_date":TARGET,"selected_count":1,"matches":[{"id":1}]
            }),encoding="utf-8")
            try:
                empty.main()
            except ValueError:
                pass
            else:
                raise AssertionError("Não deve registrar zero jogos quando há um.")
            assert got == json.loads((build/"automatico"/"manifest.json").read_text())
    # Simulação da ETAPA FINAL: zero alterações mesmo contra noticias/sitemap reais.
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        manifest_file=folder/"manifest.json"
        manifest_file.write_text(json.dumps(manifest),encoding="utf-8")
        approved=folder/"approved.txt"
        approved.write_text("",encoding="utf-8")
        report_file=apply_batch.BUILD/"teste-aplicacao-dia-sem-jogos.json"
        before_news=apply_batch.NOTICIAS.read_bytes()
        before_sitemap=apply_batch.SITEMAP.read_bytes()
        with mock.patch.object(sys,"argv",[
            "script","--manifest",str(manifest_file),
            "--artifact-root",str(folder),
            "--approved",str(approved),
            "--previews-root",str(folder),
            "--report",str(report_file),
            "--dry-run",
        ]):
            apply_batch.main()
        report=json.loads(report_file.read_text(encoding="utf-8"))
        assert report["selected_count"]==0 and report["changed_file_count"]==0
        assert report["changed_files"]==[]
        assert not report["push_executed"] and not report["commit_created"]
        assert apply_batch.NOTICIAS.read_bytes()==before_news
        assert apply_batch.SITEMAP.read_bytes()==before_sitemap
        report_file.unlink()
    print("OK: dia sem jogos é declarativo; não mascara bloqueios ou duplicatas e não toca no site.")


if __name__=="__main__":
    main()
