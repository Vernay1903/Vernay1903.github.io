#!/usr/bin/env python3
"""Reproduz falhas de 08/10 sem API: resposta truncada e texto fora do contrato."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scripts import redigir_pre_jogo_openai as writer
from scripts import preparar_redacao_pre_jogo as prepare
from teste_redacao_controlada import clean_package, valid_body


def main():
    cfg = writer.load_provider_config()
    site = prepare.load_config()
    contract = prepare.build_contract(clean_package(), config=site)
    draft = {'slug': contract['slug'], 'body_html': valid_body(),
             'fact_fields_used': contract['required_fact_fields']}
    def response(body):
        return {'status': 'completed', 'usage': {'input_tokens': 100, 'output_tokens': 100},
                'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(body)}]}]}
    good = response(draft)
    bad = response({**draft, 'body_html': '<p>Texto incompleto sem estrutura.</p>'})
    incomplete = {'status': 'incomplete', 'incomplete_details': {'reason': 'max_output_tokens'},
                  'usage': {'input_tokens': 100, 'output_tokens': 6000}, 'output': []}
    with tempfile.TemporaryDirectory() as tmp:
        audit = Path(tmp) / 'attempts.json'
        for initial in (bad, incomplete):
            with patch.object(writer, 'post_json', side_effect=[initial, good]) as api:
                _, validated, attempts = writer.generate_validated_draft(
                    contract, cfg, site, api_key='fake', audit_path=audit)
            assert api.call_count == 2
            assert validated['draft_validated'] and len(attempts) == 2
            assert attempts[0]['validation_errors'] and not attempts[1]['validation_errors']
            assert attempts[0]['estimated_cost_usd'] > 0
            assert api.call_args_list[1].args[2]['reasoning']['effort'] == 'none'
            assert api.call_args_list[1].args[2]['max_output_tokens'] == 6000
            second = api.call_args_list[1].args[2]
            if initial is bad:
                assert second['input'][-2]['role'] == 'assistant'
                assert 'NÃO validado' in second['input'][-1]['content'][0]['text']
                assert 'Acrescente ao menos' in second['input'][-1]['content'][0]['text']
        for responses, count in (([bad, bad], 2), ([RuntimeError('HTTP 401: unauthorized')], 1),
                                 ([incomplete, RuntimeError('HTTP 503: unavailable')], 2)):
            with patch.object(writer, 'post_json', side_effect=responses) as api:
                try:
                    writer.generate_validated_draft(contract, cfg, site, api_key='fake', audit_path=audit)
                except SystemExit:
                    pass
                else:
                    raise AssertionError('Texto inválido não pode ser liberado')
            assert api.call_count == count
            saved = json.loads(audit.read_text())
            assert not saved['draft_validated'] and len(saved['attempts']) == count
    print('OK: recuperação editorial, limite total de 2 chamadas e auditoria de rejeições/custos.')

if __name__ == '__main__':
    main()
