#!/bin/bash
set -e
cd /mnt/e/A4-work/out/boot2

echo "=== [1] 只替换 ramdisk 段，其余字节原样保留 ==="
python3 << 'PYEOF'
import struct
ORIG='/mnt/e/A4-work/fw/boot.img'
d=bytearray(open(ORIG,'rb').read())
ks,ka,rs,ra,ss,sa,tags,ps = struct.unpack_from('<8I', d, 8)
ks,ka,rs,ra = struct.unpack_from('<4I', d, 8)
print('原: kernel=%d ramdisk=%d page=%d 总长=%d'%(ks,rs,ps,len(d)))

# ramdisk 起点
ro = ps + ks
ro = (ro + ps - 1)//ps*ps
rend = ro + rs
print('原 ramdisk 区间: %d .. %d'%(ro, rend))

newr = open('ramdisk_new.gz','rb').read()
print('新 ramdisk: %d 字节 (原 %d, 差 %+d)'%(len(newr), rs, len(newr)-rs))

# 构造新镜像：头部 + kernel + pad + 新 ramdisk + pad + 原尾部
head = d[:ro]
tail = d[rend:]
pad_r = (ps - len(newr) % ps) % ps
out = head + newr + b'\x00'*pad_r + tail
open('boot_patched.img','wb').write(bytes(out))
print('新镜像: %d 字节 (原 %d, 差 %+d)'%(len(out), len(d), len(out)-len(d)))
print('  头部+kernel: %d  新ramdisk: %d(+pad %d)  原尾部: %d'%(len(head), len(newr), pad_r, len(tail)))

# 修正 header 里的 ramdisk_size
o = bytearray(out)
struct.pack_into('<I', o, 8+8, len(newr))   # ramdisk_size 字段偏移 = 8 + 2*4
open('boot_patched.img','wb').write(bytes(o))
print('  header ramdisk_size 已更新为 %d'%len(newr))
PYEOF

echo
echo "=== [2] 验证新 boot.img 结构 ==="
python3 << 'PYEOF'
import struct
d=open('/mnt/e/A4-work/out/boot2/boot_patched.img','rb').read()
print('magic =', d[:8])
ks,ka,rs,ra,ss,sa,tags,ps = struct.unpack_from('<8I', d, 8)
print('kernel_size=%d ramdisk_size=%d page_size=%d second=%d'%(ks,rs,ps,ss))
print('cmdline 前60:', d[8+40+16:8+40+16+60].split(b'\x00')[0].decode('latin1'))
o=ps
print('kernel : %d .. %d'%(o,o+ks)); o+=ks; o=(o+ps-1)//ps*ps
print('ramdisk: %d .. %d'%(o,o+rs))
print('ramdisk 起始字节:', ' '.join('%02x'%b for b in d[o:o+8]), '(应为 1f 8b = gzip)')
import gzip
raw = gzip.decompress(d[o:o+rs])
print('ramdisk 解压后: %d 字节'%len(raw))
print('尾部保留: %d 字节'%(len(d)-(o+rs)))
PYEOF
ls -la boot_patched.img
