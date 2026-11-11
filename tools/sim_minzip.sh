#!/bin/bash
# 模拟 AOSP minzip 的行为：逐条目用 raw inflate 解压，检测哪个条目会失败
# AOSP minzip 对每个 entry：
#   - method 0 (STORED)  -> 直接 copy
#   - method 8 (DEFLATE) -> inflateRaw
#   - 其他 -> "Unsupported compression type"
# 另外它会校验 CRC-32

cd /mnt/e/A4-work
V=/c/Users/MGXLVF/.workbuddy/binaries/python/envs/default/Scripts/python.exe

for PKG in update.zip update_v2_fixed.zip; do
  echo "############ $PKG ############"
  $V - "$PKG" << 'PYEOF'
import sys, zipfile, zlib
pkg = sys.argv[1]
z = zipfile.ZipFile(pkg)
bad = []
for n in z.namelist():
    i = z.getinfo(n)
    if i.compress_type not in (0, 8):
        bad.append((n, 'unsupported method %d' % i.compress_type)); continue
    try:
        raw = z.read(n)
    except Exception as e:
        bad.append((n, 'extract fail: %s' % e)); continue
    if len(raw) != i.file_size:
        bad.append((n, 'size mismatch %d != %d' % (len(raw), i.file_size))); continue
    if i.CRC != zlib.crc32(raw) & 0xffffffff:
        bad.append((n, 'CRC mismatch')); continue
print('  条目总数: %d' % len(z.namelist()))
print('  模拟 minzip 解压/CRC 失败数: %d' % len(bad))
for n, why in bad[:20]:
    print('    !! %-40s %s' % (n, why))
PYEOF
  echo
done
