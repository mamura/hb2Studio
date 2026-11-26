"""Exportação privada do JSON final; não abre PDF nem executa OCR."""
import json
import os
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font

FIELDS = ('nome', 'admissao', 'matricula', 'pis', 'tipo_sanguineo')
HEADERS = ('Nome completo', 'Admissão', 'Matrícula', 'PIS', 'Tipo sanguíneo',
           'Página do verso', 'Nome de guerra', 'Foto', 'Página da frente', 'Situação da revisão')
REVIEW_HEADERS = ('Página', 'Campo', 'Valor extraído', 'Origem', 'Motivo')


def flagged(info):
    return bool(info.get('reasons')) or info['status'] not in {'extraido', 'consistente_ocr'}


def rows_from_json(data, expected_pairs=163):
    pairs = data['pares']
    if (len(pairs) != expected_pairs or data['pares_contabilizados'] != expected_pairs
            or data.get('grupos_rejeitados') != 0):
        raise ValueError('Contagem de pares inválida ou grupos rejeitados.')
    badges, reviews, pages = [], [], set()
    for pair in pairs:
        front, back = pair['frente'], pair['verso']
        for side in (front, back):
            page = side['pagina']
            if type(page) is not int or page <= 0 or page in pages:
                raise ValueError('Página inválida ou duplicada.')
            pages.add(page)
            for name, info in side['campos'].items():
                value = info.get('valor')
                if value is not None and not isinstance(value, str):
                    raise ValueError('Valores devem ser texto ou nulos; não é seguro converter identificadores numéricos.')
                if not isinstance(info.get('origem'), str) or not isinstance(info.get('status'), str):
                    raise ValueError('Metadados de origem ou estado inválidos.')
                reasons = info.get('reasons', [])
                if not isinstance(reasons, list) or any(not isinstance(r, str) for r in reasons):
                    raise ValueError('Motivos de revisão inválidos.')
                if flagged(info):
                    reviews.append((page, name, value or None, info['origem'],
                                    '\n'.join(reasons) or info['status']))
        if front['pagina'] + 1 != back['pagina']:
            raise ValueError('Páginas do par fora de ordem.')
        pending = any(flagged(info) for side in (front, back) for info in side['campos'].values())
        values = tuple(back['campos'][name].get('valor') or None for name in FIELDS)
        photo = front['campos'].get('foto', {}).get('valor') or None
        if photo and photo != f"fotos/frente-{front['pagina']:03d}.png":
            raise ValueError('Caminho da foto não corresponde à página da frente.')
        badges.append((*values, back['pagina'], front['campos']['nome_frente'].get('valor') or None,
                       photo, front['pagina'], 'Pendente' if pending else 'Sem pendências'))
    return badges, reviews


def put_row(sheet, row):
    index = sheet.max_row + 1 if sheet.cell(1, 1).value is not None else 1
    for column, value in enumerate(row, 1):
        cell = sheet.cell(index, column, value)
        if isinstance(value, str):
            if len(value) > 32767:
                raise ValueError('Texto excede o limite de uma célula Excel.')
            # Force literal text, including names beginning with '=' or '+'.
            cell.data_type = 's'
            cell.number_format = '@'
        cell.alignment = Alignment(vertical='top', wrap_text=True)


def verify_xlsx(path, badges, reviews):
    """Reabre e compara todas as células com a fonte, inclusive tipos e alertas."""
    with_workbook = load_workbook(path, data_only=False)
    try:
        if with_workbook.sheetnames != ['Crachás', 'Revisão']:
            raise ValueError('Abas da planilha divergentes.')
        for title, header, expected in [('Crachás', HEADERS, badges), ('Revisão', REVIEW_HEADERS, reviews)]:
            sheet = with_workbook[title]
            if sheet.max_row != len(expected) + 1 or sheet.max_column != len(header):
                raise ValueError('Contagem de linhas ou colunas divergente.')
            if tuple(c.value for c in sheet[1]) != header:
                raise ValueError('Cabeçalhos divergentes.')
            for index, row in enumerate(expected, 2):
                for column, value in enumerate(row, 1):
                    cell = sheet.cell(index, column)
                    if cell.value != value or (isinstance(value, str) and cell.data_type != 's'):
                        raise ValueError('Valor ou tipo divergente após reabrir a planilha.')
            if title == 'Crachás':
                for index, expected_row in enumerate(expected, 2):
                    photo = expected_row[7]
                    cell = sheet.cell(index, 8)
                    if photo:
                        target = Path(path).parent / photo
                        if not cell.hyperlink or cell.hyperlink.target != photo or not target.is_file():
                            raise ValueError('Link relativo da foto inválido.')
                        from PIL import Image
                        with Image.open(target) as image:
                            image.verify()
                    elif cell.hyperlink:
                        raise ValueError('Foto ausente não pode ter link.')
                for row in range(2, len(expected) + 2):
                    for column in (3, 4):
                        if sheet.cell(row, column).number_format != '@':
                            raise ValueError('Matrícula e PIS devem ter formato texto.')
        return {'registros': len(badges), 'campos_em_revisao': len(reviews),
                'pares_com_pendencias': sum(row[-1] == 'Pendente' for row in badges),
                'identificadores_com_zero_inicial': sum(isinstance(row[i], str) and row[i].startswith('0') for row in badges for i in (2, 3)),
                'fotos_com_links_validos': sum(bool(row[7]) for row in badges),
                'verificacao': 'aprovada'}
    finally:
        with_workbook.close()


def export_xlsx(source, output, *, expected_pairs=163):
    source, output = Path(source), Path(output)
    if output.suffix.lower() != '.xlsx':
        raise ValueError('A saída deve ter extensão .xlsx.')
    badges, reviews = rows_from_json(json.loads(source.read_text(encoding='utf-8')), expected_pairs)
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, header, rows in [('Crachás', HEADERS, badges), ('Revisão', REVIEW_HEADERS, reviews)]:
        sheet = workbook.create_sheet(title)
        put_row(sheet, header)
        for row in rows:
            put_row(sheet, row)
        if title == 'Crachás':
            for index, row in enumerate(rows, 2):
                if row[7]:
                    sheet.cell(index, 8).hyperlink = row[7]
                    sheet.cell(index, 8).style = 'Hyperlink'
            for index in range(2, len(rows) + 2):
                for column in (3, 4):
                    sheet.cell(index, column).number_format = '@'
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = 28
        sheet.column_dimensions['A'].width = 44 if title == 'Crachás' else 12
        if title == 'Revisão':
            sheet.column_dimensions['E'].width = 60
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as target:
            workbook.save(target)
    finally:
        workbook.close()
    return verify_xlsx(output, badges, reviews)
