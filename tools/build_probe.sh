#!/bin/bash
# 在 WSL 里用 AOSP 的 dx.jar 把 Probe.java 编译成 classes.dex
set -e
W=/home/mxz/hijack
mkdir -p $W
cp /mnt/e/A4-work/out/Probe.java $W/
cd $W
AOSP=/home/mxz/aosp
# android.jar 提供编译期需要的 framework 引用
AJ=$AOSP/out/target/product/Hi3798MV100/system/framework/framework.jar
[ -s "$AJ" ] || AJ=$AOSP/prebuilts/android/common/build/core/framework.jar
echo "android.jar: $AJ ($(stat -c%s "$AJ" 2>/dev/null) B)"
mkdir -p classes
javac -source 1.7 -target 1.7 -bootclasspath "$AJ" -d classes Probe.java 2>&1 | head -5
ls -la classes/
echo "=== dx 转 dex ==="
DX=$AOSP/out/host/linux-x86/bin/dx
[ -x "$DX" ] || DX="java -jar $AOSP/out/host/linux-x86/framework/dx.jar"
$DX --dex --output=Probe.dex classes/Probe.class 2>&1 | head -5
ls -la Probe.dex
cp Probe.dex /mnt/e/A4-work/out/Probe.dex
echo "已复制到 /mnt/e/A4-work/out/Probe.dex"