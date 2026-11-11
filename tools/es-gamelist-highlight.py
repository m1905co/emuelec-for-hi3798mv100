#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
es-gamelist-highlight.py — 为 HiSTB 版 EmulationStation 恢复游戏列表的"选中项"视觉反馈。

背景
----
该 ES 构建裁剪了主题加载（--debug 日志中 0 次 theme 解析），gamelist 使用内置样式。
TextListComponent<FileData>::render 中的逻辑是：

    2ba374: ldr r9, [r4, #748]   ; mSelectedColor
    2ba378: cmp r9, #0
    2ba37c: bne 2b9ffc            ; != 0 才使用该颜色
    2ba380: b   2b9ff0            ; == 0 → 回落成 mTextColor（与普通项同色）

而构造函数里 `str r0, [r4, #748]` 写入的正是 0，于是"选中"这一状态在绘制时
被判为"没有独立颜色"，直接回落，导致整列表同色、看不出选的是哪一个。

补丁
----
把 0x2ba374 的 `ldr r9, [r4, #748]`（e59492ec）替换为 `mvn r9, #0`（e3e09000），
即选中行固定使用 0xFFFFFFFF（不透明白）。等长 4 字节替换，不改变文件大小与布局。

用法
----
    python es-gamelist-highlight.py emulationstation.orig  emulationstation.patched
    # 打补丁前会校验原指令，不匹配则拒绝执行（防止打错版本）

部署（设备上）
------------
    cp /opt/emuelec/bin/emulationstation /opt/emuelec/bin/emulationstation.bak-1028
    # 把打过补丁的文件覆盖回 /opt/emuelec/bin/emulationstation 并 chmod 755
    # 重启前端： kill ES/supervisor 后 /etc/init.d/S95emuelec start

回滚
----
    cp /opt/emuelec/bin/emulationstation.bak-1028 /opt/emuelec/bin/emulationstation
"""

import hashlib
import struct
import sys

# ELF 段映射：.text 的 vaddr -> 文件偏移
TEXT_VADDR = 0x0A5670
TEXT_OFF = 0x095670

PATCH_ADDR = 0x2BA374          # ldr r9, [r4, #748]
PATCH_ORIG = 0xE59492EC        # ldr r9, [r4, #748]  (mSelectedColor)
PATCH_NEW = 0xE3E09000         # mvn r9, #0  -> 0xFFFFFFFF (白, 不透明)


def addr_to_off(addr: int) -> int:
    return addr - TEXT_VADDR + TEXT_OFF


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    src, dst = sys.argv[1], sys.argv[2]

    data = bytearray(open(src, "rb").read())
    off = addr_to_off(PATCH_ADDR)

    if data[:4] != b"\x7fELF":
        print("拒绝：输入不是 ELF 文件")
        return 1

    cur = struct.unpack_from("<I", data, off)[0]
    if cur == PATCH_NEW:
        print("已经是打过补丁的版本，无需重复处理")
        return 0
    if cur != PATCH_ORIG:
        print("拒绝：0x%08x 处指令为 0x%08x，期望 0x%08x（版本不匹配）"
              % (PATCH_ADDR, cur, PATCH_ORIG))
        return 1

    struct.pack_into("<I", data, off, PATCH_NEW)
    open(dst, "wb").write(data)

    print("源文件  : %s  (%d 字节, md5 %s)" % (src, len(data), md5(open(src, "rb").read())))
    print("补丁文件: %s  (%d 字节, md5 %s)" % (dst, len(data), md5(bytes(data))))
    print("补丁点  : 0x%08x  vaddr 0x%08x  file off 0x%08x" % (PATCH_ADDR, PATCH_ADDR, off))
    print("替换    : ldr r9,[r4,#748] -> mvn r9,#0  (选中行 = 0xFFFFFFFF)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
