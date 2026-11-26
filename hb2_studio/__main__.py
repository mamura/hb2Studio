"""Comando local de diagnóstico."""
import argparse
import json
import sys

from pdfplumber.utils.exceptions import PdfminerException

from .engine import analyze_pdf


def main():
    parser = argparse.ArgumentParser(description="Diagnóstico de PDFs de crachás")
    parser.add_argument("pdf", help="Caminho do PDF local")
    parser.add_argument("--esperados", type=int, help="Quantidade esperada de pares")
    args = parser.parse_args()
    if args.esperados is not None and args.esperados < 1:
        parser.error("--esperados deve ser positivo")
    try:
        result = analyze_pdf(args.pdf)
    except (OSError, PdfminerException):
        print("Não foi possível abrir ou ler o PDF.", file=sys.stderr)
        return 1
    print(json.dumps(result.diagnostic(), indent=2))
    if result.rejected or (args.esperados is not None and args.esperados != len(result.badges)):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
