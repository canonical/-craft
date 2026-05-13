#!/usr/bin/env python3
"""Char-by-char typewriter for demos.

Reads text from stdin, writes it to stdout (and optionally a file) one chunk
at a time with a configurable delay between chunks.
"""

from __future__ import annotations

import argparse
import sys
import time


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('-d', '--delay', type=float, default=0.012,
                   help='Seconds to pause between chunks (default: 0.012)')
    p.add_argument('-b', '--burst', type=int, default=1,
                   help='Characters per chunk (default: 1)')
    p.add_argument('-o', '--output',
                   help='Also write the typed content to this file')
    p.add_argument('--newline-pause', type=float, default=0.05,
                   help='Extra pause after each newline (default: 0.05)')
    args = p.parse_args()

    sink = open(args.output, 'w', encoding='utf-8') if args.output else None

    try:
        while True:
            chunk = sys.stdin.read(args.burst)
            if not chunk:
                break
            sys.stdout.write(chunk)
            sys.stdout.flush()
            if sink is not None:
                sink.write(chunk)
                sink.flush()
            if '\n' in chunk:
                time.sleep(args.newline_pause)
            else:
                time.sleep(args.delay)
    finally:
        if sink is not None:
            sink.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
