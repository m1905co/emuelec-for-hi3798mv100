#!/bin/bash
echo "=== 1. smali/baksmali 工具 ==="
for t in smali baksmali apktool; do
  which $t 2>/dev/null && echo "  found: $t"
done
ls /home/mxz/aosp/out/host/linux-x86/bin/ 2>/dev/null | grep -iE "smali|dexdump|dexlist" | sed 's/^/  host: /'
find /home/mxz -maxdepth 4 -iname '*smali*.jar' 2>/dev/null | head -5 | sed 's/^/  jar: /'
echo
echo "=== 2. AOSP 里的 dexdump ==="
find /home/mxz/aosp -maxdepth 5 -name 'dexdump' -type f 2>/dev/null | head -3
echo
echo "=== 3. 现有 build-tools ==="
ls /home/mxz/aosp/prebuilts/sdk/ 2>/dev/null | head -5
echo
echo "=== 4. java 版本 ==="
java -version 2>&1 | head -2