#!/usr/bin/env python3
"""Transmissões equivalentes não geram falso conflito; emissoras diferentes seguem bloqueadas."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import extrair_fatos_estruturados as extrair

def source(publisher, url, segment):
    return {
        "publisher": publisher, "url": url,
        "source_type": "major_sports_media",
        "title": "Palmeiras x Bahia: onde assistir",
        "checked_at": "2026-10-08T12:00:00-03:00",
        "content_checked": True,
        "eligible_for_factual_validation": True,
        "page_evidence": {
            "metadata": {"title": "Palmeiras x Bahia: onde assistir"},
            "evidence_segments": [segment],
        },
    }

def main():
    a = "TV Globo , ge tv e Premiere"
    b = "Globo (TV aberta), do Premiere (pay-per-view) e da Getv (YouTube)"
    assert extrair.normalize_transmission_broadcasters(a) == "TV Globo, ge tv e Premiere"
    assert extrair.normalize_transmission_broadcasters(b) == "TV Globo, ge tv e Premiere"
    assert extrair.normalize_transmission_broadcasters("Canal Desconhecido e Globo") == "Canal Desconhecido e Globo"
    config = extrair.load_config()
    requirement = {
        "id": "transmission", "status": "pending",
        "required_for_drafting": True, "allow_unavailable_after_check": True,
        "source_candidates": [
            source("ge", "https://ge.globo.com/palmeiras-bahia", "Transmissão: " + a + "."),
            source("Lance!", "https://www.lance.com.br/palmeiras-bahia", "Onde assistir: " + b + "."),
        ],
    }
    context = {"home": "Palmeiras", "away": "Bahia", "competition": "Brasileirão"}
    result = extrair.extract_transmission_requirement(requirement, match_context=context, config=config)
    assert result["status"] == "verified", (result.get("fact_extraction_status"), result.get("conflicts"), result.get("validator_errors"))
    assert result["facts"][0]["text"] == "Transmissão: TV Globo, ge tv e Premiere.", result["facts"]
    bad = dict(requirement, source_candidates=[
        requirement["source_candidates"][0],
        source("Teste", "https://www.espn.com.br/palmeiras-bahia", "Transmissão: ESPN e Disney+."),
    ])
    blocked = extrair.extract_transmission_requirement(bad, match_context=context, config=config)
    assert blocked["status"] != "verified" and blocked.get("conflict_detected") is True
    print("OK: canais equivalentes conciliados, conflito real bloqueado.")

if __name__ == "__main__":
    main()
