# 18 · EmuELEC 启动耗时分析与优化（进行中）

**日期**：2026-10-15
**问题**：用户反馈"EmuELEC 启动时间比 Android 还长"
**方法**：`/proc/uptime`（单调、不受 RTC 未设置影响）在各启动阶段插桩，用**数据**定位而不是猜

---

## 1. 基线测量（改造前，一次真实启动）

| 时间点（秒，自内核启动） | 事件 | 该阶段耗时 |
|---|---|---|
| 3.23 | `init-start`（rcS 第一个脚本） | 内核→init：**3.2 s** |
| 19.63 | `pre-network`（S00…S82 之后） | **16.4 s** |
| 28.12 | `post-network`（S87wifi 之后） | **8.5 s** |
| 28.37 | `pre-frontend`（S89…S94） | 0.25 s |
| 28.43 | `supervisor-start` | 0.06 s |
| 58.64 | `input-wait-done` | **30.2 s** ← 没插手柄，等满 30 s 超时 |
| **58.65** | **`frontend-exec`：ES 启动** | 合计 **58.65 s** |

**结论：内核不慢（3.2 s 就交到 init）。慢在用户态串行 init 的三个阻塞点。**

对照：同一台机器 Android 冷启动到可用 ≈ 30–40 s。

---

## 2. 三个阻塞点与修复

### 2.1 等手柄 30 秒（**已修复，实测省 24 s**）

- 机制：supervisor 在启动 ES 前等 `/dev/input/event*`，因为 **ES 只在启动时枚举一次输入设备、不支持热插拔重扫**。
- 问题：**手柄没插时，等满 30 s 超时**（日志证据：`HiSTB no input device after 30s; starting frontend anyway`）。
- 修复：默认 30 s → **6 s**（USB HID 枚举 1–3 s 内就完成；晚到的手柄由 `/usr/bin/a4-inputwatch` 自动重启前端兜底）。
- **实测**：`input-wait-done` 出现在 34.66 s，输入等待 = 6.05 s（原 30.2 s）→ **省 24.1 s**，总时长 58.65 → 34.66 s。

### 2.2 eth0 拿不到 DHCP 仍然硬重试 15 秒（**脚本已修，启动级验证待补**）

`/etc/init.d/S81histb-network`：本机**没插网线**（`/sys/class/net/eth0/carrier` = 0），却执行 `udhcpc -i eth0 -q -n -t 5 -T 3` → 5 次 × 3 s = **15 s 纯等待**，而 rcS 是**串行**的，后面所有脚本（含游戏前端）都被拖住。
修复：DHCP 前检查 carrier，无载波直接跳过（接口保持 up，插网线后可再配）；eth0 出现等待 10 s → 3 s；有载波时重试预算 `-t 5 -T 3` → `-t 3 -T 2`。
**脚本级验证**：手动执行 `S81histb-network` = **0.03 s**（修复前会 15 s）。

### 2.3 WiFi 初始化阻塞整个启动（**脚本已修，启动级验证待补**）

`/etc/init.d/S87wifi`：`sleep 5` + 最长 20 s 等 wlan0 + 阻塞 DHCP，全部在**前台**跑。WiFi 对游戏前端启动毫无必要。
修复：整段 bring-up 放进 `( … ) &` 后台执行，脚本立即返回。
**脚本级验证**：手动执行 `S87wifi` = **0.01 s**（原 ~8.5 s）。

---

## 3. 未结项：还有约 25 秒没归属到具体脚本（**需要再一次插桩启动**）

改造后启动：`3.26 → 19.67 → 28.30 → 28.55 → 28.61 → 34.66`。

**异常点**：两个网络阶段的窗口长度（16.4 s / 8.5 s）在改造前后**几乎完全相同**（差 <0.15 s），而这两个脚本单独执行只要 0.03 s / 0.01 s。

⇒ 说明那 25 秒**不是这两个脚本体内的等待**，而是别的机制，例如：
- `S01udev` 的 `udevadm trigger` 在启动时触发**coldplug 风暴**（本机所有驱动其实都编译进内核、/dev 是 devtmpfs，coldplug 基本没必要），把 CPU/IO 打满，导致其后的每个 `sh` 脚本调用都变慢；
- 或某个初始化阶段的 IO 等待（eMMC / TF 卡）。

**已备好的下一步工具**：`emuelec/work/bootopt/rcS.timed` —— 给 rcS 加**逐脚本计时**（每个脚本前后各记一次 `/proc/uptime`，写入 `boot-timeline.log`），一次启动即可指认真凶。

---

## 4. 插桩说明（保留可用，开销 ~5 ms/次）

| 文件 | 作用 |
|---|---|
| `/etc/init.d/S00a4bootmark` | 截断并写入 `init-start` |
| `/etc/init.d/S86a4mark` / `S88a4mark` / `S94a4mark` | 网络段前后、前端前 |
| `/usr/bin/histb-emuelec-supervisor` | 增加 `a4_mark`：supervisor-start / input-wait-done / frontend-exec / health-window-passed |
| 日志 | `/storage/ee/logs/boot-timeline.log`（每次启动重写） |

---

## 5. 本轮改动清单与回滚

| 文件 | 改动 | md5 | 回滚 |
|---|---|---|---|
| `/etc/init.d/S81histb-network` | 无载波跳过 DHCP；等待 10→3 s | `5bf6f67240be4d9c67c25c46b7b92f74` | `cp /etc/init.d/S81histb-network.a4bak …` |
| `/etc/init.d/S87wifi` | 整段后台化 | `63f14e8cf2a4200fe85470a1a08185a1` | `cp /etc/init.d/S87wifi.a4bak …` |
| `/usr/bin/histb-emuelec-supervisor` | 等手柄 30→6 s + 计时标记 | `fd0225ef9a46a1822d995817862c4a83` | `.a4bak5`（v3）/`.a4bak4`（v2）/`.a4bak3`（v1）/`.a4bak`（原版） |

本地副本：`emuelec/work/bootopt/{S81histb-network.fixed,S87wifi.fixed}`、`emuelec/work/histb-emuelec-supervisor.v4`。

---

## 6. 事故记录（如实）

为定位那 25 秒，我在运行中的系统上**逐个手动执行了 init 脚本**做计时。其中手动执行 `S87wifi` 会**再起一个 wpa_supplicant 实例**，把盒子的 WiFi 弄掉了线 —— 结果：盒子 ping 有应答但 **22/23/5555 全关**，全网段扫描找不到，TTL 串口也未连接（本机无 COM 口）。
**需要用户断电重启盒子**（或用手柄在 ES 菜单选"重启系统"——该功能已在 report/17 修好且验证过）。重启后 WiFi 恢复正常。
**教训**：定位启动耗时应该用"加插桩 + 重启"的方式，**不要在运行系统上直接重跑 init 脚本来计时**（副作用不可控）。

---

## 7. 追加（2026-10-15 深夜）：发现"热重启后 WiFi 掉线"这一独立缺陷

### 7.1 现象与证据

在运行系统上执行 `reboot -f` 后，盒子表现为：

| 检查 | 结果 |
|---|---|
| `ping 192.168.31.18` | 有应答（**但见下条**） |
| 22 / 23 / 5555 端口 | **全关** |
| ARP（强制刷新后 ping） | `192.168.31.18 = 00-00-00-00-00-00` **Unreachable** |
| 全网段扫描（.2–.254 × 22/23/5555） | **0 个主机** |

⇒ 结论：**.18 上的应答不是本机**，盒子此时**根本没有拿到 IP** —— 即 **wlan0 没有起来**；前端本身是好的（用户屏上能看到系统）。

**这与用户最早抱怨的"系统内重启后黑屏、要断电"很可能是同源问题的一部分**：report/17 修好了"重启请求没人执行"（`/var/lock`），但**热重启后网络/外设的再初始化不可靠**仍然存在。

### 7.2 机理假设（有依据，待下一次启动验证）

我此前把 S87wifi 的 bring-up 改成 `( … ) &` 后台执行 —— 这个子 shell **仍与 rcS 同进程组**，rcS 退出/被回收时可能被连带清理，导致 WiFi 半途夭折。证据：改动前"前台串行"时 WiFi 从不失败；改动后**热重启多次出现 wlan0 缺失**（冷启动总是正常）——符合"后台子进程被带走 + 依赖一次性成功"的特征。

### 7.3 修复 v2（已备好，待部署验证）

| 文件 | 内容 |
|---|---|
| `/usr/bin/a4-wifi-up` | **脱离会话 + 自愈重试**：用 `setsid` 起独立 session/进程组；最多 8 轮（每轮 10 s）重试 `insmod → ip link up → wpa_supplicant → udhcpc`，直到 `ifconfig wlan0` 出现 `inet addr`；全过程写 `/storage/ee/logs/wifi-boot.log`（含 uptime 时间戳），失败也能事后诊断 |
| `/etc/init.d/S87wifi`（v2） | 瘦身为一行：`setsid /usr/bin/a4-wifi-up &`（无 setsid 时退化）；**不再阻塞启动** |

本地文件：`emuelec/work/bootopt/a4-wifi-up`、`emuelec/work/bootopt/S87wifi.v2`。

### 7.4 待办（按顺序）

1. 冷启动后读取**逐脚本计时**（`rcS.timed` 已安装，本次启动会自动产出 `boot-timeline.log` 的逐脚本行）→ 定位那 ~25 s 究竟落在哪个脚本或哪段间隙。
2. 同一次启动抓 `dmesg`（内核时间戳与 `/proc/uptime` 同一时基）→ 与用户态标记对齐，看是否有内核侧事件（USB/WiFi 固件加载、eMMC）与之对应。
3. 部署 7.3 的 WiFi v2，然后**专门做一次热重启测试**（`boot-timeline.log` + `wifi-boot.log` 会留下证据）。
4. 若确认热重启后外设再初始化不可靠，考虑把"重启"改为**看门狗硬复位**（本机有 SP805 watchdog，`/dev/watchdog0`；硬复位对 USB PHY/SoC 外设的复位比软 reboot 更彻底），并统一用到 ES 菜单重启与双系统切换路径上。
