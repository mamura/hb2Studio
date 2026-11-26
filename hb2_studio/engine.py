"""Diagnóstico público sem valores e extração local sob demanda."""
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
import subprocess

from .layout import BACK_FIELDS, FRONT_FIELDS, normalize, read_field
from .front import photo_candidates


@dataclass
class PageResult:
    number: int
    side: str
    has_text: bool
    values: dict[str, str] = field(default_factory=dict)
    details: dict[str, dict] = field(default_factory=dict)

    def diagnostic(self):
        return {
            "pagina": self.number,
            "lado": self.side,
            "tem_texto": self.has_text,
            "campos": {
                name: self.details[name]['status'] if self.details.get(name, {}).get('origem') == 'ocr' else "extraido" if value else (
                    "revisar_campo" if self.has_text else "candidato_ocr"
                )
                for name, value in self.values.items()
            },
            "origens": {name: info['origem'] for name, info in self.details.items()},
            "alertas": {name: info.get('reasons', []) for name, info in self.details.items()},
        }


@dataclass
class Badge:
    front: PageResult
    back: PageResult

    @property
    def name_check(self):
        front = normalize(self.front.values["nome_frente"]).split()
        back = normalize(self.back.values["nome"]).split()
        if not front or not back:
            return "indisponivel"
        remaining = iter(back)
        return "compativel" if all(word in remaining for word in front) else "divergente"


@dataclass
class DocumentResult:
    page_count: int
    badges: list[Badge] = field(default_factory=list)
    rejected: list[tuple[PageResult, ...]] = field(default_factory=list)

    def diagnostic(self):
        return {
            "paginas": self.page_count,
            "pares_validados_por_layout": len(self.badges),
            "pares": [
                {
                    "frente": badge.front.diagnostic(),
                    "verso": badge.back.diagnostic(),
                    "comparacao_nomes": badge.name_check,
                }
                for badge in self.badges
            ],
            "grupos_rejeitados": [
                [page.diagnostic() for page in group] for group in self.rejected
            ],
        }


def detect_side(page):
    if page.rotation or page.width < 155 or page.height < 232:
        return "desconhecido"
    images = page.images
    photo = bool(photo_candidates(page))
    icons = sum(
        115 <= image["top"] <= 207 and image["x0"] >= 0
        and image["x1"] <= 43 and 15 <= image["height"] <= 32
        for image in images
    )
    if photo == (icons >= 3):
        return "desconhecido"
    return "frente" if photo else "verso"


def inspect_page(page, *, ocr_output=None, front_output=None, tesseract="tesseract"):
    side = detect_side(page)
    has_text = any(char["text"].strip() for char in page.chars)
    fields = {"frente": FRONT_FIELDS, "verso": BACK_FIELDS}.get(side, ())
    values = dict.fromkeys((item.name for item in fields), "")
    if has_text and fields:
        clean_page = page.dedupe_chars()
        values = {item.name: read_field(clean_page, item) for item in fields}
    details = {name: {'origem': 'pdfplumber' if value else 'sem_valor',
                      'status': 'extraido' if value else 'revisar_campo',
                      'reasons': [] if value else ['vazio_nao_confirmado']}
               for name, value in values.items()}
    # Preserve every directly extracted value; only complement empty back fields.
    if side == 'verso' and ocr_output is not None and any(not v for v in values.values()):
        from .ocr import extract_back
        try:
            extracted = extract_back(page, ocr_output, tesseract)['fields']
        except (OSError, subprocess.CalledProcessError):
            extracted = {name: {'value': '', 'status': 'revisar',
                               'reasons': ['ocr_indisponivel', 'vazio_nao_confirmado']}
                         for name in values}
        for name, info in extracted.items():
            if not values[name]:
                values[name] = info['value']
                details[name] = {**info, 'origem': 'ocr'}
    if side == 'frente' and front_output is not None:
        from .front import read_front_name
        try:
            info = read_front_name(page, front_output, tesseract, values['nome_frente'])
        except (OSError, subprocess.CalledProcessError):
            info = {'valor': values['nome_frente'], 'origem': 'ocr', 'status': 'revisar',
                    'reasons': ['ocr_indisponivel', 'vazio_nao_confirmado']}
        values['nome_frente'] = info['valor']
        details['nome_frente'] = {k: v for k, v in info.items() if k != 'valor'}
    return PageResult(page.page_number, side, has_text, values, details)


def analyze_pdf(path: str | Path, *, ocr_pages=(), ocr_output=None,
                tesseract="tesseract", front_ocr_pages=(), front_output=None) -> DocumentResult:
    front_ocr_pages = set(front_ocr_pages)
    if front_ocr_pages and front_output is None:
        raise ValueError('Informe uma pasta privada para os artefatos da frente.')
    ocr_pages = set(ocr_pages)
    if ocr_pages and ocr_output is None:
        raise ValueError('Informe uma pasta privada para os artefatos OCR.')
    with pdfplumber.open(path) as document:
        result = DocumentResult(len(document.pages))
        group = []
        for page in document.pages:
            group.append(inspect_page(page, ocr_output=(ocr_output if page.page_number in ocr_pages else None),
                                      front_output=(front_output if page.page_number in front_ocr_pages else None),
                                      tesseract=tesseract))
            page.close()
            if len(group) == 2:
                front, back = group
                if (front.side, back.side) == ("frente", "verso"):
                    result.badges.append(Badge(front, back))
                else:
                    result.rejected.append(tuple(group))
                group.clear()
        if group:
            result.rejected.append(tuple(group))
    return result
