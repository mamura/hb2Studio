import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import load_workbook

from hb2_studio.xlsx import export_xlsx, rows_from_json, verify_xlsx


def fixture(count=163):
    def field(value, reasons=None):
        return {'valor': value, 'origem': 'ocr',
                'status': 'revisar' if reasons else 'consistente_ocr', 'reasons': reasons or []}
    records = []
    for i in range(count):
        records.append({'par': i+1,
                        'frente': {'pagina': 2*i+1, 'campos': {'nome_frente': field('Nome Fictício')}},
                        'verso': {'pagina': 2*i+2, 'campos': {
                            'nome': field('Nome Fictício'), 'admissao': field('01/02/2025'),
                            'matricula': field('000007'), 'pis': field('00123456789'),
                            'tipo_sanguineo': field(None, ['vazio_nao_confirmado'])}}})
    records[0]['verso']['campos']['nome'] = field('=Nome Fictício', ['confianca_baixa', 'nome_incompleto_na_origem'])
    records[0]['frente']['campos']['nome_frente'] = field('', ['vazio_nao_confirmado'])
    return {'pares_contabilizados': count, 'grupos_rejeitados': 0, 'pares': records}


class XLSXTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name)/'ficticio.json'
        self.output = Path(self.temp.name)/'ficticio.xlsx'
        self.data = fixture()
        self.source.write_text(json.dumps(self.data))

    def test_163_records_identifiers_blanks_and_review_reasons_after_reopen(self):
        result = export_xlsx(self.source, self.output)
        self.assertEqual(result['registros'], 163)
        self.assertEqual(result['campos_em_revisao'], 165)
        self.assertEqual(result['identificadores_com_zero_inicial'], 326)
        self.assertEqual(result['pares_com_pendencias'], 163)
        book = load_workbook(self.output)
        try:
            self.assertEqual(book.sheetnames, ['Crachás', 'Revisão'])
            self.assertEqual(book['Crachás'].max_row, 164)
            self.assertEqual(book['Revisão'].max_row, 166)
            self.assertEqual(book['Crachás']['A2'].value, '=Nome Fictício')
            self.assertEqual(book['Crachás']['A2'].data_type, 's')
            self.assertEqual(book['Crachás']['C2'].value, '000007')
            self.assertEqual(book['Crachás']['D2'].value, '00123456789')
            self.assertEqual(book['Crachás']['C2'].number_format, '@')
            self.assertIsNone(book['Crachás']['E2'].value)
            alerts = [row for row in book['Revisão'].iter_rows(min_row=2, values_only=True)
                      if row[0] == 2 and row[1] == 'nome']
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0][4], 'confianca_baixa\nnome_incompleto_na_origem')
        finally:
            book.close()

    def test_numeric_identifier_rejected_without_silent_loss_of_zeros(self):
        self.data['pares'][0]['verso']['campos']['pis']['valor'] = 123456789
        self.source.write_text(json.dumps(self.data))
        with self.assertRaises(ValueError):
            export_xlsx(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_existing_workbook_never_overwritten(self):
        self.output.write_bytes(b'existente')
        with self.assertRaises(FileExistsError):
            export_xlsx(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), b'existente')

    def test_pair_count_mismatch_rejected(self):
        self.data['pares'].pop()
        with self.assertRaises(ValueError):
            rows_from_json(self.data)

    def test_export_never_executes_pdf_or_ocr_pipeline(self):
        with patch('hb2_studio.engine.analyze_pdf') as pdf, patch('hb2_studio.ocr.extract_back') as ocr:
            export_xlsx(self.source, self.output)
        pdf.assert_not_called()
        ocr.assert_not_called()

    def test_verification_detects_modified_identifier_type_and_value(self):
        export_xlsx(self.source, self.output)
        book = load_workbook(self.output)
        book['Crachás']['C2'] = 7
        book.save(self.output)
        book.close()
        badges, reviews = rows_from_json(self.data)
        with self.assertRaises(ValueError):
            verify_xlsx(self.output, badges, reviews)

class CombinedXLSXTests(unittest.TestCase):
    def test_paired_name_photo_links_and_pages(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);data=fixture(2)
            (root/'fotos').mkdir()
            for i,pair in enumerate(data['pares']):
                page=pair['frente']['pagina'];name=f'fotos/frente-{page:03d}.png'
                Image.new('RGB',(10,10),('blue','red')[i]).save(root/name)
                pair['frente']['campos']['foto']={'valor':name,'origem':'imagem_incorporada','status':'extraido','reasons':[]}
                pair['frente']['campos']['nome_frente']['valor']='Ágata-Silva'
            source=root/'ficticio.json';source.write_text(json.dumps(data))
            output=root/'ficticio.xlsx';result=export_xlsx(source,output,expected_pairs=2)
            self.assertEqual(result['fotos_com_links_validos'],2)
            book=load_workbook(output)
            try:
                sheet=book['Crachás']
                self.assertEqual(sheet['A1'].value,'Nome completo')
                self.assertEqual(sheet['G2'].value,'Ágata-Silva')
                self.assertEqual(sheet['H2'].hyperlink.target,'fotos/frente-001.png')
                self.assertEqual(sheet['H3'].hyperlink.target,'fotos/frente-003.png')
                self.assertEqual(sheet['I2'].value,1)
                self.assertEqual(sheet['F2'].value,2)
                self.assertEqual(sheet['C2'].value,'000007')
            finally:book.close()

    def test_photo_cannot_reference_another_pairs_page(self):
        data=fixture(2)
        data['pares'][0]['frente']['campos']['foto']={'valor':'fotos/frente-003.png','origem':'imagem_incorporada','status':'extraido','reasons':[]}
        with self.assertRaises(ValueError):rows_from_json(data,expected_pairs=2)
