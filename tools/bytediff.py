#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Byte-diff two files: report first N differing ranges."""
import sys
a = open(sys.argv[1], 'rb').read()
b = open(sys.argv[2], 'rb').read()
print('size: %d vs %d  (%s)' % (len(a), len(b), 'same' if len(a) == len(b) else 'DIFFERENT'))
n = min(len(a), len(b))
diffs = [i for i in range(n) if a[i] != b[i]]
print('differing bytes in common prefix: %d' % len(diffs))
if not diffs and len(a) == len(b):
    print('FILES ARE BYTE-IDENTICAL')
    sys.exit(0)
if diffs:
    print('first 6 diff ranges:')
    s = diffs[0]; p = diffs[0]; shown = 0
    for i in diffs[1:] + [None]:
        if i is not None and i == p + 1:
            p = i; continue
        print('   %#010x-%#010x (%d bytes)' % (s, p, p - s + 1))
        print('      A: %s' % a[max(0, s - 8):p + 9].hex(' '))
        print('      B: %s' % b[max(0, s - 8):p + 9].hex(' '))
        shown += 1
        if shown >= 6: break
        if i is None: break
        s = p = i