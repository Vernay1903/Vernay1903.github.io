"""Read-only credential check for the Unified Login flow. Never prints tokens."""
import json
import os
import re
import urllib.error
import urllib.request


def safe_message(info, token):
    text = ' | '.join(str(info.get(key, '')) for key in ('error_user_title', 'error_user_msg', 'message'))
    text = text.replace(token, '[credencial omitida]') if token else text
    text = re.sub(r'https?://\S+', '[URL omitida]', text)
    text = re.sub(r'[A-Za-z0-9_|.-]{40,}', '[identificador omitido]', text)
    return ''.join(c if c.isprintable() else ' ' for c in text)[:600]


def main():
    token = os.environ.get('INSTAGRAM_ACCESS_TOKEN', '').strip()
    account = os.environ.get('INSTAGRAM_USER_ID', '').strip()
    if not token or not re.fullmatch(r'\d+', account):
        raise SystemExit('Secrets INSTAGRAM_ACCESS_TOKEN ou INSTAGRAM_USER_ID ausentes/inválidos.')
    url = f'https://graph.facebook.com/v27.0/{account}?fields=id,username'
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        # Only selected explanatory fields; remove credentials, URLs and opaque identifiers.
        try:
            info = json.loads(error.read()).get('error', {})
        except (ValueError, AttributeError):
            info = {}
        code = info.get('code')
        subcode = info.get('error_subcode')
        safe_code = code if isinstance(code, int) else 'desconhecido'
        safe_subcode = subcode if isinstance(subcode, int) else 'ausente'
        print('Explicação da Meta: ' + safe_message(info, token))
        raise SystemExit(f'Meta recusou a consulta: HTTP {error.code}, código {safe_code}, subcódigo {safe_subcode}.')
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise SystemExit('Não foi possível concluir a consulta à Meta. Token não exibido.')
    if str(result.get('id')) != account or result.get('username') != 'cortedosesportes':
        raise SystemExit('Credencial não corresponde à conta esperada; interrompido.')
    print('Consulta autenticada confirmou @cortedosesportes. Nenhuma publicação realizada.')
    print('Este teste não comprova permissão de publicação nem validade futura do token.')


if __name__ == '__main__':
    main()
