#!/system/bin/sh
# 精确追加 hiplayer.jar 到 BOOTCLASSPATH（全部使用 busybox）
RC=/init.environ.rc

echo "[1] jar 存在性"
busybox ls -l /system/framework/hiplayer.jar || exit 1

echo "[2] 当前是否已注入"
if busybox grep -q 'hiplayer.jar' "$RC"; then
  echo "ALREADY INJECTED - 跳过"
  exit 0
fi

echo "[3] 改动前 md5"
busybox md5sum "$RC"

echo "[4] 执行追加"
busybox sed -i 's|/system/framework/HMTAdapter.jar|/system/framework/HMTAdapter.jar:/system/framework/hiplayer.jar|' "$RC"

echo "[5] 改动后 md5"
busybox md5sum "$RC"

echo "[6] BOOTCLASSPATH 末尾 4 项"
busybox grep 'BOOTCLASSPATH' "$RC" | busybox tr ':' '\n' | busybox tail -4

echo "[7] hiplayer.jar 出现次数（应为 1）"
busybox grep -c 'hiplayer.jar' "$RC"

echo "[8] BOOTCLASSPATH 行数（应为 1）"
busybox grep -c 'BOOTCLASSPATH' "$RC"

echo "[9] 文件总行数（改动前应为 13）"
busybox wc -l < "$RC"

echo "[10] 与备份 diff（应只有 1 行变化）"
busybox diff /data/local/tmp/init.environ.rc.bak "$RC" | busybox head -8
