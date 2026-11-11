#!/bin/bash
# 权威标定：取 HiMediaPlayer 中第一个有 code 的方法，打印其 code 偏移与 code_item 头
cd /tmp/mcx
/home/mxz/aosp/out/host/linux-x86/bin/dexdump -d classes.dex 2>/dev/null > /tmp/all.dis

echo "=== HiMediaPlayer 方法表：前若干个方法的 access / code / insns size ==="
awk '
/Class descriptor  : .Lcom\/hisilicon\/android\/mediaplayer\/HiMediaPlayer;/{f=1}
f && /name  *:/{name=$0}
f && /access  *:/{acc=$0}
f && /insns size/{print name" | "acc" | "$0; c++}
f && /source_file_idx/{exit}
c>6{exit}
' /tmp/all.dis

echo
echo "=== 含 'code' 字段的格式样本 ==="
grep -m3 -n "code  *:" /tmp/all.dis | head -5
