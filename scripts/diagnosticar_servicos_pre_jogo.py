#!/usr/bin/env python3
"""Checa fontes e acesso ao modelo com uma resposta mínima, sem publicar matérias."""
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts import pesquisa_publica_gratuita as public
from scripts import redigir_pre_jogo_openai as writer


def check_model():
    config = json.loads((ROOT/'config/redacao-pre-jogo.json').read_text())
    token = os.environ.get('OPENAI_API_KEY', '').strip()
    if not token:
        raise RuntimeError('OPENAI_API_KEY ausente.')
    model = config['provider']['model']
    # Chaves restritas podem permitir Responses e negar GET /models.
    # Usa o mesmo endpoint/modelo da redação, com no máximo 256 tokens de saída.
    provider = config['provider']
    result = writer.post_json(provider['endpoint'], token, {
        'model': model, 'input': 'Responda somente OK.', 'max_output_tokens': 256,
        'reasoning': {'effort': provider['reasoning_effort']}, 'store': False,
    }, timeout=provider['timeout_seconds'])
    text = writer.extract_output_text(result)
    if 'OK' not in text.upper():
        raise RuntimeError('Resposta mínima do redator não confirmada.')
    print('OK: Responses API e modelo de redação responderam ao teste mínimo.')



def main():
    import subprocess
    from datetime import datetime
    from zoneinfo import ZoneInfo
    date = datetime.now(ZoneInfo('America/Sao_Paulo')).date().isoformat()
    subprocess.run([sys.executable, 'scripts/buscar_fixtures_football_data.py',
                    '--date', date, '--force'], cwd=ROOT, check=True)
    _, result = public.search_rss('Arsenal futebol', [])
    if not result.get('organic'):
        raise RuntimeError('Nenhum resultado de descoberta no teste da busca pública.')
    print(f'OK: descoberta pública retornou {len(result["organic"])} URLs; não são fatos validados.')
    check_model()


if __name__ == '__main__': main()
