#!/bin/bash
set -e
cd /mnt/e/A4-work/out/boot2

echo "=== [1] 备份原 kernel ==="
cp kernel.bin kernel.bin.orig
ls -la kernel.bin kernel.bin.orig

echo
echo "=== [2] 准备新 ramdisk（pad 到 2048 字节页对齐）==="
NEWLEN=$(stat -c%s ramdisk_new.gz)
echo "new ramdisk raw size = $NEWLEN"
# kernel + ramdisk 都要按 page_size(2048) 对齐
KLEN=$(stat -c%s kernel.bin)
echo "kernel size = $KLEN"
PADK=$(( (2048 - KLEN % 2048) % 2048 ))
PADR=$(( (2048 - NEWLEN % 2048) % 2048 ))
echo "kernel pad = $PADK, ramdisk pad = $PADR"

echo
echo "=== [3] 组装 boot.img ==="
python3 << 'PYEOF'
import struct
KLEN=7836720; RLEN_OLD=329180; RLEN_NEW=606208  # 注意：这是解压后? 不，是压缩后
PYEOF

# 直接用实际值
KLEN_ACT=$(stat -c%s kernel.bin)
RLEN_ACT=$(stat -c%s ramdisk_new.gz)
echo "kernel=$KLEN_ACT  ramdisk_new=$RLEN_ACT"

# boot_img_hdr: kernel_size(4) kernel_addr(4) ramdisk_size(4) ramdisk_addr(4)
#               second_size(4) second_addr(4) tags_addr(4) page_size(4)
#               hdr_version(4) os_version(4) name[16] cmdline[512] id[32] extra_cmdline[1024]
python3 - "$KLEN_ACT" "$RLEN_ACT" << 'PYEOF'
import sys, struct
klen=int(sys.argv[1]); rlen=int(sys.argv[2])
hdr = struct.pack('<II', klen, 0x3e08000)
hdr += struct.pack('<II', rlen, 0x4e00000)
hdr += struct.pack('<II', 0, 0x4d00000)
hdr += struct.pack('<I', 0x3e00100)
hdr += struct.pack('<I', 2048)
hdr += struct.pack('<II', 0, 0)
hdr += b'\x00'*16
hdr += b'coherent_pool=2M console=ttyAMA0,115200 blkdevparts=mmcblk0:1M(fastboot),4M(bootargs),16M(recovery),1M(deviceinfo),4M(baseparam),4M(pqparam),4M(logo),16M(fastplay),8M(misc),24M(factory),12M(kernel),8M(iptv_data),340M(backup),340M(cache),520M(system),-(userdata)' + b'\x00'*512
hdr += bytes.fromhex('122206437367b5277fef83b9cf074007e6b425c7000000000000000000000000')
hdr += b'\x00'*1024
open('hdr_new.bin','wb').write(hdr)
print('hdr size', len(hdr), '(应为 1648)')
PYEOF

# 拼接
cat hdr_new.bin > boot_new.img
# kernel 按 2048 对齐
cat kernel.bin >> boot_new.img
PADK=$(( (2048 - KLEN_ACT % 2048) % 2048 ))
if [ "$PADK" -ne 0 ]; then head -c "$PADK" /dev/zero >> boot_new.img; fi
cat ramdisk_new.gz >> boot_new.img
PADR=$(( (2048 - RLEN_ACT % 2048) % 2048 ))
if [ "$PADR" -ne 0 ]; then head -c "$PADR" /dev/zero >> boot_new.img; fi

echo
echo "=== [4] 结果 ==="
ls -la boot_new.img
echo "原 boot.img: $(stat -c%s /mnt/e/A4-work/fw/boot.img) B"
echo "新 boot.img: $(stat -c%s boot_new.img) B"

echo
echo "=== [5] 用 bootparse 验证新 boot.img ==="
cd /mnt/e/A4-work
python3 tools/bootparse.py out/boot2/boot_new.img 2>&1 | head -12
