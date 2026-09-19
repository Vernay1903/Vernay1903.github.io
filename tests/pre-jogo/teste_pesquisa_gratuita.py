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
    assert not any(key in str(page) for key in ("Not a verified fact", "SERPER_API_KEY"))
    print("OK: RSS apenas descobre, página original fornece texto, Serper não é chamado.")


if __name__ == "__main__":
    main()
