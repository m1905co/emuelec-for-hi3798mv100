#!/bin/bash
cd /mnt/e/A4-work/tools/lib
BASE="https://maven.aliyun.com/repository/public"
fetch() {
  local f="${2}-${3}.jar"
  if [ -s "$f" ] && [ "$(stat -c%s "$f")" -gt 1024 ]; then echo "  have $f"; return 0; fi
  rm -f "$f"
  curl -sSL --retry 2 -o "$f" "${BASE}/${1}/${2}/${3}/${f}"
  local sz=$(stat -c%s "$f" 2>/dev/null || echo 0)
  if [ "$sz" -gt 1024 ]; then echo "  got  ${f} ($sz B)"; else echo "  FAIL ${f} ($sz)"; rm -f "$f"; fi
}
fetch org/guava/guava                       guava          27.0.1-jre
fetch com/google/code/gson/gson              gson           2.8.6
fetch org/apache/commons/commons-lang3      commons-lang3  3.9
fetch com/google/code/findbugs/jsr305       jsr305         3.0.2
fetch com/google/protobuf/protobuf-java      protobuf-java  3.19.1
fetch com/google/protobuf/protobuf-java-util protobuf-java-util 3.19.1
echo
echo "=== 最终 jar 清单 ==="
ls -la *.jar | awk '{printf "  %-40s %8s\n", $9, $5}'
echo
echo "=== 测试 baksmali ==="
CP=$(ls *.jar | tr '\n' ':')
java -cp "$CP" org.jf.baksmali.Main --version 2>&1 | head -3