"""Identify the agenda snapshot by its last commit, without changing the agenda."""
import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

repo = os.environ['GITHUB_REPOSITORY']
ref = os.environ['GITHUB_SHA']
url = 'https://api.github.com/repos/' + repo + '/commits?' + urllib.parse.urlencode({'path':'agenda.json','sha':ref,'per_page':1})
request = urllib.request.Request(url, headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
with urllib.request.urlopen(request, timeout=30) as response:
    commits = json.load(response)
if not commits:
    raise SystemExit('Não foi possível determinar a data da agenda.')
stamp = dt.datetime.fromisoformat(commits[0]['commit']['committer']['date'].replace('Z','+00:00'))
date = stamp.astimezone(ZoneInfo('America/Sao_Paulo')).date().isoformat()
with open(os.environ['GITHUB_ENV'], 'a') as stream:
    stream.write('AGENDA_DATE='+date+'\n')
print('Prévia da agenda atualizada em '+date+'. A data do commit não verifica o calendário esportivo.')
