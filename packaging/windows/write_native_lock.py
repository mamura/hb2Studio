"""Lock explícito público, sem caminhos locais e compatível com micromamba."""
import json
from pathlib import Path
import sys

prefix, output = map(Path, sys.argv[1:])
lines = ['# platform: win-64', '@EXPLICIT']
for path in sorted((prefix / 'conda-meta').glob('*.json')):
    meta = json.loads(path.read_text(encoding='utf-8'))
    url, md5 = meta['url'], meta['md5']
    if not url.startswith('https://conda.anaconda.org/conda-forge/') or len(md5) != 32:
        raise RuntimeError('Origem ou hash inválido no lock nativo.')
    lines.append(f'{url}#{md5}')
output.write_text('\n'.join(lines) + '\n', encoding='utf-8')
