#!/bin/sh
# TITLE: 2) 清掉模拟器(RA)预置映射
# DESC: 把 ZhiXu / Xbox / USB 手柄的 autoconfig 移走 → 进游戏后 R3+L3 打开菜单，自己在「设置→输入」里绑
#
# 为什么要这一项：RetroArch **没有"首次配置向导"**，它只会按
# /storage/.config/retroarch/autoconfig/<设备>.cfg 自动套用。预置文件是我之前
# 按标定值写进去的，所以插上就直接能用 —— 也就绕过了"自己设一遍"的过程。
# 移走后 RA 会退回内置默认（button 0/1/2…），再由你在菜单里改，改完会写进
# retroarch.cfg（input_player1_*），以后就按你的来。

A=/storage/.config/retroarch/autoconfig
B=/storage/ee/padcfg/backup
LOG=/storage/ee/logs/padcfg.log
T=$(busybox date +%Y%m%d-%H%M%S)
mkdir -p "$B/autoconfig-$T"

for f in "ZhiXu-Gamepad.cfg" "Game-USB-Joystick.cfg" "Microsoft-XBox360.cfg"; do
    [ -f "$A/$f" ] && busybox mv -f "$A/$f" "$B/autoconfig-$T/$f"
done
echo "pad-ra-clear: 预置映射已移到 $B/autoconfig-$T" >>"$LOG"

/usr/bin/a4-es-restart
exit 0
