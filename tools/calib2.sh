#!/bin/bash
# 用 dexdump 的 code offset 模式定位 HiMediaPlayer.<clinit> 的真实 code_item 地址
cd /tmp/mcx
echo "=== dexdump 中所有 'code' 相关字段格式 ==="
grep -oE "code[a-z ]*:" /tmp/all.dis | sort | uniq -c

echo
echo "=== 搜索包含 'code' 与 'offset' 的行 ==="
grep -m5 -E "code.*0x[0-9a-f]{4,}" /tmp/all.dis | head -5

echo
echo "=== -d 模式下的 Class # 索引行样例（用于确认 class 边界）==="
grep -n -m3 "Class descriptor  : .Lcom/hisilicon/android/mediaplayer/HiMediaPlayer;" /tmp/all.dis

echo
echo "=== 该类第一行号到下一类之间的行数 ==="
S=$(grep -n "Class descriptor  : .Lcom/hisilicon/android/mediaplayer/HiMediaPlayer;" /tmp/all.dis | head -1 | cut -d: -f1)
echo "start line=$S"
sed -n "${S},$((S+25))p" /tmp/all.dis
