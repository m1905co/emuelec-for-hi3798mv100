#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
switch_probe.py —— 受控切换实验：
  1) 记录 p13(rootfs) 头 64K 的 md5（EmuELEC 若真启动并 rw 挂载，这里必变）
  2) 往 misc(p9) 写 product-test 并回读确认真的落到 flash
  3) reboot，然后每 2 秒探测 192.168.31.16 的 ICMP / 23 / 5555，画出时间线
  4) 回到 Android 后再次比对 p13 md5，判定 EmuELEC 到底有没有启动
"""
import hashlib
import os
import socket
import subprocess
import sys
import time

ADB = ["adb", "-s", "192.168.31.16:5555"]
IP = "192.168.31.16"
OUT = os.path.dirname(os.path.abspath(__file__))


def sh(cmd, timeout=60):
    p = subprocess.run(ADB + ["shell", cmd], capture_output=True, timeout=timeout)
    return p.stdout.decode("utf-8", "replace").strip()


def adb_up():
    try:
        return "device" in subprocess.run(ADB + ["get-state"], capture_output=True, timeout=6).stdout.decode()
    except Exception:
        return False


def port_open(port, t=1.0):
    s = socket.socket()
    s.settimeout(t)
    try:
        s.connect((IP, port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def ping(t=1):
    r = subprocess.run(["ping", "-n", "1", "-w", str(t * 1000), IP], capture_output=True)
    return r.returncode == 0


def p13_md5():
    # 用 busybox 在设备上算，避免再传 64K
    return sh("busybox dd if=/dev/block/mmcblk0p13 bs=65536 count=1 2>/dev/null | busybox md5sum")


def misc_show():
    return sh("busybox dd if=/dev/block/platform/hi_mci.1/by-name/misc bs=32 count=1 2>/dev/null | busybox hexdump -C | head -2")


def main():
    if not adb_up():
        print("!! adb 不在线，先 connect")
        subprocess.run(["adb", "connect", "192.168.31.16:5555"], capture_output=True)
        time.sleep(2)
        if not adb_up():
            print("!! 仍然连不上，退出")
            return 1

    print("=== 1) 切换前 p13 头 64K md5 ===")
    before = p13_md5()
    print("   ", before)

    print("=== 2) 写 misc=product-test 并回读 ===")
    print(sh("busybox printf '%-32s' 'product-test' | busybox dd of=/dev/block/platform/hi_mci.1/by-name/misc bs=32 count=1 conv=notrunc 2>&1; busybox sync; echo written"))
    print(misc_show())

    print("=== 3) reboot，开始探测（最多 300 秒）===")
    subprocess.run(ADB + ["shell", "reboot"], capture_output=True)
    t0 = time.time()
    timeline = []
    last = None
    while time.time() - t0 < 300:
        el = time.time() - t0
        p = ping(1)
        t23 = port_open(23, 0.6)
        t55 = port_open(5555, 0.6)
        state = (p, t23, t55)
        if state != last:
            timeline.append((round(el), state))
            print("  %6.1fs  ping=%-5s :23=%-5s :5555=%-5s" % (el, p, t23, t55))
            last = state
        if el > 40 and t55:
            break
        time.sleep(2)

    print("=== 4) 回来了，判定是什么系统 ===")
    for _ in range(10):
        if adb_up():
            break
        time.sleep(2)
    if adb_up():
        print("  adb 在线 → Android")
        print("  misc:", misc_show())
        after = p13_md5()
        print("=== 5) p13 头 64K md5（切换后）===")
        print("   ", after)
        print("   EmuELEC 是否真的挂载过 rootfs:", "是（变了）" if after != before else "否（一致）")
    else:
        print("  adb 不在线，试 telnet 23 判断：")
        print("   :23 =", port_open(23, 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
