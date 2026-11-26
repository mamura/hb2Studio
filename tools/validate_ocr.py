"""Validação limitada a 20 versos explícitos; stdout sem dados pessoais."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hb2_studio.engine import analyze_pdf
from hb2_studio.layout import BACK_FIELDS

PAGES = [4, 6, 8, 90, 148, 208, 266, 322,
         92, 110, 128, 146, 164, 182, 200, 218, 236, 254, 284, 310]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--tesseract', default='tesseract')
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    root = Path(__file__).resolve().parents[1] / 'resultados'
    output = root / ('integracao-ocr-' + datetime.now(ZoneInfo('America/Fortaleza')).strftime('%Y-%m-%d_%H-%M-%S_%f'))
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    result = analyze_pdf(args.pdf, ocr_pages=PAGES, ocr_output=output,
                         tesseract=args.tesseract)
    selected = [b.back for b in result.badges if b.back.number in PAGES]
    if len(selected) != 20 or any(p.has_text for p in selected):
        raise ValueError('A seleção deve validar exatamente 20 versos candidatos a OCR.')
    records = [{'pagina': p.number, 'campos': {
        name: {'valor': value, **{k: v for k, v in p.details[name].items() if k != 'value'}}
        for name, value in p.values.items()}} for p in selected]
    (output/'valores-finais.json').write_text(json.dumps(records, ensure_ascii=False, indent=2))
    counts = {}
    for f in BACK_FIELDS:
        values = [r['campos'][f.name] for r in records]
        counts[f.name] = {'preenchidos': sum(bool(v['valor']) for v in values),
                          'vazios_sem_confirmacao': sum(not v['valor'] for v in values),
                          'estados': dict(Counter(v['status'] for v in values)),
                          'origens': dict(Counter(v['origem'] for v in values))}
    summary = {'arquivo': str(output/'valores-finais.json'), 'versos_ocr': len(records),
               'layouts': {'original': 3, 'deslocado': 17},
               'pares_validados': len(result.badges), 'grupos_rejeitados': len(result.rejected),
               'contagens': counts,
               'paginas_conferir': [r['pagina'] for r in records if any(v['status'] != 'consistente_ocr' for v in r['campos'].values())],
               'paginas_por_campo': {f.name: [r['pagina'] for r in records if r['campos'][f.name]['status'] != 'consistente_ocr'] for f in BACK_FIELDS},
               'zeros_iniciais_preservados': sum(v['valor'].startswith('0') for r in records for v in r['campos'].values())}
    if args.baseline:
        baseline = json.loads(args.baseline.read_text())
        current = {r['pagina']: r for r in records}
        summary['regressao_oito'] = {
            'versos': len(baseline),
            'campos_identicos': sum(current[r['page']]['campos'][name]['valor'] == info['value'] for r in baseline for name, info in r['fields'].items())}
    (output/'agregado.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (output/'manifesto.json').write_text(json.dumps({
        'paginas': PAGES, 'timezone': 'America/Fortaleza',
        'fonte_sha256': hashlib.sha256(args.pdf.read_bytes()).hexdigest(),
        'codigo_sha256': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['hb2_studio/engine.py', 'hb2_studio/ocr.py']},
        'nota': 'Consistência OCR e regressão de integração; não constitui conferência humana dos 100 campos.'}, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
