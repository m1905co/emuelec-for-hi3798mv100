#!/bin/bash
# 诊断 Java 读证书失败的原因，并尝试绕过
set -e
cd /mnt/e/A4-work

echo "=== [1] Java 版本 ==="
java -version 2>&1 | head -3

echo
echo "=== [2] 用 keytool 读取本地 pem ==="
keytool -printcert -file keys/testkey.x509.pem 2>&1 | head -8

echo
echo "=== [3] 尝试转成 PKCS8 DER 再看 ==="
openssl x509 -in keys/testkey.x509.pem -outform DER -out /tmp/cert.der 2>&1
ls -la /tmp/cert.der
openssl x509 -in keys/testkey.x509.pem -noout -text 2>&1 | head -6

echo
echo "=== [4] 关键：cert 的 signature algorithm 是否带显式 NULL 参数 ==="
openssl asn1parse -in keys/testkey.x509.pem -i 2>&1 | head -12

echo
echo "=== [5] 换用较新的 JDK（若有）==="
ls /usr/lib/jvm/ 2>/dev/null
for jv in /usr/lib/jvm/*/bin/java; do
  [ -x "$jv" ] && echo "  $jv -> $($jv -version 2>&1|head -1)"
done
