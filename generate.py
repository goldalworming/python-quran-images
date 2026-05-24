#!/usr/bin/env python3
"""
generate.py – Quran page image generator (QPC v2).

Usage:
    python generate.py --pages 1..10 --width 1280
    python generate.py --pages 1 --tajwid
"""

import argparse
import os
import sys

from src.db import QuranDBv2
from src.generator import PageGeneratorV2

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), 'quran_v2.db')


def parse_pages(pages_str):
    result = set()
    for part in pages_str.split(','):
        part = part.strip()
        if '..' in part:
            s, e = part.split('..', 1)
            result.update(range(int(s), int(e) + 1))
        else:
            result.add(int(part))
    return sorted(result)


def main():
    p = argparse.ArgumentParser(description='QPC v2 Quran page generator.')
    p.add_argument('--pages', '-p', default='1..604',
                   help='Page range (default: 1..604)')
    p.add_argument('--width', '-w', type=int, default=1024,
                   help='Image width in pixels (default: 1024)')
    p.add_argument('--output', '-o', default='./output',
                   help='Output directory (default: ./output)')
    p.add_argument('--db', default=DEFAULT_DB_PATH,
                   help=f'SQLite path (default: {DEFAULT_DB_PATH})')
    p.add_argument('--tajwid', '-t', action='store_true',
                   help='Enable per-letter Tajweed colouring')
    args = p.parse_args()

    pages = [n for n in parse_pages(args.pages) if 1 <= n <= 604]
    if not pages:
        print('No valid pages in 1..604.', file=sys.stderr)
        sys.exit(1)

    print(f'Generating {len(pages)} page(s) at width={args.width}px -> {args.output}')

    db = QuranDBv2(args.db)
    try:
        gen = PageGeneratorV2(db, tajwid=args.tajwid)
        gen.generate(pages=pages, width=args.width, output=args.output)
    finally:
        db.close()
    print('Done.')


if __name__ == '__main__':
    main()
