#!/usr/bin/env python3
"""Solicita build do Pages existente e confirma commit e URLs, sem editar o site."""
import argparse
import json
import os
import subprocess
import time
from urllib.request import Request, urlopen


def api(path, method='GET'):
    result = subprocess.run(['gh', 'api', '--method', method, path],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'GitHub API {method} {path}: {result.stderr.strip()}')
    return json.loads(result.stdout)


def includes_commit(repository, expected, actual):
    if expected == actual:
        return True
    if not actual:
        return False
    comparison = api(f'repos/{repository}/compare/{expected}...{actual}')
    return comparison.get('status') in {'ahead', 'identical'}


def live_check(site, slugs):
    # Cabeçalhos privados nunca são enviados ao site público.
    def get(path):
        request = Request(site + '/' + path,
                          headers={'Cache-Control': 'no-cache', 'User-Agent': 'CDE-Publication-Check/1.0'})
        with urlopen(request, timeout=20) as response:
            return response.read(5_000_000).decode('utf-8')
    if slugs:
        news = json.loads(get('noticias.json'))
        home = json.loads(get('noticias-home.json'))
        if home != news[:10]:
            raise ValueError('A home ainda não corresponde às dez primeiras notícias.')
        urls = {item.get('url') for item in news}
        if not set(slugs).issubset(urls):
            raise ValueError('Matérias ainda ausentes de noticias.json público.')
        for slug in slugs:
            body = get(slug)
            if '<article' not in body or slug not in body:
                raise ValueError(f'HTML publicado não corresponde à matéria: {slug}')
    else:
        if '<html' not in get('index.html').lower():
            raise ValueError('Home pública inválida.')


def confirm(repository, commit, site, slugs, timeout=900):
    endpoint = f'repos/{repository}/pages/builds'
    # Somente dispara o site existente; não muda source, domínio ou configuração.
    requested = api(endpoint, 'POST')
    build_path = endpoint + '/latest'
    requested_url = requested.get('url', '')
    expected_prefix = 'https://api.github.com/' + endpoint + '/'
    if requested_url.startswith(expected_prefix):
        build_path = requested_url.removeprefix('https://api.github.com/')
    deadline = time.monotonic() + timeout
    last_error = 'Build ainda não concluído.'
    while time.monotonic() < deadline:
        try:
            build = api(build_path)
            if build.get('status') == 'built' and includes_commit(repository, commit, build.get('commit')):
                live_check(site, slugs)
                print(f'PAGES CONFIRMADO: commit {build["commit"]}; {len(slugs)} matéria(s) acessível(is).')
                return
            if build.get('status') == 'errored':
                raise RuntimeError('Build do Pages falhou: ' + str(build.get('error')))
        except (OSError, ValueError) as exc:
            last_error = str(exc)
        time.sleep(10)
    raise RuntimeError('Pages não confirmado dentro do prazo: ' + last_error)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--commit', required=True)
    p.add_argument('--report')
    args = p.parse_args()
    slugs = []
    if args.report:
        with open(args.report, encoding='utf-8') as f:
            report = json.load(f)
        slugs = report['selected_slugs']
        slugs += [x['slug'] for x in report.get('skipped', [])
                  if x.get('reason') in {'html_already_exists', 'url_already_in_noticias', 'same_match_already_in_noticias'}]
    with open('config/pre-jogo.json', encoding='utf-8') as f:
        site = json.load(f)['article']['internal_link_domain'].rstrip('/')
    confirm(os.environ['GITHUB_REPOSITORY'], args.commit, site, slugs)


if __name__ == '__main__':
    main()
