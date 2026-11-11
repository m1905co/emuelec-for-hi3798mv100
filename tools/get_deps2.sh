#!/bin/bash
cd /mnt/e/A4-work/tools/lib
BASE="https://repo1.maven.org/maven2"
fetch() { # path artifact version
  local f="${2}-${3}.jar"
  [ -s "$f" ] && [ "$(stat -c%s "$f")" -gt 1024 ] && { echo "  have $f"; return 0; }
  rm -f "$f"
  # 用 -L 跟随重定向，加 UA，部分 CDN 需要
  curl -sSL -A "Mozilla/5.0" --retry 3 --retry-delay 1 \
       -o "$f" "${BASE}/${1}/${2}/${3}/${f}"
  local sz=$(stat -c%s "$f" 2>/dev/null || echo 0)
  if [ "$sz" -gt 1024 ]; then echo "  got ${f} ($sz B)"; else echo "  FAIL ${f} ($sz B)"; rm -f "$f"; fi
}
fetch org/guava/guava                       guava          27.0.1-jre
fetch com/google/code/gson/gson              gson           2.8.6
fetch org/apache/commons/commons-lang3      commons-lang3  3.9
fetch com/google/code/findbugs/jsr305       jsr305         3.0.2
echo
echo "=== 保留的 jar ==="
ls -la *.jar | awk '{printf "  %-40s %8s\n", $9, $5}'