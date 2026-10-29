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

    # Dados de cartões HTML renderizados, sem depender de scripts privados.
    class Cards(HTMLParser):
        def __init__(self):
            super().__init__()
            self.depth=0
            self.active=None
            self.cards=[]
            self.inscript=False
            self.times=[]
        def handle_starttag(self,tag,attrs):
            if tag=="script": self.inscript=True
            if self.active is not None:
                self.depth+=1
                if tag=="time": self.active["time_tags"].append(dict(attrs))
                if tag=="a": self.active["links"].append(dict(attrs).get("href",""))
            elif tag=="article":
                self.active={"attrs":dict(attrs),"text":[],"time_tags":[],"links":[]}
                self.depth=1
        def handle_endtag(self,tag):
            if self.active:
                self.depth-=1
                if self.depth==0:
                    self.cards.append(self.active)
                    self.active=None
            if tag=="script": self.inscript=False
        def handle_data(self,d):
            if self.active is not None and d.strip():self.active["text"].append(d.strip())
    cards=Cards()
    cards.feed(raw)
    print("CARDS",len(cards.cards))
    for ix,c in enumerate(cards.cards[:20]):
        print("CARD",ix,"ATTR",repr(c["attrs"])[:400],"TEXT",repr(c["text"][:35])[:750],"TIME",c["time_tags"][:4],"LINKS",c["links"][:5])
    for needle in ['href="/jogo/', 'Jogo<!-- -->', 'Rodada<!-- -->', '29/10', '30/10','2026-10-30','datetime=']:
        pos=raw.find(needle)
        print("RAW NEEDLE",needle,"INDEX",pos,"CONTEXT",repr(raw[pos-320:pos+1000])[:1350] if pos>0 else None)

    # Parse somente a serializacao publica React/Next embutida no HTML.
    import json
    scripts = re.findall(r'<script>(self\.__next_f\.push\(\[1,.*?\]\))</script>',raw,re.S)
    textblocks=[]
    for script in scripts:
        encoded=script.split("push(",1)[1].rsplit(")",1)[0]
        try:
            v=json.loads(encoded)
            if len(v)>1 and isinstance(v[1],str):
                textblocks.append(v[1])
        except Exception as e:
            print("RSC parse warning",repr(e)[:80])
    alltext="".join(textblocks)
    print("RSC decoded",len(alltext),"matches",alltext.count('"Match_ID"'),"dates",alltext.count('"MatchDateTime"'))
    for m in list(re.finditer(r'"Match_ID":(\d+)',alltext))[:8]:
        print("RSC GAME",repr(alltext[m.start():m.start()+1350])[:1600])
