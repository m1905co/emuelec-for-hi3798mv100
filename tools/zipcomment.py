#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dump the trailing ZIP comment (where AOSP's whole-file signature lives)."""
import struct, sys, hashlib
raw = open('update.zip', 'rb').read()
eocd = raw.rindex(b'PK\x05\x06')
clen = struct.unpack_from('<H', raw, eocd + 20)[0]
comment = raw[eocd + 22:eocd + 22 + clen]
print('EOCD at %#x  comment len=%d  comment ends at file end: %s'
      % (eocd, clen, eocd + 22 + clen == len(raw)))
print('comment printable head: %r' % comment[:120])
print()
print('--- comment tail 80 bytes ---')
print(comment[-80:])
print()
# look for magic strings
for magic in [b'signed by SignApk', b'SignApk', b'signed', b'SAPK', b'\xa0\x1f\xb5\x21']:
    i = comment.find(magic)
    print('magic %-18r at %s' % (magic, hex(i) if i >= 0 else 'not found'))
print()
# print the whole comment as printable with offsets
import re
for m in re.finditer(rb'[\x20-\x7e]{6,}', comment):
    print('  @%#06x  %r' % (m.start(), m.group()))
print()
print('--- last 24 bytes as uint32s LE ---')
tail = comment[-24:]
for i in range(0, 24, 4):
    print('   %2d: %s  = %d' % (i, tail[i:i+4].hex(), struct.unpack_from('<I', tail, i)[0]))