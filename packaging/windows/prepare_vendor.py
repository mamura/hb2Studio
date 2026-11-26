"""Monta apenas binários redistribuíveis e licenças, nunca dados do projeto."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys


def copy_tree(source, target):
    if source.exists():
        shutil.copytree(source, target, dirs_exist_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prefix', type=Path, required=True)
    ap.add_argument('--cache', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    runtime = args.output / 'tesseract'
    licenses = args.output / 'licenses'
    runtime.mkdir(parents=True, exist_ok=True)
    licenses.mkdir(parents=True, exist_ok=True)
    # Keep the native DLLs together, including app-local VC runtime.
    copy_tree(args.prefix / 'Library/bin', runtime / 'Library/bin')
    for pattern in ('vcruntime*.dll', 'msvcp*.dll', 'concrt*.dll', 'vcomp*.dll'):
        for library in args.prefix.glob(pattern):
            shutil.copy2(library, runtime / 'Library/bin' / library.name)
    for name in ('icuuc.dll', 'icuin.dll', 'icudt.dll', 'icuio.dll', 'icutu.dll', 'icutest.dll'):
        alias = runtime / 'Library/bin' / name
        if alias.exists():
            alias.unlink()
    copy_tree(args.prefix / 'Library/etc', runtime / 'Library/etc')
    for name in ('fonts', 'fontconfig', 'icu'):
        copy_tree(args.prefix / 'Library/share' / name, runtime / 'Library/share' / name)
    models = list(args.prefix.rglob('por.traineddata'))
    if len(models) != 1:
        raise RuntimeError('Pacote nativo deve conter exatamente um modelo português.')
    tessdata = runtime / 'tessdata'
    tessdata.mkdir(exist_ok=True)
    shutil.copy2(models[0], tessdata / 'por.traineddata')
    for name in ('configs', 'tessconfigs'):
        for parent in (models[0].parent, args.prefix / 'Library/share/tessdata'):
            copy_tree(parent / name, tessdata / name)
    if not (tessdata / 'configs/tsv').is_file():
        raise RuntimeError('Configuração TSV do Tesseract não encontrada.')
    python_license = next((Path(sys.base_prefix) / n for n in ('LICENSE.txt', 'LICENSE_PYTHON.txt') if (Path(sys.base_prefix) / n).is_file()), None)
    if python_license is None:
        raise RuntimeError('Licença do CPython não encontrada.')
    shutil.copy2(python_license, licenses / 'Python-LICENSE.txt')
    cache_info = {info.parent.name: info for info in args.cache.rglob('info') if info.is_dir()}
    records = []
    for path in sorted((args.prefix / 'conda-meta').glob('*.json')):
        meta = json.loads(path.read_text(encoding='utf-8'))
        package = f"{meta['name']}-{meta['version']}-{meta['build']}"
        info = cache_info.get(package, args.cache / package / 'info')
        destination = licenses / 'native' / package
        copy_tree(info / 'licenses', destination / 'licenses')
        copy_tree(info / 'recipe', destination / 'recipe')
        destination.mkdir(parents=True, exist_ok=True)
        for name in ('about.json', 'index.json'):
            if (info / name).exists():
                shutil.copy2(info / name, destination / name)
        # An installed native payload must not lose its license notices.
        payload = any(f.replace('\\', '/').startswith('Library/bin/') for f in meta.get('files', []))
        notices = [p for p in destination.rglob('*') if p.is_file()
                   and any(word in p.name.lower() for word in ('license', 'copying', 'copyright', 'eula'))]
        if payload and not notices:
            raise RuntimeError(f'Licença nativa não encontrada: {package}')
        records.append({k: meta.get(k) for k in ('name', 'version', 'build', 'url', 'sha256', 'md5', 'license')})
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata['Name']
        for member in distribution.files or ():
            lower = str(member).lower()
            if not any(word in lower for word in ('license', 'copying', 'copyright', '/notice')):
                continue
            source = Path(distribution.locate_file(member))
            if source.is_file() and source.suffix.lower() not in ('.py', '.pyc', '.exe', '.dll', '.pyd'):
                safe = Path(*[part for part in member.parts if part not in ('.', '..')])
                target = licenses / 'python' / name / safe
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    (licenses / 'native-packages.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    notice = '''HB2 Studio — componentes redistribuídos

Tesseract e tessdata_fast: Apache-2.0, https://github.com/tesseract-ocr
Binários Windows e dependências: conda-forge; versões, URLs e hashes em
native-packages.json; licenças e receitas originais (com fontes upstream) em native/.
PySide6 / Qt: LGPL-3.0 / GPL e licenças de terceiros; textos originais em python/.
Qt é ligado dinamicamente. As DLLs Qt/PySide podem ser substituídas por versões
compatíveis; não é imposta restrição à engenharia reversa para depurar essas alterações.
Fontes Qt: https://download.qt.io/official_releases/qt/6.12/6.12.0/submodules/
Fontes PySide: https://download.qt.io/official_releases/QtForPython/pyside6/
Python, PDFium, Pillow, pdfminer.six, pdfplumber, openpyxl e demais componentes:
consulte os respectivos avisos e licenças originais em python/.
As receitas dos pacotes nativos apontam às fontes correspondentes de cada versão.
Micromamba, Python de compilação e Inno Setup Compiler não são requisitos do usuário final.
'''
    (licenses / 'LEIA-ME.txt').write_text(notice, encoding='utf-8')
    if not (runtime / 'Library/bin/tesseract.exe').is_file():
        raise RuntimeError('tesseract.exe não encontrado no pacote Windows.')
    print('Runtime Windows e licenças preparados.')


if __name__ == '__main__':
    main()
