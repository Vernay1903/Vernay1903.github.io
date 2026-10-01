#!/usr/bin/env python3
"""Checa fontes e acesso ao modelo sem consumir tokens ou publicar matérias."""
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts import pesquisa_publica_gratuita as public
from scripts import buscar_fixtures_football_data as fixtures


def check_model():
    config = json.loads((ROOT/'config/redacao-pre-jogo.json').read_text())
    token = os.environ.get('OPENAI_API_KEY', '').strip()
    if not token:
        raise RuntimeError('OPENAI_API_KEY ausente.')
    model = config['provider']['model']
    # GET apenas verifica o modelo e a chave; não finge comprovar saldo/redação.
    request = Request('https://api.openai.com/v1/models/' + model,
                      headers={'Authorization': 'Bearer ' + token})
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get('id') != model:
        raise RuntimeError('Modelo retornado difere da configuração.')
    print('OK: chave OpenAI aceita e modelo acessível; nenhuma redação cobrada.')


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
