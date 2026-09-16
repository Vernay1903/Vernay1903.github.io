#!/usr/bin/env python3
"""Teste determinístico do cliente OpenAI do Passo 26, sem chamada externa."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import redigir_pre_jogo_openai as writer  # noqa: E402

CONTRACT_PATH = ROOT / "tests" / "pre-jogo" / "contrato-redacao-controlado.json"
OUTPUT = ROOT / "build" / "pre-jogo" / "teste-redator-openai.json"


def main() -> None:
    provider = writer.load_provider_config()
    site_config = writer.load_json(writer.SITE_CONFIG_PATH)
    contract = writer.load_json(CONTRACT_PATH)
    assert isinstance(site_config, dict)
    assert isinstance(contract, dict)

    writer.validate_contract_for_model(contract, site_config)
    request = writer.build_request(contract, provider)

    assert provider["provider"]["name"] == "openai-responses"
    assert provider["provider"]["endpoint"] == "https://api.openai.com/v1/responses"
    assert provider["provider"]["api_key_env"] == "OPENAI_API_KEY"
    assert provider["provider"]["model"] == "gpt-5.6-terra"
    assert request["model"] == "gpt-5.6-terra"
    assert request["store"] is False
    assert "tools" not in request
    assert "web_search" not in json.dumps(request, ensure_ascii=False).casefold()

    text_format = request["text"]["format"]
    assert text_format["type"] == "json_schema"
    assert text_format["strict"] is True
    schema = text_format["schema"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["slug"]["enum"] == [contract["slug"]]
    fact_schema = schema["properties"]["fact_fields_used"]
    assert "uniqueItems" not in fact_schema
    assert fact_schema["minItems"] == len(contract["required_fact_fields"])
    assert fact_schema["maxItems"] == len(contract["required_fact_fields"])

    serialized = json.dumps(request, ensure_ascii=False)
    lowered = serialized.casefold()
    assert "publisher" not in lowered
    assert "source_candidates" not in lowered
    assert "checked_at" not in lowered
    assert "provenance" not in lowered
    assert "https://cortedosesportes.com.br/premier-league-historia-campeoes.html" in serialized
    assert "é expressamente proibido citar" in lowered
    assert "use exclusivamente" in lowered

    fake_draft = {
        "slug": contract["slug"],
        "body_html": "<p>Rascunho controlado.</p>",
        "fact_fields_used": contract["required_fact_fields"],
    }
    fake_response = {
        "id": "resp_test_26",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(fake_draft, ensure_ascii=False),
                    }
                ],
            }
        ],
        "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    }
    parsed = writer.parse_draft(fake_response)
    assert parsed == fake_draft
    assert writer.usage_summary(fake_response)["total_tokens"] == 150

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "step": 26,
        "provider": provider["provider"]["name"],
        "model": provider["provider"]["model"],
        "endpoint": provider["provider"]["endpoint"],
        "structured_output_enabled": True,
        "contract_clean": True,
        "sources_sent_to_model": False,
        "provenance_sent_to_model": False,
        "web_search_enabled": False,
        "tools_enabled": False,
        "explicit_execute_required": True,
        "real_api_call_performed": False,
        "ready_for_html": False,
        "publication_unlocked": False,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("OK: cliente OpenAI do Passo 26 validado sem chamada externa.")
    print("Contrato enviado ao futuro redator contém somente pacote limpo.")
    print("Structured Output configurado: sim")
    print("Pesquisa web/ferramentas: não")
    print("Chamada real executada neste teste: não")
    print("HTML e publicação permanecem bloqueados.")


if __name__ == "__main__":
    main()
