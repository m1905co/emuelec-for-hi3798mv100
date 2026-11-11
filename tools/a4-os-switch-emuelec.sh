#!/bin/sh
# a4-os-switch — 用 misc 标记切换启动目标（原厂 U-Boot 的 mode 选择）
#
#   status            查看当前标记
#   android / clear   清空标记 -> 下次启动安卓
#   emuelec           写 product-test -> 下次启动 EmuELEC（p10 里的内核）
#   recovery          写 boot-recovery -> 下次启动 recovery
#
# misc 分区（安卓编号 p9）位于 50MiB 起、8MiB 长。
# EmuELEC 的分区表把它并进了 p8(fastplay)，所以这里按整盘偏移写：
#   50MiB / 512 = 102400 扇区
MISC_OFF=102400
DISK=/dev/mmcblk0
B=/bin/busybox

[ -x "$B" ] || B=""
say() { echo "$@"; }

case "$1" in
    status)
        say "misc @50MiB:"
        $B dd if=$DISK bs=512 skip=$MISC_OFF count=1 2>/dev/null | $B hexdump -C | $B head -2
        exit 0
        ;;
    emuelec)  MARK='product-test' ;;
    recovery) MARK='boot-recovery' ;;
    android|clear) MARK='' ;;
    *) say "usage: $0 {status|android|emuelec|recovery|clear}"; exit 1 ;;
esac

if [ -z "$MARK" ]; then
    $B dd if=/dev/zero of=$DISK bs=512 seek=$MISC_OFF count=1 conv=notrunc 2>/dev/null
    say "misc 已清空 -> 下次启动 Android"
else
    printf '%-32s' "$MARK" | $B dd of=$DISK bs=512 seek=$MISC_OFF count=1 conv=notrunc 2>/dev/null
    if [ "$MARK" = "boot-recovery" ]; then
        say "misc <- 'boot-recovery' -> 下次进 recovery"
    else
        say "misc <- 'product-test' -> 下次进 EmuELEC"
    fi
fi
sync
say "rebooting in 2s ..."
sleep 2
reboot -f
