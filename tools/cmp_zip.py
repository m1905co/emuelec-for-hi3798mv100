#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import zipfile, hashlib, sys, os
a = zipfile.ZipFile('update.zip')
b = zipfile.ZipFile(sys.argv[1] if len(sys.argv) > 1 else 'update_fixed2.zip')
print('testzip (None=OK):', b.testzip())
na = [n for n in a.namelist()]
nb = [n for n in b.namelist()]
print('entries: %d -> %d   order identical: %s' % (len(na), len(nb), na == nb))
ch = [n for n in na if not n.startswith('META-INF/')
      and hashlib.sha1(a.read(n)).digest() != hashlib.sha1(b.read(n)).digest()]
print('changed payload files (%d): %s' % (len(ch), ch))
for n in ['META-INF/MANIFEST.MF', 'META-INF/CERT.SF', 'META-INF/CERT.RSA']:
    same = hashlib.sha1(a.read(n)).digest() == hashlib.sha1(b.read(n)).digest()
    print('  %-24s %s' % (n.split('/')[-1], 'unchanged' if same else 'regenerated'))
print()
for f in ['update.zip', 'update_fixed.zip', 'update_fixed2.zip']:
    if os.path.exists(f):
        print('  %-22s %10.1f MB' % (f, os.path.getsize(f) / 1048576.0))