"""Monta o HTML com o padrão fornecido pelo editor, sem publicar."""
import argparse
import hashlib
import html
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from editorial_pos_jogo import ROOT,validate

# Somente estas regiões podem variar no documento fornecido pelo editor.
FIELDS={
 'page_title':r'(<title>)(.*?)(</title>)',
 'description':r'(<meta name="description" content=")(.*?)("\s*/>)',
 'title':r'(<h1 id="articleTitle">)(.*?)(</h1>)',
 'excerpt':r'(<p class="subhead" id="articleExcerpt">)(.*?)(</p>)',
 'date':r'(<span id="articleDate">)(.*?)(</span>)',
 'category':r'(<a id="categoryLink" href="#">)(.*?)(</a>)',
 'body':r'(<article id="articleBody">)(.*?)(</article>)',
 'category_slug_js':r'(const CATEGORY_SLUG = )(.*?)(;)',
 'category_name_js':r'(const CATEGORY_NAME = )(.*?)(;)'
}


def replace_field(text,key,value):
    pattern=FIELDS[key]
    if len(list(re.finditer(pattern,text,re.S)))!=1:raise ValueError('Campo ausente/duplicado no padrão: '+key)
    return re.sub(pattern,lambda m:m[1]+value+m[3],text,count=1,flags=re.S)


def fixed_shell(text):
    for key in FIELDS:text=replace_field(text,key,'__'+key+'__')
    return text


def words(text):return len(re.findall(r'\b[\wÀ-ÿ]+\b',re.sub('<[^>]+>','',text)))


class Inline(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[]
    def handle_data(self,data):self.parts.append(html.escape(data,quote=False))
    def handle_starttag(self,tag,attrs):
        if tag!='a' or len(attrs)!=1 or attrs[0][0]!='href':raise ValueError('Marcação não permitida')
        self.parts.append('<a href="'+html.escape(attrs[0][1],quote=True)+'">')
    def handle_endtag(self,tag):
        if tag!='a':raise ValueError('Marcação não permitida')
        self.parts.append('</a>')


def inline(text):
    p=Inline();p.feed(text);p.close();return ''.join(p.parts)


def ad_positions(blocks,policy):
    counts=[words(b['text']) for b in blocks];total=sum(counts)
    desired=3 if total>=policy['three_ads_from_words'] else 2 if total>=policy['two_ads_from_words'] else 1
    desired=min(desired,policy['max_body_ads'])
    candidates=[];cumulative=0
    for i,(block,count) in enumerate(zip(blocks,counts)):
        cumulative+=count
        # Não inserir dentro de parágrafos/listas nem após um subtítulo.
        if block['type']!='paragraph' or i==len(blocks)-1 or blocks[i+1]['type']=='list':continue
        if cumulative>=policy['minimum_intro_words'] and total-cumulative>=policy['minimum_tail_words']:
            candidates.append((i,cumulative))
    selected=[];previous=0
    for n in range(1,desired+1):
        eligible=[p for p in candidates if p[1]-previous>=policy['minimum_gap_words']]
        if not eligible:break
        pos=min(eligible,key=lambda p:abs(p[1]-total*n/(desired+1)))
        selected.append(pos[0]);previous=pos[1]
    return selected


def render_html(article,published_on,allowed_urls):
    config=json.loads((ROOT/'config/html-pos-jogo.json').read_text())
    raw=(ROOT/config['template']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=config['sha256']:raise ValueError('HTML padrão alterado sem nova validação')
    template=raw.decode('utf-8')
    check=validate(article,allowed_urls)
    if not check['format_passed']:raise ValueError('; '.join(check['errors']))
    parsed=datetime.strptime(published_on,'%d/%m/%Y')
    if parsed.strftime('%d/%m/%Y')!=published_on:raise ValueError('Data deve ser DD/MM/AAAA')
    original_body=re.search(FIELDS['body'],template,re.S)[2]
    ads=re.findall(r'<!-- ANÚNCIO \(ARTIGO - (?:TOPO|MEIO|FIM)\) -->.*?</div>',original_body,re.S)
    if len(ads)!=3:raise ValueError('Blocos de anúncio do modelo não reconhecidos')
    positions=ad_positions(article['blocks'],config['ads']);parts=[];ad_index=0
    for i,block in enumerate(article['blocks']):
        text=inline(block['text'])
        if block['type']=='paragraph':parts.append('<p>'+text+'</p>')
        elif block['type']=='subtitle':parts.append('<p><strong>'+text+'</strong></p>')
        else:
            items=[inline(re.sub(r'^\s*[-•]\s+','',line)) for line in block['text'].splitlines() if line.strip()]
            parts.append('<ul style="list-style-type: disc;">'+''.join('<li>'+x+'</li>' for x in items)+'</ul>')
        if i in positions:parts.append(ads[ad_index]);ad_index+=1
    newline='\r\n' if '\r\n' in template else '\n'
    values={'page_title':html.escape(article['title']+' | Corte dos Esportes'),
        'description':html.escape(article['excerpt'],quote=True),'title':html.escape(article['title']),
        'excerpt':html.escape(article['excerpt']),'date':published_on,
        'category':config['category'],'category_slug_js':json.dumps(config['category_slug']),
        'category_name_js':json.dumps(config['category'],ensure_ascii=False),
        'body':newline+newline.join(parts)+newline}
    output=template
    for key,value in values.items():output=replace_field(output,key,value)
    if fixed_shell(template)!=fixed_shell(output):raise ValueError('Alteração fora dos campos permitidos')
    return output,{'template_sha256':config['sha256'],'fixed_shell_unchanged':True,
        'title_chars':check['title_chars'],'body_words':check['body_words'],'body_ad_count':len(positions),
        'ad_after_blocks':positions,'publication_enabled':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--article',required=True,type=Path);p.add_argument('--links',required=True,type=Path)
    p.add_argument('--date',required=True);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();out=a.output.resolve()
    if not out.is_relative_to((ROOT/'build/pos-jogo').resolve()):raise ValueError('Saída fora do piloto')
    result,report=render_html(json.loads(a.article.read_text()),a.date,json.loads(a.links.read_text()))
    out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(result.encode('utf-8'))
    out.with_suffix('.validacao.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
