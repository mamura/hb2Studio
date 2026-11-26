"""Processamento local explícito de documento completo, com folha privada de revisão."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hb2_studio.engine import analyze_pdf


def apply_source_confirmation(page, confirmations):
    """Só uma confirmação humana vinculada ao documento promove o alerta."""
    if page.number not in confirmations:
        return
    info = page.details['nome']
    info['reasons'] = [r for r in info.get('reasons', []) if r != 'possivel_corte_de_texto']
    if 'nome_incompleto_na_origem' not in info['reasons']:
        info['reasons'].append('nome_incompleto_na_origem')
    info['status'] = 'revisar'
    info['confirmacao_origem'] = confirmations[page.number]


def load_confirmations(path, digest):
    if path is None:
        return {}
    data = json.loads(path.read_text())
    if (data.get('documento_sha256') != digest
            or data.get('confirmado_visualmente') is not True
            or data.get('motivo') != 'nome_incompleto_na_origem'):
        raise ValueError('A confirmação deve ser visual, explícita e vinculada ao hash do PDF.')
    pages = data['paginas']
    if not all(type(n) is int and n > 0 and n % 2 == 0 for n in pages):
        raise ValueError('A confirmação deve identificar páginas de verso válidas.')
    return {n: {'arquivo': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            for n in pages}


def serialize_page(page):
    return {'pagina': page.number, 'lado': page.side, 'tem_texto': page.has_text,
            'campos': {name: {'valor': value,
                                **{k: v for k, v in page.details[name].items() if k != 'value'}}
                       for name, value in page.values.items()}}


def write_review(path, badges):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, PageBreak
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    font_path = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    font = 'Helvetica'
    if font_path.is_file():
        pdfmetrics.registerFont(TTFont('LocalSans', str(font_path)))
        font = 'LocalSans'
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = font
    body = styles['BodyText']
    body.fontSize = 8
    body.leading = 11
    def para(value):
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), body)
    story = []
    total_rows = 0
    for pair in badges:
        rows = []
        for page in [pair.front, pair.back]:
            for name, value in page.values.items():
                info = page.details[name]
                if info['status'] in {'extraido', 'consistente_ocr'} and not info.get('reasons'):
                    continue
                reasons = info.get('reasons') or ['revisar_campo']
                rows.append([para(page.number), para(name),
                             para(value if value else '[vazio — ausência não confirmada]'),
                             para('\n'.join(reasons) + '\nOrigem: ' + info['origem']),
                             para('[ ] Correto\n[ ] Incorreto\n[ ] Vazio confirmado\n[ ] Ilegível')])
        if not rows:
            continue
        if story:
            story.append(PageBreak())
        story.extend([Paragraph(f'Revisão local — páginas {pair.front.number}/{pair.back.number}', styles['Heading2']),
                      para('Dados pessoais. Valores lidos preservados, sem completar nomes por inferência.'),
                      para('Referência separada — nome da frente: ' + (pair.front.values['nome_frente'] or '[indisponível por extração direta]')),
                      para('Origem da referência: ' + pair.front.details['nome_frente']['origem']),
                      Spacer(1, 10)])
        table = LongTable([[para(v) for v in ['Página', 'Campo', 'Valor lido', 'Motivo da revisão', 'Conferência']]] + rows,
                          colWidths=[33, 64, 140, 170, 100], repeatRows=1, hAlign=TA_LEFT)
        table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'),
                                   ('GRID', (0,0), (-1,-1), 0.4, colors.grey),
                                   ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e8e8e8')),
                                   ('TOPPADDING', (0,0), (-1,-1), 7),
                                   ('BOTTOMPADDING', (0,0), (-1,-1), 7)]))
        story.extend([table, Spacer(1, 10), para('Observações / correção: _________________________________________________________'), Spacer(1,20), para('Conferido por: ______________________________    Data: __________________')])
        total_rows += len(rows)
    def footer(canvas, doc):
        canvas.setFont(font, 8)
        canvas.drawString(30, 18, f'Folha privada de revisão — {doc.page}')
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=30, rightMargin=30,
                      topMargin=30, bottomMargin=30, title='Folha privada de revisão HB2 Studio',
                      author='HB2 Studio').build(story, onFirstPage=footer, onLaterPages=footer)
    return total_rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('pdf', type=Path)
    ap.add_argument('--esperados', type=int, default=163)
    ap.add_argument('--tesseract', default='tesseract')
    ap.add_argument('--confirmacoes', type=Path)
    args = ap.parse_args()
    os.umask(0o077)
    digest = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    confirmations = load_confirmations(args.confirmacoes, digest)
    root = Path(__file__).resolve().parents[1] / 'resultados'
    output = root/('documento-completo-' + datetime.now(ZoneInfo('America/Fortaleza')).strftime('%Y-%m-%d_%H-%M-%S_%f'))
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    print(json.dumps({'pasta': str(output), 'etapa': 'extracao_direta'}), flush=True)
    baseline = analyze_pdf(args.pdf)
    if len(baseline.badges) != args.esperados or baseline.rejected:
        raise ValueError('Contagem inicial ou ordem dos pares inválida; processamento interrompido.')
    if not set(confirmations).issubset({b.back.number for b in baseline.badges}):
        raise ValueError('Confirmação aponta uma página fora dos versos validados.')
    pages = [b.back.number for b in baseline.badges if any(not v for v in b.back.values.values())]
    print(json.dumps({'etapa': 'ocr_complementar', 'pares': len(baseline.badges), 'versos_selecionados': len(pages), 'confirmacoes_na_origem': len(confirmations)}), flush=True)
    result = analyze_pdf(args.pdf, ocr_pages=pages, ocr_output=output, tesseract=args.tesseract)
    assert len(result.badges) == args.esperados and not result.rejected
    assert result.page_count == args.esperados * 2
    preserved = 0
    for before, after in zip(baseline.badges, result.badges):
        assert (before.front.number, before.back.number) == (after.front.number, after.back.number)
        for old_page, new_page in [(before.front, after.front), (before.back, after.back)]:
            for name, value in old_page.values.items():
                if value:
                    assert new_page.values[name] == value
                    assert new_page.details[name]['origem'] == 'pdfplumber'
                    preserved += 1
        apply_source_confirmation(after.back, confirmations)
    records = [{'par': i, 'frente': serialize_page(b.front), 'verso': serialize_page(b.back),
                'comparacao_nomes': b.name_check} for i, b in enumerate(result.badges, 1)]
    payload = {'paginas': result.page_count, 'pares_contabilizados': len(records),
               'grupos_rejeitados': len(result.rejected), 'pares': records}
    (output/'valores-finais.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    count = {}
    reasons = Counter()
    for side in ['frente', 'verso']:
        for name in records[0][side]['campos']:
            fields = [r[side]['campos'][name] for r in records]
            by_reason = Counter(reason for v in fields for reason in v.get('reasons', []))
            reasons.update(by_reason)
            count[name] = {'preenchidos': sum(bool(v['valor']) for v in fields),
                           'vazios': sum(not v['valor'] for v in fields),
                           'revisar': sum(v['status'] not in {'extraido', 'consistente_ocr'} or bool(v.get('reasons')) for v in fields),
                           'origens': dict(Counter(v['origem'] for v in fields)),
                           'motivos': dict(by_reason)}
    rows = write_review(output/'folha-revisao.pdf', result.badges)
    assert rows == sum(c['revisar'] for c in count.values())
    summary = {'json': str(output/'valores-finais.json'), 'folha': str(output/'folha-revisao.pdf'),
               'pares_contabilizados': len(records), 'paginas': result.page_count,
               'grupos_rejeitados': len(result.rejected), 'versos_com_ocr': len(pages),
               'valores_diretos_preservados': preserved, 'confirmacoes_na_origem': len(confirmations),
               'contagens_por_campo': count, 'motivos_revisao': dict(reasons),
               'linhas_folha_revisao': rows,
               'valores_com_zero_inicial': sum(v['valor'].startswith('0') for r in records for side in ['frente', 'verso'] for v in r[side]['campos'].values())}
    (output/'agregado.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (output/'manifesto.json').write_text(json.dumps({'documento_sha256': digest,
        'confirmacoes': str(args.confirmacoes) if args.confirmacoes else None,
        'regra_confirmacao': 'Sem registro explícito, suspeitas permanecem possivel_corte_de_texto.',
        'timezone': 'America/Fortaleza',
        'codigo_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in map(Path, ['hb2_studio/engine.py', 'hb2_studio/ocr.py', 'tools/process_document.py'])},
        'artefatos_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}}, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
