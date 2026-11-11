#!/bin/sh
# TITLE: 3) 恢复标定好的默认映射
# DESC: 前端还原最近一次备份；模拟器还原 /storage/ee/padcfg/default 里的标定文件
#
# 还原来源：
#   前端(ES)   ← /storage/ee/padcfg/backup/es_input.cfg.<时间>（最近一份）
#   模拟器(RA) ← /storage/ee/padcfg/default/ZhiXu-Gamepad.cfg（原始副本，不会被误删带走）

E=/storage/ee/config/.emulationstation/es_input.cfg
A=/storage/.config/retroarch/autoconfig
B=/storage/ee/padcfg/backup
D=/storage/ee/padcfg/default
LOG=/storage/ee/logs/padcfg.log

LAST=$(busybox ls -1t "$B"/es_input.cfg.[0-9]* 2>/dev/null | busybox head -1)
if [ -n "$LAST" ]; then
    busybox cp -f "$LAST" "$E"
    echo "pad-restore: ES <- $LAST" >>"$LOG"
fi

if [ -f "$D/ZhiXu-Gamepad.cfg" ]; then
    busybox cp -f "$D/ZhiXu-Gamepad.cfg" "$A/ZhiXu-Gamepad.cfg"
    echo "pad-restore: RA autoconfig <- $D/ZhiXu-Gamepad.cfg" >>"$LOG"
fi
if [ -f "$D/ZhiXu Gamepad.cfg" ]; then
    busybox cp -f "$D/ZhiXu Gamepad.cfg" "/opt/emuelec/share/retroarch/autoconfig/sdl2/ZhiXu Gamepad.cfg" 2>/dev/null
fi

/usr/bin/a4-es-restart
exit 0
