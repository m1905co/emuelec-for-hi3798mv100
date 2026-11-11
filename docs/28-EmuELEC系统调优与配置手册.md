# 28 - EmuELEC 系统调优与配置手册（2026-10-28）

> 本文档记录本轮对 EmuELEC 侧的排查与改造，所有结论都基于设备实测（命令输出 / 日志 / 帧率读数），不写"应该没问题"。
> 目标：让**按键、显示、性能、音频、WiFi**五件事都有明确入口、可自己改、可回滚。

---

## 0. 一句话结论

| 问题 | 根因 | 现状 |
|---|---|---|
| 一手柄控两人 / 投币翻倍 | `player2` 默认 index 与 `player1` 相同（都是同一个 jsN） | 已修：按物理手柄顺序分配 P1~P4 |
| 按 LB+Start 退不出 | `player1` 被绑到了 uinput 遥控上，热键只对 P1 设备生效 | 已修：joymap 保证 P1=实体手柄；两把手柄热键统一为 LB |
| 按键错位（A/B、X/Y） | EmuELEC 自带 X360 映射是反向的（a=1 b=0 x=3 y=2） | 已改为 a=0 b=1 x=2 y=3 |
| 声音断续/"卡顿来自声音" | 音频缓冲长期只有 100~250 帧（2~5ms），多次掉到 0（饥饿） | 已修：`alsathread`，缓冲稳定 2304~3072/3072 |
| 画面顿 | HDMI 输出固定 `1080P50`，NeoGeo 59.19Hz 被压到 50 | 仅定位，未解（驱动层固定，见 §4） |
| 600MHz 是否可用 | 600MHz 实测 47fps（<50 上限） | 可自行切换，见 §5 |
| WiFi 凭据找不到 | 凭据写死在 `/opt/wifi/wpa_supplicant.conf`，且 `emuelec.conf` 的 `wifi.ssid/key` **根本不生效** | 已改为 `/storage/.config/emuelec/configs/wifi.conf` |

---

## 1. 按键

### 1.1 玩家端口（多手柄分离）

**为什么要动态分配**：`jsN` 编号取决于设备注册顺序 —— 冷启动时 USB 手柄可能先拿到 `js0`，热插拔后又是别的号；`A4 IR Remote` 是 a4-ird 造的 uinput 虚拟手柄，也会随时插进来占号。

**实现**：`/opt/emuelec/bin/a4-joymap.sh`（已挂在 `run-retroarch.sh` 第 121 行，位于 `echo "HiSTB controller database path..."` 之前）。

```
规则：
  第 1 支实体手柄 → player1_joypad_index = 它的 jsN
  第 2 支          → player2
  第 3/4 支        → player3/4
  没有对应设备      → 写「手柄数+1」（不存在的 index，等于该玩家禁用）
  A4 IR Remote     → 永远排除，不占玩家位
```

**★ 踩过的坑**：禁用值**不能写成 99 这种大数**。RetroArch 会按这个 index 去取设备数组，越界会让 sdl2 joypad 驱动**直接段错误**（实测退出码 139，连续两次复现）。改成「手柄数+1」这种贴近范围的小值即正常。

实测（单手柄）：`ZhiXu=js0`、`Remote=js1` → `player1=0`、`player2/3/4=2`，游戏正常启动（PID 2951）。

### 1.2 输入设备的枚举时机（为什么插手柄要"重启一下"）

**ES（SDL2）只在启动时枚举一次 `/dev/input`，永不重扫。**
`/etc/init.d/S94a4-ird` 头部注释原文：`EmulationStation enumerates input devices once, at start-up, and never rescans.`
另一个实证：用 uinput 虚拟手柄在 ES 运行中注入，ES 完全看不到；只有"先建设备、再启 ES"才生效。

推论与现状：

| 场景 | 结果 |
|---|---|
| 冷启动前插好手柄 | 正常识别 |
| ES 运行中插手柄 | 由 `/storage/a4-hotplug`（`S96a4-inputrecover` 拉起，inotify + 800ms 防抖）检测到 → **杀掉 ES 让它重启一次**，重启后就认到 |
| ES 运行中拔手柄 | 只记录 `removal only, no restart needed`；若 ES 仍持有该设备的 fd，才额外重启一次 |
| 游戏运行中（ES 不在） | `no frontend running, nothing to do` —— 不打断游戏；退出游戏回 ES 时自然重新枚举 |
| 反复快速插拔 | `%d restarts within %d s, backing off` 退避，避免 ES 被反复杀 |

日志：`/storage/ee/logs/a4-hotplug.log`（实测片段见 report/30 §4.4.2）。

**手动兜底**：`/etc/init.d/S96a4-inputrecover restart` → `/etc/init.d/S95emuelec restart` → `reboot`。

### 1.3 「遥控」= a4-ird 造的 uinput 虚拟手柄

这块板 EmuELEC 内核是 `CFG_HI_IR_TYPE_S2`，红外驱动只吐 `/dev/hi_ir` 原始码、**不注册 input 设备**，
所以遥控在 ES 里原本无效。`S94a4-ird` + `/storage/a4-ird` 解绑原驱动、直接按 NEC 时序采样 `IR_DATAL`，
把按键注入 uinput 虚拟手柄 `A4 IR Remote`（GUID `030000004d0a00000100000000010000`，
与 `es_input.cfg` 对应）——**必须在 S95emuelec 之前启动**，否则 ES 枚举时它还不存在。

因此 `jsN` 里同时有"遥控"和"实体手柄"两种：`a4-joymap` 永远排除 `A4 IR Remote`，
它只用于 ES 菜单导航，不占玩家位。映射表 `/storage/.config/a4-ir/keys.map`，日志 `/storage/ird.log`。

### 1.4 按键表

| 操作 | 按键 | 说明 |
|---|---|---|
| 投币 | **Select / Back**（X360=btn6，ZhiXu=btn10） | 单按，只投 P1 |
| 退出游戏 | **按住 LB + 按 Start** | X360: LB=4 + Start=7；ZhiXu: LB=6 + Start=11 |
| 呼出 RetroArch 菜单 | 按住 LB + 按 Select | 同上 |
| 存档 / 读档 | 未绑定（避免与热键冲突） | 需要时在菜单里做 |

**★ 热键只能绑按钮，不能绑轴**：`input_enable_hotkey_axis` 不是合法配置项。ES 里给 X360 配的 `hotkeyenable` 是 `type="axis" id="5"`（右扳机），所以之前 `RT+Start` 从原理上就不可能生效。

### 1.5 映射文件在哪个目录

```
/opt/emuelec/share/retroarch/autoconfig/sdl2/     ← 真正被读取的目录（86 个 .cfg）
/storage/.config/retroarch/autoconfig/            ← 不起作用（别改这里）
```

已修改：
- `Microsoft X-Box 360 pad.cfg`：a=0 b=1 x=2 y=3，L=4 R=5 select=6 start=7 L3=9 R3=10，hotkey=4（原版备份 `.orig`）
- `ZhiXu Gamepad.cfg`：`input_enable_hotkey_btn` 9 → **6（LB）**（原版备份 `.orig-1028`）

---

## 2. 音频（"卡顿来自声音"的真因）

### 2.1 定位过程

```
配置：audio_driver = alsa, audio_out_rate = 48000, 无 audio_latency（默认 64ms）
hw_params：period_size=768, buffer_size=3072（64ms）
```

连续采样 `/proc/asound/card0/pcm0p/sub0/status` 的 `delay`（缓冲中待播帧数）：

| 阶段 | delay 采样 | 含义 |
|---|---|---|
| 修复前（alsa） | 138 / 106 / 837 / 248 / 209 / ... / **0** | 只有 2~5ms 余量，**多次掉到 0**＝DMA 跑空 |
| 修复后（alsathread） | 2304 / 3072 / 3072 / 2304 / 3072 ...（8 次） | 保持 75%~100% 满，**零次掉到 0** |

补充：HDMI 侧 `Audio FIFO Underflow: 0`、`dmesg` 无 AIAO 报错 —— 说明不是硬件/驱动报错，就是**应用层喂不饱缓冲**。

### 2.2 修复

```
/opt/emuelec/etc/retroarch.cfg
    audio_driver  = "alsathread"     ← 关键：音频写入独立线程
    audio_latency = "128"
```

`alsathread` 把音频写入从主循环剥离，主循环偶尔迟到也不会让 DMA 跑空 —— 这正是弱 SoC 上声音断续的标准解法。

代价：音频比画面晚约 48~64ms（街机游戏无所谓）。

---

## 3. 显示

`/proc/hisi/msp/disp1` → `Formt/DispMode : 1080P50`、`Out Timing 2640x1125 p`。

NeoGeo 原生 59.19Hz、CPS 59.63Hz → 被压到 50fps（RetroArch OSD 实测 `FPS: 50.00`）。

**试过但无效**（都记录了，避免重复踩）：

| 尝试 | 结果 |
|---|---|
| `/storage/.config/EE_VIDEO_MODE` = `1080P60` | 无效，disp 仍 50Hz |
| `emuelec.conf` → `global.videomode=1080P60` | 无效 |
| 同上改成 `1080p60hz` | 无效 |
| `/sys/class/graphics/fb0/mode` | 空文件 |
| `/sys/class/graphics/fb0/modes` | 只有 `U:0x0p-0` |
| 命令行工具（hifb/disp/hdmi） | 系统里没有 |
| `hi_fb` 模块参数 `video` | 值为 `(null)`，且模块在启动时已加载，参数只读 |

**结论**：时序在**驱动初始化时固定**，用户态改不动。要改只能动内核启动参数（U-Boot mode2 cmdline 加 `hi_fb.video=...`），格式未验证、有风险，暂未执行。

注：这个限制只影响帧率上限（50fps），不影响可玩性；用户已确认 47fps 也能接受。

---

## 4. CPU / GPU 频率

### 4.1 CPU（可自定义，已交付）

四档：**600 / 1000 / 1200 / 1500 MHz**（`scaling_available_frequencies`）。实测电压：600M=1040mV / 1.0G=1140mV / 1.2G=1270mV；`performance` 会拉 1495mV（1.5G 档）但频率只跑 1.2G，已废弃。

**温度实测（同一台机器，游戏负载）**：

| 上限 | 稳态温度 | 帧率（NeoGeo） |
|---|---|---|
| 原厂 `performance` / 1495mV | **82 °C** | — |
| **1.0GHz（默认）** | **63 °C（−19 °C）** | 50 fps（撞 50Hz 上限） |
| 600MHz | 54 °C | 47 fps |

> 注意：EmuELEC 侧 `/proc/hisi/msp/pm_cpu` 是 `-r--r--r--`（**只读**），
> 所以这里**没有降压**，只有频率挡位。降压只在安卓侧可做（见 report/30 §3.5）。
> 600MHz 的 47fps 是可接受档位（街机原生 50~60Hz，47fps 体感差别小），
> 换来的 9 °C 温降是实打实的——别当成"不可用"。

**配置文件**（可手动编辑，下次开机生效）：
```
/storage/.config/emuelec/configs/a4-perf.conf
    MAX_FREQ=1000000
    GOVERNOR=ondemand
```

**命令行**（立即生效，同时写回配置）：
```sh
a4-perf show          # 看当前频率/电压/温度/上限 + GPU 状态
a4-perf 600           # 上限 600MHz（实测 47fps，功耗温度最低）
a4-perf 1000          # 默认
a4-perf 1200
a4-perf 1500          # 玩大游戏临时拉满（温度会明显上升）
a4-perf auto          # 回到 ondemand + 配置里的上限
```

**开机生效**：`/etc/init.d/S97a4-cpufreq` 读同一份 a4-perf.conf，在 S95 之后延迟 6 秒套用（躲开 EmuELEC 的 `global.maxperf`）。

实测（冷启动）：`gov=ondemand`、`max=1000000`、空闲 `600MHz / 1030mV / 52°C`。

### 4.2 GPU：**被驱动了**，只负责"放大 + 合成"

#### 4.2.1 驱动确实加载了（四条证据）

| 证据 | 内容 |
|---|---|
| 内核日志 | `dmesg` → `Mali: Mali device driver loaded` |
| 设备节点 | `/dev/mali`（字符设备 `10,58`） |
| 库 | `/usr/lib/libMali.so` 1 109 900 B；`libEGL.so.1.4 → libMali.so`、`libGLESv2.so.2.0 → libMali.so` |
| 进程映射 | `EmulationStation` 与 `retroarch` 的 `/proc/<pid>/maps` 里都有 `/usr/lib/libMali.so` |

`libMali.so` 内含 `Mali-400 MP` / `Mali-450 MP`、`OpenGL ES 2.0`、`GLSL ES 1.00`（无 ES3）。

#### 4.2.2 渲染路径是 GL，不是软件

```
/opt/emuelec/etc/retroarch.cfg
    video_driver         = "gl"
    video_context_driver = "fbdev_mali"     ← 海思定制 context，直接渲染到 fb0
```

`retroarch` 二进制里能查到 `fbdev_mali` 与 `ARM Mali-4xx` 字符串。
**实测把 `video_driver` 改成 `sdl2` → RetroArch 直接段错误（退出码 139）**
⇒ 这个构建只有 `gl + fbdev_mali` 这一条可用渲染路径，不存在"退回软件渲染"的选项。

#### 4.2.3 它到底在干什么（实测采样 `/proc/hisi/msp/pm_gpu`）

| 场景 | Frequency | GP_util | PP_util | Power |
|---|---|---|---|---|
| 无图形进程（纯空闲） | 0 kHz | 0% | 0% | **power down** |
| ES 静止在列表（不重绘） | 200 MHz | 0% | **0%** | power up |
| ES 滚动菜单（按键连发） | 200 MHz | 1~2% | **27~34%** | power up |
| 游戏中（Metal Slug / FBNeo） | 200 MHz | 1~2% | **31~37%** | power up |

同一时刻 CPU（retroarch）占用：**220~232 jiffies / 3 s ≈ 单核 73~77%**。

**结论（GPU 干的活）**：

1. **每帧全屏放大**：核心输出 320×224 的帧缓冲，用 GL 纹理做最近邻放大到 1920×1080，
   50 fps ⇒ `PP`（像素流水）30% 左右就是这块填充；`GP`（几何）只有 1~2%，因为只是两个三角形。
2. **合成 OSD/菜单**：fps 文字、菜单、ES 界面文字图片都是 GL 纹理，ES 按键滚动时 PP 27~34%。
3. **不参与**：视频硬解（那是 VDEC 硬件块）、音频、模拟器逻辑（FBNeo 是纯 CPU 模拟，
   画面先在内存里画好，再交给 GL 放大）。没有配 shader，也没有用 GPU 做计算。

#### 4.2.4 为什么"调 GPU 频率"没有意义

```
/proc/hisi/msp/pm_gpu        -r--r--r--     只读
  DVFS_enable : enable      但实测永远 200 MHz，从不升频
  AVS_enable  : disable
/sys/class/devfreq/          不存在
/sys/devices/platform/soc/f9200000.gpu/   只有 driver_override / uevent 可写
```

- PP 只有 30%、频率从未升过 ⇒ **GPU 余量很大，不是瓶颈**，超频不会提帧率。
- `pm_gpu` 的 `volt=` / `freq=` / `dvfs` 写入全是 no-op（只有 `avs on/off` 生效）。
- 想通过 GPU 这条线降温，只能动 **core 域**（喂 GPU/VPU/VPSS/DDR 的那一路），
  安卓侧实测 core 1060→1000 mV = **−2.3 °C**（见 report/30 §3.5）。
- EmuELEC 这边 `pm_core` 同样是 `-r--r--r--`，所以**在这里连 core 也改不了**，只能调 CPU 频率。

---

## 5. WiFi（已做成可编辑配置）

### 5.1 真相

EmuELEC 的 WiFi **完全不读** `emuelec.conf` 的 `wifi.ssid / wifi.key`。链路是：

```
/etc/init.d/S87wifi
    → insmod rtl8188eu.ko            （USB RTL8188EU）
    → /opt/wifi/bin/wpa_supplicant -c /opt/wifi/wpa_supplicant.conf
    → udhcpc
```

所以以前改 `emuelec.conf` 是**无效操作**（我之前的改动属于这一类）。

### 5.2 现在的配置项（唯一入口）

```
/storage/.config/emuelec/configs/wifi.conf
    SSID=PandoraBox
    PSK=你的密码
    # HIDDEN=1        (可选，隐藏 SSID)
```

`S87wifi` 每次启动据此**重新生成** `/opt/wifi/wpa_supplicant.conf`（原文件首次会备份为 `.orig`）；`wifi.conf` 不存在或为空则沿用原文件，向后兼容。

### 5.3 手动操作与日志

```sh
/etc/init.d/S87wifi status     # 看 IP / 关联状态 / 配置 / 最近日志
/etc/init.d/S87wifi restart    # 改完 wifi.conf 后重连（前台，能看过程）
```

日志：`/storage/ee/logs/wifi.log`（每次启动重写）、`/storage/ee/logs/wpa_supplicant.log`

失败时会额外记录：`wlan0` 是否出现、扫描到的周边 AP 列表、supplicant 尾部日志 —— 下次再断网能直接定位到哪一步。

### 5.4 冷启动实测

```
4.96 wifi: start
4.99 cfg: generated from wifi.conf ssid=PandoraBox hidden=0
5.11 wifi: insmod rc=17 (attempt 1)          ← 17=已加载，正常
5.11 wifi: wlan0 present after 0s
6.96 wifi: supplicant rc=0
9.00 wifi: associated after 2s
11.70 wifi: OK ip=192.168.31.16
```

关于"上次为什么没连上"：当时脚本**失败静默退出、不留日志**，原始证据已不可追溯；现在所有分支都有日志，同类问题可定位。两次冷启动（含 `restart`）均成功。

---

## 6. 改动清单与回滚

| 文件 | 改动 | 备份 |
|---|---|---|
| `/etc/init.d/S87wifi` | 重写：读 wifi.conf、生成 supplicant、日志、重试、支持 restart/status | `S87wifi.bak-1028` |
| `/etc/init.d/S97a4-cpufreq` | 改为读 a4-perf.conf | `S97a4-cpufreq.bak-1021` |
| `/usr/bin/a4-perf` | 新增：频率档位切换 | — |
| `/opt/emuelec/bin/a4-joymap.sh` | 新增：玩家端口动态分配 | `a4-joymap.sh.off`（中间版本） |
| `/opt/emuelec/bin/run-retroarch.sh` | 第 121 行插入 joymap 调用 | `run-retroarch.sh.bak-1028` |
| `/opt/emuelec/etc/retroarch.cfg` | audio_driver=alsathread、audio_latency=128、播放器端口、热键、fps_show=true | `retroarch.cfg.bak-1021b` |
| `/opt/emuelec/share/retroarch/autoconfig/sdl2/Microsoft X-Box 360 pad.cfg` | a/b/x/y 修正 + hotkey | `.orig` |
| `/opt/emuelec/share/retroarch/autoconfig/sdl2/ZhiXu Gamepad.cfg` | hotkey 9→6 | `.orig-1028` |
| `/storage/.config/emuelec/configs/wifi.conf` | 新增 WiFi 配置项 | — |
| `/storage/.config/emuelec/configs/a4-perf.conf` | 新增 CPU 配置项 | — |

**整体回滚**（把 EmuELEC 恢复成本次改动前）：把上面每个 `.bak-*` / `.orig*` 覆盖回原名即可；`fps_show` 可单独 `sed -i '/^fps_show/d'`。

---

## 7. 仍需你按一下确认的

| 项 | 怎么判定 |
|---|---|
| 投币只加 1 | 按 Select，看 `CREDIT` 从 00 → **01**（不是 02） |
| LB+Start 退出 | 按住 LB 再按 Start，应直接回到 ES |
| A/B、X/Y 是否顺手 | 按 A 应是"确认"，按 B 是"取消"；若反了告诉我，我换回来 |

这三项只能靠物理按键验证，我这边已把配置和端口绑定都验证到"逻辑正确"（P1=实体手柄、映射文件按你的 ES 配置对齐）。

---

## 8. 附：游戏列表"全是蓝色看不出选中"与 ROM 完整性（2026-10-28 晚）

### 8.1 现象与真相

用户反馈"游戏选择界面全是蓝色，看不到选了哪个"。抓 `fb0` 实测：

- 列表 10 个条目**全部是纯蓝 `(0,0,224)` 居中文字**，没有选中条、没有高亮；
- 注入 `A` 进入列表后，再注入两次 `下移`，**两帧截图逐像素完全相同**（diff = 0）。
  ⇒ 这个列表控件**根本没有绘制"当前选中项"**（选中色与普通文字同色，且不画 selector）。

### 8.2 为什么改主题没用（已穷举）

| 尝试 | 结果 |
|---|---|
| 改 `/opt/emuelec/share/emulationstation/themes/HiSTB-EmuELEC-carbon/carbon.xml` 的 `selectorColor/selectedColor` | 无效（10-21 试过，用户确认"找不到差异"） |
| 改 `/storage/ee/config/.emulationstation/themes/.../carbon.xml`（真正被 ES 看到的目录） | 无效 |
| 建 `/storage/ee/config/themes` → 指向主题目录（软链接） | ES 不解析 |
| 建**真实**目录 `/storage/ee/config/themes/a4test` + 最小 theme.xml，`ThemeSet=a4test` | ES 不解析 |
| 同上放 `/storage/ee/config/.emulationstation/themes/a4test` | 不解析 |
| 同上放 `/storage/.config/emulationstation/themes/a4test` | 不解析 |
| `--debug` 日志里搜 `theme` | **0 命中**（只有 `:/frame.png`、`ubuntu_condensed.ttf` 这类内置资源） |

**结论：这个 HiSTB 版 ES 的主题加载功能被裁剪掉了**，永远只用内置 UI。主题目录里那些 `HiSTB-EmuELEC-carbon.new.<pid>` 垃圾软链接，就是主题更新机制反复失败留下的证据。

### 8.3 可选方案（未执行，需确认）

| 方案 | 说明 | 风险 |
|---|---|---|
| A. 打补丁改 ES 二进制里的默认颜色常量 | 只能改文字色，**不会凭空生成选中条**；需先定位 .rodata 里的 ARGB 常量，可能要试错多次 | 中高（改坏=前端起不来，需备份） |
| B. 保持现状 | 靠"数第几个"盲选 | 无 |
| C. 换启动方式 | 直接用 RetroArch 菜单选游戏（它有正常高亮） | 无，但操作路径变了 |

ES 的**菜单/对话框**（如 OPTIONS）是有选中条的（截图可证），只有游戏列表这个控件没有。

### 8.4 ROM 完整性（已修 2 个）

用户下载的包 `E:/BaiduNetdiskDownload/FBNEO neogeo`：**392 个 zip / 4.0 GB**，是 NeoGeo 向的 FBNeo 包。

本地校验发现两个 zip 本身是残缺的（不是传输问题）：

| ROM | 缺什么 | 补法 | 实测 |
|---|---|---|---|
| `mslug3.zip` | `256-m1.m1` + `256-v1..v4.v4`（5 个音频 ROM） | 从 `mslug3fd.zip` 抽取合并 → 76.7 MB | ✅ 已实测进游戏（Metal Slug 3 标题 + INSERT COIN） |
| `mslug4.zip` | `263-p1.p1` + `263-p2.sp2`（程序 ROM） | 从 `mslug4fd.zip` 抽取合并 → 60.5 MB | ✅ 已实测进游戏（Metal Slug 4 标题 + INSERT COIN） |

补好的文件在本地 `emuelec/work/romfix/`，设备上已替换 `mslug3.zip` / `mslug4.zip`。

### 8.5 这份包里没有的游戏（不是漏拷）

| 游戏 | 原因 |
|---|---|
| 恐龙快打（dino） | **CPS1 系统**，整包一个 CPS1 游戏都没有（`dino/punisher/ffight` 全 0 命中） |
| 三国战记（kov/kov2） | **PGM 系统**，整包也没有（连 `pgm.zip` BIOS 都没有） |
| 合金弹头 6 | FBNeo 无原生支持（属 PGM/SVN 分支），任何 FBNeo 包都不会有 |

要玩这三个，需要另外下载 **CPS1 romset** 和 **PGM romset**（含 `pgm.zip` BIOS）。

### 8.6 空间约束

安卓 userdata 可用 **1.6 GB**（挂载在 `/storage/android-roms`），整包 4.0 GB 放不下。
若想多放游戏，建议按需挑（单个 NeoGeo 游戏 10~80 MB）；或换大 TF 卡。

---

## 9. 游戏列表"看不出选中"——已修复（二进制补丁）

### 9.1 根因（指令级定位）

`/opt/emuelec/bin/emulationstation` 未被 strip，带完整 `.symtab`，因此可以直接定位到：

```
TextListComponent<FileData>::render(Transform4x4f const&)   @ 0x002b9d34  size 3320
TextListComponent<FileData>::TextListComponent(Window*)     @ 0x002b7f10  size 2196
```

构造函数把成员 `mSelectedColor`（`this+0x2EC`）初始化为 **0**：

```
2b82d8: e3a00000  mov r0, #0
2b82dc: e58402ec  str r0, [r4, #748]     ; mSelectedColor = 0
```

绘制时：

```
2b9fe0: ldr r3, [r4, #204]   ; mCursor
2b9fe8: cmp r3, r6           ; 当前行是不是光标行
2b9fec: beq  2ba374          ; 是 → 走"选中"分支

2ba374: e59492ec  ldr r9, [r4, #748]   ; r9 = mSelectedColor
2ba378: e3590000  cmp r9, #0
2ba37c: 1affff1e  bne 2b9ffc           ; != 0 才使用这个颜色
2ba380: eaffff1a  b   2b9ff0           ; == 0 → 回落成 mTextColor
```

**结论：`mSelectedColor == 0` 使"选中"分支永远回落到普通文字色**，于是整列表同色。
普通文字色初值来自 `movw r1, #0xffff` → `0x0000FFFF`（该构建的颜色为 ARGB 风格，
R=0 G=0 B=255 的纯蓝），正好对应抓屏实测的 `(0,0,224)`。

主题改不动的原因也顺带解释清楚了：`applyTheme` 走 `ThemeData::getElement(<view>, "textlist", <name>)`，
element 为 null 时直接 `return`（0x2b38c4），**不会覆盖构造函数里的默认值**；而这份主题
（内嵌默认主题 `formatVersion 7`、`defaultView="Tiles"`）里根本没有 `textlist` 定义。

### 9.2 补丁

4 字节等长替换（不改文件大小、不改段布局）：

| 地址 | 原指令 | 新指令 | 效果 |
|---|---|---|---|
| `0x002BA374` | `e59492ec` `ldr r9, [r4, #748]` | `e3e09000` `mvn r9, #0` | 选中行固定使用 `0xFFFFFFFF`（不透明白） |

文件偏移 `0x002AA374`（`.text` vaddr `0x0A5670` ↔ offset `0x095670`）。

- 原始二进制：`md5 ca4b3941a3c071344f67ac748fa20594`（5 778 100 字节）
- 补丁后：　　`md5 ff8f5b131badb0184ed1bfb247ec4d0a`（同尺寸）

补丁工具（可重复执行、原指令校验不过则拒绝）：

```
python tools/es-gamelist-highlight.py <原文件> <输出文件>
```

本地产物：`emuelec/work/esbin/emulationstation.orig` / `emulationstation.p1`。

### 9.3 部署与回滚

```sh
# 设备上（EmuELEC 运行时）
cp /opt/emuelec/bin/emulationstation /opt/emuelec/bin/emulationstation.bak-1028   # 已在本次操作中生成
# 覆盖新文件后
chmod 755 /opt/emuelec/bin/emulationstation
# 重启前端
for p in /proc/[0-9]*; do ... kill -TERM <es/supervisor>; done
rm -f /var/run/histb-emuelec.pid; /etc/init.d/S95emuelec start

# 回滚
cp /opt/emuelec/bin/emulationstation.bak-1028 /opt/emuelec/bin/emulationstation
```

⚠️ `/opt` 属于 rootfs（p13），**重新刷写固件后补丁会丢失**，需要用上面的命令重打。
设备上现有的回滚备份：`/opt/emuelec/bin/emulationstation.bak-1028`。

### 9.4 实测验证

用 uinput 虚拟手柄（`/storage/a4-vpad`，伪装 X360 身份避免触发 CONFIGURE INPUT 弹窗）
在 ES 启动前注入按键，再用 `tools/fbgrab2.py` 抓帧：

| 注入序列 | 结果 | 截图 |
|---|---|---|
| `a` + `down`×2 | 第 3 行 `Metal Slug 2` **白色**，其余正常色 | `emuelec/work/es_white_rgba_1.png` |
| `a` + `down`×5 | 第 6 行 `Metal Slug 5` **白色** | `emuelec/work/es_white2_rgba_1.png` |

白色高亮停在 `Metal Slug 5` 而不是前一次的位置（这次多按了 3 次下）——说明改的是**真正的光标行**，
不是某个固定索引。

---

## 10. 退出热键"按 LB 就出菜单"与"选了 Exit 却重载游戏"（2026-10-28 晚修）

### 10.1 现象

用户反馈：**按住 LB + Start** 出来的不是退出，而是 RetroArch 菜单；在菜单里选 "Exit" 也不退出，
而是把当前游戏重新加载一遍。

### 10.2 根因一：`hotkey` 和 `menu_toggle` 指向同一个键

ZhiXu 手柄的实际按键码（来自 `/opt/emuelec/share/retroarch/autoconfig/sdl2/ZhiXu Gamepad.cfg`）：

| 物理键 | code | | 物理键 | code |
|---|---|---|---|---|
| A | 0 | | L（左肩） | **6** |
| B | 1 | | R（右肩） | 7 |
| X | 3 | | Select | 10 |
| Y | 4 | | Start | **11** |
| L3 | 13 | | R3 | 14 |

而当时的 `retroarch.cfg` 是 `hotkey=4 / exit=7 / menu_toggle=6` —— 那其实是**另一把 X360 手柄**的码。

冲突点：`input_enable_hotkey_btn = 6`（由 autoconfig 覆盖而来）与 `input_menu_toggle_btn = 6`
**是同一个键**。菜单键不需要热键修饰，单按即触发，所以**单按 LB 就直接弹菜单**，跟 Start 完全无关。

### 10.3 根因二：菜单里 "Restart RetroArch" 冒充了 "退出"

RetroArch 主菜单底部相邻两项：

| 菜单项 | 实际行为 |
|---|---|
| `Quit RetroArch` | 退出进程 → `run-retroarch.sh` 返回 → ES 恢复（**这才是退出**） |
| `Restart RetroArch` | 退出后**立刻重启自己**，并重载当前内容 → 看起来就是"又进了一遍游戏" |

用户点的那个 "Exit" 是后者。已加 `menu_show_restart_retroarch = "false"` 把它从菜单里隐藏。

### 10.4 修改内容

全局 `/opt/emuelec/etc/retroarch.cfg`（备份 `retroarch.cfg.bak-1028b`）：

```
input_enable_hotkey_btn = "6"        # LB / L1
input_exit_emulator_btn = "11"       # Start
input_menu_toggle_btn   = "nul"      # 不再占用任何单键，彻底消除与 hotkey 撞车
input_menu_toggle_gamepad_combo = "2"  # 原厂已有：用组合键开菜单（按 RetroArch 定义应为 L3+R3）
menu_show_restart_retroarch = "false"  # 隐藏会"重载游戏"的 Restart RetroArch
```

两把手柄的 autoconfig 也各自补全（换手柄时不会错位）：

| 文件 | hotkey | exit | menu_toggle |
|---|---|---|---|
| `ZhiXu Gamepad.cfg` | 6 (L) | 11 (Start) | nul |
| `Microsoft X-Box 360 pad.cfg` | 4 (LB) | 7 (Start) | nul |

全局值与 ZhiXu 一致，所以**即使 autoconfig 没被应用也能正常退出**（双保险）。

### 10.5 现在的按键表

| 操作 | 按键 |
|---|---|
| **退出游戏回前端** | **按住 LB（左肩）+ 按 Start** |
| 打开 RetroArch 菜单 | 按住两个摇杆按下（L3+R3） |
| 投币 | Select（单按，只投 1 个） |
| 方向 / 确认 / 取消 | 十字键或摇杆 / A / B |

### 10.6 已排除的猜测

- `run-retroarch.sh` **没有** while 循环（只有 `wait` 一次，退出即返回）
- `histb-emuelec-supervisor` 在游戏退出后只是 `wait` 并等其它前端结束，不会重开游戏
- `histb-runtime-exec` 只做动态加载器包装，不拦截退出
- `retroarch.cfg` 里没有任何 `quit*` 覆盖项（除新增的 `menu_show_restart_retroarch`）

实测佐证：直接 `kill -TERM` 当前的 retroarch 后，进程消失、ES 立即恢复，
**没有**出现游戏被重新拉起 —— 说明"重载"只来自菜单里的 `Restart RetroArch`。

---

## 11. WiFi 界面真相与按键映射核对（2026-10-28 晚二）

### 11.1 "找不到 WiFi 列表"——ES 菜单里根本没有这一项

抓帧确认，ES 的 `MAIN MENU` **只有两项**：

```
INFORMATIONS
QUIT
```

二进制里确实存在 `NETWORK SETTINGS` / `WIFI SSID` / `WIFI KEY` / `WIFI ENABLED` /
`WIFI CONFIGURATION ERROR` 这些字符串（用 `strings` 可查到），但**菜单入口被厂商裁掉了**，
普通用户没有任何可点的地方。截图：`emuelec/work/es_menu_rgba_1.png`。

而且原本就算点进去也无效：ES 会把值写进 `emuelec.conf` 的 `wifi.ssid / wifi.key`，
而真正干活的 `S87wifi` **从来不读那个文件**（它只读 `/opt/wifi/wpa_supplicant.conf`）。
两头对不上，所以"改了没反应"。

### 11.2 修复：两个入口打通 + 命令行工具

`S87wifi` 的 `gen_conf()` 改为按优先级取值：

1. `emuelec.conf` 的 `wifi.enabled / wifi.ssid / wifi.key`（ES 界面写的那一套）
2. 都没有时退回 `wifi.conf` 的 `SSID / PSK`
3. 生成后把实际使用的值**回写** `wifi.conf`，保持两边一致
4. `wifi.enabled=0` 时直接跳过连接

实测日志（`/storage/ee/logs/wifi.log`）已从

```
cfg: generated from wifi.conf ssid=PandoraBox
```

变成

```
cfg: generated from emuelec.conf (ES 界面) ssid=PandoraBox hidden=0
wifi: insmod rc=17 (attempt 1) → wlan0 present → supplicant rc=0 → OK
```

新增 `/usr/bin/a4-wifi`：

```sh
a4-wifi status                # IP / 关联 / 两处配置 / 最近日志
a4-wifi scan                  # 扫描周边 AP（SSID + 信号 + 加密）
a4-wifi set <SSID> <密码>     # 写入两处并立即重连
a4-wifi restart               # 用当前配置重连
```

实测 `a4-wifi scan` 输出（当前环境）：

| SSID | 信号 | 加密 |
|---|---|---|
| PandoraBox（当前连接） | -46 dBm | WPA2 |
| TP-LINK_QD | -72 dBm | WPA2 |
| ChinaNet-SSID1 | -78 dBm | WPA2 |
| zhaiji | -82 dBm | WPA2 |
| CU_669E | -86 dBm | WPA2 |

> 首版 awk 有两个 bug：`HESSID:` 被当成 SSID、加密字段因 RSN 出现在 SSID 之后而恒显示"开放"。
> 已改为"遇到下一个 BSS 才输出上一条"的两阶段解析。

### 11.3 "游戏内外 ABXY 不同步"——三处映射完全一致，不存在错位

用 `a4-pad show` 一次性取出三处定义：

| 层 | 文件 | A | B | X | Y | Start | Select |
|---|---|---|---|---|---|---|---|
| SDL 映射库 | `share/sdl/gamecontrollerdb.txt`（GUID `1c18000011010000` → TGZ Controller） | b0 | b1 | **b3** | **b4** | b11 | b10 |
| 游戏内 | `autoconfig/sdl2/ZhiXu Gamepad.cfg` | 0 | 1 | **3** | **4** | 11 | 10 |
| 游戏外 | `.emulationstation/es_input.cfg` | 0 | 1 | **3** | **4** | 11 | 10 |

三处逐项相同，链路无断点。**本次对 A/B/X/Y 的改动为零**（历史改动只有：
ZhiXu 的 `hotkey` 9→6；X360 的 a/b/x/y 由 `a=1 b=0 x=3 y=2` 修正为 `a=0 b=1 x=2 y=3`）。

需要注意的一点：这把手柄的 `X/Y` 是 **3/4**，而不是标准 Xbox 的 **2/3**。
如果物理按键实际发出的是 2/3，就会表现为"按 X 出来 Y"。这类问题只能靠实测确认，
因此新增：

```sh
a4-pad show                    # 三处映射对照表
a4-pad test [秒]               # 监听实体手柄，实时打印按键编号（按 A/B/X/Y 各一次）
a4-pad swapxy                  # 一键交换 X/Y（同时改游戏内与游戏外）
a4-pad swapab                  # 一键交换 A/B
a4-pad restore                 # 从 .bak-a4pad 恢复
```

底层工具 `/storage/a4-evinfo`（静态 ARM 二进制，源码 `tools/a4-evinfo.c`）直接读
`/dev/input/eventN` 输出 `KEY code=N value=V`，用来排除"配置文件看着对、按下去不对"的情况。

---

## 12. 首页新增「Network」与「CPU Speed」两个入口（2026-10-28 深夜）

### 12.1 思路

不改二进制。ES 的 `es_systems.cfg` 本来就支持"脚本系统"——自带的 `switchos` / `diagnostics`
就是这么做：目录里每个 `.sh` 就是一个可点条目，`<command>/bin/sh %ROM%</command>` 负责执行。

于是照抄这个结构，在首页系统轮播里加两个 system：

```xml
  <system>
    <name>a4network</name>
    <fullname>Network</fullname>
    <path>/storage/ee/network</path>
    <extension>.sh .SH</extension>
    <command>/bin/sh %ROM%</command>
    <platform>ignore</platform>
    <theme>ports</theme>
  </system>
  <system>
    <name>a4cpufreq</name>
    <fullname>CPU Speed</fullname>
    <path>/storage/ee/cpufreq</path>
    ...
```

首页效果：`favorites | CPU Speed | Network`（两者插在 systemList 最前面）。

### 12.2 生成器：`/usr/bin/a4-menu`

一条命令重建全部内容、状态与注册，可反复执行（幂等）：

```sh
a4-menu
```

它做四件事：

1. 写 `/storage/ee/cpufreq/cpu-{600,1000,1200,1500}.sh`（调用 `a4-perf`，已持久化）
2. 写 `/storage/ee/network/{net-wired,net-wifi,net-scan}.sh`
3. 生成 **系统目录内的** `gamelist.xml`（注意：ES 读 `<path>/gamelist.xml`，
   不是 `~/.emulationstation/gamelists/<system>/gamelist.xml`，这一点踩过坑）
4. 把两个 system 注册进 `es_systems.cfg`——**先剥离旧块再插到 `<systemList>` 之后**

### 12.3 踩过的两个坑

| 坑 | 现象 | 原因 |
|---|---|---|
| 插入位置错 | ES 日志里既没有这两个系统、也没有 "no games" 警告 | awk 把新 `<system>` 插到了 `<name>diagnostics</name>` **前面**，等于嵌进 diagnostics 的块内部，XML 结构被破坏。正确位置是 `<systemList>` 之后 |
| gamelist 放错目录 | 系统加载了但条目为空 | ES 读 `<path>/gamelist.xml`（日志可见 `Parsing XML file "/storage/ee/diagnostics/gamelist.xml"`），不是 `gamelists/<system>/` |

另外 supervisor 会打印 `preserving user-modified EmulationStation systems configuration`，
即它检测到用户改过 `es_systems.cfg` 就保留，不会覆盖回去。

### 12.4 实测

| 项 | 结果 |
|---|---|
| 首页出现两个入口 | `favorites / CPU Speed / Network`（截图 `menu4_rgba_1.png`） |
| CPU 列表 | `1) 600 / 2) 1000 ★当前 / 3) 1200 / 4) 1500`（截图 `cpu_list_rgba_1.png`） |
| 点选是否真生效 | 注入 `A → 下 → 下 → A`（选 1500），`a4-perf.conf` 的 `MAX_FREQ` 由 `1000000` 变为 **`1500000`** ✅ |
| 网络列表 | `1) 有线网络 / 2) 无线网络：PandoraBox / 3) 扫描周边 WiFi`（截图 `net_final_rgba_1.png`） |
| 状态显示 | 无线条目描述里带 `● 已连接：PandoraBox  192.168.31.16` |

中文显示正常（ES 用系统字体渲染 gamelist）。

### 12.5 当前限制

- **新 WiFi 需要密码**：现在只能连已保存的网络。输入密码需要一个全屏输入界面（ES 无可用输入框），
  待实现；临时办法是 `a4-wifi set <SSID> <密码>`。
- 选完 CPU 后当前项文字会变（`★当前` 移到新挡位），但 ES 不自动刷新列表，
  需要退出该系统再进一次才看到。

---

## 13. EmuELEC 启动时自动读取安卓已保存的 WiFi（2026-10-28 深夜，已实测）

### 13.1 安卓 /data 到底在哪

之前卡住是因为 `blkdevparts` 覆盖了分区表，`/dev/mmcblk0p10` 挂出来只有
`backup / lost+found / recovery`，让人误以为"读不到"。真正的位置是：

```
/dev/loop0  offset=1365245952  →  /mnt/android        ← 这就是安卓的 /data
                                 →  /storage/android-roms（EmuELEC 的 roms 视角，同一分区）
```

`/mnt/android` 下能看到完整安卓 data 结构：

```
a4 app app-asec app-lib app-private backup bugreports dalvik-cache data
dontpanic drm emu iptv local lost+found media mediadrm misc ppp property
resource-cache security skyplay ssh system tombstones user
```

WiFi 配置就在 `/mnt/android/misc/wifi/wpa_supplicant.conf`（实测可读，含全部已保存网络）。

> 探测手段：`losetup /dev/loop3 -o 819986432 /dev/mmcblk0` 探到 782MB 处是 system，
> 最终从 `df -h` 看到 `loop0` 同时挂在 `/mnt/android`，才定位到 data。

### 13.2 关键：S87 早于 S93

```
S87wifi              ← WiFi 在这里启动
S93a4-androidroms    ← 安卓分区在这里才挂载
```

所以 WiFi 启动时 `/mnt/android` 还不存在。解法：**S87wifi 自己按偏移挂一个只读的**。

```sh
AND_OFF=1365245952
AND_LOOP=/dev/loop7
find_android_conf() {
    for p in /mnt/android /storage/android-roms /tmp/and; do
        [ -f "$p/misc/wifi/wpa_supplicant.conf" ] && { echo "$p/misc/wifi/wpa_supplicant.conf"; return 0; }
    done
    losetup "$AND_LOOP" -o "$AND_OFF" /dev/mmcblk0 || return 1
    mount -o ro,noload "$AND_LOOP" /tmp/and || { losetup -d "$AND_LOOP"; return 1; }
    [ -f /tmp/and/misc/wifi/wpa_supplicant.conf ] && echo /tmp/and/misc/wifi/wpa_supplicant.conf
}
```

读完立即 `umount + losetup -d` 释放，不影响后面 S93 的正常挂载（它用 loop0）。

### 13.3 生成策略

`/opt/wifi/wpa_supplicant.conf` 由两部分合成：

1. **安卓里保存的全部 network 块**（原样搬过来，保留各自 priority）
2. **手动/ES 界面配置的那个**（`wifi.conf` 或 `emuelec.conf`），priority=5 更高
   —— 若与安卓同名则自动跳过，避免重复

支持多网络后，wpa_supplicant 会按 priority + 信号自动选，不用人工干预。

### 13.4 冷启动实测（reboot 后）

```
4.92  wifi: start
5.09  android: mounted read-only at /tmp/and        ← 自己挂载成功
5.12  cfg: android=1 manual=none source=wifi.conf (dup, skipped)   ← 读到 1 个网络并去重
7.89  wifi: associated after 1s
      inet 192.168.31.16/24                          ← 联网成功
```

`losetup -a` 只剩系统的 `/dev/loop0`，临时 loop7 已释放。

### 13.5 效果

- **在安卓里连过的 WiFi，切到 EmuELEC 开机就自动可用**，不需要任何输入
- 安卓里存多个网络也全部导入，按信号自动选
- 需要临时覆盖时：`a4-wifi set <SSID> <密码>`（priority 更高）

> 注意：偏移 `1365245952` 是针对当前固件实测值。若重刷固件导致分区变化，
> 用 `cat /sys/block/loop0/loop/offset` 重新确认（开机后 loop0 已由 S93 挂好）。

---

## 14. 首页菜单「看不出变化」的修复（2026-10-29 下午）

### 14.1 现象

在 CPU Speed 里选 600MHz / 在 Network 里点无线，**界面毫无变化**，看不出到底生效没有
（实测配置其实已经改了：`a4-perf.conf` 的 `MAX_FREQ` 变了、`pm_cpu` 频率变了）。

### 14.2 原因

ES 只在启动时读 `es_systems.cfg` 与 `<path>/gamelist.xml`，**运行中不会重扫**。
`a4-menu` 虽然重写了这两份文件，但 ES 还拿着内存里的旧数据渲染 ⇒ 看起来"没变"。

### 14.3 修法（三处）

| 改动 | 说明 |
|---|---|
| **系统标题带状态** | `a4cpufreq` 的 `<fullname>` 写成 `CPU 1000M`；`a4network` 写成 `Net PandoraB`（网络名截 8 字符，避免被主题截断成 `10...`） |
| **点完自动重启前端** | 每个条目脚本收尾依次执行：动作 → `a4-menu`（重建列表与标题）→ `a4-es-restart`（杀 ES，supervisor 拉起） |
| **开机重建** | 新增 `/etc/init.d/S94a4-menu`：`S93wifi`（已连上、能拿到 IP）之后、`S95emuelec`（启 ES）之前跑一次 `a4-menu` |

生成脚本示例（`/storage/ee/cpufreq/cpu-600.sh`）：

```sh
#!/bin/sh
/usr/bin/a4-perf 600 >/dev/null 2>&1      # 改配置
/usr/bin/a4-menu    >/dev/null 2>&1       # 重建 gamelist + 系统标题
/usr/bin/a4-es-restart                    # 重启前端，让 ES 重新读
exit 0
```

`/usr/bin/a4-es-restart`：

```sh
for p in /proc/[0-9]*; do
    c=$(tr '\0' ' ' < "$p/cmdline" 2>/dev/null)
    case "$c" in *emulationstation*) kill -TERM "${p#/proc/}" 2>/dev/null ;; esac
done
```

### 14.4 实测

```
$ /usr/bin/a4-menu
menu ready: cpu=600MHz(now 600MHz/57C) net=PandoraBox wifi_ip=192.168.31.16
$ grep -oE 'CPU [^<]*|Net [^<]*' es_systems.cfg
CPU 1000M
Net PandoraB

$ sh /storage/ee/cpufreq/cpu-1000.sh     # 模拟点一下
→ a4-perf.conf: MAX_FREQ=1000000
→ es_systems.cfg: CPU 1000M
→ 前端重启：ES pid 2786（新），supervisor 1888 未变
```

首页截图：`favorites | CPU 1000M | Net PandoraB`（标题完整不截断）。

### 14.5 注意

- 点完后**屏幕会闪一下**（3~8 秒），这是前端重启，属正常；不是卡死。
- 温度解析原来写错（`temperature: 58` vs 实际 `temperature = 58 degree`），已改成
  `grep -oE 'temperature *= *[0-9]+'`。
- **别用 Windows 文本模式写这些脚本**：`open(p,'w')` 会引入 CRLF，设备上 ash 直接报
  `not found` / `syntax error: unexpected "elif"`。本次踩过一次，已统一 `newline='\n'`。

---

## 15. 手柄映射修正 + 声音卡顿的真正原因（2026-10-29 晚）

### 15.1 手柄映射：不用抓包，靠 HID 描述符就能算出来

`/sys/kernel/debug/hid/0003:0079:181C.0001/rdesc` 里有一份完整的"字段 → evdev 码"表：

```
Button.0001 ---> Key.BtnA     Button.0008 ---> Key.BtnTR
Button.0002 ---> Key.BtnB     Button.0009 ---> Key.BtnTL2
Button.0003 ---> Key.BtnC     Button.000a ---> Key.BtnTR2
Button.0004 ---> Key.BtnX     Button.000b ---> Key.BtnSelect
Button.0005 ---> Key.BtnY     Button.000c ---> Key.BtnStart
Button.0006 ---> Key.BtnZ     Button.000d ---> Key.BtnMode
Button.0007 ---> Key.BtnTL    Button.000e ---> Key.BtnThumbL
                              Button.000f ---> Key.BtnThumbR
Consumer.0223 ---> Key.HomePage
GenericDesktop.HatSwitch ---> Absolute.Hat0X/Y      （十字键 = hat）
X/Y/Z/Rz ---> Absolute.X/Y/Z/Rz                      （左右摇杆）
Simulation.00c4/c5 ---> Absolute.Gas/Brake           （这两个本手柄**没用到**）
```

BTN_A 的码是 304（`BTN_GAMEPAD=0x130`），并且 SDL 的 linux 驱动按 **码升序** 排按钮序号，
所以 **SDL 序号 = 码 − 304**：

| SDL 序号 | evdev 码 | 物理键 | 旧配置 | 新配置 |
|---|---|---|---|---|
| 0 | BTN_A(304) | A | a=0 ✔ | a=0 |
| 1 | BTN_B(305) | B | b=1 ✔ | b=1 |
| 2 | BTN_C(306) | C（本手柄无） | — | — |
| 3 | BTN_X(307) | X | x=3 ✔ | x=3 |
| 4 | BTN_Y(308) | Y | y=4 ✔ | y=4 |
| 5 | BTN_Z(309) | Z（本手柄无） | — | — |
| **6** | **BTN_TL(310)** | **LB** | l=6 ✔ **但 hotkey 也=6 ✘** | l=6 |
| **7** | **BTN_TR(311)** | **RB** | r=7 ✔ | r=7 |
| **8** | **BTN_TL2(312)** | **LT** | ✘ 写成了 `l2_axis=+5` | **l2_btn=8** |
| **9** | **BTN_TR2(313)** | **RT** | ✘ 写成了 `r2_axis=+4` | **r2_btn=9** |
| 10 | BTN_SELECT(314) | Select | 10 ✔ | 10 |
| 11 | BTN_START(315) | Start | 11 ✔ | 11 |
| 12 | BTN_MODE(316) | Home | — | （备用） |
| 13 | BTN_THUMBL(317) | L3 | 13 ✔ | 13（+热键=菜单） |
| 14 | BTN_THUMBR(318) | R3 | 14 ✔ | **14（改为热键）** |

**两个真错误**：

1. **热键 = LB**：`input_enable_hotkey_btn = "6"` 和 `input_l_btn = "6"` 撞在同一个键上。
   RetroArch 会把热键键吞掉，所以 **LB 永远不可能被当作 L1 送进游戏**，
   而且 LB+Start 会直接退出游戏 —— 这就是"LB 不是正常的结果"。
2. **LT/RT 当成了轴**：配置里写 `l2_axis="+5"` / `r2_axis="+4"`（即 ABS_Brake / ABS_Gas），
   可这两个轴本手柄根本没有映射到扳机（扳机是数字按键 BTN_TL2/BTN_TR2）。
   按键 → 轴，永远等不到信号 ⇒ 两个扳机全废。

**新方案**（已写入 `/storage/.config/retroarch/autoconfig/ZhiXu-Gamepad.cfg` 和
`/opt/emuelec/share/retroarch/autoconfig/sdl2/ZhiXu Gamepad.cfg`）：

```
l_btn=6  r_btn=7  l2_btn=8  r2_btn=9  l3_btn=13  r3_btn=14
enable_hotkey_btn = "14"   ← 热键挪到 R3
exit_emulator_btn = "11"   → R3+Start 退出
menu_toggle_btn   = "13"   → R3+L3 打开菜单（原来就是"L3+R3"的说法）
```

代价：R3 单独按下不再进游戏（它现在是热键）；其余 13 个键全部可用于游戏。

### 15.2 声音卡顿：不是音频缓冲，是 CPU 被钉在 600 MHz

先把音频排除掉（`audio_driver=alsathread` + `audio_latency=128` 一直在生效）：

```
hw_params : S16_LE 48000Hz period=768 buffer=3072
delay 采样 : 3072 / 2304 / 3072 / 2304 ...  （10 次，从未掉到 0）
PCM state : RUNNING
dmesg     : 无 aiao underflow / xrun
```

再看真实的帧率（RetroArch OSD，同一个 ROM）：

| CPU 上限 | FPS（OSD） | 结论 |
|---|---|---|
| 600 MHz | **42.88** | 掉帧 → 画面/声音都在抖 |
| 1000 MHz | **49.99** | 满帧 |
| 1500 MHz | 49.97 | 满帧（无收益） |

原因：`/storage/.config/emuelec/configs/a4-perf.conf` 里存着 `MAX_FREQ=600000`
（之前在 CPU 菜单里点过 600，被持久化了），开机 `S97a4-cpufreq` 就按 600 设上限。
600 MHz 下 FBNeo 只能跑 42~47 fps，被 display(50Hz) 拖着走，听起来就是"声音卡顿"。

**修正**：`a4-perf 1000`（已执行，现 `scaling_max_freq=1000000`，FPS 49.99）。

> 顺带记录一个坑：**同时跑两个 RetroArch 实例会让 FPS 掉到 25**（我调试时踩到，
> 一个 mslug2 一个 mslug3 同时开着）。以后测帧率前先确认只有 1 个 retroarch 进程。

---

## 16. 为什么"刷完手柄直接能用、从来没让我设过"（2026-10-29 夜）

### 16.1 两份预置配置，都是之前打进镜像的

**前端 ES 侧**：

```
/storage/ee/config/.emulationstation/es_input.cfg        3964 B，3 段
        A4 IR Remote / Microsoft X-Box 360 pad / ZhiXu Gamepad
/storage/ee/config/.emulationstation/es_temporaryinput.cfg  1643 B，向导过程中的暂存
```

`es_input.cfg` 是**刷机前在这个系统上跑过一次配置向导**留下的结果，被一起打进了 p13 镜像。
ES 启动时看到"这台设备已经有按键表"，就直接 `Added known joystick`，**永远不会再弹向导**
（日志可证：`Added known joystick ZhiXu Gamepad`）。

**模拟器 RA 侧**：

```
/storage/.config/retroarch/autoconfig/A4-IR-Remote.cfg
/storage/.config/retroarch/autoconfig/Game-USB-Joystick.cfg
/storage/.config/retroarch/autoconfig/ZhiXu-Gamepad.cfg
/storage/.config/retroarch/autoconfig/Microsoft-XBox360.cfg
/opt/emuelec/share/retroarch/autoconfig/sdl2/ZhiXu Gamepad.cfg
```

这几个是我按标定值手写的，RetroArch 按"设备名/GUID"自动套用，所以插上就能玩。
**RA 本身没有"首次配置向导"**，它只有 autoconfig + 菜单里的手动绑定。

⇒ 两边都认为"已经配好了"，所以你看不到任何设置过程。你的判断是对的：
预置一份错映射，比"没配好让你自己配"更糟 —— 它把错误藏起来了。

### 16.2 现在的处理

| 位置 | 改动 |
|---|---|
| p13 镜像 | **删掉** `es_input.cfg` 和 `es_temporaryinput.cfg` ⇒ 刷完第一次进 ES 就是官方 `WELCOME / N GAMEPADS DETECTED / HOLD A BUTTON` 向导 |
| ES 首页 | 新增 **「手柄设置」** 系统（轮播里 CPU/Net 右边），3 个条目： |
| ① | 重新配置前端(ES)按键 —— 移走 es_input.cfg 并重启前端，重新出 WELCOME 向导 |
| ② | 清掉模拟器(RA)预置映射 —— 把 ZhiXu/XBox/USB 的 autoconfig 移走，改由你在游戏里绑 |
| ③ | 恢复标定好的默认映射 —— ES 用最近备份还原，RA 用 `padcfg/default/` 里的原始副本还原 |

在 ES 里绑 RA 的按键：进游戏 → **R3 + L3** 打开 RetroArch 菜单 → 设置 → 输入 → 端口1 绑定
（以前 `menu_toggle_btn="nul"` + 热键被 LB 占着，菜单根本打不开，所以"想自己设也没入口"）。

### 16.3 一个佐证

`es_temporaryinput.cfg` 里那张向导结果表写着：

```
leftshoulder  = button 6      （LB）
lefttrigger   = button 8      （LT）
leftthumb     = button 13     （L3）
```

和从 HID 描述符推出来的 `BTN_TL=6 / BTN_TL2=8 / BTN_THUMBL=13` 完全一致 ——
也就是说**当初那次向导其实配对了**，真正的问题是 RA 侧那份手写 autoconfig 把
LT/RT 写成了轴、又把热键压在 LB 上。

---

## 17. "LB+Start 变成开菜单、退不出去" —— 用注入实测，最后绕开 RetroArch

### 17.1 症状

按 **LB+Start** 不退游戏，反而弹出 RetroArch 菜单；之后就退不出去（只能断电）。

### 17.2 排查：配置链三处都是对的

| 位置 | 值 |
|---|---|
| `/opt/emuelec/etc/retroarch.cfg` | `enable_hotkey=14(R3)`、`menu_toggle=13(L3)`、`exit_emulator=11(Start)` |
| `/opt/emuelec/share/retroarch/autoconfig/sdl2/ZhiXu Gamepad.cfg` | 同上 |
| `/storage/ee/config/retroarch-histb-runtime.cfg`（appendconfig） | 只有目录项，**没有** input_ 行 |

直接改 U-Boot 之外没别的地方了，于是做**注入实测**（`tools/a4-keys`：root 能往
`/dev/input/event0` 写 input_event，等于替手柄按键）：

```
Select(314) + Start(315)  → 投币成功、进 Soldier Select   ← 证明注入有效、RA 收得到
R3(318) + L3(317)         → 打开 QUICK MENU               ← 证明热键机制本身是活的
LB(310) + Start(315)      → 打开 MAIN MENU               ← 用户报的现象，复现了
```

然后把 8 个候选热键逐个配 Start 试一遍（脚本 `/storage/ee/padtest.sh`）：

```
hotkey=310/311/312/313/314/316/317/318 + Start(315) → RA 全部存活，一次都没退出
```

⇒ **这个 RA 1.9 构建里 `input_exit_emulator_btn` 根本不触发**（热键是好的，唯独"退出"这个动作失灵）。
LB+Start 打开菜单的原因没完全挖出来（配置里没有任何一处把 LB 绑成热键/菜单），但不影响结论：
不能靠 RetroArch 自己的退出绑定。

### 17.3 解决：在 evdev 层做一个小守护（不依赖 RA 配置）

`tools/a4-exitd.c` → `/usr/bin/a4-exitd`，开机由 `/etc/init.d/S96a4-exitd` 拉起：

```
读 /dev/input/event0（只读，不 grab，不抢 RA 的键）
命中 LB(310)+Start(315) 或 R3(318)+Start(315)（同按，间隔 <400ms）
  → 找 cmdline 含 retroarch 的进程 → kill -TERM
  → histb-emuelec-supervisor 自动把 EmulationStation 拉回来
日志：/storage/ee/logs/exit.log
```

**实测（真机，注入按键）**：

```
RA=1 ──注入 LB+Start──▶ RA=0，ES(pid 5435) 回来    exit.log: LB+Start -> kill retroarch pid=8623
RA=1 ──注入 R3+Start──▶ RA=0                      exit.log: R3+Start -> kill retroarch pid=8984
```

现在可用的组合：

| 组合 | 作用 |
|---|---|
| **LB + Start** | 退出游戏，回 ES |
| **R3 + Start** | 同上（R3 是热键，习惯用哪个都行） |
| **R3 + L3** | 打开 RetroArch 菜单（菜单里也能 Close Content） |
| LB / RB / LT(8) / RT(9) | 游戏内 L1 / R1 / L2 / R2，不再被热键占用 |

### 17.4 遗留

LB+Start 会先闪一下 RetroArch 菜单（RA 内部某个动作）再被杀掉退出，结果正确、
画面有一下跳变。要彻底干净，得把 RA 里那条动作找出来，属于"锦上添花"，先记账。

> 工具留档：`tools/a4-keys`（注入）、`tools/a4-exitd.c`（守护）、`tools/padtest.sh`（穷举热键）。
