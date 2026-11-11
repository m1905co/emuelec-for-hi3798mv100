#!/bin/bash
# 用 AOSP 原生 signapk 重签 update_v2_hdmi4k.zip
set -e
cd /mnt/e/A4-work

AOSP=/home/mxz/aosp
SIGNAPK=$AOSP/prebuilts/sdk/tools/lib/signapk.jar

echo "=== [1] 准备：把 v2 包解开（去掉旧签名）==="
rm -rf v2work && mkdir v2work && cd v2work
unzip -q /mnt/e/A4-work/update_v2_hdmi4k.zip -x 'META-INF/MANIFEST.MF' 'META-INF/CERT.SF' 'META-INF/CERT.RSA'
echo "条目数（去掉签名后）: $(ls -R | grep -c '^-' || true)"
ls META-INF/

echo
echo "=== [2] 检查是否有预签名目录要排除 ==="
ls -d META-INF/com 2>/dev/null && echo "(com/ 存在，signapk 会保留)"

echo
echo "=== [3] 调用 AOSP signapk 签名 ==="
java -jar $SIGNAPK \
    /mnt/e/A4-work/keys/testkey.pk8 \
    /mnt/e/A4-work/keys/testkey.x509.pem \
    /mnt/e/A4-work/v2work \
    /mnt/e/A4-work/update_v2_signapk.zip

echo "签名完成"
ls -la /mnt/e/A4-work/update_v2_signapk.zip
