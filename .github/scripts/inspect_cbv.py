"""Diagnóstico de leitura somente leitura: estrutura HTML das páginas CBV."""
from html.parser import HTMLParser
from collections import Counter
import re
import urllib.request

class Probe(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts=[]
        self.tags=Counter()
        self.stack=[]
        self.pos=[]
        self.scripts=[]
        self.inscript=False
    def handle_starttag(self,tag,attrs):
        self.tags[tag]+=1
        a=dict(attrs)
        if tag=="script":
            self.inscript=True
            self.script_attrs=a
        if any("jogo" in (v or "").lower() or "match" in (v or "").lower() for v in a.values()):
            if len(self.pos)<12: self.pos.append((tag,{k:v for k,v in a.items() if k in ("class","data-testid","id","href")}))
    def handle_endtag(self,tag):
        if tag=="script":
            self.inscript=False
    def handle_data(self,data):
        if self.inscript:
            self.scripts.append((self.script_attrs.get("src"),len(data),data[:220]))
        elif data.strip():
            self.parts.append(data.strip())

for gender in ("masculina","feminina"):
    url="https://cbv.com.br/volei-de-quadra/superliga-a-"+gender
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"text/html","Accept-Language":"pt-BR,pt;q=0.9"})
    print("URL:",url)
    try:
        with urllib.request.urlopen(req,timeout=25) as response:
            raw=response.read(5_000_000).decode("utf-8","replace")
            print("STATUS",response.status,"HTML LENGTH",len(raw),"FINAL URL",response.url)
        p=Probe();p.feed(raw)
        print("HTML COUNTS",p.tags)
        print("MATCHY ATTRS",p.pos[:12])
        print("TEXT AROUND JOGO")
        for ix,txt in enumerate(p.parts):
            if re.fullmatch(r"Jogo \d+[\s·—–]*Rodada \d+",txt):
                print("CARD",ix,repr(p.parts[ix:ix+18]))
                if ix>220:break
        print("SCRIPTS TOTAL",len(p.scripts),"SAMPLE",p.scripts[:5])
        for marker in ["__NEXT_DATA__","self.__next_f.push","Jogo 55","Jogo 14","SADA CRUZEIRO","DENTIL PRAIA","application/ld+json","/api/"]:
            print("MARKER",marker,raw.find(marker))
            at=raw.find(marker)
            if at>=0: print("CONTEXT",repr(raw[max(at-400,0):at+600])[:1000])
    except Exception as exc:
        print("ERROR",type(exc).__name__,str(exc)[:500])
