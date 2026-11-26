"""Regressões OCR com dados exclusivamente fictícios."""
import unittest

from hb2_studio.layout import BACK_FIELDS
from tools.pilot_ocr import clean


class NameAssemblyTests(unittest.TestCase):
    def test_label_on_second_line_and_border_on_first(self):
        def token(text, line, word, level='5'):
            return dict(level=level, page_num='1', block_num='1', par_num='1',
                        line_num=str(line), word_num=str(word), text=text)

        rows = [
            token('Ágata', 1, 1),
            token('Lúcia', 1, 2),
            token('|', 1, 3),
            token('NOME:', 2, 1),
            token('Sá-Félix', 2, 2),
            token('IGNORAR', 1, 0, level='4'),
        ]
        # A ordem deve vir da hierarquia TSV, inclusive com entrada embaralhada.
        self.assertEqual(clean(list(reversed(rows)), BACK_FIELDS[0]),
                         'Ágata Lúcia Sá-Félix')

class ShiftedNameCropTests(unittest.TestCase):
    def test_top_includes_first_line_with_margin(self):
        from tools.pilot_ocr import shifted_name_top
        row = dict(level='5', page_num='1', block_num='1', par_num='1',
                   line_num='1', word_num='1', text='Ágata',
                   top='328', height='26', left='175')
        self.assertEqual(shifted_name_top([row], 341, 353, 425, 28, 833), 316)
        self.assertEqual(shifted_name_top([], 341, 353, 425, 28, 833), 341)


if __name__ == '__main__':
    unittest.main()
