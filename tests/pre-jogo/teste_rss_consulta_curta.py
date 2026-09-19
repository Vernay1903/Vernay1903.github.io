#!/usr/bin/env python3
"""Fallback do feed malformado: duas consultas gratuitas e nenhuma inferência."""
import os
import sys
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import pesquisa_publica_gratuita as rss

def main():
    rss._SEARCH_CACHE.clear()
    original="https://www.lance.com.br/futebol-nacional/flamengo-x-bragantino-previa.html"
    bing="http://www.bing.com/news/apiclick.aspx?"+urlencode({"url":original})
    payload=("<rss><channel><item><title>Flamengo x Bragantino: escalações</title>"
             f"<link>{bing.replace('&','&amp;')}</link><description>não verificado</description>"
             "</item></channel></rss>").encode()
    attempts=[]
    def fake_fetch(url,*a,**k):
        attempts.append(url)
        return ((b"<!DOCTYPE html><html>feed unavailable</html>" if len(attempts)==1 else payload),"utf-8")
    with patch.object(rss,"fetch",side_effect=fake_fetch), patch.dict(os.environ,{"CDE_RSS_MAX_REQUESTS":"8"}):
        _,result=rss.search_rss('"Flamengo" "Bragantino" "Brasileirao" 2026 escalações',
                                ["lance.com.br"])
    assert len(attempts)==2,attempts
    assert "Flamengo+Bragantino" in attempts[1],attempts
    assert result["organic"][0]["link"]==original
    assert result["organic"][0]["snippet"]=="não verificado"
    print("OK: RSS inválido recuperado por busca curta sem autenticação/Serper nem fato publicado.")

if __name__=="__main__":
    main()
