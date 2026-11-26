import tempfile
import unittest
from pathlib import Path

from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from PIL import Image

from hb2_studio.engine import analyze_pdf


def make_pdf(path, pages):
    pdf = canvas.Canvas(str(path), pagesize=(612, 792))
    image = ImageReader(Image.new("RGB", (20, 20), "white"))

    def text(x, top, value):
        pdf.drawString(x, 792 - top, value)

    for side, selectable in pages:
        pdf.setFont("Helvetica", 7)
        if side in {"frente", "frente_deslocada"}:
            photo_bottom = 565 if side == "frente_deslocada" else 596
            photo_height = 110 if side == "frente_deslocada" else 120
            pdf.drawImage(image, 33, photo_bottom, 87, photo_height)
            if selectable:
                text(7, 208, "Nome:")
                text(42, 222, "Ágata")
        if side in {"verso", "verso_deslocado"}:
            offset = 32 if side == "verso_deslocado" else 0
            for top in (121 + offset, 146 + offset, 171 + offset, 196 + offset):
                pdf.drawImage(image, 4, 792 - top - 24, 27, 24)
            if selectable:
                text(33, 29, "Ágata")
                text(7, 34, "Nome:")
                text(33, 37, "Silva Exemplo")
                text(7, 50, "Admissão: 01/02/2025")
                text(7, 63, "Matrícula: 0007")
                text(7, 76, "PIS:")
                text(7, 89, "Tipo Sanguíneo: O+")
                text(7, 112, "Texto de outra região")
        pdf.showPage()
    pdf.save()


class EngineTests(unittest.TestCase):
    def analyze(self, pages):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sintetico.pdf"
            make_pdf(path, pages)
            return analyze_pdf(path)

    def test_field_regions_and_redacted_diagnostic(self):
        result = self.analyze([("frente", True), ("verso", True)])
        badge, = result.badges
        self.assertEqual(badge.front.values["nome_frente"], "Ágata")
        self.assertEqual(badge.back.values, {
            "nome": "Ágata Silva Exemplo",
            "admissao": "01/02/2025",
            "matricula": "0007",
            "pis": "",
            "tipo_sanguineo": "O+",
        })
        self.assertEqual(badge.name_check, "compativel")
        badge.front.values["nome_frente"] = "Exemplo"
        self.assertEqual(badge.name_check, "compativel")
        badge.front.values["nome_frente"] = "Outro"
        self.assertEqual(badge.name_check, "divergente")
        report = result.diagnostic()
        self.assertNotIn("Ágata", str(report))
        self.assertNotIn("0007", str(report))
        self.assertEqual(report["pares"][0]["verso"]["campos"]["pis"], "revisar_campo")

    def test_pair_without_text_flags_ocr(self):
        result = self.analyze([("frente_deslocada", False), ("verso_deslocado", False)])
        pair, = result.diagnostic()["pares"]
        self.assertEqual(pair["verso"]["campos"]["nome"], "candidato_ocr")
        self.assertEqual(pair["comparacao_nomes"], "indisponivel")

    def test_reversed_pair_unknown_page_and_orphan(self):
        result = self.analyze([
            ("verso", False), ("frente", False),
            ("desconhecido", False), ("verso", False), ("frente", False),
        ])
        self.assertEqual(result.page_count, 5)
        self.assertEqual(result.badges, [])
        self.assertEqual([[page.number for page in group] for group in result.rejected],
                         [[1, 2], [3, 4], [5]])

class OCRIntegrationTests(unittest.TestCase):
    def run_pdf(self, pages, extraction):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sintetico.pdf'
            make_pdf(path, pages)
            with patch('hb2_studio.ocr.extract_back', return_value={'fields': extraction}) as mocked:
                result = analyze_pdf(path, ocr_pages=[2], ocr_output=Path(directory)/'privado')
            return result, mocked

    def test_complements_only_empty_fields_and_keeps_direct_zeros(self):
        result, mocked = self.run_pdf([('frente', True), ('verso', True)], {
            'matricula': {'value': '9999', 'status': 'consistente_ocr', 'reasons': []},
            'pis': {'value': '00123456789', 'alternative': '00123456789',
                    'status': 'revisar', 'reasons': ['confianca_baixa']},
        })
        back = result.badges[0].back
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(back.values['matricula'], '0007')
        self.assertEqual(back.details['matricula']['origem'], 'pdfplumber')
        self.assertEqual(back.values['pis'], '00123456789')
        self.assertEqual(back.details['pis']['origem'], 'ocr')
        self.assertEqual(back.diagnostic()['campos']['pis'], 'revisar')
        self.assertNotIn('00123456789', str(result.diagnostic()))

    def test_unconfirmed_empty_ocr_remains_flagged(self):
        result, _ = self.run_pdf([('frente', False), ('verso', False)], {
            name: {'value': '', 'status': 'revisar', 'reasons': ['vazio_nao_confirmado']}
            for name in ['nome', 'admissao', 'matricula', 'pis', 'tipo_sanguineo']})
        back = result.badges[0].back
        self.assertTrue(all(v['origem'] == 'ocr' for v in back.details.values()))
        self.assertTrue(all(v['reasons'] == ['vazio_nao_confirmado'] for v in back.details.values()))

    def test_ocr_never_runs_for_front_or_unknown_page(self):
        result, mocked = self.run_pdf([('verso', False), ('frente', False)], {})
        mocked.assert_not_called()

    def test_missing_tesseract_keeps_values_empty_and_flags_failure(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'sintetico.pdf'
            make_pdf(path, [('frente', False), ('verso', False)])
            with patch('hb2_studio.ocr.extract_back', side_effect=FileNotFoundError):
                result = analyze_pdf(path, ocr_pages=[2], ocr_output=directory)
        back = result.badges[0].back
        self.assertEqual(back.values['nome'], '')
        self.assertIn('ocr_indisponivel', back.details['nome']['reasons'])

class FrontOCRIntegrationTests(unittest.TestCase):
    def test_front_enrichment_is_explicit_and_never_runs_back_ocr(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sintetico.pdf'
            make_pdf(path,[('frente',False),('verso',True)])
            with patch('hb2_studio.front.read_front_name',return_value={
                'valor':'Ágata-Silva','origem':'ocr','status':'consistente_ocr','reasons':[]}) as name, patch('hb2_studio.ocr.extract_back') as back:
                result=analyze_pdf(path,front_ocr_pages=[1],front_output=directory)
            name.assert_called_once()
            back.assert_not_called()
            self.assertEqual(result.badges[0].front.values['nome_frente'],'Ágata-Silva')
            self.assertEqual(result.badges[0].front.details['nome_frente']['origem'],'ocr')
            self.assertEqual(result.badges[0].back.values['matricula'],'0007')
