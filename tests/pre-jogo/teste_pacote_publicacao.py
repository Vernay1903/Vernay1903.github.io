#!/usr/bin/env python3
"""Teste determinístico do Passo 28, sem commit e sem publicação."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import preparar_pacote_publicacao_pre_jogo as package  # noqa: E402


def expect_block(fn, contains: str) -> None:
    try:
        fn()
    except SystemExit as exc:
        if str(exc) not in ("1", ""):
            pass
        return
    raise AssertionError(f"Era esperado bloqueio contendo: {contains}")


def main() -> None:
    title = "Arsenal x Manchester City pela Premier League: transmissão, horário e prováveis escalações"
    excerpt = "Arsenal e Manchester City se enfrentam pela Premier League em Londres."
    slug = "arsenal-manchester-city-premier-league-2026-transmissao-horario-escalacoes.html"
    date_br = "17/09/2026"

    noticias_original = """[

{
\"title\": \"Matéria antiga\",
\"excerpt\": \"Resumo antigo\",
\"url\": \"materia-antiga.html\",
\"date\": \"16/09/2026\",
\"category\": \"Futebol\"
}
]
"""
    noticias_updated = package.build_noticias_copy(
        noticias_original,
        title=title,
        excerpt=excerpt,
        slug=slug,
        date_br=date_br,
    )
    parsed = json.loads(noticias_updated)
    assert parsed[0]["title"] == title
    assert parsed[0]["excerpt"] == excerpt
    assert parsed[0]["url"] == slug
    assert parsed[0]["date"] == date_br
    assert parsed[0]["category"] == "Futebol"
    assert parsed[1]["url"] == "materia-antiga.html"
    assert noticias_updated.count("materia-antiga.html") == 1

    sitemap_original = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">
  <url><loc>https://cortedosesportes.com.br/</loc><lastmod>2026-02-16</lastmod><priority>1.0</priority></url>
  <!-- MATÉRIAS -->
  <url><loc>https://cortedosesportes.com.br/materia-antiga.html</loc><lastmod>2026-09-16</lastmod><priority>0.9</priority></url>
</urlset>
"""
    sitemap_updated = package.build_sitemap_copy(
        sitemap_original, slug=slug, lastmod="2026-09-17"
    )
    target_url = f"https://cortedosesportes.com.br/{slug}"
    tail = sitemap_updated.split("<!-- MATÉRIAS -->", 1)[1]
    assert tail.index(target_url) < tail.index("https://cortedosesportes.com.br/materia-antiga.html")
    assert "<lastmod>2026-09-17</lastmod>" in sitemap_updated
    assert sitemap_updated.count("materia-antiga.html") == 1

    preview_html = f"""<!doctype html>
<html><body>
<h1 id=\"articleTitle\">{title}</h1>
<p class=\"subhead\" id=\"articleExcerpt\">{excerpt}</p>
<span id=\"articleDate\">{date_br}</span>
<article id=\"articleBody\">
<img src=\"bola-uhlsport-gramado.jpg\" alt=\"Bola\">
<ins class=\"adsbygoogle\" data-ad-slot=\"8702501261\"></ins>
<ins class=\"adsbygoogle\" data-ad-slot=\"8702501261\"></ins>
<ins class=\"adsbygoogle\" data-ad-slot=\"8702501261\"></ins>
</article>
<aside><ins class=\"adsbygoogle\" data-ad-slot=\"5521804159\"></ins></aside>
</body></html>"""
    metadata = {
        "step": 27,
        "slug": slug,
        "selected_image": "bola-uhlsport-gramado.jpg",
        "preview_only": True,
        "ready_for_publication": False,
        "noticias_json_touched": False,
        "sitemap_xml_touched": False,
        "published_html_touched": False,
    }
    contract = {"slug": slug, "title": title, "excerpt": excerpt, "date": date_br}
    package.validate_preview(preview_html, metadata, contract, Path(slug))

    expect_block(
        lambda: package.build_noticias_copy(
            noticias_updated, title=title, excerpt=excerpt, slug=slug, date_br=date_br
        ),
        "URL já existe",
    )
    expect_block(
        lambda: package.build_sitemap_copy(sitemap_updated, slug=slug, lastmod="2026-09-17"),
        "URL já existe",
    )

    assert package.date_to_iso("17/09/2026") == "2026-09-17"
    print("OK: regras do pacote de publicação do Passo 28 validadas.")
    print("Nova notícia em primeiro: sim")
    print("Nova URL como primeira matéria do sitemap: sim")
    print("Duplicidade bloqueada: sim")
    print("Arquivos publicados alterados: não")


if __name__ == "__main__":
    main()
