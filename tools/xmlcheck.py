#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import zipfile, difflib, xml.dom.minidom
orig = zipfile.ZipFile('update.zip').read('system/etc/media_codecs.xml').decode('utf-8')
new = open('fw/system/etc/media_codecs.xml', encoding='utf-8').read()
print('orig %d B -> new %d B (delta %+d)'
      % (len(orig.encode()), len(new.encode()), len(new.encode()) - len(orig.encode())))
print()
for l in difflib.unified_diff(orig.splitlines(), new.splitlines(),
                              'orig', 'new', lineterm='', n=1):
    print(l)
print()
xml.dom.minidom.parseString(new)
print('XML well-formed: OK')