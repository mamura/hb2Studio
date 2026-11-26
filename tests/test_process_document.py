import json
from pathlib import Path
import tempfile
import unittest

import pdfplumber

from hb2_studio.engine import Badge, PageResult
from tools.process_document import apply_source_confirmation, load_confirmations, write_review


class FullDocumentReviewTests(unittest.TestCase):
    def test_source_confirmation_keeps_value_and_replaces_only_cut_reason(self):
        page = PageResult(6, 'verso', False, {'nome': 'Ágata Exem'}, {
            'nome': {'origem': 'ocr', 'status': 'revisar',
                     'reasons': ['possivel_corte_de_texto', 'confianca_baixa']}})
        apply_source_confirmation(page, {})
        self.assertIn('possivel_corte_de_texto', page.details['nome']['reasons'])
        apply_source_confirmation(page, {6: {'arquivo': 'confirmacao-ficticia.json'}})
        self.assertEqual(page.values['nome'], 'Ágata Exem')
        self.assertEqual(page.details['nome']['reasons'],
                         ['confianca_baixa', 'nome_incompleto_na_origem'])

    def test_confirmation_requires_explicit_visual_record_and_matching_document(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'confirmacoes.json'
            data = {'documento_sha256': 'abc', 'confirmado_visualmente': True,
                    'motivo': 'nome_incompleto_na_origem', 'paginas': [6]}
            path.write_text(json.dumps(data))
            self.assertEqual(set(load_confirmations(path, 'abc')), {6})
            with self.assertRaises(ValueError):
                load_confirmations(path, 'outro-documento')
            data['confirmado_visualmente'] = False
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                load_confirmations(path, 'abc')

    def test_review_pdf_keeps_front_reference_separate_from_readable_back_fragment(self):
        front = PageResult(5, 'frente', True, {'nome_frente': 'Ágata Referência'}, {
            'nome_frente': {'origem': 'pdfplumber', 'status': 'extraido', 'reasons': []}})
        back = PageResult(6, 'verso', False, {'nome': 'Ágata Exem'}, {
            'nome': {'origem': 'ocr', 'status': 'revisar',
                     'reasons': ['nome_incompleto_na_origem']}})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'revisao.pdf'
            self.assertEqual(write_review(output, [Badge(front, back)]), 1)
            with pdfplumber.open(output) as pdf:
                text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
            for expected in ['Ágata Referência', 'Ágata Exem', 'nome_incompleto_na_origem']:
                self.assertIn(expected, text)
        self.assertEqual(back.values['nome'], 'Ágata Exem')
