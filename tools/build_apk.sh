#!/bin/bash
# 构建测试 APK：HiPlayerTest.apk（用 SDK19 android.jar，对应 Android 4.4）
set -e
AOSP=/home/mxz/aosp
BT=$AOSP/out/host/linux-x86/bin
AJ=$AOSP/prebuilts/sdk/19/android.jar
W=/home/mxz/hijack/apk
rm -rf $W; mkdir -p $W/src
cp -r /mnt/e/A4-work/out/apk/* $W/src/
cd $W

echo "=== 1. aapt package==="
$BT/aapt package -f -M src/AndroidManifest.xml -I $AJ -F base.apk 2>&1 | head -5
ls -la base.apk | head -2

echo "=== 2. javac（android.jar 作 bootclasspath）==="
mkdir -p classes
javac -source 1.6 -target 1.7 -bootclasspath $AJ -d classes \
      $(find src -name '*.java') 2>&1 | grep -vE 'bootstrap|deprecat|source value|target value' | head -8
echo "  编译产物:"; ls classes/com/test/hiplayer/ 2>/dev/null | head -5

echo "=== 3. dx==="
$BT/dx --dex --output=classes.dex classes 2>&1 | head -3
ls -la classes.dex | head -2

echo "=== 4. 塞进 apk==="
zip -q base.apk classes.dex
cp base.apk HiPlayer-unsigned.apk
ls -la HiPlayer-unsigned.apk | head -2

echo "=== 5. 签名==="
KEYS=/mnt/e/A4-work/keys
java -jar $AOSP/prebuilts/sdk/tools/lib/signapk.jar $KEYS/testkey.pk8 $KEYS/testkey.x509.pem HiPlayer-unsigned.apk HiPlayerTest.apk 2>&1 | head -3
ls -la HiPlayerTest.apk 2>/dev/null | head -2
cp HiPlayerTest.apk /mnt/e/A4-work/out/ && echo "COPIED -> out/HiPlayerTest.apk"