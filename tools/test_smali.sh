#!/bin/bash
cd /mnt/e/A4-work/tools/lib
# 剔除 554 字节的坏文件
echo "=== 清理无效 jar (<1KB =下载失败) ==="
for f in *.jar; do
  sz=$(stat -c%s "$f")
  if [ "$sz" -lt 1024 ]; then echo "  remove $f ($sz B)"; rm -f "$f"; fi
done
echo
echo "=== 测试 baksmali（只需 asm + guava 等）==="
CP=$(ls *.jar | tr '\n' ':')
java -cp "$CP" org.jf.baksmali.Main --version 2>&1 | head -5
echo
echo "=== 用 dexdump 反汇编（不用 smali，纯 AOSP 工具）==="
/home/mxz/aosp/out/host/linux-x86/bin/dexdump --help 2>&1 | head -8