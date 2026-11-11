#!/system/bin/sh
# a4-os-switch — 用 misc 分区标记切换启动目标（原厂 U-Boot 自带的三档模式）
#
#   原厂 U-Boot 0xC2A284 的判定（子串搜索，匹配 misc 前 0xC00 字节内任意位置）：
#     含 "product-test" -> mode 2 -> bootcmd = "mmc read 0 0x82000000 0x1D000 0xC000; bootm 0x82000000"
#                                     即从 58MiB(p10) 读 24MiB 到 0x82000000 后 bootm -> uImage 必须在 p10 偏移 0
#     含 "boot-recovery" -> mode 1 -> 读 5MiB/13MiB 处 4MiB -> RSA 校验 -> first/second-recovery
#     无标记             -> mode 0 -> 读 p11(82MiB) 10MiB -> bootimg 0x1FFBFC0 -> 安卓
#
# 用法（需 root）：
#   a4-os-switch status      查看当前标记
#   a4-os-switch android     回到安卓
#   a4-os-switch emuelec     切 EmuELEC（要求 p10 偏移 0 处是 uImage）
#   a4-os-switch recovery    下次启动进 recovery
#   a4-os-switch clear       等价 android（清标记）
#
# 注意：本脚本只改 misc 前 32 字节（BCB command 字段），改前自动备份前 0xC00 字节到 /data/a4/misc.bak

MISC=/dev/block/mmcblk0p9
BAK=/data/a4/misc.bak
B=/system/bin/busybox

mkdir -p /data/a4

backup_once() {
    [ -f "$BAK" ] && return 0
    $B dd if=$MISC of=$BAK bs=3072 count=1 2>/dev/null
    echo "backup -> $BAK"
}

set_marker() {
    # $1 = 标记字符串（空串表示清零）
    backup_once
    [ -z "$1" ] && set -- ""
    $B printf '%-32s' "$1" | $B dd of=$MISC bs=32 count=1 conv=notrunc 2>/dev/null
    sync
    echo "misc[0..32] <- '$1'"
    status
}

status() {
    echo -n "misc cmd: "
    $B dd if=$MISC bs=32 count=1 2>/dev/null | $B hexdump -C | $B head -2
}

reboot_now() {
    sync
    echo "rebooting in 2s ..."
    sleep 2
    reboot
}

case "$1" in
    android|clear) set_marker "";             reboot_now ;;
    emuelec)       set_marker "product-test"; reboot_now ;;
    recovery)      set_marker "boot-recovery"; reboot_now ;;
    status|"")     status ;;
    *) echo "usage: $0 {status|android|emuelec|recovery|clear}"; exit 1 ;;
esac
