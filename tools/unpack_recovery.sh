#!/bin/bash
# 解开 recovery.img（标准 boot_img_hdr 结构），拿到 recovery 真正的 ramdisk
set -e
cd /mnt/e/A4-work/out
python3 << 'PYEOF'
import struct, gzip, io, os
d = open('rec_recovery.img','rb').read()
ks,ka,rs,ra,ss,sa,tags,ps = struct.unpack_from('<8I', d, 8)
print('kernel_size  =', ks)
print('ramdisk_size =', rs)
print('page_size    =', ps)
print('second_size  =', ss)
off = ps
print('kernel  : %d .. %d' % (off, off+ks))
off += ks
off = (off + ps - 1)//ps*ps
print('ramdisk : %d .. %d' % (off, off+rs))
r = d[off:off+rs]
print('ramdisk 首字节:', r[:4].hex())
raw = gzip.decompress(r)
print('ramdisk 解压后: %d 字节' % len(raw))
os.makedirs('recovery_rd', exist_ok=True)
open('recovery_rd/ramdisk.cpio','wb').write(raw)
print('已保存 out/recovery_rd/ramdisk.cpio')
PYEOF

echo
echo "=== 解包 recovery ramdisk ==="
cd recovery_rd
rm -rf x && mkdir x && cd x
cpio -idm < ../ramdisk.cpio 2>/dev/null
echo "--- 根目录 ---"
ls -la | head -25
echo
echo "--- init.rc 里的关键内容 ---"
grep -nE 'package_extract|verify|signature|certif' init.rc 2>/dev/null | head -10
echo
echo "--- 是否有独立的签名校验程序 ---"
ls -la sbin/ 2>/dev/null | head -30
