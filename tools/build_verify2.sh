#!/bin/bash
# 构建验证 APK v2
#   - MainActivity 的 classes.dex（我的代码）
#   - assets/himediaplayer.dex = 厂商 dex 包成 jar（zip 容器，.dex 后缀）
#     ★ Dalvik 4.4 的 DexFile 打不开裸 .dex，但对 zip 容器内的 dex 正常
set -e

SDK19=/home/mxz/aosp/prebuilts/sdk/19
AAPT=/home/mxz/aosp/out/host/linux-x86/bin/aapt
DX=/home/mxz/aosp/out/host/linux-x86/bin/dx
ZIPALIGN=/home/mxz/aosp/out/host/linux-x86/bin/zipalign

SRC=/mnt/e/A4-work/out/apk
WORK=/home/mxz/hijack/verify2
OUT=/mnt/e/A4-work/out/HiPlayerVerify2-unsigned.apk

rm -rf $WORK && mkdir -p $WORK/classes $WORK/apk/assets
cd $SRC

echo "=== [1] 编译 MainActivity ==="
javac -source 1.6 -target 1.7 \
    -bootclasspath $SDK19/android.jar \
    -d $WORK/classes com/test/hiplayer/MainActivity.java 2>&1 \
    | grep -vE "bootstrap class path|deprecat" || true
ls $WORK/classes/com/test/hiplayer/*.class | wc -l

echo "=== [2] dx ==="
$DX --dex --output=$WORK/apk/classes.dex $WORK/classes
ls -la $WORK/apk/classes.dex

echo "=== [3] 厂商 dex 打成 zip 容器（assets 里）==="
cd $WORK/apk/assets
cp /mnt/e/A4-work/out/mc_classes.dex classes.dex
zip -q /mnt/e/A4-work/out/apk/assets/himediaplayer.dex classes.dex
rm -f classes.dex
ls -la /mnt/e/A4-work/out/apk/assets/himediaplayer.dex
python3 -c "
import zipfile
z=zipfile.ZipFile('/mnt/e/A4-work/out/apk/assets/himediaplayer.dex')
for i in z.infolist(): print('  ',i.filename, i.file_size, 'compress=%d'%i.compress_type)
print('  内层 dex 头:', z.read('classes.dex')[:8])
"

echo "=== [4] aapt（assets 先拷到工作区，aapt 只接受它能读到的路径）==="
mkdir -p $WORK/pkg
cp $SRC/AndroidManifest.xml $WORK/pkg/
mkdir -p $WORK/pkg/assets
cp /mnt/e/A4-work/out/apk/assets/himediaplayer.dex $WORK/pkg/assets/
cd $WORK/pkg
$AAPT package -f -M AndroidManifest.xml -A assets \
    -I $SDK19/android.jar -F $WORK/base.apk
ls -la $WORK/base.apk
python3 -c "
import zipfile
z=zipfile.ZipFile('$WORK/base.apk')
for i in z.infolist(): print('  ',i.filename,i.file_size)
"

echo "=== [5] 合并 + 对齐 ==="
cp $WORK/base.apk $WORK/merged.apk
cd $WORK/apk && zip -q $WORK/merged.apk classes.dex
cd $WORK && $ZIPALIGN -f 4 $WORK/merged.apk $WORK/aligned.apk
cp $WORK/aligned.apk $OUT
ls -la $OUT

echo "=== [6] 校验 ==="
python3 - "$OUT" <<'PY'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
for k in z.namelist():
    print('  %-32s %d' % (k, z.getinfo(k).file_size))
PY
echo "未签名: $OUT"
