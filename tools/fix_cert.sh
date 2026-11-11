#!/bin/bash
# 绕过 signapk 的证书解析：把证书转成 PKCS#8 DER（signapk 支持 .key/pk8 格式的公钥）
set -e
cd /mnt/e/A4-work
AOSP=/home/mxz/aosp
SIGNAPK=$AOSP/prebuilts/sdk/tools/lib/signapk.jar

echo "=== [1] 生成 PKCS8 格式的公钥文件 ==="
# signapk 支持：-pubkey（从 .pk8 推导）或直接给 .x509.pem
# 但它对 pem 的解析有 bug → 改用 openssl 生成 DER 格式的公钥
openssl rsa -in <(openssl x509 -in keys/testkey.x509.pem -noout -pubkey 2>/dev/null) \
    -pubout -outform DER -out /tmp/pub.der 2>/dev/null || \
openssl x509 -in keys/testkey.x509.pem -noout -modulus 2>/dev/null | \
    sed 's/Modulus=//' | xxd -r -p | \
    openssl rsa -pubin -inform DER -modulus -noout 2>/dev/null
ls -la /tmp/pub.der 2>/dev/null || echo "(pub.der 未生成)"

echo
echo "=== [2] 方案A：把 pem 转成 DER 后让 signapk 读 ==="
openssl x509 -in keys/testkey.x509.pem -outform DER -out /tmp/cert.der
# signapk 期望 PEM 文本，若给 DER 需重包成 PEM
openssl x509 -in keys/testkey.x509.pem -out /tmp/cert_as_pem.pem
echo "转换完成"

echo
echo "=== [3] 方案B：用 keytool 生成 JKS/PKCS12 再导出 ==="
rm -f /tmp/keystore.jks
keytool -importkeystore \
    -srckeystore /dev/null -srcstoretype PKCS12 \
    2>/dev/null || true
# 直接把 PEM 转 PKCS12
openssl pkcs12 -export -in keys/testkey.x509.pem -nokeys \
    -out /tmp/cert.p12 -passout pass:android 2>&1 | head -2
ls -la /tmp/cert.p12 2>/dev/null

echo
echo "=== [4] 方案C：升级 JDK 后用原版 signapk ==="
ls /usr/lib/jvm/
