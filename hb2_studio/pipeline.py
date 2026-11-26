"""Fluxo da aplicação, independente de Qt. Usa os extratores e exportador existentes."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Callable

import pdfplumber
import pypdfium2 as pdfium

from .engine import Badge, DocumentResult, analyze_pdf, detect_side, inspect_page
from .front import extract_photo, read_front_name
from .runtime import subprocess_options


class PipelineError(RuntimeError):
    """Mensagem segura e acionável para a interface."""


class ProcessingCancelled(PipelineError):
    pass


@dataclass(frozen=True)
class Progress:
    stage: str
    pages: int | None = None
    pairs: int | None = None
    processed: int | None = None


@dataclass(frozen=True)
class Inspection:
    path: Path
    digest: str
    document: DocumentResult


@dataclass(frozen=True)
class PreviewRow:
    display_name: str
    full_name: str
    registration: str
    review: str


@dataclass(frozen=True)
class ProcessingResult:
    output_dir: Path
    workbook: Path
    photo_dir: Path
    json_path: Path
    total: int
    pending: int
    preview: tuple[PreviewRow, ...]


Notify = Callable[[Progress], None]
Cancelled = Callable[[], bool]


def _check_cancel(cancelled):
    if cancelled():
        raise ProcessingCancelled('Operação interrompida. Você pode tentar novamente.')


def _digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_pdf(path, notify: Notify = lambda _: None,
                cancelled: Cancelled = lambda: False) -> Inspection:
    path = Path(path).expanduser().resolve()
    _check_cancel(cancelled)
    notify(Progress('Contando páginas'))
    try:
        digest = _digest(path)
        with pdfplumber.open(path) as pdf:
            pages = len(pdf.pages)
        notify(Progress('Identificando frentes e versos', pages=pages))
        document = analyze_pdf(path)
        _check_cancel(cancelled)
        if _digest(path) != digest:
            raise PipelineError('O PDF foi alterado durante a leitura. Selecione-o novamente.')
    except ProcessingCancelled:
        raise
    except PipelineError:
        raise
    except Exception as error:
        raise PipelineError('Não foi possível ler o PDF. Verifique se o arquivo está íntegro e sem senha e tente novamente.') from error
    notify(Progress('PDF analisado', pages=document.page_count, pairs=len(document.badges)))
    return Inspection(path, digest, document)


def _tesseract(binary):
    configured = binary or os.environ.get('HB2_TESSERACT') or 'tesseract'
    executable = shutil.which(os.path.expanduser(configured))
    if not executable:
        raise PipelineError('Tesseract não encontrado. Instale-o com o idioma português e configure o PATH ou HB2_TESSERACT antes de reabrir o aplicativo.')
    try:
        result = subprocess.run([executable, '--list-langs'], capture_output=True,
                                text=True, encoding='utf-8', timeout=20, check=True, **subprocess_options())
    except (OSError, subprocess.SubprocessError) as error:
        raise PipelineError('Não foi possível iniciar o Tesseract. Verifique a instalação e o caminho configurado e tente novamente.') from error
    if 'por' not in result.stdout.split():
        raise PipelineError('O idioma português (por) não está disponível no Tesseract. Instale os dados de português e tente novamente.')
    return executable


def _serialize(page):
    return {'pagina': page.number, 'lado': page.side, 'tem_texto': page.has_text,
            'campos': {name: {'valor': value,
                             **{k: v for k, v in page.details[name].items() if k != 'value'}}
                       for name, value in page.values.items()}}


def _save_json(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
        json.dump(value, output, ensure_ascii=False, indent=2)


def process_pdf(inspection: Inspection, destination, *, tesseract=None,
                notify: Notify = lambda _: None,
                cancelled: Cancelled = lambda: False) -> ProcessingResult:
    """Executa os pares apurados, sem limites fixos de 163 ou widgets Qt."""
    from .xlsx import export_xlsx, flagged

    _check_cancel(cancelled)
    baseline = inspection.document
    total = len(baseline.badges)
    if baseline.rejected:
        raise PipelineError(f'O motor encontrou {len(baseline.rejected)} grupo(s) de páginas sem pareamento válido. Confira o PDF e selecione o arquivo corrigido.')
    if not total:
        raise PipelineError('Nenhum par de crachá foi identificado. Selecione um PDF com frentes e versos no layout aceito pelo motor.')
    notify(Progress('Preparando processamento', pairs=total, processed=0))
    try:
        if _digest(inspection.path) != inspection.digest:
            raise PipelineError('O PDF mudou desde a seleção. Selecione-o novamente antes de processar.')
        needs_ocr = any(not value for badge in baseline.badges
                        for page in (badge.front, badge.back) for value in page.values.values())
        binary = _tesseract(tesseract) if needs_ocr else (tesseract or 'tesseract')
        _check_cancel(cancelled)
        output = Path(destination).expanduser().resolve() / ('HB2Studio-' + datetime.now().astimezone().strftime('%Y-%m-%d_%H-%M-%S_%f'))
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        intermediate = output / 'intermediarios'
        intermediate.mkdir(mode=0o700)
        photos = output / 'fotos'
        photos.mkdir(mode=0o700)
        records = []
        with pdfplumber.open(inspection.path) as document, pdfium.PdfDocument(inspection.path) as native:
            for index, original in enumerate(baseline.badges, 1):
                _check_cancel(cancelled)
                f, b = original.front.number, original.back.number
                front_page, back_page = document.pages[f - 1], document.pages[b - 1]
                if detect_side(front_page) != 'frente' or detect_side(back_page) != 'verso':
                    raise PipelineError('A ordem das páginas mudou. Selecione o PDF novamente.')
                notify(Progress('Extraindo dados do verso', pairs=total, processed=index - 1))
                back = inspect_page(back_page, ocr_output=intermediate, tesseract=binary)
                _check_cancel(cancelled)
                notify(Progress('Extraindo nome de guerra e foto', pairs=total, processed=index - 1))
                front = deepcopy(original.front)
                try:
                    name = read_front_name(front_page, intermediate, binary, front.values['nome_frente'])
                except (OSError, subprocess.CalledProcessError):
                    name = {'valor': front.values['nome_frente'], 'origem': 'ocr', 'status': 'revisar',
                            'reasons': ['ocr_indisponivel', 'vazio_nao_confirmado']}
                front.values['nome_frente'] = name['valor']
                front.details['nome_frente'] = {k: v for k, v in name.items() if k != 'valor'}
                _check_cancel(cancelled)
                native_page = native[f - 1]
                try:
                    photo = extract_photo(front_page, native_page, output)
                except (OSError, RuntimeError, ValueError):
                    photo = {'valor': '', 'origem': 'sem_valor', 'status': 'revisar',
                             'reasons': ['foto_falha_extracao']}
                finally:
                    native_page.close()
                front.values['foto'] = photo['valor']
                front.details['foto'] = {k: v for k, v in photo.items() if k != 'valor'}
                for old, new in ((original.front, front), (original.back, back)):
                    if any(value and new.values[name] != value for name, value in old.values.items()):
                        raise PipelineError('Não foi possível preservar os dados diretos do PDF. Selecione o arquivo novamente.')
                badge = Badge(front, back)
                if badge.name_check == 'divergente':
                    info = front.details['nome_frente']
                    info['reasons'] = list(dict.fromkeys(info['reasons'] + ['conferir_associacao_nome']))
                    info['status'] = 'revisar'
                records.append({'par': index, 'frente': _serialize(front), 'verso': _serialize(back),
                                'comparacao_nomes': badge.name_check})
                _save_json(intermediate / f'par-{index:03d}.json', records[-1])
                front_page.close()
                back_page.close()
                notify(Progress('Processando crachás', pairs=total, processed=index))
        _check_cancel(cancelled)
        if _digest(inspection.path) != inspection.digest:
            raise PipelineError('O PDF foi alterado durante o processamento. Selecione-o novamente.')
        json_path = output / 'valores-combinados.json'
        _save_json(json_path, {'paginas': baseline.page_count, 'pares_contabilizados': total,
                              'grupos_rejeitados': 0, 'pares': records})
        notify(Progress('Exportando planilha e conferindo links', pairs=total, processed=total))
        workbook = output / 'crachas.xlsx'
        verified = export_xlsx(json_path, workbook, expected_pairs=total)
        _save_json(output / 'agregado.json', verified)
        _save_json(output / 'manifesto.json', {'documento_sha256': inspection.digest,
                                              'arquivo_origem': inspection.path.name,
                                              'pares': total})
        _check_cancel(cancelled)
        preview = tuple(PreviewRow(r['frente']['campos']['nome_frente']['valor'] or '',
                                   r['verso']['campos']['nome']['valor'] or '',
                                   r['verso']['campos']['matricula']['valor'] or '',
                                   'Pendente' if any(flagged(v) for side in ('frente', 'verso')
                                                     for v in r[side]['campos'].values()) else 'Sem pendências')
                        for r in records)
        return ProcessingResult(output, workbook, photos, json_path, total,
                                verified['pares_com_pendencias'], preview)
    except PipelineError:
        raise
    except OSError as error:
        raise PipelineError('Não foi possível ler ou gravar os arquivos. Verifique o acesso ao PDF, as permissões da pasta de saída e o espaço livre e tente novamente.') from error
