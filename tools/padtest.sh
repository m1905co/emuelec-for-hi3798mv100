#!/bin/sh
# padtest.sh —— 找出"热键+Start 真能退出"的那个热键（就地测，不改任何配置）
# 用法：sh /storage/ee/padtest.sh
K=/storage/ee/a4-keys
D=/dev/input/event0
LOG=/storage/ee/logs/padtest.log
: >"$LOG"

alive() {
    a=0
    for p in /proc/[0-9]*; do
        c=$(tr '\0' ' ' < "$p/cmdline" 2>/dev/null)
        case "$c" in *bin/retroarch*) a=1 ;; esac
    done
    echo $a
}

start_ra() {
    for p in /proc/[0-9]*; do
        c=$(tr '\0' ' ' < "$p/cmdline" 2>/dev/null)
        case "$c" in *emulationstation*|*bin/retroarch*) kill -TERM "${p#/proc/}" 2>/dev/null ;; esac
    done
    sleep 4
    (busybox setsid /opt/emuelec/bin/run-retroarch.sh fbneo /media/emuelec-tf/EmuELEC/roms/fbneo/mslug3.zip \
        >/storage/ee/logs/padtest_ra.log 2>&1 </dev/null &)
    sleep 16
}

echo "== 启动 RA ==" >>"$LOG"
start_ra
echo "alive_after_start=$(alive)" >>"$LOG"

for h in 310 311 312 313 314 316 317 318; do
    $K $D d$h w250 d315 w300 u315 w100 u$h >/dev/null 2>&1
    sleep 3
    a=$(alive)
    echo "hotkey=$h + Start(315) -> alive=$a" >>"$LOG"
    if [ "$a" = "0" ]; then
        echo ">>> 退出成功，热键 = $h" >>"$LOG"
        break
    fi
    # 关掉可能被打开的任何菜单
    $K $D d305 w150 u305 >/dev/null 2>&1
    sleep 1
done
echo "== 结束 ==" >>"$LOG"
cat "$LOG"
