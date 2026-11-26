"""Regiões em pontos PDF, medidas a partir do canto superior esquerdo."""
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    name: str
    top: float
    bottom: float
    label: str = ""
    left: float = 0
    right: float = 155

    @property
    def box(self):
        return self.left, self.top, self.right, self.bottom


FRONT_FIELDS = (Field("nome_frente", 209, 232, "nome"),)
BACK_FIELDS = (
    Field("nome", 20, 42, "nome"),
    Field("admissao", 42, 55, "admiss[aã]o"),
    Field("matricula", 55, 68, "matr[ií]cula"),
    Field("pis", 68, 81, "pis"),
    Field("tipo_sanguineo", 81, 95, "tipo(?: +sangu[ií]neo)?"),
)


def normalize(text):
    return "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )


def label_pattern(field):
    return rf"(?im)^ *{field.label}\b *[:.\-]? *"


def read_field(page, field):
    lines = page.crop(field.box).extract_text(x_tolerance=2, y_tolerance=2) or ""
    if field.label:
        lines = re.sub(label_pattern(field), "", lines)
        # The name label can sit vertically between two lines of the value.
        lines = re.sub(rf"(?im)\b{field.label}\s*:", "", lines)
    return " ".join(lines.split())
