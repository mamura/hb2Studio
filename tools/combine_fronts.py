"""Enriquece os pares existentes com nomes de guerra/fotos; não refaz OCR de verso."""
import argparse
from collections import Counter
import copy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

import pdfplumber
import pypdfium2 as pdfium

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hb2_studio.engine import detect_side
from hb2_studio.front import read_front_name,extract_photo
from hb2_studio.layout import normalize
from hb2_studio.xlsx import export_xlsx,flagged


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('pdf',type=Path)
    ap.add_argument('json',type=Path)
    ap.add_argument('--output',type=Path)
    ap.add_argument('--sample',type=Path)
    ap.add_argument('--tesseract',default='tesseract')
    args=ap.parse_args()
    os.umask(0o077)
    root=Path(__file__).resolve().parents[1]/'resultados'
    output=args.output or root/('frentes-combinadas-'+datetime.now(ZoneInfo('America/Fortaleza')).strftime('%Y-%m-%d_%H-%M-%S_%f'))
    if not output.resolve().is_relative_to(root):ap.error('A saída deve estar em resultados/.')
    if (output/'crachas.xlsx').exists():ap.error('A planilha de saída já existe.')
    data=json.loads(args.json.read_text());original=copy.deepcopy(data)
    if data['pares_contabilizados']!=163 or len(data['pares'])!=163 or data['grupos_rejeitados']:
        raise ValueError('O JSON deve conter os 163 pares validados.')
    digest=hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    manifest=json.loads((args.json.parent/'manifesto.json').read_text())
    if manifest['documento_sha256']!=digest:raise ValueError('O JSON não corresponde ao PDF.')
    output.mkdir(mode=0o700,parents=True,exist_ok=True)
    sample={}
    if args.sample:
        verified=json.loads((args.sample.parent/'validacao-amostra.json').read_text())
        if verified['associacoes_corretas']!=8 or verified['nomes_corretos']!=8 or verified['fotos_corretas']!=8:
            raise ValueError('A amostra ainda não foi conferida.')
        sample={r['pagina']:r for r in json.loads(args.sample.read_text())}
        if args.sample.parent.resolve()!=output.resolve():raise ValueError('A amostra deve estar na mesma pasta de saída.')
    layouts=Counter();seen=set()
    with pdfplumber.open(args.pdf) as document,pdfium.PdfDocument(args.pdf) as native:
        if len(document.pages)!=326:raise ValueError('Quantidade de páginas inesperada.')
        for i,pair in enumerate(data['pares'],1):
            f,b=pair['frente']['pagina'],pair['verso']['pagina']
            if type(f) is not int or type(b) is not int or b!=f+1 or f in seen or b in seen:
                raise ValueError('Associação de páginas inválida.')
            seen.update([f,b]);page=document.pages[f-1];back=document.pages[b-1]
            if detect_side(page)!='frente' or detect_side(back)!='verso':raise ValueError('Ordem do par divergente no PDF.')
            if f in sample:
                name=sample[f]['nome_frente'];photo=sample[f]['foto']
            else:
                try:name=read_front_name(page,output/'intermediarios',args.tesseract,pair['frente']['campos']['nome_frente']['valor'])
                except (OSError,subprocess.CalledProcessError):
                    name={'valor':'','origem':'ocr','status':'revisar','reasons':['ocr_indisponivel','vazio_nao_confirmado']}
                native_page=native[f-1]
                try:photo=extract_photo(page,native_page,output)
                finally:native_page.close()
            pair['frente']['campos']['nome_frente']=name
            pair['frente']['campos']['foto']=photo
            front_words=normalize(name['valor']).split();back_words=normalize(pair['verso']['campos']['nome']['valor']).split()
            if front_words and back_words:
                remaining=iter(back_words)
                compatible=all(w in remaining for w in front_words)
                pair['comparacao_nomes']='compativel' if compatible else 'divergente'
                if not compatible:
                    name['reasons']=list(dict.fromkeys(name['reasons']+['conferir_associacao_nome']))
                    name['status']='revisar'
            else:pair['comparacao_nomes']='indisponivel'
            layouts['deslocado' if name.get('box_pdf',[0,0])[1]>230 else 'original']+=1
            # Preserve completed records even before the workbook is built.
            (output/f'intermediarios/par-{i:03d}.json').parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            (output/f'intermediarios/par-{i:03d}.json').write_text(json.dumps(pair,ensure_ascii=False,indent=2))
            page.close();back.close()
            if i%20==0:print(json.dumps({'pares_processados':i,'total':163}),flush=True)
    assert seen==set(range(1,327))
    assert all(a['verso']==b['verso'] for a,b in zip(data['pares'],original['pares']))
    assert all(not before['frente']['campos']['nome_frente']['valor'] or before['frente']['campos']['nome_frente']['valor']==after['frente']['campos']['nome_frente']['valor'] for before,after in zip(original['pares'],data['pares']))
    source=output/'valores-combinados.json';source.write_text(json.dumps(data,ensure_ascii=False,indent=2))
    verified=export_xlsx(source,output/'crachas.xlsx')
    names=[p['frente']['campos']['nome_frente'] for p in data['pares']];photos=[p['frente']['campos']['foto'] for p in data['pares']]
    summary={'planilha':str(output/'crachas.xlsx'),'json':str(source),'fotos':str(output/'fotos'),
             **verified,'campos_verso_preservados':815,'layouts':dict(layouts),
             'nomes_guerra_preenchidos':sum(bool(v['valor']) for v in names),
             'origens_nomes':dict(Counter(v['origem'] for v in names)),
             'nomes_guerra_revisar':sum(flagged(v) for v in names),
             'motivos_nome_guerra':dict(Counter(r for v in names for r in v['reasons'])),
             'metodos_fotos':dict(Counter(v['origem'] for v in photos)),
             'fotos_revisar':sum(flagged(v) for v in photos),
             'motivos_fotos':dict(Counter(r for v in photos for r in v['reasons']))}
    (output/'agregado.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    (output/'manifesto.json').write_text(json.dumps({'documento_sha256':digest,'json_origem':str(args.json),
        'json_origem_sha256':hashlib.sha256(args.json.read_bytes()).hexdigest(),
        'regra':'Versos imutáveis; nomes da frente sem completar pelo verso; fotos ligadas à página da frente.',
        'codigo_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in map(Path,['hb2_studio/front.py','hb2_studio/xlsx.py','tools/combine_fronts.py'])},
        'fotos_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (output/'fotos').glob('*.png')}},ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
