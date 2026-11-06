"""Remove atribuição de bloqueio ao assistente, somente com lance literal da fonte."""
import copy,re

def correct_text(text,commentary):
    for row in commentary:
        source=row.get('text','') if isinstance(row,dict) else row
        match=re.search(r'^Attempt blocked\. (.+?) \([^)]*\).*? is blocked\. Assisted by ([^.]+)\.',source)
        if not match:continue
        shooter,assistant=match.groups()
        # O passe é inequívoco, mas a identidade de quem bloqueou não foi informada.
        wrong=f'{shooter} teve uma finalização bloqueada por {assistant}'
        text=text.replace(wrong,f'{shooter} teve uma finalização bloqueada')
    return text

def correct_candidate(narrative,article,commentary):
    narr=copy.deepcopy(narrative);draft=copy.deepcopy(article)
    for claim in narr['claims']:claim['text']=correct_text(claim['text'],commentary)
    for block in draft['blocks']:block['text']=correct_text(block['text'],commentary)
    return narr,draft
