#!/bin/bash
set -e
cd /mnt/e/A4-work/out/boot2/rd2

echo "=== [1] 备份原始 init.environ.rc ==="
cp init.environ.rc init.environ.rc.orig

echo "=== [2] 注入 hiplayer.jar 到 BOOTCLASSPATH ==="
sed -i 's|/system/framework/HMTAdapter.jar|/system/framework/HMTAdapter.jar:/system/framework/hiplayer.jar|' init.environ.rc

echo "=== [3] 校验：BOOTCLASSPATH 末尾 ==="
grep 'BOOTCLASSPATH' init.environ.rc | tr ':' '\n' | tail -3

echo "=== [4] 校验：出现次数应为 1 ==="
grep -c 'hiplayer.jar' init.environ.rc

echo "=== [5] 校验：diff 只有一行 ==="
diff init.environ.rc.orig init.environ.rc | head -8

echo "=== [6] 确认 jar 存在于 system 分区（后面要打包）==="
ls -l /mnt/e/A4-work/out/hiplayer.jar
