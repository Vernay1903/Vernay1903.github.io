"""Prepara HTML, notícia e sitemap em uma pasta de teste; nunca publica."""
import argparse
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from montar_html_pos_jogo import ROOT, render_html

BASE = 'https://cortedosesportes.com.br/'
NS = '{http://www.sitemaps.org/schemas/sitemap/0.9}'


def slug_part(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Nome de clube/competição ausente')
    ascii_text = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    result = re.sub('[^a-z0-9]+', '-', ascii_text).strip('-')
    if not result:
        raise ValueError('Nome inválido')
    return result


def prepare(article, match, written_at, news_text, sitemap_text, allowed_urls, existing_files=()):
    # Instante registrado na redação, não o relógio de uma tentativa de publicação.
    instant = datetime.fromisoformat(written_at)
    if instant.tzinfo is None:
        raise ValueError('Instante da redação precisa informar fuso')
    day = instant.astimezone(ZoneInfo('America/Sao_Paulo')).date()
    year = date.fromisoformat(match['match_date']).year
    filename = '-'.join(slug_part(match[k]) for k in ('home', 'away', 'competition')) + f'-{year}-resultado.html'
    news = json.loads(news_text)
    if not isinstance(news, list) or any(not isinstance(n, dict) for n in news):
        raise ValueError('noticias.json precisa ser uma lista de objetos')
    if '<!DOCTYPE' in sitemap_text.upper() or '<!ENTITY' in sitemap_text.upper():
        raise ValueError('Declaração XML não permitida')
    root = ET.fromstring(sitemap_text)
    if root.tag != NS+'urlset':
        raise ValueError('Sitemap não é urlset no padrão esperado')
    loc = BASE + filename
    if filename in existing_files or any(n.get('url') in (filename, '/'+filename, loc) for n in news) or any(e.text == loc for e in root.iter(NS+'loc')):
        raise ValueError('URL já existente: revisão necessária; nada sobrescrito')
    html, report = render_html(article, day.strftime('%d/%m/%Y'), allowed_urls)
    entry = dict(title=article['title'], excerpt=article['excerpt'], url=filename,
                 date=day.strftime('%d/%m/%Y'), category='Futebol')
    # Inserção textual conserva integralmente os registros e sua formatação.
    opening = re.match(r'\s*\[', news_text)
    if not opening:
        raise ValueError('Abertura JSON inválida')
    at = opening.end()
    updated_news = news_text[:at] + '\n' + json.dumps(entry, ensure_ascii=False, indent=2) + (',' if news else '') + news_text[at:]
    if json.loads(updated_news) != [entry] + news:
        raise ValueError('Falha na preservação das notícias')
    marker = '<!-- MATÉRIAS -->'
    if sitemap_text.count(marker) != 1:
        raise ValueError('Marcador de matérias ausente/duplicado no sitemap')
    xml_entry = f'\n\n  <url>\n    <loc>{loc}</loc>\n    <lastmod>{day.isoformat()}</lastmod>\n    <priority>0.9</priority>\n  </url>'
    updated_map = sitemap_text.replace(marker, marker+xml_entry, 1)
    parsed = ET.fromstring(updated_map)
    if len(list(parsed)) != len(list(root))+1:
        raise ValueError('Falha na preservação do sitemap')
    report.update(filename=filename, written_at=written_at, article_date=entry['date'],
                  sitemap_lastmod=day.isoformat(), news_position=0,
                  old_news_preserved=True, old_sitemap_preserved=True)
    return {filename: html, 'noticias.json': updated_news, 'sitemap.xml': updated_map,
            'validacao.json': json.dumps(report, ensure_ascii=False, indent=2)+'\n'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('article', 'facts', 'news', 'sitemap', 'links', 'output', 'site-root'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--written-at', required=True)
    a = p.parse_args()
    out = a.output.resolve()
    if not out.is_relative_to((ROOT/'build/pos-jogo').resolve()) or out.exists():
        raise ValueError('Usar pasta nova dentro de build/pos-jogo')
    result = prepare(json.loads(a.article.read_text()), json.loads(a.facts.read_text())['match'],
                     a.written_at, a.news.read_bytes().decode('utf-8'), a.sitemap.read_bytes().decode('utf-8'),
                     json.loads(a.links.read_text()), [p.name for p in a.site_root.glob('*.html')])
    out.mkdir(parents=True)
    for name, content in result.items():
        (out/name).write_bytes(content.encode('utf-8'))
    print(result['validacao.json'])

if __name__ == '__main__':
    main()
