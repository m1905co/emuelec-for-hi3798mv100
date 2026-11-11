#!/bin/bash
cd /mnt/e/A4-work/tools/lib
rm -f *-jre-guava-*.jar 9.2-asm-*.jar 3.9-commons-*.jar 2.8.6-gson-*.jar \
      3.19.1-protobuf-*.jar 2.8-j2objc-*.jar 3.5-checker-*.jar \
      2.3.4-error_*.jar 1.3-j2objc-*.jar 3.0.2-jsr305-*.jar
BASE="https://repo1.maven.org/maven2"
fetch() { # $1=group/path  $2=artifact  $3=version
  local p="$1" a="$2" v="$3"
  local f="${a}-${v}.jar"
  if [ -s "$f" ]; then echo "  have $f"; return 0; fi
  curl -sSL -o "$f" "${BASE}/${p}/${a}/${v}/${f}" \
    && echo "  got ${f} ($(stat -c%s "$f") B)"
}
fetch org/guava/guava                       guava                27.0.1-jre
fetch com/google/code/findbugs/jsr305       jsr305                3.0.2
fetch org/ow2/asm                            asm                   9.2
fetch org/ow2/asm                            asm-commons           9.2
fetch org/ow2/asm                            asm-tree              9.2
fetch org/ow2/asm                            asm-util              9.2
fetch org/apache/commons/commons-lang3        commons-lang3         3.9
fetch com/google/code/gson/gson                gson                  2.8.6
fetch com/google/protobuf/protobuf-java      protobuf-java         3.19.1
fetch com/google/protobuf/protobuf-java-util protobuf-java-util    3.19.1
fetch com/google/code/findbugs/j2objc-annotations j2objc-annotations 2.8
fetch org/checkerframework/checker-qual      checker-qual          3.5
fetch com/google/errorprone/error_prone_annotations error_prone_annotations 2.3.4
echo "=== 结果 ==="
ls -la *.jar | awk '{printf "  %-42s %8s\n", $9, $5}'