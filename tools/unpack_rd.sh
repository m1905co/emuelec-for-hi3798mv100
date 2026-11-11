#!/bin/bash
set -e
cd /mnt/e/A4-work/out/boot2
rm -rf rd2 && mkdir rd2 && cd rd2
zcat ../ramdisk.bin | cpio -idm 2>/dev/null
echo "=== 解包完成，根目录内容 ==="
ls -la | head -25
echo
echo "=== init*.rc 文件 ==="
ls -la init*.rc 2>/dev/null
echo
echo "=== init.environ.rc 的 BOOTCLASSPATH 行 ==="
grep 'BOOTCLASSPATH' init.environ.rc | tr ':' '\n' | tail -4
echo
echo "=== init.environ.rc md5（应为 4e7f66e39974fc6ba0c339564f786ec2）==="
md5sum init.environ.rc
