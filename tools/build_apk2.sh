#!/bin/bash
# 完整构建 HiPlayerTest.apk：含 assets 里的厂商 dex
set -e
AOSP=/home/mxz/aosp
BT=$AOSP/out/host/linux-x86/bin
AJ=$AOSP/prebuilts/sdk/19/android.jar
W=/home/mxz/hijack/apk2
rm -rf $W; mkdir -p $W/src
cp -r /mnt/e/A4-work/out/apk/* $W/src/
cd $W

echo "=== 1. aapt package（带 assets）==="
$BT/aapt package -f -M src/AndroidManifest.xml \
   -A src/assets -I $AJ -F base.apk 2>&1 | head -5
ls -la base.apk | head -2

echo "=== 2. javac==="
mkdir -p classes
javac -source 1.6 -target 1.7 -bootclasspath $AJ -d classes \
      $(find src -name '*.java') 2>&1 | grep -vE 'bootstrap|deprecat|source value|target value' | head -8
ls classes/com/test/hiplayer/ 2>/dev/null | head -3

echo "=== 3. dx==="
$BT/dx --dex --output=classes.dex classes 2>&1 | head -3
ls -la classes.dex | head -2

echo "=== 4.合并 classes.dex + assets 进 apk ==="
zip -q base.apk classes.dex
cp base.apk app-unsigned.apk
ls -la app-unsigned.apk | head -2
cp app-unsigned.apk /mnt/e/A4-work/out/HiPlayer-unsigned.apk
echo "-> out/HiPlayer-unsigned.apk"

echo "=== 5. 校验内容 ==="
unzip -l app-unsigned.apk