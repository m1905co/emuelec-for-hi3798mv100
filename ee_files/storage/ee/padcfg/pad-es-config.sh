#!/bin/sh
# TITLE: 1) 重新配置前端(ES)按键
# DESC: 出官方 WELCOME 向导：按住手柄任意键 → 依次按 A/B/X/Y/LB/RB/START/SELECT…
#
# 背景：镜像里 /storage/ee/config/.emulationstation/es_input.cfg 原本带着一份
# 手柄按键表，ES 就认为"已配好"，永远不会再问。删掉这一份，ES 下次启动就是
# 标准首次配置流程（WELCOME / N GAMEPADS DETECTED / HOLD A BUTTON）。
# 原文件备份在 /storage/ee/padcfg/backup/，第 3 项可以还原。

E=/storage/ee/config/.emulationstation/es_input.cfg
B=/storage/ee/padcfg/backup
LOG=/storage/ee/logs/padcfg.log
mkdir -p "$B"

if [ -f "$E" ]; then
    busybox cp -f "$E" "$B/es_input.cfg.$(busybox date +%Y%m%d-%H%M%S)"
    busybox mv -f "$E" "$B/es_input.cfg.moved"
    echo "pad-es-config: 已移走 es_input.cfg，下次启动走 WELCOME 向导" >>"$LOG"
fi

/usr/bin/a4-es-restart
exit 0
