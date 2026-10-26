"""Liga redação revisada ao pacote de teste, sem publicar ou chamar API."""
import argparse
import hashlib
import json
from pathlib import Path
from editorial_pos_jogo import ROOT, prepare as editorial_prepare
from preparar_publicacao_pos_jogo import prepare


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def package_reviewed(directory, site_root, allowed_urls):
    directory=Path(directory).resolve();site_root=Path(site_root).resolve()
    if not directory.is_relative_to((ROOT/'build/pos-jogo').resolve()):
        raise ValueError('Redação fora do piloto')
    if not site_root.is_dir():raise ValueError('Diretório do site ausente')
    read=lambda p:json.loads(p.read_text())
    facts=read(directory/'fatos.json')
    meta=read(directory/'redacao/metadata.json')
    article=read(directory/'redacao/artigo.json')
    if meta.get('semantic_review_passed') is not True or meta.get('format_passed') is not True:
        raise ValueError('Redação não aprovada')
    if meta.get('fixture_id')!=facts['fixture_id'] or not facts.get('ready_for_drafting'):
        raise ValueError('Identidade ou fatos incompatíveis')
    package=editorial_prepare(facts,read(directory/'narrativa.json'),allowed_urls)
    if meta.get('article_sha256')!=digest(article) or meta.get('package_sha256')!=digest(package):
        raise ValueError('Artigo/fatos alterados após a revisão')
    # Releitura dos destinos a cada tentativa; data vem da versão redigida.
    outputs=prepare(article,facts['match'],meta['written_at'],
        (site_root/'noticias.json').read_bytes().decode('utf-8'),
        (site_root/'sitemap.xml').read_bytes().decode('utf-8'),allowed_urls,
        [p.name for p in site_root.glob('*.html')])
    report=json.loads(outputs['validacao.json'])
    report.update(fixture_id=facts['fixture_id'],article_sha256=digest(article),
                  human_review_required=True,semantic_review_passed=True)
    outputs['validacao.json']=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    out=directory/'publicacao-teste'
    if out.exists():
        if {p.name for p in out.iterdir()}!=set(outputs) or any((out/n).read_bytes()!=s.encode('utf-8') for n,s in outputs.items()):
            raise ValueError('Pacote existente diverge; preservar para revisão')
        return report
    temp=directory/'publicacao-teste.tmp'
    if temp.exists():raise ValueError('Pacote parcial de tentativa anterior; revisar antes de repetir')
    temp.mkdir()
    for name,text in outputs.items():(temp/name).write_bytes(text.encode('utf-8'))
    temp.rename(out)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--site-root',type=Path,required=True)
    p.add_argument('--links',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(package_reviewed(a.directory,a.site_root,json.loads(a.links.read_text())),ensure_ascii=False))

if __name__=='__main__':main()
