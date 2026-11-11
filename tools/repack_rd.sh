#!/bin/bash
set -e
cd /mnt/e/A4-work/out/boot2/rd2

echo "=== [1] 清理备份文件（不能打进 ramdisk）==="
rm -f init.environ.rc.orig
ls -la init*.rc

echo
echo "=== [2] 生成新的 cpio（新格式 cpio，保留设备原有的）==="
# 设备 ramdisk 用的是 newc 格式（从 bootparse 看是标准 gzip）
find . -print0 | cpio --null -o -H newc --owner=0:0 2>/dev/null | gzip -9 > ../ramdisk_new.gz
ls -la ../ramdisk_new.gz

echo
echo "=== [3] 解压验证新 cpio ==="
cd ..
zcat ramdisk_new.gz | wc -c
echo "原始解压后: 605696 B"

echo
echo "=== [4] 验证新 cpio 里 init.environ.rc 的内容 ==="
mkdir -p verify && cd verify && rm -rf *
zcat ../ramdisk_new.gz | cpio -idm init.environ.rc 2>/dev/null
md5sum init.environ.rc
grep 'BOOTCLASSPATH' init.environ.rc | tr ':' '\n' | tail -3

echo
echo "=== [5] 验证文件总数一致 ==="
find . -type f | wc -l
cd ..
mkdir -p verify2 && cd verify2 && rm -rf *
zcat ../ramdisk_new.gz | cpio -idm 2>/dev/null
find . -type f | wc -l
echo "（原始 rd2 的文件数应为同一值）"
cd ..
find rd2 -type f | wc -l
