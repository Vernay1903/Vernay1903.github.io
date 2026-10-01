#!/usr/bin/env python3
"""Uma publicação parcial mantém as matérias válidas, mas nunca recebe sucesso total."""
import argparse
import json

DUPLICATES = {'html_already_exists', 'url_already_in_noticias', 'same_match_already_in_noticias'}


def pending(manifest, report):
    return list(manifest.get('skipped', [])) + [
        item for item in report.get('skipped', []) if item.get('reason') not in DUPLICATES
    ]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', required=True)
    p.add_argument('--report', required=True)
    args = p.parse_args()
    with open(args.manifest, encoding='utf-8') as f:
        manifest = json.load(f)
    with open(args.report, encoding='utf-8') as f:
        report = json.load(f)
    blocked = pending(manifest, report)
    for item in blocked:
        print('::error::PENDENTE: ' + json.dumps(item, ensure_ascii=False))
    if blocked:
        raise SystemExit(f'{len(blocked)} matéria(s) pendente(s); as aprovadas foram preservadas.')
    print('OK: nenhuma matéria pendente no lote.')


if __name__ == '__main__':
    main()
