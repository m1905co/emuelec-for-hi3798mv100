#!/bin/bash
# 通用编译脚本：$1 = java 文件名（不含 .java）
set -e
N="$1"
W=/home/mxz/hijack
cd $W
cp "/mnt/e/A4-work/out/$N.java" .
rm -rf "c_$N" "$N.dex"; mkdir "c_$N"
javac -source 1.6 -target 1.6 -d "c_$N" "$N.java" 2>&1 | grep -v 'bootstrap class path' | head -5 || true
AOSP=/home/mxz/aosp
$AOSP/out/host/linux-x86/bin/dx --dex --output="$N.dex" "c_$N" 2>&1 | head -3
ls -la "$N.dex"
cp "$N.dex" /mnt/e/A4-work/out/
echo "OK -> out/$N.dex"