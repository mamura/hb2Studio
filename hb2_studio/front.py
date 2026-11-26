"""Nome de guerra e foto visível da frente, sem alterar dados do verso."""
from pathlib import Path
import re

from PIL import Image, ImageChops, ImageStat, ImageOps

from .layout import Field, read_field
from .ocr import ocr, name_words


def photo_candidates(page):
    return [i for i in page.images if
            ((65 <= i['top'] <= 95 and 175 <= i['bottom'] <= 205)
             or (100 <= i['top'] <= 120 and 215 <= i['bottom'] <= 235))
            and 55 <= i['width'] <= 145 and i['x1'] <= 155]


def front_name_box(page):
    photos = photo_candidates(page)
    if len(photos) != 1:
        return None
    return (7, 239, 140, 263) if photos[0]['top'] > 100 else (5, 209, 150, 232)


def read_front_name(page, output, binary='tesseract', existing=None):
    output = Path(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    box = front_name_box(page)
    if box is None:
        return {'valor': existing or '', 'origem': 'pdfplumber' if existing else 'sem_valor',
                'status': 'revisar', 'reasons': ['layout_frente_ambiguo']}
    value = existing or read_field(page.dedupe_chars(), Field('nome_frente', box[1], box[3], 'nome', box[0], box[2]))
    if value:
        # Glyph geometry of the printed name (small label excluded).
        glyphs = [c for c in page.chars if c['height'] >= 6 and c['top'] < box[3]
                  and c['bottom'] > box[1] and c['x0'] < box[2] and c['x1'] > box[0]]
        cut = any(c['x0'] < box[0] or c['x1'] > box[2] or c['top'] < box[1]
                  or c['bottom'] > box[3] for c in glyphs)
        return {'valor': value, 'origem': 'pdfplumber', 'status': 'revisar' if cut else 'extraido',
                'reasons': ['possivel_corte_de_texto'] if cut else [], 'box_pdf': box}
    crop = page.crop(box).to_image(resolution=400).original.convert('RGB')
    a = name_words(ocr(crop, output/f'frente-{page.page_number}-nome-a', binary, 6))
    b_image = ImageOps.expand(crop.resize((crop.width*3//2, crop.height*3//2)), border=20, fill='white')
    b = name_words(ocr(b_image, output/f'frente-{page.page_number}-nome-b', binary, 6))
    def usable(rows, image, minimum):
        words = [r for r in rows if r['text'].strip()
                 and not re.fullmatch(r'nome\s*[:.;]?', r['text'], re.I)]
        large = [r for r in words if int(r['height']) >= minimum
                 and not (int(r['height']) > image.height*.75 and int(r['width']) < image.width*.02)]
        if large:
            minimum = max(minimum, max(int(r['height']) for r in large)*.45)
            large = [r for r in large if int(r['height']) >= minimum]
        # Tiny remnants of the label are not name glyphs. Keep printed separators
        # when they are aligned vertically with the name's larger glyphs.
        separators = [r for r in words if r not in large and r['text'] in {"-", "'", "’"}
                      and any(int(t['top']) <= int(r['top'])+int(r['height'])/2 <= int(t['top'])+int(t['height']) for t in large)]
        return [r for r in words if r in large or r in separators]
    a, b = usable(a, crop, 12), usable(b, b_image, 18)
    va, vb = (' '.join(r['text'].strip() for r in rows) for rows in [a, b])
    reasons = []
    confidence = min([float(r['conf']) for r in a+b] or [0])
    if not va: reasons.append('vazio_nao_confirmado')
    if not any(c.isalpha() for c in va): reasons.append('nome_ilegivel')
    if confidence < 85: reasons.append('confianca_baixa')
    if va != vb: reasons.append('divergencia_entre_passagens')
    if any(int(r['left']) <= 2 or int(r['top']) <= 2
           or int(r['left'])+int(r['width']) >= crop.width-2
           or int(r['top'])+int(r['height']) >= crop.height-2 for r in a):
        reasons.append('possivel_corte_de_texto')
    if any(not (c.isalpha() or c.isspace() or c in "-'.’") for c in va):
        reasons.append('leitura_duvidosa')
    return {'valor': va, 'alternative': vb, 'origem': 'ocr', 'status': 'revisar' if reasons else 'consistente_ocr',
            'reasons': reasons, 'confidence_min': confidence, 'box_pdf': box}


def extract_photo(page, pdfium_page, output):
    """Só aproveita imagem nativa se sua aparência coincidir com a região visível."""
    import pypdfium2 as pdfium
    photos = photo_candidates(page)
    if len(photos) != 1:
        return {'valor': '', 'origem': 'sem_valor', 'status': 'revisar',
                'reasons': ['foto_ausente' if not photos else 'foto_ambigua']}
    photo = photos[0]
    box = (photo['x0'], photo['top'], photo['x1'], photo['bottom'])
    # The photo rectangle is disjoint from the name region and badge logo above.
    name = front_name_box(page)
    if box[0] < 0 or box[2] > page.width or box[3] >= name[1]:
        return {'valor': '', 'origem': 'sem_valor', 'status': 'revisar', 'reasons': ['foto_ambigua']}
    visible = page.crop(box).to_image(resolution=300).original.convert('RGB')
    chosen, origin = visible, 'renderizacao_regiao_visivel'
    matched_error = None
    objects = []
    for obj in pdfium_page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE]):
        left, bottom, right, top = obj.get_bounds()
        bounds = (left, page.height-top, right, page.height-bottom)
        if max(abs(a-b) for a,b in zip(bounds,box)) < 0.1:
            objects.append(obj)
    attrs = photo['stream'].attrs
    if len(objects) == 1 and 'SMask' not in attrs and 'Mask' not in attrs:
        try:
            bitmap = objects[0].get_bitmap()
            # Native bitmap is owned by PDFium's image object, not this caller.
            native = bitmap.to_pil().convert('RGB').copy()
            ratio_error = abs((native.width/native.height) / (visible.width/visible.height) - 1)
            a = native.resize((160,200), Image.Resampling.LANCZOS)
            b = visible.resize((160,200), Image.Resampling.LANCZOS)
            diff = ImageChops.difference(a,b)
            matched_error = sum(ImageStat.Stat(diff).mean)/3
            strong = sum(count for count, color in diff.getcolors(160*200) if max(color)>30) / (160*200)
            if ratio_error < 0.02 and matched_error <= 4 and strong <= 0.02:
                chosen, origin = native, 'imagem_incorporada'
        except (RuntimeError, ValueError, pdfium.PdfiumError):
            pass
    output = Path(output)
    target = output/'fotos'/f'frente-{page.page_number:03d}.png'
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    chosen.save(target)
    target.chmod(0o600)
    return {'valor': target.relative_to(output).as_posix(), 'origem': origin, 'status': 'extraido',
            'reasons': [], 'box_pdf': box, 'comparacao_media_rgb': matched_error,
            'dimensoes': list(chosen.size)}
