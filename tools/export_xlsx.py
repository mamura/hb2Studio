"""Exporta somente o JSON existente, mantendo dados privados em resultados/."""
import argparse
from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hb2_studio.xlsx import export_xlsx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('json', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / 'resultados'
    stamp = datetime.now(ZoneInfo('America/Fortaleza')).strftime('%Y-%m-%d_%H-%M-%S_%f')
    output = args.output or root / f'crachas-{stamp}.xlsx'
    if not output.resolve().is_relative_to(root):
        parser.error('A planilha deve ser salva dentro de resultados/.')
    try:
        result = export_xlsx(args.json, output)
    except FileNotFoundError:
        print('JSON de origem indisponível; nenhuma planilha foi gerada.', file=sys.stderr)
        return 1
    except FileExistsError:
        print('A saída já existe; escolha um caminho novo.', file=sys.stderr)
        return 1
    except (ValueError, KeyError, TypeError):
        print('JSON inválido ou falha na verificação da planilha.', file=sys.stderr)
        return 1
    print(json.dumps({'planilha': str(output), **result}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
