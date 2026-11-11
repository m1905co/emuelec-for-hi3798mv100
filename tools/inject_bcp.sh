#!/system/bin/sh
# 精确追加 hiplayer.jar 到 BOOTCLASSPATH 末尾
# 只做一件事：把 ":/system/framework/HMTAdapter.jar" 替换为
#":/system/framework/HMTAdapter.jar:/system/framework/hiplayer.jar"
# 幂等：若已存在 hiplayer.jar 则不重复追加

RC=/init.environ.rc
BAK=/data/local/tmp/init.environ.rc.bak

echo "[1] 校验备份存在"
if [ ! -f "$BAK" ]; then echo "FATAL: no backup"; exit 1; fi

echo "[2] 检查是否已注入"
if grep -q 'hiplayer.jar' "$RC"; then
  echo "already injected, skip"
  grep 'BOOTCLASSPATH' "$RC"
  exit 0
fi

echo "[3] 确认 jar 存在"
if [ ! -f /system/framework/hiplayer.jar ]; then echo "FATAL: jar missing"; exit 1; fi
ls -l /system/framework/hiplayer.jar

echo "[4] 追加"
# 用 sed 在 BOOTCLASSPATH 行末追加（该行以 HMTAdapter.jar 结尾）
sed -i 's|/system/framework/HMTAdapter.jar|/system/framework/HMTAdapter.jar:/system/framework/hiplayer.jar|' "$RC"
RC=$?

echo "[5] 校验结果"
BOOT_LINE=$(grep 'BOOTCLASSPATH' "$RC")
echo "$BOOT_LINE" | tr ':' '\n' | tail -4
echo "---"
echo "$BOOT_LINE" | grep -c 'hiplayer.jar'
echo "[6] 确认只有一个 BOOTCLASSPATH 行"
grep -c 'BOOTCLASSPATH' "$RC"
echo "[7] 确认行数未变（应为 13 行）"
wc -l < "$RC"
