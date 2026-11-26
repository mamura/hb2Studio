"""Falhas técnicas locais, sem capturar variáveis ou conteúdos de campos."""
from datetime import datetime
import locale
import os
from pathlib import Path
import sys
import traceback


def record_failure(error, stage):
    base = Path(os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_STATE_HOME')
                or Path.home() / '.local/state')
    path = base / 'HB2 Studio/logs/erros.log'
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # No locals, images, PDF content or OCR values are included explicitly.
        trace = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        entry = (f'\n{datetime.now().astimezone().isoformat()} | etapa={stage} | '
                 f'erro={type(error).__name__} | codec={locale.getencoding()} | '
                 f'empacotado={bool(getattr(sys, "frozen", False))}\n{trace}')
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as log:
            log.write(entry)
        return path
    except OSError:
        return None


def failure_message(error, stage):
    from .pipeline import PipelineError
    from .ocr import OCRFormatError
    log = record_failure(error, stage)
    if isinstance(error, PipelineError):
        message = str(error)
    elif isinstance(error, OCRFormatError):
        message = 'O OCR não devolveu os dados no formato esperado. Reinstale a versão atual do HB2 Studio e tente novamente.'
    elif isinstance(error, UnicodeError):
        message = 'Não foi possível ler um texto retornado pelo OCR. Verifique se está usando a versão atual do HB2 Studio e tente novamente.'
    else:
        message = f'Falha técnica na etapa "{stage}" ({type(error).__name__}). Tente novamente; se persistir, consulte o registro de diagnóstico.'
    if log:
        message += f'\nRegistro local: {log}'
    return message
