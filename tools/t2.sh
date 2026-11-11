#!/bin/bash
cd /mnt/e/A4-work/tools/lib
mkdir -p /tmp/bt && cd /tmp/bt
CP=""
for j in asm-9.2 asm-commons-9.2 asm-tree-9.2 asm-util-9.2 smali-2.5.2 baksmali-2.5.2 \
         guava-27.0.1-jre gson-2.8.6 commons-lang3-3.9 jsr305-3.0.2; do
  src=/mnt/e/A4-work/tools/lib/$j.jar
  [ -s "$src" ] && CP="$CP:$src"
done
CP=${CP#:}
echo "classpath entries:"; echo "$CP" | tr ':' '\n' | sed 's/^/  /'
echo
echo "=== 逐个验证 jar完整性 ==="
for j in $(echo "$CP" | tr ':' '\n'); do
  unzip -t "$j" >/dev/null 2>&1 && echo "  OK   $(basename $j)" || echo "  BAD  $(basename $j)"
done
echo
echo "=== 运行 ==="
java -cp "$CP" org.jf.baksmali.Main --version 2>&1 | head -5