#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import zipfile, sys
z = zipfile.ZipFile(sys.argv[1] if len(sys.argv) > 1 else 'update.zip')
print('=== updater-script ===')
print(z.read('META-INF/com/google/android/updater-script').decode('utf-8', 'replace'))
d = z.read('META-INF/com/google/android/update-binary')
print('=== update-binary: %d bytes, first 100 raw ===' % len(d))
print(repr(d[:100]))
# zip structural facts
print('=== zip facts ===')
tot = sum(i.file_size for i in z.infolist())
print('entries: %d  total uncompressed: %d (%.1f MB)' % (len(z.infolist()), tot, tot/1048576.0))
from collections import Counter
print('compress_type:', Counter(i.compress_type for i in z.infolist()))
print('create_version:', Counter(i.create_version for i in z.infolist()))
print('extract_version:', Counter(i.extract_version for i in z.infolist()))
print('flag_bits:', Counter(i.flag_bits for i in z.infolist()))
print('create_system:', Counter(i.create_system for i in z.infolist()))
print('first 8 entry names in order:')
for i in z.infolist()[:8]:
    print('   %-50s ct=%d cv=%d ev=%d fb=0x%x cs=%d' % (i.filename, i.compress_type, i.create_version, i.extract_version, i.flag_bits, i.create_system))