#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reverse-engineer AOSP whole-file signature: which byte range is digested?"""
import struct, hashlib, itertools
from asn1crypto import cms

raw = open('update.zip', 'rb').read()
eocd = raw.rindex(b'PK\x05\x06')
clen = struct.unpack_from('<H', raw, eocd + 20)[0]
comment = raw[eocd + 22:]
print('file len      :', len(raw))
print('EOCD offset   : %#x' % eocd)
print('comment len   :', clen)

# magic = printable prefix up to NUL
nul = comment.index(b'\x00')
magic = comment[:nul]
print('magic         : %r (%d bytes)' % (magic, nul))
pk_start = nul + 1
# find DER end
der = comment[pk_start:]
ci = cms.ContentInfo.load(der)
full = ci.dump()
print('PKCS7 starts  : comment+%d (file %#x)' % (pk_start, eocd + 22 + pk_start))
print('PKCS7 DER len : %d' % len(full))
print('PKCS7 ends    : comment+%d ; trailing bytes after DER: %d'
      % (pk_start + len(full), len(der) - len(full)))
trailer = der[len(full):]
print('trailer hex   :', trailer.hex(' '))

si = ci['content']['signer_infos'][0]
print('digest alg    :', si['digest_algorithm']['algorithm'].native)
md = None
if si['signed_attrs'] is not None and len(si['signed_attrs']):
    for a in si['signed_attrs']:
        if a['type'].native == 'message_digest':
            md = a['values'][0].native
print('message_digest: %s' % (md.hex() if md else None))

print()
print('=== brute force: which byte range + which digest matches? ===')
cands = {}
L = len(raw)
comment_start = eocd + 22
for name, (a, b) in {
    'file[0 : eocd+22)  (everything before comment)': (0, comment_start),
    'file[0 : eocd)': (0, eocd),
    'file[0 : L-commentlen)': (0, L - clen),
    'file[0 : L-1720)': (0, L - 1720),
    'file[0 : L-1721)': (0, L - 1721),
    'file[0 : L-(1720+magiclen+1))': (0, L - (1720 + nul + 1)),
    'file[0 : L-(1720+magiclen+1)-4)': (0, L - (1720 + nul + 1) - 4),
    'file[magiclen+1 : L-1720)': (nul + 1, L - 1720),
    'file[0 : comment_start-(magiclen+1))': (0, comment_start - (nul + 1)),
}.items():
    cands[name] = raw[a:b]
for name, data in cands.items():
    for alg in ('sha1', 'sha256', 'sha512'):
        d = hashlib.new(alg, data).digest()
        if md and d[:len(md)] == md:
            print('*** MATCH  %-55s %s  (len=%d)' % (name, alg, len(data)))
        elif md and d[-len(md):] == md:
            print('*** MATCH(tail) %-49s %s (len=%d)' % (name, alg, len(data)))
print('(no match printed above means none of the simple ranges matched)')