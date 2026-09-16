#!/usr/bin/env python3
"""Testes locais das travas do Passo 31, sem tocar no Git remoto."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "preflight_publicacao_pre_jogo.py"

spec = importlib.util.spec_from_file_location("preflight31", SCRIPT)
if spec is None or spec.loader is None:
    raise SystemExit("ERRO: não foi possível carregar o script do Passo 31.")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

slug = "arsenal-manchester-city-premier-league-2026-transmissao-horario-escalacoes.html"
current_news = '[\n{\n"title":"Antiga",\n"excerpt":"Anterior",\n"url":"antiga.html",\n"date":"16/09/2026",\n"category":"Futebol"\n}\n]\n'
new_item = {
    "title": "Arsenal x Manchester City pela Premier League: transmissão, horário e prováveis escalações",
    "excerpt": "Arsenal e Manchester City se enfrentam pela Premier League em Londres.",
    "url": slug,
    "date": "17/09/2026",
    "category": "Futebol",
}
old_item = json.loads(current_news)[0]
obj = module.render_news_object(
    new_item["title"], new_item["excerpt"], slug, new_item["date"]
)
prepared_news = "[\n\n" + obj + "," + current_news[current_news.find("[") + 1 :]
rebuilt_news = module.expected_noticias_from_current(current_news, prepared_news, slug)
if rebuilt_news != prepared_news:
    raise SystemExit("ERRO: reconstrução de noticias.json não é byte a byte estável.")
if json.loads(prepared_news)[1:] != [old_item]:
    raise SystemExit("ERRO: notícia antiga não foi preservada no teste.")

stale_news = json.dumps([new_item, {**old_item, "title": "Foi alterada"}], ensure_ascii=False)
try:
    module.expected_noticias_from_current(current_news, stale_news, slug)
except SystemExit:
    pass
else:
    raise SystemExit("ERRO: pacote obsoleto de noticias.json não foi bloqueado.")

current_sitemap = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">
<!-- MATÉRIAS -->
<url>
  <loc>https://cortedosesportes.com.br/antiga.html</loc>
  <lastmod>2026-09-16</lastmod>
  <priority>0.9</priority>
</url>
</urlset>
"""
entry = module.sitemap_entry(slug, "2026-09-17")
marker_pos = current_sitemap.index(module.SITEMAP_MARKER) + len(module.SITEMAP_MARKER)
prepared_sitemap = (
    current_sitemap[:marker_pos]
    + "\n\n  "
    + entry.replace("\n", "\n  ")
    + current_sitemap[marker_pos:]
)
rebuilt_sitemap = module.expected_sitemap_from_current(current_sitemap, prepared_sitemap, slug)
if rebuilt_sitemap != prepared_sitemap:
    raise SystemExit("ERRO: reconstrução de sitemap.xml não é byte a byte estável.")

source = SCRIPT.read_text(encoding="utf-8")
for forbidden in ('run_git("commit"', 'run_git("push"', "git push"):
    if forbidden in source:
        raise SystemExit(f"ERRO: Passo 31 contém operação proibida de publicação: {forbidden}")

print("OK: testes do Passo 31 passaram.")
print("Pacote obsoleto: bloqueado")
print("noticias.json atual: preservado")
print("sitemap.xml atual: preservado")
print("git commit no preflight: ausente")
print("git push no preflight: ausente")
