#!/usr/bin/env python3
"""Falha real reproduzida: HTML de erro, fallback RSS, publicação parcial e Pages."""
import sys
import tempfile
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import pesquisa_publica_gratuita as rss
from scripts import confirmar_pages_pre_jogo as pages
from scripts import verificar_resultado_pre_jogo as outcome
from scripts import preparar_lote_pre_jogo_automatico as prepare


def main():
    rss._SEARCH_CACHE.clear()
    rss._RSS_REQUESTS = 0
    feed = b'<rss><channel><item><title>Partida</title><link>https://arsenal.com/preview</link></item></channel></rss>'
    calls = []
    def fetch(url, **kw):
        calls.append(url)
        return (feed if url.startswith(rss.WEB_RSS_ENDPOINT+'?') else b'<html>erro</html>', 'utf-8')
    with patch.object(rss, 'fetch', side_effect=fetch):
        _, value = rss.search_rss('Arsenal teste', ['arsenal.com'])
    assert value['organic'][0]['link'] == 'https://arsenal.com/preview'
    assert len(calls) == 3
    rss._SEARCH_CACHE.clear()
    rss._RSS_REQUESTS = 0
    with patch.object(rss, 'fetch', return_value=(b'<html>erro</html>', 'utf-8')):
        try: rss.search_rss('teste', [])
        except ValueError: pass
        else: raise AssertionError('HTML não pode significar zero notícias')
    assert not rss._SEARCH_CACHE
    assert outcome.pending({'skipped': [{'slug': 'bloqueada'}]}, {'skipped': []})
    assert not outcome.pending({'skipped': []}, {'skipped': [{'reason': 'html_already_exists'}]})
    responses = [{}, {'status': 'built', 'commit': 'abc'}]
    with patch.object(pages, 'api', side_effect=responses) as api, patch.object(pages, 'live_check') as live:
        pages.confirm('owner/repo', 'abc', 'https://example.com', ['jogo.html'])
        assert api.call_args_list[0].args == ('repos/owner/repo/pages/builds', 'POST')
        live.assert_called_once_with('https://example.com', ['jogo.html'])
    # API legada com erro, mas a execução substituta terminou corretamente.
    responses = [{}, {'status': 'errored', 'error': {'message': 'Page build failed.'}},
                 {'workflow_runs': [{'path': 'dynamic/pages/pages-build-deployment',
                                     'conclusion': 'success', 'head_sha': 'abc', 'id': 123}]}]
    with patch.object(pages, 'api', side_effect=responses), patch.object(pages, 'live_check') as live:
        pages.confirm('owner/repo', 'abc', 'https://example.com', ['jogo.html'])
        live.assert_called_once()
    with patch.object(pages, 'api', return_value={'status': 'behind'}):
        assert not pages.includes_commit('owner/repo', 'new', 'old')
    # Só reutilizar redações com a mesma data, SHA e hashes íntegros.
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        now = datetime.now(ZoneInfo('America/Sao_Paulo'))
        data = {'step': 34, 'target_date': now.date().isoformat(), 'source_main_sha': 'a'*40,
                'generated_at': now.isoformat(), 'articles': [{'slug': 'jogo.html'}]}
        (directory/'manifest.json').write_text(json.dumps(data))
        with patch('scripts.aplicar_lote_pre_jogo_automatico.validate_artifact_files') as validate:
            assert 'jogo.html' in prepare.reusable_articles(directory, data['target_date'], 'a'*40)
            validate.assert_called_once()
            assert prepare.reusable_articles(directory, data['target_date'], 'b'*40) == {}
    print('OK: fallback, falha explícita, reuso, pendências e confirmação Pages.')


if __name__ == '__main__': main()
