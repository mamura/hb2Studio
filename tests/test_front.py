from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pdfplumber
import pypdfium2 as pdfium
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from hb2_studio.front import read_front_name, extract_photo, front_name_box


def make_front(path, masked=False, count=1, shifted=False, text=True, clip=False):
    c = canvas.Canvas(str(path), pagesize=(612,792))
    logo=Image.new('RGB',(140,30),'green')
    c.drawImage(ImageReader(logo),5,742,width=140,height=30)
    image=Image.new('RGBA' if masked else 'RGB',(80,120), (0,0,255,0) if masked else 'blue')
    if masked:
        for x in range(10,70):
            for y in range(10,110): image.putpixel((x,y),(255,0,0,255))
    for i in range(count):
        top=108 if shifted else 75
        c.saveState()
        if clip:
            clipping=c.beginPath();clipping.rect(50,792-top-120,40,120)
            c.clipPath(clipping,stroke=0,fill=0)
        c.drawImage(ImageReader(image), 30+i*10,792-top-120,width=80,height=120,mask='auto')
        c.restoreState()
    if text:
        c.setFont('Helvetica',12)
        c.drawString(30,792-(251 if shifted else 222),'Agata-Silva')
    c.save()


class FrontTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'ficticio.pdf'

    def photo(self, **kwargs):
        make_front(self.path,**kwargs)
        with pdfplumber.open(self.path) as doc,pdfium.PdfDocument(self.path) as native:
            p=native[0]
            try:return extract_photo(doc.pages[0],p,self.root)
            finally:p.close()

    def test_native_photo_contains_neither_badge_logo_nor_name(self):
        result=self.photo()
        self.assertEqual(result['origem'],'imagem_incorporada')
        with Image.open(self.root/result['valor']) as image:
            self.assertEqual(image.getpixel((0,0)),(0,0,255))
            self.assertEqual(image.getcolors(),[(80*120,(0,0,255))])

    def test_alpha_mask_uses_visible_rendered_region(self):
        result=self.photo(masked=True)
        self.assertEqual(result['origem'],'renderizacao_regiao_visivel')
        with Image.open(self.root/result['valor']) as image:
            self.assertEqual(image.getpixel((0,0)),(255,255,255))
            self.assertEqual(image.getpixel((image.width//2,image.height//2)),(255,0,0))

    def test_missing_and_ambiguous_photo_flagged(self):
        self.assertEqual(self.photo(count=0)['reasons'],['foto_ausente'])
        self.assertEqual(self.photo(count=2)['reasons'],['foto_ambigua'])

    def test_name_regions_and_direct_printed_text_preserved(self):
        for shifted,top in [(False,209),(True,239)]:
            make_front(self.path,shifted=shifted)
            with pdfplumber.open(self.path) as doc,patch('hb2_studio.front.ocr') as mocked:
                p=doc.pages[0]
                self.assertEqual(front_name_box(p)[1],top)
                result=read_front_name(p,self.root,existing='Ágata-Silva')
                self.assertEqual(result['valor'],'Ágata-Silva')
                self.assertEqual(result['origem'],'pdfplumber')
                mocked.assert_not_called()

    def test_ocr_removes_tiny_label_noise_and_preserves_accents_hyphens(self):
        make_front(self.path,shifted=True,text=False)
        def row(text,top,height,width=50,left=100):
            return dict(text=text,top=str(top),height=str(height),width=str(width),left=str(left),
                        level='5',page_num='1',block_num='1',par_num='1',line_num='1',word_num=str(left),conf='96')
        a=[row('X',20,4,left=1),row('Ágata-Silva',55,60,left=180),row('|',0,170,3,790)]
        b=[row('X',50,6,left=1),row('Ágata-Silva',103,90,left=290),row('|',20,255,4,1205)]
        with pdfplumber.open(self.path) as doc,patch('hb2_studio.front.ocr',side_effect=[a,b]):
            result=read_front_name(doc.pages[0],self.root)
        self.assertEqual(result['valor'],'Ágata-Silva')
        self.assertEqual(result['reasons'],[])

    def test_clipping_path_uses_visible_photo_instead_of_native_image(self):
        result=self.photo(clip=True)
        self.assertEqual(result['origem'],'renderizacao_regiao_visivel')
        with Image.open(self.root/result['valor']) as image:
            self.assertEqual(image.getpixel((0,0)),(255,255,255))
            self.assertEqual(image.getpixel((image.width//2,image.height//2)),(0,0,255))

    def test_empty_front_name_stays_empty_and_unconfirmed(self):
        make_front(self.path,text=False)
        with pdfplumber.open(self.path) as doc,patch('hb2_studio.front.ocr',return_value=[]):
            result=read_front_name(doc.pages[0],self.root)
        self.assertEqual(result['valor'],'')
        self.assertIn('vazio_nao_confirmado',result['reasons'])
        self.assertIn('nome_ilegivel',result['reasons'])

    def test_possible_name_cut_keeps_readable_fragment(self):
        make_front(self.path,shifted=True,text=False)
        row=dict(text='Ágata',top='90',height='81',width='150',left='180',level='5',
                 page_num='1',block_num='1',par_num='1',line_num='1',word_num='1',conf='96')
        with pdfplumber.open(self.path) as doc,patch('hb2_studio.front.ocr',return_value=[row]):
            result=read_front_name(doc.pages[0],self.root)
        self.assertEqual(result['valor'],'Ágata')
        self.assertIn('possivel_corte_de_texto',result['reasons'])
