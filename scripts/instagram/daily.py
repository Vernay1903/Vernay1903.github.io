"""Daily Stories, 00:40–01:00 Sao Paulo; durable, fail-closed publication journal."""
import base64
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from publish_test import ACCOUNT, REPO, STATE_BRANCH, SafeError, gh, meta, request

TZ = ZoneInfo('America/Sao_Paulo')
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'out/instagram'


def now():
    return datetime.now(TZ)


def check_window(day, clock=None):
    local = (clock or now()).astimezone(TZ)
    # Leave a minute for the final API request (transport timeout is 45 seconds).
    if local.date().isoformat() != day or not '00:40' <= local.strftime('%H:%M') < '00:59':
        raise SafeError('Fora da janela: novas publicações só entre 00h40 e 00h59, Brasília.')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dated_source(commit, pr, day):
    first = commit['commit']['message'].splitlines()[0]
    match = re.fullmatch(r'Atualiza agenda de (\d{4}-\d{2}-\d{2}) \(#(\d+)\)', first)
    timestamp = datetime.fromisoformat(commit['commit']['committer']['date'].replace('Z', '+00:00'))
    if (not match or match[1] != day or timestamp.astimezone(TZ).date().isoformat() != day
            or not pr.get('merged') or pr.get('number') != int(match[2])
            or pr.get('merge_commit_sha') != commit['sha']
            or pr.get('head', {}).get('ref') != 'agenda-auto-' + day
            or pr.get('base', {}).get('ref') != 'main'):
        raise SafeError('Agenda do dia ainda não confirmada pelo fluxo validado; aguardar próxima tentativa.')


def source(day):
    commits = gh('commits?path=agenda.json&sha=main&per_page=1')
    commit = commits[0]
    match = re.search(r'\(#(\d+)\)', commit['commit']['message'].splitlines()[0])
    if not match:
        raise SafeError('Agenda sem publicação diária validada; revisão necessária.')
    pr = gh('pulls/' + match[1])
    dated_source(commit, pr, day)
    raw = base64.b64decode(gh('contents/agenda.json?ref=' + commit['sha'])['content'])
    current = base64.b64decode(gh('contents/agenda.json?ref=main')['content'])
    if raw != current:
        raise SafeError('Agenda mudou durante a conferência; tentar novamente.')
    rows = json.loads(raw)
    if not isinstance(rows, list) or not rows:
        raise SafeError('Agenda vazia; nenhum Story será publicado.')
    return raw, commit['sha']


def state_path(day):
    return 'state/' + ACCOUNT + '/' + day + '-daily.json'


def read_state(day):
    try:
        item = gh('contents/' + state_path(day) + '?ref=' + STATE_BRANCH)
    except SafeError as exc:
        if str(exc) == 'HTTP 404':
            return None, None
        raise
    return json.loads(base64.b64decode(item['content'])), item['sha']


def save_state(state, sha):
    body = {'message': 'Registra Stories de ' + state['date'], 'branch': STATE_BRANCH,
            'content': base64.b64encode((json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode()).decode()}
    if sha:
        body['sha'] = sha
    return gh('contents/' + state_path(state['date']), body, 'PUT')['content']['sha']


def check_plan(state, day, agenda_hash):
    if (state.get('date') != day or state.get('account') != ACCOUNT
            or state.get('agenda_sha256') != agenda_hash):
        raise SafeError('A agenda difere do plano iniciado; interrompido para evitar páginas inconsistentes.')


def prepare():
    day = now().date().isoformat()
    real = os.environ.get('PUBLISH_DAILY') == 'true'
    if real:
        check_window(day)
    raw, commit = source(day)
    state, _ = read_state(day)
    if state:
        check_plan(state, day, digest(raw))
    ROOT.joinpath('agenda.json').write_bytes(raw)
    OUT.mkdir(parents=True, exist_ok=True)
    OUT.joinpath('receipt.json').write_text(json.dumps({'date': day, 'agenda_sha256': digest(raw), 'source_commit': commit}))
    with open(os.environ['GITHUB_ENV'], 'a') as env:
        env.write('AGENDA_DATE=' + day + '\nSTORY_UPCOMING_ONLY=false\n')
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write('resume=' + str(bool(state) and real).lower() + '\n')
    print('Agenda validada para ' + day + ('; retomada do plano persistido.' if state and real else '; gerar prévia completa.'))


def manifest_plan(manifest, receipt, images):
    if (manifest['date'] != receipt['date'] or manifest['agenda_sha256'] != receipt['agenda_sha256']
            or manifest.get('selected_after') is not None or not manifest.get('pages')):
        raise SafeError('Prévia não corresponde à agenda completa de hoje.')
    rows = json.loads(ROOT.joinpath('agenda.json').read_bytes())
    if [row for page in manifest['pages'] for row in page['events']] != rows:
        raise SafeError('Eventos da prévia divergem da agenda validada.')
    if len(images) != len(manifest['pages']):
        raise SafeError('Prévia incompleta.')
    return {'date': receipt['date'], 'account': ACCOUNT, 'agenda_sha256': receipt['agenda_sha256'],
            'source_commit': receipt['source_commit'], 'pages': [
                {'file': page['file'], 'image_sha256': digest(data), 'status': 'pending'}
                for page, data in zip(manifest['pages'], images)]}


def upload_plan(state, images):
    check_window(state['date'])
    head = gh('git/ref/heads/' + STATE_BRANCH)['object']['sha']
    tree = gh('git/commits/' + head)['tree']['sha']
    entries = []
    for page, image in zip(state['pages'], images):
        blob = gh('git/blobs', {'encoding': 'base64', 'content': base64.b64encode(image).decode()})
        path = state['date'] + '/daily/' + page['file']
        entries.append({'path': path, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
    tree = gh('git/trees', {'base_tree': tree, 'tree': entries})['sha']
    commit = gh('git/commits', {'message': 'Artes diárias de ' + state['date'], 'tree': tree, 'parents': [head]})['sha']
    # Fast-forward only; concurrent branch changes fail, never overwrite another state.
    gh('git/refs/heads/' + STATE_BRANCH, {'sha': commit, 'force': False}, 'PATCH')
    for page, entry in zip(state['pages'], entries):
        page['image_url'] = 'https://raw.githubusercontent.com/' + REPO + '/' + commit + '/' + entry['path']
        if digest(request(page['image_url'])) != page['image_sha256']:
            raise SafeError('Imagem pública indisponível ou diferente da renderizada.')
    return state


def publish_pages(state, persist, api, check, sleep=time.sleep):
    """Intent is durable before each non-idempotent publish; never retry ambiguous POST."""
    for page in state['pages']:
        if page['status'] == 'published':
            continue
        check()
        cid = page.get('container_id')
        if page['status'] == 'publishing':
            if cid and api(cid + '?fields=status_code').get('status_code') == 'PUBLISHED':
                page['status'] = 'published'
                persist(state)
                continue
            raise SafeError('Publicação anterior inconclusiva; não repetir. Conferir Story no Instagram.')
        if not cid:
            # Recreating an orphan container is safe: containers alone do not publish Stories.
            check()
            result = api(ACCOUNT + '/media', {'media_type': 'STORIES', 'image_url': page['image_url']})
            cid = str(result.get('id', ''))
            if not cid.isdigit():
                raise SafeError('Contêiner sem identificação válida.')
            page.update(container_id=cid, status='container_created')
            persist(state)
        for attempt in range(7):
            check()
            status = api(cid + '?fields=status_code').get('status_code')
            if status == 'PUBLISHED':
                page['status'] = 'published'
                persist(state)
                break
            if status == 'FINISHED':
                # Check after state save too: storage requests can take time.
                page['status'] = 'publishing'
                persist(state)
                check()
                result = api(ACCOUNT + '/media_publish', {'creation_id': cid})
                mid = str(result.get('id', ''))
                if not mid.isdigit():
                    raise SafeError('Publicação inconclusiva; revisão manual necessária.')
                page.update(status='published', media_id=mid)
                persist(state)
                break
            if status in ('ERROR', 'EXPIRED'):
                # This container cannot publish; a later run can create a fresh one.
                page.pop('container_id', None)
                page['status'] = 'pending'
                persist(state)
                raise SafeError('Contêiner falhou; aguardar recuperação dentro da janela.')
            if status != 'IN_PROGRESS' or attempt == 6:
                raise SafeError('Processamento pendente; retomar na próxima tentativa.')
            sleep(15)
    return sum(page['status'] == 'published' for page in state['pages'])


def verify_meta_identity():
    """Identity must match exactly; alternate Graph version is read-only."""
    try:
        identity = meta(ACCOUNT + '?fields=id,username')
    except SafeError as exc:
        if str(exc) != 'HTTP 400 code=100 subcode=33':
            raise
        print('Meta v27 recusou a consulta de identidade (100/33); verificando v26 sem publicar.', flush=True)
        identity = json.loads(request(
            'https://graph.facebook.com/v26.0/' + ACCOUNT + '?fields=id,username',
            os.environ['INSTAGRAM_ACCESS_TOKEN']))
    if (not isinstance(identity, dict) or str(identity.get('id')) != ACCOUNT
            or identity.get('username') != 'cortedosesportes'):
        raise SafeError('Credencial não identifica a conta aprovada.')
    print('Identidade de @cortedosesportes confirmada.', flush=True)


def run():
    receipt = json.loads(OUT.joinpath('receipt.json').read_text())
    day = receipt['date']
    real = os.environ.get('PUBLISH_DAILY') == 'true'
    state, sha = read_state(day)
    if state:
        check_plan(state, day, receipt['agenda_sha256'])
    if not real or not state:
        manifest = json.loads(OUT.joinpath('manifest.json').read_text())
        images = [OUT.joinpath(page['file']).read_bytes() for page in manifest['pages']]
        plan = manifest_plan(manifest, receipt, images)
    if not real:
        print('SIMULAÇÃO: ' + str(len(plan['pages'])) + ' páginas conferidas; nenhuma chamada de publicação ou escrita remota.')
        return
    if (os.environ.get('GITHUB_REF') != 'refs/heads/main'
            or os.environ.get('GITHUB_EVENT_NAME') not in ('schedule', 'workflow_dispatch', 'workflow_run')):
        raise SafeError('Publicação permitida apenas pelo agendamento ou execução manual na main.')
    check_window(day)
    if os.environ.get('INSTAGRAM_USER_ID', '').strip() != ACCOUNT:
        raise SafeError('Conta configurada não corresponde a @cortedosesportes.')
    if state and all(page['status'] == 'published' for page in state['pages']):
        print('Todos os Stories de hoje já publicados; nenhuma duplicação.')
        return
    verify_meta_identity()
    raw, _ = source(day)
    if digest(raw) != receipt['agenda_sha256']:
        raise SafeError('Agenda mudou após a renderização; tentar novamente.')
    if json.loads(request('https://cortedosesportes.com.br/agenda.json')) != json.loads(raw):
        raise SafeError('Site ainda não está servindo a agenda atualizada; aguardar recuperação.')
    if not state:
        state = upload_plan(plan, images)
        sha = save_state(state, None)

    def persist(value):
        nonlocal sha
        sha = save_state(value, sha)

    def check():
        check_window(day)

    count = publish_pages(state, persist, meta, check)
    message = str(count) + ' Stories de ' + day + ' confirmados; sequência completa em @cortedosesportes.'
    print(message)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
            out.write(message + '\n')


def retry(operation, clock=now, sleep=time.sleep):
    if os.environ.get('PUBLISH_DAILY') != 'true':
        return operation()
    day = clock().date().isoformat()
    while True:
        check_window(day, clock())
        try:
            return operation()
        except SafeError as exc:
            print(str(exc), flush=True)
            check_window(day, clock())
            sleep(30)


if __name__ == '__main__':
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ''
        if command.startswith('retry-'):
            retry(prepare if command == 'retry-prepare' else run)
        else:
            prepare() if command == 'prepare' else run()
    except SafeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('Falha inesperada; conferir o registro diário antes de repetir. Credenciais omitidas.', file=sys.stderr)
        sys.exit(1)
