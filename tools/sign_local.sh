#!/bin/bash
# 在 WSL 本地盘完成打包+签名，再复制回 /mnt/e
set -e
WORK=/tmp/a4sign
AOSP=/home/mxz/aosp
SIGNAPK=$AOSP/prebuilts/sdk/tools/lib/signapk.jar
KEYDIR=$AOSP/build/target/product/security
JDK=$(cat $HOME/JDK7_PATH.txt)

echo "=== [1] 准备工作目录 ==="
rm -rf $WORK && mkdir -p $WORK/stage
cp /mnt/e/A4-work/update_v2_fixed.zip $WORK/in.zip
ls -la $WORK/in.zip

echo
echo "=== [2] 在 WSL 本地盘解包（排除旧签名）==="
cd $WORK/stage
unzip -q -o $WORK/in.zip -x 'META-INF/MANIFEST.MF' 'META-INF/CERT.SF' 'META-INF/CERT.RSA'
echo "  条目数: $(find . -type f | wc -l)"

echo
echo "=== [3] 用 JDK7 + AOSP signapk 签名 ==="
cd $WORK
"$JDK/bin/java" -jar "$SIGNAPK" \
    -w "$KEYDIR/testkey.x509.pem" "$KEYDIR/testkey.pk8" \
    "$WORK/in.zip" "$WORK/signed.zip"

echo
echo "=== [4] 复制回 Windows 目录，命名为 update.zip ==="
cp $WORK/signed.zip /mnt/e/A4-work/update.zip
ls -la /mnt/e/A4-work/update.zip
echo "完成"
