"""Audita coleta real até pacote editorial, sem chamar redator ou publicar."""
import json,sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from scripts.recuperar_preparo_pre_jogo_automatico import command_plan,call,CONFIG,BUILD

def main():
    target=datetime.now(ZoneInfo('America/Sao_Paulo')).date().isoformat()
    original=CONFIG.read_bytes()
    try:
        cfg=json.loads(original);cfg['research']['discovery']['external_search_enabled']=True
        for index,command in enumerate(command_plan(target)):
            if index == 6:
                CONFIG.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n')
            if index == 11:
                CONFIG.write_bytes(original)
            call(*command)
            if index==2:
                plan=json.loads((BUILD/f'planos-{target}.json').read_text())
                if not plan['planned_count']:
                    print('Coleta consultada: nenhum jogo novo para testar redação.');return
        packages=json.loads((BUILD/f'pacotes-editoriais-{target}.json').read_text())
        blocked=[{'slug':a['slug'],'unresolved':a.get('unresolved_required_requirement_ids',[])} for a in packages['articles'] if not a.get('ready_for_drafting')]
        if blocked:raise SystemExit('COLETA REAL INCOMPLETA: '+json.dumps(blocked,ensure_ascii=False))
        print('COLETA REAL APROVADA: todos os pacotes do dia prontos para redação.')
    finally:CONFIG.write_bytes(original)
if __name__=='__main__':main()
