#!/bin/bash
L=/mnt/e/A4-work/tools/lib
CP="$L/baksmali-2.5.2.jar:$L/smali-2.5.2.jar:$L/asm-9.2.jar:$L/asm-commons-9.2.jar:$L/asm-tree-9.2.jar:$L/asm-util-9.2.jar:$L/guava-27.0.1-jre.jar:$L/gson-2.8.6.jar:$L/commons-lang3-3.9.jar:$L/jsr305-3.0.2.jar"
WORK=/tmp/hi
rm -rf $WORK; mkdir -p $WORK/smali; cd $WORK
unzip -o -q /mnt/e/A4-work/out/MediaCenter.apk classes.dex

echo "=== 1. baksmali 反汇编 ==="
java -cp "$CP" org.jf.baksmali.Main d classes.dex -o smali 2>&1 | tail -3
echo "产出类数: $(find smali -name '*.smali' | wc -l)"
[ -d smali/com/hisilicon ] && echo "✓ 目标包已生成" || { echo "✗ 目标包缺失"; exit 1; }

echo
echo "=== 2. 提取目标包 ==="
mkdir -p keep/com
cp -r smali/com/hisilicon keep/com/
echo "保留: $(find keep -name '*.smali' | wc -l) 个类"
find keep -name '*.smali' | sed 's|keep/||' | head -6

echo
echo "=== 3. 回编成 dex ==="
java -cp "$CP" org.jf.smali.Main assemble keep -o hiplayer.dex 2>&1 | tail -3
ls -la hiplayer.dex 2>/dev/null

echo
echo "=== 4. 验证 ==="
DX=/home/mxz/aosp/out/host/linux-x86/bin/dexdump
$DX hiplayer.dex 2>&1 | head -3
echo "回编后类数: $($DX hiplayer.dex 2>/dev/null | grep -c 'Class descriptor')"