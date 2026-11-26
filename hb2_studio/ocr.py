"""OCR complementar de versos, com recortes calibrados e revisão conservadora."""
import csv
import io
from pathlib import Path
import re
import subprocess
from datetime import datetime
from PIL import ImageOps
from .layout import BACK_FIELDS

def ocr(image, target, binary, psm):
    image.save(target.with_suffix('.png'))
    target.with_suffix('.png').chmod(0o600)
    run = subprocess.run([binary, str(target.with_suffix('.png')), 'stdout',
                          '-l', 'por', '--psm', str(psm), 'tsv'],
                         capture_output=True, check=True, text=True)
    target.with_suffix('.tsv').write_text(run.stdout)
    target.with_suffix('.tsv').chmod(0o600)
    return [r for r in csv.DictReader(io.StringIO(run.stdout), delimiter='\t')
            if r['text'].strip()]


def name_words(rows):
    """Palavras do nome em ordem TSV, sem rótulo nem borda isolada."""
    words = [r for r in rows if str(r.get('level')) == '5'
             and r['text'].strip() != '|'
             and not re.fullmatch(r'NOME\s*:', r['text'].strip(), re.I)]
    return sorted(words, key=lambda r: tuple(int(r[k]) for k in (
        'page_num', 'block_num', 'par_num', 'line_num', 'word_num')))


def clean(rows, field):
    if field.name == 'nome':
        return ' '.join(r['text'].strip() for r in name_words(rows)
                        if r['text'].strip())
    text = ' '.join(r['text'] for r in rows)
    text = text.strip(' |[]')
    text = re.sub(rf'(?i)\b{field.label}\s*[:.\-]?\s*', '', text)
    text = text.strip(' |[]')
    return ' '.join(text.split()).strip()


def shifted_name_top(rows, current_top, label_top, bottom, left, right):
    """Inclui a linha acima do rótulo, com 12 px de margem a 400 dpi."""
    tops = [int(r['top']) for r in name_words(rows)
            if label_top - 60 <= int(r['top']) < current_top
            and int(r['top']) + int(r['height']) < bottom
            and left <= int(r['left']) < right]
    return min(current_top, min(tops) - 12) if tops else current_top


def extract_back(p, output, binary="tesseract"):
    output = Path(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    n = p.page_number
    image = p.to_image(resolution=400).original.convert('RGB')
    prefix = output / f'verso-{n}'
    rows = ocr(image, prefix, binary, 6)
    anchors = {}
    for f in BACK_FIELDS:
        for r in rows:
            if re.fullmatch(f.label + r'[:.\-]?', r['text'], re.I):
                anchors[f.name] = int(r['top'])
                break
    scale = 400 / 72
    shifted = min(i['top'] for i in p.images if i['x1'] <= 43 and 15 <= i['height'] <= 32) > 140
    result = {'page': n, 'layout': 'deslocado' if shifted else 'original', 'fields': {}}
    for i, f in enumerate(BACK_FIELDS):
        # Derive shifted rows from detected labels, never reuse original boxes.
        if shifted:
            y0 = anchors.get(f.name)
            y1 = anchors.get(BACK_FIELDS[i + 1].name) if i < 4 else (y0 + 60 if y0 else None)
            if y0 is None or y1 is None:
                result['fields'][f.name] = {'status': 'revisar_recorte', 'value': '',
                                          'reasons': ['ancora_ausente', 'vazio_nao_confirmado']}
                continue
            box = (round(5 * scale), y0 - 12, min(image.width, round(150 * scale)), y1 - 12)
            if f.name == 'nome':
                left, top, right, bottom = box
                box = (left, shifted_name_top(rows, top, y0, bottom, left, right), right, bottom)
        else:
            box = tuple(round(v * scale) for v in (5, f.top, 150, f.bottom))
        crop = image.crop(box)
        a = ocr(crop, output / f'{n}-{f.name}-a', binary, 6)
        b = ocr(ImageOps.expand(crop.resize((crop.width * 3 // 2, crop.height * 3 // 2)), border=20, fill='white'),
                output / f'{n}-{f.name}-b', binary, 6 if f.name == 'nome' else 7)
        va, vb = clean(a, f), clean(b, f)
        confidence = min([float(r['conf']) for r in a + b] or [0])
        reasons = []
        x0, y0, x1, y1 = box
        crossing = any(
            int(t['left']) < x1 and int(t['left']) + int(t['width']) > x0
            and any(int(t['top']) < y < int(t['top']) + int(t['height']) for y in (y0, y1))
            for t in (name_words(rows) if f.name == 'nome' else rows))
        if crossing: reasons.append('possivel_corte_de_texto')
        if va != vb: reasons.append('divergencia_entre_passagens')
        if confidence < 85: reasons.append('confianca_baixa')
        if not va: reasons.append('vazio_nao_confirmado')
        if f.name == 'admissao':
            try: datetime.strptime(va, '%d/%m/%Y')
            except ValueError: reasons.append('formato_data')
        if f.name == 'matricula' and not re.fullmatch(r'\d+', va): reasons.append('formato_matricula')
        if f.name == 'pis' and not re.fullmatch(r'\d{11}', re.sub(r'[.\- /]', '', va)): reasons.append('pis_ausente_ou_formato')
        if f.name == 'tipo_sanguineo' and not re.fullmatch(r'(?:A|B|AB|O)[+-]', va.upper().replace(' ', '')): reasons.append('tipo_ausente_ou_formato')
        result['fields'][f.name] = {'value': va, 'alternative': vb, 'confidence_min': confidence,
            'status': 'revisar' if reasons else 'consistente_ocr', 'reasons': reasons,
            'box_pixels': box, 'crop_check': 'revisar' if crossing else 'sem_cruzamento_detectado', 'leading_zero': va.startswith('0')}
    return result
