#!/system/bin/sh
# a4-p11 — 通过覆盖 p11(内核分区) 切换 Android / EmuELEC
#
# 原理：原厂 U-Boot mode 0 固定从 p11(82MiB) 读 10MiB 交给 bootimg 启动。
#       所以"切系统"= 把对应 boot.img 写进 p11，等价于给这个固定位置换内容。
#       recovery 走的是另一条路(p3)，不受影响，电源键照常能进。
#
# 依赖：/data/a4/p11-emuelec.img  (emuelec_boot_v9.img, 10,475,520 B, 20460 扇区)
#       /data/a4/p11-android.img  (原厂 boot.img, 10,486,020 B, 写前 20480 扇区)
#
# 用法：a4-p11 status | emuelec | android
P=/dev/block/mmcblk0p11
EMU_MD5=f67608d3cb041589291782bae6753add
STOCK_MD5=202d0143c05501473758385bd30769fd
B=/system/bin/busybox

write_img() {
    IMG="$1"; SEC="$2"; WANT="$3"
    [ -f "$IMG" ] || { echo "missing $IMG"; exit 1; }
    got=$($B dd if="$IMG" bs=512 count=$SEC 2>/dev/null | $B md5sum | $B cut -d' ' -f1)
    [ "$got" = "$WANT" ] || { echo "local image md5 mismatch: $got != $WANT"; exit 1; }
    echo "writing $IMG ($SEC sectors) -> $P"
    $B dd if="$IMG" of="$P" bs=512 count=$SEC 2>/dev/null
    sync
    back=$($B dd if="$P" bs=512 count=$SEC 2>/dev/null | $B md5sum | $B cut -d' ' -f1)
    echo "readback md5: $back"
    [ "$back" = "$WANT" ] && echo "OK" || { echo "READBACK MISMATCH - 不要重启，先排查"; exit 2; }
}

case "$1" in
    status)
        echo "p11 head:"; $B dd if=$P bs=512 count=1 2>/dev/null | $B hexdump -C | $B head -2
        echo -n "p11 first 10MiB md5: "
        $B dd if=$P bs=1048576 count=10 2>/dev/null | $B md5sum
        echo "  android expect(20480sec): $STOCK_MD5"
        echo "  emuelec expect(20460sec): $EMU_MD5"
        ;;
    emuelec)  write_img /data/a4/p11-emuelec.img 20460 "$EMU_MD5";   echo "reboot 后进 EmuELEC" ;;
    android)  write_img /data/a4/p11-android.img 20480 "$STOCK_MD5"; echo "reboot 后进 Android" ;;
    *) echo "usage: $0 {status|emuelec|android}"; exit 1 ;;
esac
