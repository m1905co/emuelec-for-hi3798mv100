#!/bin/bash
# 用 AOSP signapk + JDK7 重新签名（复刻 A6-Work 的成功流程）
set -e
cd /mnt/e/A4-work

AOSP=/home/mxz/aosp
SIGNAPK=$AOSP/prebuilts/sdk/tools/lib/signapk.jar
KEYDIR=$AOSP/build/target/product/security
JDK=$(cat $HOME/JDK7_PATH.txt)
OUT=update_v2_signed.zip
STAGE=/tmp/sigstage

echo "=== [1] 环境 ==="
echo "  JDK: $($JDK/bin/java -version 2>&1 | head -1)"
echo "  signapk: $SIGNAPK"

echo
echo "=== [2] 准备签名区（去掉旧签名）==="
rm -rf $STAGE && mkdir -p $STAGE
cd /mnt/e/A4-work
unzip -q -o update_v2_fixed.zip -d $STAGE \
    -x 'META-INF/MANIFEST.MF' 'META-INF/CERT.SF' 'META-INF/CERT.RSA'
echo "  条目数（去掉签名后）: $(cd $STAGE && find . -type f | wc -l)"

echo
echo "=== [3] 用 AOSP signapk 签名（JDK7）==="
cd $STAGE
"$JDK/bin/java" -jar "$SIGNAPK" \
    -w "$KEYDIR/testkey.x509.pem" "$KEYDIR/testkey.pk8" \
    "/mnt/e/A4-work/update_v2_fixed.zip" \
    "/mnt/e/A4-work/$OUT"

echo
echo "=== [4] 结果 ==="
ls -la "/mnt/e/A4-work/$OUT"
