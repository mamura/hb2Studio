"""Recursos redistribuídos: sem Python/Tesseract externos no aplicativo congelado."""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys


def configure_bundled_runtime():
    if not getattr(sys, 'frozen', False):
        return
    root = Path(sys._MEIPASS) / 'tesseract'
    executable = root / 'Library' / 'bin' / 'tesseract.exe'
    data = root / 'tessdata'
    if not executable.is_file() or not (data / 'por.traineddata').is_file():
        raise RuntimeError('Instalação incompleta do HB2 Studio. Reinstale o aplicativo para restaurar o OCR em português.')
    os.environ['HB2_TESSERACT'] = str(executable)
    os.environ['TESSDATA_PREFIX'] = str(data)
    os.environ['PATH'] = str(executable.parent) + os.pathsep + os.environ.get('PATH', '')


def subprocess_options():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


@contextmanager
def external_application_environment():
    """Não faz Excel/Explorer herdarem a preferência de DLLs do PyInstaller."""
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        yield
        return
    import ctypes
    kernel = ctypes.windll.kernel32
    buffer = ctypes.create_unicode_buffer(32768)
    kernel.GetDllDirectoryW(len(buffer), buffer)
    previous_directory = buffer.value
    previous_path = os.environ.get('PATH', '')
    bundle = os.path.normcase(str(Path(sys._MEIPASS)))
    try:
        kernel.SetDllDirectoryW(None)
        os.environ['PATH'] = os.pathsep.join(
            entry for entry in previous_path.split(os.pathsep)
            if not os.path.normcase(entry).startswith(bundle))
        yield
    finally:
        os.environ['PATH'] = previous_path
        kernel.SetDllDirectoryW(previous_directory or None)
