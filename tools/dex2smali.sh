#!/bin/bash
DEX=/tmp/mc.dex
# 取出 MediaCenter 的 classes.dex
mkdir -p /tmp/mc
cd /tmp/mc
unzip -o -q /mnt/e/A4-work/out/MediaCenter.apk classes.dex && mv classes.dex $DEX
echo "dex: $(stat -c%s $DEX) B"
DX=/home/mxz/aosp/out/host/linux-x86/bin/dexdump
echo "=== dexdump -d 输出前20 行（smali 格式）==="
$DX -d $DEX 2>&1 | head -20
echo
echo "=== 检查是否含目标包 ==="
$DX -d $DEX 2>&1 | grep -c "hisilicon/android/mediaplayer"
echo "  ↑ 目标包出现次数"
echo
echo "=== 整包反汇编耗时测试 ==="
time ($DX -d $DEX > /tmp/mc/full.smali 2>/dev/null)
echo "full.smali: $(stat -c%s /tmp/mc/full.smali) B"