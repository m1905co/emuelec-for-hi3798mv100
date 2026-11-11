#!/bin/bash
cd /home/mxz/hijack/lib
echo "=== 1. 用 jar 命令验证 ==="
jar tf baksmali-2.5.2.jar 2>&1 | grep -c class
echo
echo "=== 2. 提取 Main.class 并用 javap 看 ==="
mkdir -p /tmp/x && cd /tmp/x && rm -rf * 
jar xf /home/mxz/hijack/lib/baksmali-2.5.2.jar org/jf/baksmali/Main.class
ls -la org/jf/baksmali/Main.class
javap -p org/jf/baksmali/Main.class 2>&1 | head -8
echo
echo "=== 3. main 方法签名 ==="
javap -c org/jf/baksmali/Main.class 2>&1 | grep -A3 "public static void main"
echo
echo "=== 4. 试探：只加 asm ==="
cd /home/mxz/hijack/lib
for combo in "baksmali-2.5.2.jar" \
             "baksmali-2.5.2.jar:smali-2.5.2.jar" \
             "baksmali-2.5.2.jar:smali-2.5.2.jar:asm-9.2.jar" \
             "baksmali-2.5.2.jar:smali-2.5.2.jar:asm-9.2.jar:asm-commons-9.2.jar:asm-tree-9.2.jar:asm-util-9.2.jar:guava-27.0.1-jre.jar:gson-2.8.6.jar:commons-lang3-3.9.jar:jsr305-3.0.2.jar"; do
  out=$(java -cp "$combo" org.jf.baksmali.Main 2>&1 | head -1)
  echo "  [${#combo} chars] $out"
done