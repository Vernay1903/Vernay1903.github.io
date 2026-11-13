"""One manually confirmed Story; fixed approved image, no scheduled publishing."""
import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

REPO = 'Vernay1903/Vernay1903.github.io'
ACCOUNT = '17841446409607682'
DAY = '2026-11-13'
AGENDA_HASH = 'ad13f7443aaf3ce088f26c401544bf17a64a60e5efadcc661fc4f88a68725351'
IMAGE_HASH = '385b05687def0bb5e87b719e4babf3905dbeca6c302364db453a8a42e041a17e'
IMAGE_URL = ('https://raw.githubusercontent.com/' + REPO +
             '/fbbc9182441d8ec999830abfe00ef2e77ddcc660/2026-11-13/night-story-01.jpg')
FIRST_EVENT_TIME = '21:00'
STATE_BRANCH = 'instagram-story-media'
STATE_PATH = 'state/' + ACCOUNT + '/' + DAY + '-story-01.json'

class SafeError(Exception):
    pass


def request(url, token=None, payload=None, method=None):
    headers = {'User-Agent': 'CDE-Instagram-Manual-Test'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers['Content-Type'] = 'application/json'
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, data=body, headers=headers, method=method), timeout=45) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        # Never emit response bodies, URLs, headers or exception repr: credentials stay private.
        code = subcode = None
        try:
            error = json.loads(exc.read()).get('error', {})
            code, subcode = error.get('code'), error.get('error_subcode')
        except (ValueError, AttributeError):
            pass
        suffix = ''.join(' ' + key + '=' + str(value) for key, value in
                         [('code', code), ('subcode', subcode)] if isinstance(value, int))
        raise SafeError('HTTP ' + str(exc.code) + suffix) from None
    except (OSError, TimeoutError):
        raise SafeError('Falha de rede; nenhuma tentativa automática adicional.') from None


def gh(path, payload=None, method=None):
    return json.loads(request('https://api.github.com/repos/' + REPO + '/' + path,
                             os.environ['GH_TOKEN'], payload, method))


def meta(path, payload=None):
    return json.loads(request('https://graph.facebook.com/v27.0/' + path,
                             os.environ['INSTAGRAM_ACCESS_TOKEN'], payload))


def verify_inputs(today, agenda, image, account):
    if today != DAY:
        raise SafeError('Esta imagem aprovada é de ' + DAY + '; gere e aprove uma prévia atual.')
    if account != ACCOUNT:
        raise SafeError('INSTAGRAM_USER_ID não corresponde à conta aprovada.')
    if hashlib.sha256(agenda).hexdigest() != AGENDA_HASH:
        raise SafeError('A agenda mudou desde a prévia aprovada. Teste interrompido.')
    if hashlib.sha256(image).hexdigest() != IMAGE_HASH:
        raise SafeError('Imagem pública diferente da prévia aprovada.')


def ensure_window(now=None):
    now = now or datetime.now(ZoneInfo('America/Sao_Paulo'))
    local = now.astimezone(ZoneInfo('America/Sao_Paulo'))
    if local.date().isoformat() != DAY or local.strftime('%H:%M') >= FIRST_EVENT_TIME:
        raise SafeError('A primeira partida da imagem já chegou ao horário previsto. Gere uma nova prévia.')


def save_state(state, sha=None):
    body = {'message': 'Registra estado do teste manual de Story', 'branch': STATE_BRANCH,
            'content': base64.b64encode((json.dumps(state, indent=2) + '\n').encode()).decode()}
    if sha:
        body['sha'] = sha
    # Without sha this is create-only: an existing marker fails closed, even after a crash.
    return gh('contents/' + STATE_PATH, body, 'PUT')['content']['sha']


def publish_once(api, persist, state, sleep=time.sleep, check_window=lambda: None):
    check_window()
    sha = persist(state)
    container = api(ACCOUNT + '/media', {'media_type': 'STORIES', 'image_url': IMAGE_URL})
    cid = container.get('id', '')
    if not str(cid).isdigit():
        raise SafeError('Meta não retornou identificação do contêiner.')
    state.update(status='container_created', container_id=str(cid))
    sha = persist(state, sha)
    for attempt in range(6):
        status = api(str(cid) + '?fields=status_code').get('status_code')
        if status == 'FINISHED':
            break
        if status != 'IN_PROGRESS':
            raise SafeError('Contêiner não está pronto para publicação; revisar no painel da Meta.')
        if attempt == 5:
            raise SafeError('Processamento excedeu cinco minutos; publicação não iniciada.')
        sleep(60)
    check_window()
    # Persist intent BEFORE the non-idempotent request. A timeout remains blocked for manual review.
    state['status'] = 'publishing'
    sha = persist(state, sha)
    result = api(ACCOUNT + '/media_publish', {'creation_id': str(cid)})
    mid = result.get('id', '')
    if not str(mid).isdigit():
        raise SafeError('Resposta de publicação inconclusiva. Confira o Instagram antes de qualquer repetição.')
    state.update(status='published', media_id=str(mid))
    persist(state, sha)
    return str(mid)


def main():
    if os.environ.get('CONFIRM_PUBLISH') != 'true' or os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise SafeError('Requer execução manual confirmada na main.')
    if os.environ.get('GITHUB_EVENT_NAME') != 'workflow_dispatch':
        raise SafeError('Somente execução manual é permitida.')
    for key in ['GH_TOKEN', 'INSTAGRAM_ACCESS_TOKEN', 'INSTAGRAM_USER_ID']:
        if not os.environ.get(key):
            raise SafeError('Secret obrigatório ausente: ' + key)
    today = datetime.now(ZoneInfo('America/Sao_Paulo')).date().isoformat()
    # Cheap date check first, before any external mutation or expensive work.
    if today != DAY:
        raise SafeError('Prévia expirada: teste limitado a ' + DAY + '.')
    ensure_window()
    source = gh('contents/agenda.json?ref=main')
    agenda = base64.b64decode(source['content'])
    image = request(IMAGE_URL)
    verify_inputs(today, agenda, image, os.environ['INSTAGRAM_USER_ID'])
    live = request('https://cortedosesportes.com.br/agenda.json')
    if json.loads(live) != json.loads(agenda):
        raise SafeError('Agenda servida pelo site difere da agenda aprovada.')
    account = meta(ACCOUNT + '?fields=id,username')
    if account.get('id') != ACCOUNT or account.get('username') != 'cortedosesportes':
        raise SafeError('A credencial não identifica @cortedosesportes.')
    state = {'status': 'claimed', 'date': DAY, 'account': ACCOUNT,
             'image_sha256': IMAGE_HASH, 'run_id': os.environ.get('GITHUB_RUN_ID')}
    mid = publish_once(meta, save_state, state, check_window=ensure_window)
    print('Meta confirmou a publicação de UM Story. ID da mídia: ' + mid)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as output:
            output.write('## Teste de Story\n\nMeta confirmou um Story em @cortedosesportes. '
                         'ID: `' + mid + '`. Confira a aparência no aplicativo.\n')


if __name__ == '__main__':
    try:
        main()
    except SafeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('Falha inesperada. Revisar estado do teste e Instagram; não repetir publicação às cegas.', file=sys.stderr)
        sys.exit(1)
