# EmuELEC 救回 + 卡第一屏根因 + 启动耗时修复

日期：2026-10-16
结论：**盒子已完全救回**；卡第一屏的根因是我把 `rcS` 里的 `mount -a` 弄丢了；启动耗时 **58.65 s → 11.00 s**。

---

## 1. 根因（我的错，说清楚）

**原版 `/etc/init.d/rcS`**（备份 `rcS.a4bak`，257 B）第 2 行是：

```sh
#!/bin/sh

# Mount fs accroding to /etc/fstab
mount -a          ← 按 /etc/fstab 挂载 proc / sys / dev / tmp
```

我当初为了加"逐脚本计时"重写 rcS 时，**漏掉了 `mount -a` 这一行**（我部署的 612 B 版本 = 原版减掉 mount -a 再加上计时代码）。

由此产生的连锁反应，和你的现象完全对得上：

```
/proc 未挂载
  → /proc/cmdline 不存在、/proc/uptime 不存在、/proc/self/mountinfo 不存在
  → 启动守卫执行 awk /proc/self/mountinfo 失败
  → "HiSTB EmuELEC not started: /storage failed the authenticated p9 guard"
  → EmulationStation 永不启动
  → 屏幕上就是"卡第一屏"，而且没有网络
```

日志原文（串口抓到）：
```
awk: /proc/self/mountinfo: No such file or directory
HiSTB EmuELEC not started: /storage failed the authenticated p9 guard
```

## 2. 第二个真问题：备份文件被当成启动脚本执行

`rcS` 的循环是 `for initscript in /etc/init.d/S[0-9][0-9]*`，而我把备份放在同一目录：

- `S81histb-network.a4bak`（1989 B，旧的阻塞版）
- `S87wifi.a4bak`（789 B，旧的阻塞版）

**它们完全匹配这个通配符，所以每次开机都被执行一遍**。后果：

- 我"优化"过的新脚本跑完，紧跟又跑一遍旧脚本 → 那 16.4 s / 8.5 s 的窗口怎么改都不变（就是它自己）；
- 每次开机起**两个 wpa_supplicant** 抢同一张 wlan0 → WiFi 时好时坏、热重启后掉网。

> 教训：备份不能放在 `/etc/init.d/`，且不能以 `S` + 两位数字开头。

## 3. 抢救过程

| 步骤 | 做法 |
|---|---|
| 1 | TTL 串口（**COM3 / CH340 / 115200**）。脚本持续发 Ctrl+C，抢 U-Boot 的 3 s 自动引导窗口，不需要掐时间按键 |
| 2 | 在 `fastboot#` 提示符自动敲入安卓启动命令（参数取自 `env_android_switch.bin`），**不 saveenv、不写 flash**，板内启动项保持 EmuELEC 不变 |
| 3 | 安卓起来后走 adb（192.168.31.18），挂载 p13（= EmuELEC rootfs） |
| 4 | 删掉两个 `.a4bak`；`cp rcS.a4bak rcS` 还原 rcS；sync + umount |
| 5 | 重启，串口全程录制，验证 |

安卓启动命令（备用，记录在此）：
```
setenv bootargs coherent_pool=2M console=ttyAMA0,115200 blkdevparts=mmcblk0:1M(fastboot),4M(bootargs),16M(recovery),1M(deviceinfo),4M(baseparam),4M(pqparam),4M(logo),16M(fastplay),8M(misc),24M(factory),12M(kernel),8M(iptv_data),340M(backup),340M(cache),520M(system),-(userdata) mem=1G mmz=ddr,0,0,400M
mmc read 0 0x10000000 0x29000 0x6000
mmc read 0 0x11000000 0x23000 0x400
bootm 0x10000800 0x11000000
```

## 4. 实测结果

时间线（秒，自内核启动，由板内插桩记录）：

| 阶段 | 修复前 | 修复后 |
|---|---|---|
| 内核 → init | 3.26 | 3.31 |
| 网络阶段 | **24.9**（16.4 + 8.5） | **1.3** |
| 等手柄 | 30.2 | 6.05 |
| **EmulationStation 启动** | **58.65** | **11.00** |

其余验证：

- 守卫报错消失，`HiSTB EmuELEC supervisor started as PID 1842/1843`
- `ps` 可见 `/opt/emuelec/bin/emulationstation` 在跑
- wlan0 拿到 `192.168.31.18`，SSH(22)/telnet(23) 均可用
- **系统内热重启复测通过**：WiFi 重新 `assoc success`、ES 正常起来 —— 之前"重启后掉网"一并解决
- 内存：总 747 MB / 已用 94 MB

## 5. 产物与证据

```
E:\A4-work\emuelec\work\
├── serial\
│   ├── serial_rescue.py       # 抢 U-Boot 窗口 + 引导安卓
│   ├── serial_listen.py       # 纯监听
│   ├── serial_cmd.py          # 批量发命令
│   ├── serial_bootwatch.py    # 发 reboot 并录全程
│   ├── console.log            # 抢救当次完整串口记录
│   └── diag*.log              # 诊断命令记录
├── evidence\
│   ├── boot-timeline.log.after
│   ├── supervisor.log.after
│   ├── es_log.txt.after
│   └── boot2.log / boot3.log  # 两次启动的串口全文
└── rcS.restored.good          # 修复后的 rcS 存档（md5 99c2c89a5909514f895bc0eeb0c6cb95）
```

## 6. 未做 / 待你决定

1. **在设备上验证改过的 U-Boot**：这一步要刷 p1。当前 `fastboot-burn.bin` 是**验证件**
   （缺 product 库，248 KB vs 官方 539 KB，无 logo/keyled/adp 初始化），
   **我不建议拿它去刷**。两条路：
   - A（稳）：先用完整 SDK 出正式包（需要补 `source/common`、`source/boot/product` 与工具链），再刷；
   - B（快）：直接刷这份验证件，接受"没有启动 logo"等副作用与变砖风险（变砖要靠 HiTool USB 救）。
2. **设备上仍有测试插桩**：`/etc/init.d/S00a4bootmark|S86a4mark|S88a4mark|S94a4mark`，以及 supervisor 里的 `a4_mark`。
   按你"验证完的脚本下设备"的习惯本应清掉——**但我这次不擅自再动**，你说了我再清。
3. 「等手柄」还有 6.05 s（原 30 s）。想更快可以降到 2–3 s，代价是慢速手柄可能来不及枚举。
