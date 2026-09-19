#!/usr/bin/env python3
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
q='"Brighton" "Arsenal" Premier League 2026 match'
sources={
 'google_news':"https://news.google.com/rss/search?"+urlencode({'q':q,'hl':'en-US','gl':'US','ceid':'US:en'}),
 'bing_news':"https://www.bing.com/news/search?"+urlencode({'q':q,'format':'rss'}),
 'bing_web':"https://www.bing.com/search?"+urlencode({'q':q,'format':'rss'}),
}
for name,url in sources.items():
 try:
  req=Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; CorteEsportes/1.0)"})
  with urlopen(req,timeout=18) as resp:
   raw=resp.read(250_000)
  root=ET.fromstring(raw)
  items=root.findall(".//item")[:5]
  print(name,"items",len(items))
  for x in items:
   link=x.findtext("link","")
   print(" ",urlparse(link).hostname, (x.findtext("title","") or "")[:110],link[:120])
 except Exception as exc:
  print(name,"falha",type(exc).__name__,str(exc)[:130])

for qx in ['site:premierleague.com Brighton Arsenal 2026 preview stadium referee',
           'site:arsenal.com Brighton Arsenal 2026 team news',
           'site:espn.com.br Sevilla Barcelona 2026 estatisticas']:
 url="https://www.bing.com/search?"+urlencode({'q':qx,'format':'rss'})
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=20) as resp: raw=resp.read(200_000)
  items=ET.fromstring(raw).findall(".//item")[:6]
  print("bing_site",qx,"items",len(items))
  for item in items:
   link=item.findtext("link","")
   print(" ",urlparse(link).hostname,(item.findtext("title","") or "")[:75])
 except Exception as e: print("bing_site_error",type(e).__name__,str(e)[:120])
