"""Prepara instruções e valida formato editorial; não chama API nem publica."""
import argparse
import copy
import json
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def normalized(text):
    return unicodedata.normalize('NFC', text)


def prepare(facts, narrative, allowed_urls):
    if facts.get('ready_for_drafting') is not True:
        raise ValueError('Base factual ainda não liberada')
    if narrative.get('fixture_id') != facts['fixture_id'] or narrative.get('reviewed') is not True:
        raise ValueError('Apuração narrativa ausente/divergente')
    sources = {s['id']: s for s in narrative.get('sources', [])}
    if not narrative.get('claims'):
        raise ValueError('Sem fatos narrativos')
    for claim in narrative['claims']:
        if not claim.get('source_ids') or any(i not in sources or sources[i].get('opened') is not True for i in claim['source_ids']):
            raise ValueError('Fato sem página efetivamente consultada')
    clean = {k: copy.deepcopy(facts[k]) for k in ['fixture_id','match','venue','score','goals','campaign','competition_context','upcoming']}
    if 'outcome' in facts: clean['outcome'] = copy.deepcopy(facts['outcome'])
    # Notas de restrição não são fatos esportivos e não devem virar reportagem.
    clean['competition_context'].pop('note', None)
    from datetime import date
    weekdays=['segunda-feira','terça-feira','quarta-feira','quinta-feira','sexta-feira','sábado','domingo']
    clean['match']['weekday_brasilia']=weekdays[date.fromisoformat(clean['match']['match_date']).weekday()]
    for side in clean['upcoming'].values():
        for game in side.values():
            if isinstance(game,dict) and game.get('date_brasilia'):
                game['weekday_brasilia']=weekdays[date.fromisoformat(game['date_brasilia']).weekday()]
    # Valores em conflito e links de pesquisa não são entregues ao redator.
    return {'instructions': (ROOT/'prompts/pos-jogo-editorial.txt').read_text(),
            'facts': clean, 'narrative_facts': [c['text'] for c in narrative['claims']],
            'allowed_internal_urls': allowed_urls, 'title_max_chars':70, 'body_min_words':600,
            'publication_enabled':False}


class Anchors(HTMLParser):
    def __init__(self, allowed):
        super().__init__(convert_charrefs=True); self.allowed=set(allowed); self.errors=[]; self.depth=0
    def handle_starttag(self, tag, attrs):
        if tag != 'a' or len(attrs) != 1 or attrs[0][0] != 'href' or attrs[0][1] not in self.allowed or self.depth:
            self.errors.append('HTML/link não autorizado')
        if tag == 'a': self.depth += 1
    def handle_endtag(self, tag):
        if tag != 'a' or self.depth != 1: self.errors.append('HTML desbalanceado')
        if tag == 'a': self.depth -= 1
    def handle_startendtag(self, tag, attrs): self.errors.append('HTML não autorizado')
    def handle_comment(self, data): self.errors.append('Comentário HTML proibido')


def validate(article, allowed_urls):
    errors=[]
    title=normalized(article.get('title','')); excerpt=article.get('excerpt',''); blocks=article.get('blocks',[])
    if not title or title != title.strip() or '\n' in title or len(title)>70:
        errors.append('Título deve ter de 1 a 70 caracteres, incluindo espaços/pontuação')
    if not excerpt.strip(): errors.append('Chamada ausente')
    if not blocks or any(b.get('type') not in {'paragraph','subtitle','list'} or not b.get('text','').strip() for b in blocks):
        errors.append('Corpo inválido')
    if not any(b.get('type')=='subtitle' for b in blocks): errors.append('Subtítulos ausentes')
    if blocks and blocks[-1].get('type')!='paragraph': errors.append('Fechamento deve ser prosa')
    body='\n\n'.join(b.get('text','') for b in blocks)
    words=len(re.findall(r'\b[\wÀ-ÿ]+\b', re.sub('<[^>]+>','',body)))
    if words<600: errors.append('Corpo com menos de 600 palavras')
    full='\n'.join([title,excerpt,body])
    if re.search(r'(?m)^\s*(#{1,6}\s|>|```)|\*\*|\[[^\]]+\]\(',full): errors.append('Formatação proibida')
    if re.search(r'placeholder|\bTODO\b|dados verificados|jogos registrados|recorte consultado|conclusão independente|avaliação é do próprio|não representa, por si só|não permite afirmar|sem antecipar o resultado|o resumo (?:da partida )?registra|com a mudança de funções descrita',full,re.I): errors.append('Marca de bastidor')
    closing=False
    for block in blocks:
        if block.get('type')=='subtitle' and re.search(r'próximos? (?:jogos?|compromissos?)|voltam? a se enfrentar|agenda',block.get('text',''),re.I):
            closing=True
        elif closing and re.search(r'\b(?:substituiu|substituições|entrou no lugar|entraram nos lugares|cruzou|finalizou|defendeu|cobrou)\b',block.get('text',''),re.I):
            errors.append('Organização: após a seção de próximos jogos, não retomar lances ou substituições; reorganize o texto completo cronologicamente')
            break
    parser=Anchors(allowed_urls); parser.feed(full)
    errors.extend(parser.errors)
    if parser.depth: errors.append('Âncora não fechada')
    if '<' in title+excerpt or 'http' in title+excerpt: errors.append('Título/chamada com marcação')
    return {'format_passed':not errors,'title_chars':len(title),'body_words':words,'errors':errors,
            'factual_accuracy_validated_by_this_script':False,'publication_enabled':False}


def render(article):
    return '\n\n'.join([article['title'],article['excerpt'],*[b['text'] for b in article['blocks']]])+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--facts',type=Path,required=True);p.add_argument('--narrative',type=Path,required=True)
    p.add_argument('--links',type=Path,required=True);p.add_argument('--article',type=Path)
    a=p.parse_args(); read=lambda path:json.loads(path.read_text())
    request=prepare(read(a.facts),read(a.narrative),read(a.links))
    if a.article:
        result=validate(read(a.article),request['allowed_internal_urls']);print(json.dumps(result,ensure_ascii=False,indent=2))
        if not result['format_passed']:raise SystemExit(1)
    else:print(json.dumps(request,ensure_ascii=False,indent=2))
if __name__=='__main__': main()


def coverage_errors(article,package):
    """Gate mínimo de cobertura; revisão semântica confirma ação e ordem dos gols."""
    def canon(t):
        return ''.join(c for c in unicodedata.normalize('NFKD',t) if not unicodedata.combining(c)).casefold().replace('’',"'")
    body=canon(' '.join(b['text'] for b in article['blocks'] if b['type']=='paragraph'))
    errors=[]
    for goal in package['facts'].get('goals',[]):
        name=goal['scorer'];surname=canon(name).split()[-1]
        if not re.search(r'(?<!\w)'+re.escape(surname)+r'(?!\w)',body):
            errors.append('Cobertura: falta o gol de '+name+' no corpo; narrar todos os gols confirmados na ordem fornecida')
    return errors
