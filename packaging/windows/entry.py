"""Entrada sem console do executável Windows."""
import multiprocessing

if __name__ == '__main__':
    multiprocessing.freeze_support()
    from hb2_studio.desktop import main
    raise SystemExit(main())
