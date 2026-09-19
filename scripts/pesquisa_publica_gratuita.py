#!/usr/bin/env python3
"""Busca pública GRATUITA por RSS e leitura direta de páginas.

Não utiliza Serper, OpenAI, serviços de proxy ou mecanismo com créditos.
Feed = descoberta, NUNCA evidência factual; o conteúdo da URL original é
obtido separadamente e passa pelos validadores editoriais já existentes.
Não permite URL de IP interno, credenciais na URL nem HTTP no destino.
"""
from __future__ import annotations

import html
import ipaddress
import os
import re
import socket
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from typing import Any

RSS_ENDPOINT = "https://www.bing.com/news/search"
MAX_RSS_BYTES = 500_000
MAX_PAGE_BYTES = 1_200_000
MAX_RESULTS = 8
USER_AGENT = "Mozilla/5.0 (compatible; CorteDosEsportes/1.0; editorial research)"
_SEARCH_CACHE: dict[str, dict[str, Any]] = {}
_PAGE_CACHE: dict[str, dict[str, Any]] = {}


def valid_public_https(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return False
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in {"localhost"} or hostname.endswith((".localhost", ".local", ".internal")):
        return False
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return addr.is_global


def domain_allowed(url: str, domains: list[str]) -> bool:
    hostname = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return not domains or any(
        hostname == domain.lower().removeprefix("www.")
        or hostname.endswith("." + domain.lower().removeprefix("www."))
        for domain in domains
    )


def original_link(raw: str) -> str | None:
    """Bing RSS usa apiclick http com parâmetro url=https://fonte/original."""
    parsed = urlparse(raw)
    if parsed.hostname in ("www.bing.com", "bing.com") and parsed.path.startswith("/news/apiclick"):
        raw = parse_qs(parsed.query).get("url", [""])[0]
    return raw if valid_public_https(raw) else None


def fetch(url: str, max_bytes: int = MAX_RSS_BYTES, timeout: int = 15) -> tuple[bytes, str]:
    if not valid_public_https(url):
        raise ValueError("Somente URL HTTPS pública é aceita.")
    req = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/xml, text/html, application/xhtml+xml",
        "Accept-Language": "pt-BR,pt;q=0.8,en;q=0.7",
    })
    with urlopen(req, timeout=timeout) as response:
        effective = response.geturl()
        if not valid_public_https(effective):
            raise ValueError("Redirecionamento para URL não pública bloqueado.")
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("Página excedeu o limite de bytes.")
        return raw, response.headers.get_content_charset() or "utf-8"


def search_rss(query: str, domains: list[str], config: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """Mesma interface de request_serper: organic com URLs originais verificáveis."""
    key = query + "|" + ",".join(sorted(domains))
    if key in _SEARCH_CACHE:
        return query, _SEARCH_CACHE[key]
    # Tempo de GitHub Actions e serviços públicos são finitos: encerrar busca
    # com ZERO candidatos, nunca inventar evidências nem comprar pesquisas.
    budget = max(1, min(80, int(os.environ.get("CDE_RSS_MAX_REQUESTS", "45"))))
    if len(_SEARCH_CACHE) >= budget:
        return query, {"organic": [], "public_feed_request_limit": True}
    if not query.strip():
        raise ValueError("Consulta RSS vazia.")
    q = query.strip()
    # Mantém o filtro local como autoridade: o buscador pode ignorar "site:".
    url = RSS_ENDPOINT + "?" + urlencode({"q": q, "format": "rss"})
    raw, _charset = fetch(url)
    root = ET.fromstring(raw)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in root.findall(".//item"):
        link = original_link(item.findtext("link", "").strip())
        if not link or link in seen or not domain_allowed(link, domains):
            continue
        title = html.unescape(item.findtext("title", "").strip())
        if not title:
            continue
        seen.add(link)
        candidates.append({
            "title": title,
            "link": link,
            "snippet": re.sub(r"<[^>]+>", " ", html.unescape(item.findtext("description", "")))[:450],
            "position": len(candidates) + 1,
            "date": item.findtext("pubDate"),
        })
        if len(candidates) >= MAX_RESULTS:
            break
    result = {"organic": candidates}
    _SEARCH_CACHE[key] = result
    return query, result


class TextExtractor(HTMLParser):
    BLOCK = {"p", "h1", "h2", "h3", "h4", "li", "blockquote", "time"}
    IGNORE = {"script", "style", "noscript", "svg", "form", "nav", "footer", "aside"}
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.depth = 0
        self.current: list[str] = []
        self.lines: list[str] = []
        self.title: list[str] = []
        self.in_title = False
        self.metadata: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.IGNORE:
            self.skip += 1
        if self.skip:
            return
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            info = dict(attrs)
            name = info.get("property") or info.get("name")
            content = info.get("content")
            if name in ("description", "og:title", "og:description") and content:
                self.metadata[name] = content[:450]
        if tag in self.BLOCK:
            self.flush()
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self.IGNORE:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == "title":
            self.in_title = False
        if tag in self.BLOCK:
            self.flush()
            self.depth = max(0, self.depth - 1)

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        if self.in_title:
            self.title.append(data)
        if self.depth:
            self.current.append(data)

    def flush(self) -> None:
        line = " ".join(" ".join(self.current).split())
        if len(line) >= 18:
            self.lines.append(line[:2500])
        self.current.clear()


def read_public_page(url: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """A falha de download não cria fatos: validador recebe conteúdo vazio."""
    if url in _PAGE_CACHE:
        return _PAGE_CACHE[url]
    raw, charset = fetch(url, max_bytes=MAX_PAGE_BYTES, timeout=20)
    decoder = raw.decode(charset, errors="replace")
    parser = TextExtractor()
    parser.feed(decoder)
    parser.flush()
    title = " ".join(" ".join(parser.title).split())
    if title:
        parser.metadata["title"] = title[:300]
    # O conteúdo textual, NÃO a manchete/descrição do RSS, é a evidência.
    content = "\n".join(dict.fromkeys(parser.lines))[:140_000]
    result = {"markdown": content, "metadata": parser.metadata, "credits": 0}
    _PAGE_CACHE[url] = result
    return result
