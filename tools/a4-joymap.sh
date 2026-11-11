#!/bin/sh
# a4-joymap.sh - 启动游戏前，按实际 js 编号分配玩家端口
#
# 部署：/opt/emuelec/bin/a4-joymap.sh（755）
# 挂载：/opt/emuelec/bin/run-retroarch.sh，在 `echo "HiSTB controller database path..."` 之前
#
# 为什么需要它：
#   1) jsN 的编号取决于设备注册顺序 —— 冷启动时 USB 手柄可能先拿到 js0，
#      热插拔后又是另一个号；遥控（uinput，由 a4-ird 创建）也会随时插进来。
#      写死 index 必然出错。
#   2) RetroArch 的 player2 index 默认是 "1"，如果 player1 也被设成 1，
#      就会两个玩家抢同一设备 —— 表现是"一个手柄同时控两人、投币翻倍"。
#
# 规则（按物理手柄出现顺序）：
#   第 1 支实体手柄 → Player 1
#   第 2 支实体手柄 → Player 2
#   第 3/4 支        → Player 3/4
#   没有对应设备时写 99（不存在的 index = 该玩家禁用）
#   `A4 IR Remote` 是 a4-ird 造的虚拟手柄，永远排除，不占玩家位。
CFG=/opt/emuelec/etc/retroarch.cfg
[ -f "$CFG" ] || exit 0

PADS=$(awk '
  /^N: Name=/ { name=$0 }
  /^H: Handlers=/ {
    if (name ~ /A4 IR Remote/) next
    if (name ~ /X-Box|ZhiXu|Joystick|Gamepad|Pad/) {
      if (match($0, /js[0-9]+/)) print substr($0, RSTART+2, RLENGTH-2)
    }
  }
' /proc/bus/input/devices)

CNT=0
for n in $PADS; do CNT=$((CNT + 1)); done

i=1
for n in $PADS; do
    [ "$i" -gt 4 ] && break
    sed -i "s/^input_player${i}_joypad_index = .*/input_player${i}_joypad_index = \"$n\"/" "$CFG"
    i=$((i + 1))
done
# 剩余玩家位禁用，避免默认值（player2 默认 "1"）撞车。
# 注意：不能用 99 这种大数值 —— RetroArch 会按该 index 取设备数组，
# 越界会让 sdl2 joypad 驱动崩溃（实测退出码 139）。用「手柄数+1」这种
# 贴近范围的小值是安全的：它必然大于所有物理手柄的 jsN。
D=$((CNT + 1))
while [ "$i" -le 4 ]; do
    sed -i "s/^input_player${i}_joypad_index = .*/input_player${i}_joypad_index = \"$D\"/" "$CFG"
    i=$((i + 1))
done
exit 0
