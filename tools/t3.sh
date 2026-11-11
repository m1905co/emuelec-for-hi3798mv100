#!/bin/bash
# 全部在 WSL 本地文件系统操作，避开 /mnt/e 挂载
LOCAL=/home/mxz/hijack
rm -rf $LOCAL; mkdir -p $LOCAL/lib $LOCAL/work
cp /mnt/e/A4-work/tools/lib/*.jar $LOCAL/lib/
cd $LOCAL/lib
CP=$(ls *.jar | tr '\n' ':')
echo "=== jar 清单 ==="; ls -la *.jar | awk '{printf "  %-34s %8s\n",$9,$5}'
echo
echo "=== 测试 baksmali（本地路径）==="
java -cp "$CP" org.jf.baksmali.Main 2>&1 | head -6