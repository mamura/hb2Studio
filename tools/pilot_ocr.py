"""Piloto local limitado a 6–10 versos; stdout contém somente agregados.

Usa o mesmo extrator OCR complementar do motor. Artefatos privados em resultados/.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from collections import Counter

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hb2_studio.layout import BACK_FIELDS


from hb2_studio.ocr import clean, name_words, shifted_name_top, extract_back


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('pdf', type=Path)
    ap.add_argument('--pages', nargs='+', type=int, required=True)
    ap.add_argument('--tesseract', default='tesseract')
    ap.add_argument('--output', type=Path, default=Path('resultados/piloto-ocr'))
    args = ap.parse_args()
    if not 6 <= len(set(args.pages)) <= 10 or len(set(args.pages)) != len(args.pages):
        ap.error('Selecione de 6 a 10 versos distintos.')
    # Only the ignored directory is allowed to receive personal artifacts.
    root = Path(__file__).resolve().parents[1] / 'resultados'
    if not args.output.resolve().is_relative_to(root):
        ap.error('A saída deve estar dentro de resultados/.')
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    with pdfplumber.open(args.pdf) as doc:
        for n in args.pages:
            p = doc.pages[n - 1]
            from hb2_studio.engine import detect_side
            if detect_side(p) != 'verso' or p.chars:
                raise ValueError('A seleção deve conter apenas versos candidatos a OCR.')
            result = extract_back(p, args.output, args.tesseract)
            records.append(result)
    (args.output / 'leituras-privadas.json').write_text(json.dumps(records, ensure_ascii=False, indent=2))
    summary = {'versos': len(records), 'layouts': dict(Counter(r['layout'] for r in records)),
               'campos': {f.name: dict(Counter(r['fields'][f.name]['status'] for r in records)) for f in BACK_FIELDS},
               'recortes_com_possivel_corte': sum(v.get('crop_check') == 'revisar' for r in records for v in r['fields'].values()),
               'nao_vazios': {f.name: sum(bool(r['fields'][f.name]['value']) for r in records) for f in BACK_FIELDS},
               'concordancias': {f.name: sum(r['fields'][f.name]['value'] == r['fields'][f.name].get('alternative') for r in records) for f in BACK_FIELDS},
               'campos_com_zero_inicial': sum(v.get('leading_zero', False) for r in records for v in r['fields'].values()),
               'validacao': 'Consistência entre duas passagens OCR; não equivale a conferência humana.'}
    (args.output / 'agregado.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
