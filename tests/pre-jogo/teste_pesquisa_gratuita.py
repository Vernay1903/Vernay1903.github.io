#!/usr/bin/env python3
"""Teste sem rede, sem Serper e sem chamada paga da pesquisa pública."""
import os
import sys
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import pesquisa_publica_gratuita as free
from scripts import buscar_fontes_serper as search
from scripts import ler_fontes_candidatas_base as reader

def main():
    free._SEARCH_CACHE.clear()
    free._PAGE_CACHE.clear()
    original = "https://www.arsenal.com/news/match-preview-2026"
    wrapped = "http://www.bing.com/news/apiclick.aspx?" + urlencode({"ref": "FexRss", "url": original})
    assert free.original_link(wrapped) == original
    assert free.original_link("https://127.0.0.1/admin") is None
    assert free.original_link("http://example.org") is None
    assert free.original_link("https://news.google.com/rss/articles/ABC") is not None
    assert free.domain_allowed(original, ["arsenal.com"])
    assert not free.domain_allowed(original, ["espn.com.br"])
    rss = ('<rss><channel><item><title>Brighton Arsenal Premier League 2026</title>'
           '<link>' + wrapped.replace("&", "&amp;") +
           '</link><description>Not a verified fact</description></item>'
           '<item><title>Other</title><link>https://other.com/article</link></item>'
           '</channel></rss>').encode()
    with patch.object(free, "fetch", return_value=(rss, "utf-8")):
        with patch.dict(os.environ, {"CDE_FREE_RESEARCH": "1", "SERPER_API_KEY": ""}):
            query, result = search.request_serper(
                query="Brighton Arsenal", domains=["arsenal.com"], config={})
    assert query == "Brighton Arsenal"
    assert [item["link"] for item in result["organic"]] == [original]
    html = ("<html><head><title>Arsenal x Brighton</title>"
            '<meta name="description" content="Preview oficial"></head><body>'
            "<nav>Compre nossos produtos de futebol</nav>"
            "<article><h1>Arsenal x Brighton pela Premier League 2026</h1>"
            "<p>O confronto acontecerá no Emirates Stadium, conforme o anúncio oficial.</p>"
            "<p>Transmissão será confirmada depois pela organização.</p></article>"
            "<script>var false_fact = 'Referee is INVENTED';</script></body></html>").encode("utf-8")
    with patch.object(free, "fetch", return_value=(html, "utf-8")):
        with patch.dict(os.environ, {"CDE_FREE_RESEARCH": "1", "SERPER_API_KEY": ""}):
            page = reader.request_serper_scrape(original, config={})
    assert page["credits"] == 0
    assert "Emirates Stadium" in page["markdown"]
    assert "INVENTED" not in page["markdown"]
    assert "Compre nossos produtos" not in page["markdown"]
    assert "Preview oficial" == page["metadata"]["description"]
    assert free._PAGE_CACHE[original] == page
    # Regressão: vários portais fecham <article> antes do bloco de escalações.
    # Esses jogadores devem continuar legíveis para a extração posterior.
    free._PAGE_CACHE.clear()
    lineup_html = (
        "<html><body><article><h1>Palmeiras x Fluminense 21/10/2026</h1>"
        "<p>A decisão da Libertadores será na quarta-feira.</p></article>"
        "<h3>Provável escalação do Palmeiras</h3>"
        "<p>Carlos Miguel; Murilo, Gustavo Gómez e Barboza; Giay, Marlon Freitas, "
        "Andreas Pereira, Lucas Evangelista e Piquerez; Arias e Flaco López. "
        "Técnico: Abel Ferreira.</p>"
        "<h3>Provável escalação do Fluminense</h3>"
        "<p>Fábio; Guga, Thiago Silva, Millán e Guilherme Arana; Nonato, "
        "Martinelli e Ganso; Canobbio, Savarino e Hulk. Técnico: Marcão.</p>"
        "</body></html>"
    ).encode("utf-8")
    with patch.object(free, "fetch", return_value=(lineup_html, "utf-8")):
        parsed_lineup = free.read_public_page(original)
    assert "Carlos Miguel;" in parsed_lineup["markdown"]
    assert "Thiago Silva" in parsed_lineup["markdown"]
    windows = reader.structured_lineup_windows(parsed_lineup["markdown"], 700)
    assert any("Palmeiras | Provável escalação:" in row for row in windows), windows
    assert any("Fluminense | Provável escalação:" in row for row in windows), windows
    free._PAGE_CACHE.clear()
    # Alguns portais apresentam os jogadores em DIVs, sem tags <p> ou <li>.
    div_html = (
        "<html><body><article><h1>Palmeiras x Fluminense 21/10/2026</h1>"
        "<div><h3>Provável escalação do Palmeiras</h3>"
        "<div>Carlos Miguel; Murilo, Gustavo Gómez e Barboza; Giay, "
        "Marlon Freitas, Andreas Pereira, Lucas Evangelista e Piquerez; "
        "Arias e Flaco López. Técnico: Abel Ferreira.</div></div>"
        "<div><h3>Provável escalação do Fluminense</h3>"
        "<div>Fábio; Guga, Thiago Silva, Millán e Guilherme Arana; "
        "Nonato, Martinelli e Ganso; Canobbio, Savarino e Hulk. "
        "Técnico: Marcão.</div></div>"
        "</article></body></html>"
    ).encode("utf-8")
    with patch.object(free, "fetch", return_value=(div_html, "utf-8")):
        div_page = free.read_public_page(original)
    div_windows = reader.structured_lineup_windows(div_page["markdown"], 700)
    assert any("Palmeiras | Provável escalação:" in row for row in div_windows), div_windows
    assert any("Fluminense | Provável escalação:" in row for row in div_windows), div_windows
    free._PAGE_CACHE.clear()
    # RSS malformado continua servindo apenas para descobrir URL original.
    malformed = (
        b'<rss><channel><item><title>Arsenal & City</title>'
        + ('<link>' + wrapped.replace("&", "&amp;") + '</link>').encode()
        + b'<description><![CDATA[Somente descoberta]]></description></item>'
        + b'<quebrado></channel></rss>'
    )
    rows = free._rss_items(malformed)
    assert len(rows) == 1
    assert "Arsenal" in rows[0]["title"]
    assert not any(key in str(page) for key in ("Not a verified fact", "SERPER_API_KEY"))
    with patch.dict(os.environ, {"CDE_FREE_RESEARCH": "1"}):
        gambling=search.normalize_serper_response({"organic":[
            {"title":"Palpite","link":"https://www.lance.com.br/sites-de-apostas/palpites/teste.html"},
            {"title":"Notícia jornalística","link":"https://www.lance.com.br/futebol-nacional/teste.html"}
        ]},allowed_domains=["lance.com.br"])
        assert len(gambling)==1 and gambling[0]["title"]=="Notícia jornalística"
    print("OK: RSS apenas descobre, página original fornece texto e apostas são excluídas.")


if __name__ == "__main__":
    main()
