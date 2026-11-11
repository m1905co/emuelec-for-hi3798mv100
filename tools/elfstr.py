#!/usr/bin/env python3
"""Minimal ELF strings extractor (no external deps)."""
import re
import sys

MIN = 4


def extract(path):
    with open(path, 'rb') as f:
        data = f.read()
    out = []
    for m in re.finditer(rb'[\x20-\x7e]{%d,}' % MIN, data):
        out.append((m.start(), m.group().decode('ascii', 'replace')))
    return out


def main():
    path = sys.argv[1]
    mode = 'list'
    pats = []
    args = sys.argv[2:]
    if args and args[0] in ('-i', '-g'):
        mode = 'grep'
        pats = args[1:]
    res = extract(path)
    if mode == 'grep':
        rx = re.compile('|'.join(pats), re.I)
        for off, s in res:
            if rx.search(s):
                print('0x%08x %s' % (off, s))
    else:
        for off, s in res:
            print('0x%08x %s' % (off, s))


if __name__ == '__main__':
    main()