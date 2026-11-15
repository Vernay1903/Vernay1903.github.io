"""Start from agenda completion, wait locally, never rely solely on cron delivery."""
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo('America/Sao_Paulo')


def await_window(real, event, clock=lambda: datetime.now(TZ), sleep=time.sleep):
    if not real:
        return True
    day = clock().astimezone(TZ).date()
    while True:
        current = clock().astimezone(TZ)
        if current.date() != day or current.strftime('%H:%M') >= '00:59':
            return False
        if current.strftime('%H:%M') >= '00:40':
            return True
        if event != 'workflow_run':
            return False
        sleep(min(30, (current.replace(hour=0, minute=40, second=0, microsecond=0) - current).total_seconds()))


if __name__ == '__main__':
    proceed = await_window(os.environ.get('PUBLISH_DAILY') == 'true', os.environ.get('GITHUB_EVENT_NAME'))
    with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
        out.write('proceed=' + str(proceed).lower() + '\n')
    message = 'Janela aberta.' if proceed else 'FORA DA JANELA: nenhuma publicação foi tentada nesta execução.'
    print(message)
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
        out.write(message + '\n')
