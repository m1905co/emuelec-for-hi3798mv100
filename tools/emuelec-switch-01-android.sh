#!/bin/sh
# 01-reboot-to-android.sh - 从 EmuELEC 切回 Android（misc 标记方式）
#
# ES 菜单「系统切换 / Switch OS」通过 es_systems.cfg 的 "switchos" 条目调用本脚本。
#
# 原理：清空 misc(p9) 里的引导标记 -> 原厂 U-Boot 走 mode0 -> 从 p11 启动 Android。
# 旧实现是把 64KiB 的 env 块写进 p2；原厂 U-Boot 不读 env 里的 bootcmd（板级代码会覆盖），
# 所以那条路已废弃。真正干活的是 /usr/bin/a4-os-switch，这里只负责日志与检查。
LOG=/storage/ee/logs/a4-switch.log

say() {
    echo "[a4-switch] $*"
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >>"${LOG}" 2>/dev/null || true
}

say "menu: reboot to Android requested"

if [ ! -x /usr/bin/a4-os-switch ]; then
    say "ERROR: /usr/bin/a4-os-switch missing or not executable"
    exit 1
fi

say "clearing misc marker -> Android"
exec /usr/bin/a4-os-switch android
