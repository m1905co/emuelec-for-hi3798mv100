#!/bin/bash
# 构建验证 APK：厂商类以 classes2.dex 形式随 APK 分发
# 关键点：MediaCenter 的 classes.dex 改名 classes2.dex 放进 APK，
#        Dalvik/ART 的 classloader 会自动加载它，无需运行时注入。
set -e

SDK19=/home/mxz/aosp/prebuilts/sdk/19
AAPT=/home/mxz/aosp/out/host/linux-x86/bin/aapt
DX=/home/mxz/aosp/out/host/linux-x86/bin/dx
ZIPALIGN=/home/mxz/aosp/out/host/linux-x86/bin/zipalign

SRC=/mnt/e/A4-work/out/apk
WORK=/home/mxz/hijack/verify
OUT=/mnt/e/A4-work/out/HiPlayerVerify-unsigned.apk

rm -rf $WORK && mkdir -p $WORK/classes $WORK/apk
cd $SRC

echo "=== [1] 编译 MainActivity ==="
javac -source 1.6 -target 1.7 \
    -bootclasspath $SDK19/android.jar \
    -d $WORK/classes com/test/hiplayer/MainActivity.java 2>&1 | grep -v "bootstrap class path" || true
ls $WORK/classes/com/test/hiplayer/ | head

echo
echo "=== [2] dx -> classes.dex ==="
$DX --dex --output=$WORK/apk/classes.dex $WORK/classes
ls -la $WORK/apk/classes.dex

echo
echo "=== [3] 厂商 dex 作为 classes2.dex ==="
cp /mnt/e/A4-work/out/mc_classes.dex $WORK/apk/classes2.dex
ls -la $WORK/apk/classes2.dex

echo
echo "=== [4] aapt 打包资源 + manifest ==="
$AAPT package -f -M AndroidManifest.xml \
    -I $SDK19/android.jar \
    -F $WORK/base.apk
ls -la $WORK/base.apk

echo
echo "=== [5] 合并（classes.dex 必须在最前，classes2.dex 紧随）==="
cd $WORK/apk
cp $WORK/base.apk $WORK/merged.apk
zip -q $WORK/merged.apk classes.dex classes2.dex
cd $WORK
$ZIPALIGN -f 4 $WORK/merged.apk $WORK/aligned.apk
cp $WORK/aligned.apk $OUT
ls -la $OUT

echo
echo "=== [6] 校验 ==="
python3 - "$OUT" <<'PY'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
n = z.namelist()
print('  条目数:', len(n))
for k in ['AndroidManifest.xml','classes.dex','classes2.dex']:
    if k in n:
        print('  %-20s %d bytes' % (k, z.getinfo(k).file_size))
    else:
        print('  %-20s ★ 缺失' % k)
print('  classes2.dex 头部:', z.read('classes2.dex')[:8])
PY
echo
echo "未签名包: $OUT"
