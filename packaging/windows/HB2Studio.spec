# Compilar somente com Python Windows x64. Nenhum glob do diretório do cliente.
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

root = Path(SPECPATH).parents[1]
vendor = Path(os.environ['HB2_VENDOR'])
a = Analysis(
    [str(root / 'packaging/windows/entry.py')], pathex=[str(root)],
    binaries=collect_dynamic_libs('pypdfium2_raw') + collect_dynamic_libs('pypdfium2'),
    datas=[(str(vendor / 'tesseract'), 'tesseract'), (str(vendor / 'licenses'), 'licenses')]
          + collect_data_files('pypdfium2_raw') + collect_data_files('pypdfium2'),
    hiddenimports=['hb2_studio.runtime', 'openpyxl', 'PIL.Image'],
    runtime_hooks=[str(root / 'packaging/windows/runtime_hook.py')],
    excludes=['tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'pytest', 'reportlab'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='HB2Studio',
          debug=False, strip=False, upx=False, console=False,
          contents_directory='_internal',
          version=str(root / 'packaging/windows/version_info.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='HB2Studio')
