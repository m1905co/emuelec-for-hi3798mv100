# 22 · EmuELEC 红外遥控实现（用户态直驱 IR 控制器 → 虚拟手柄）

日期：2026-10-16
设备：Hi3798MV100 / EC6108V9C（mdmo1d），EmuELEC（kernel 4.4.35_ecoo_81082668）
目标：让随盒遥控器在 EmuELEC（EmulationStation）里可用

---

## 1. 结论

遥控**已经可用**：上下左右/OK/返回在 ES 菜单里都能操作，菜单键能调出 ES 主菜单，音量键绑成整页翻页。
全部通过 `a4-ird`（用户态程序，静态 ARM）实现，**没有重编内核、没有改 U-Boot、没有改内核驱动**。

---

## 2. 根因（三层，逐层排除后才定位）

### 2.1 第一层：EmuELEC 的内核编的是 S2 型红外驱动，本板需要 STD 型

| 内核字符串 | EmuELEC 内核 | 安卓内核 |
|---|---|---|
| `hi_ir_std_irq` / `IR_CODE_NEC` / `IrBlockTime` / `Hi keyboard` | **无** | 有 |
| `IR_S2` / `Chip Report Symbols` | 有 | **无** |

- Android 侧实测（切过去抓的）：按键时 `/proc/interrupts` 的 **`hi_ir_std_irq`（GIC 79）在涨**，
  `hi_keyled_ct1642_irq` 全程为 0；`getevent` 在 `event0 "Hi keyboard"` 上抓到标准 `KEY_UP/DOWN/LEFT/RIGHT`。
  ⇒ 遥控是**纯红外**，走 SoC 控制器，**前面板 keyled 完全没参与**。
- EmuELEC 的 S2 驱动只把**原始符号**塞进自己内部的 symbol buffer，`read()` 只吐 key_buf，
  且**不注册输入设备**。SDK 里 `hi3798mdmo1d_hi3798mv100_cfg.mak` 写的是 `CFG_HI_IR_TYPE_S2=y`，
  ⇒ **本板遥控在 EmuELEC 上从来就没工作过**，不是被改坏的。

### 2.2 第二层：IR 块被时钟门控关着

- IR 控制器基址 **`0xF8001000`**（S2 与 STD 共用同一套寄存器定义）。
- 时钟门控在 **`0xF8000048`**：`bit4=1` 开时钟、`bit5=0`。开机默认 `0x00011161` ⇒ **时钟是关的**，
  于是整块寄存器读出来全是 0，写也写不进去。
- 写 `0x00011151` 打开时钟后，读写全部正常。

### 2.3 第三层：内置驱动的 ISR 会抢走解码结果

- 未处理时：用户按 6 个键，我们 **0 帧**，而 `/proc/interrupts` 里 `ir_s2` 从 40 涨到 59
  ⇒ 驱动 ISR 把解码好的帧读走并清掉了。
- 处理：`echo hi_ir.0 > /sys/bus/platform/drivers/hi_ir/unbind`
  → `ir_s2` 从 `/proc/interrupts` 消失、`/dev/hi_ir` 消失，之后立刻能抓到帧。
- **注意：重启后驱动会重新 probe**，所以必须由开机脚本再 unbind 一次。

---

## 3. 实现要点

### 3.1 寄存器配置的两个坑

1. **必须先使能再写配置**：写 `IR_EN=1` 会重载块内默认值并冲掉 `IR_CFG/CNT_*`。
   正确顺序 `EN=1 → 写 CNT/CFG`。（这个顺序是拿安卓可用状态的寄存器值当基准比对出来的。）
2. **这些寄存器按 12 位字段截断**（写 `0xDEADBEEF` 回读 `0x00AD00EF`），属正常现象。

写入值与安卓基准逐项一致：

```
CRG 0xf8000048 = 0x00011151      IR_CFG    = 0x00001F17   (Type=0 NEC, Len=32, fdiv=23)
CNT_LEADS  = 0x033C03CC          CNT_LEADE = 0x019E01E6   CNT_SLEADE = 0x00B4010E
CNT0_B     = 0x00270054          CNT1_B    = 0x008700CB   INTM = 0
```

### 3.2 帧格式与合法性

- `IR_DATAH` 恒为 0，`IR_DATAL` 给出 32 位 NEC 帧。
- 每帧**两对字节互为反码**（`b0^b1==0xFF && b2^b3==0xFF`）。随机数据满足这个结构的概率是 1/65536，
  所以这是**帧合法性自证**。`a4-ird` 在注入前强制校验，畸形帧一律不注入。
- 本遥控：低字节对恒为 `4D/B2`（地址 0x4D + 反码），高字节对随键变化。

### 3.3 一次按键必须只产生一次动作（踩过的坑）

- 现象：按一下右，有时走两格；有时"往右走一下又往左走一下"。
- 日志定位：每次按键只解出 1 帧、全部 `pairs:ok ok` ⇒ 解码没问题。
- 真因：**一次按键的状态脉冲会持续 2~3 个轮询周期（约 4–6ms）**，
  我最初把"同一帧仍在 + 状态位非零"当成"长按"，在每个非零轮询都判一次 → 多发 1 次。
  "走两格"是这一次多余；"先右后左"是走过头触发 ES 列表**绕回开头**。
- 修复（三条同时上）：
  1. 去掉自作聪明的自动连发；
  2. 只在**观察到状态位先归零、之后再次置位**时才认作"新的一帧"（`status_seen_clear`），
     并对同键值加 **350ms 去抖**（`SAME_KEY_DEBOUNCE_MS`）；
  3. 注入前强制 NEC 反码校验。
- **为什么不能只判"帧值变化"**：连按两次同一个键（右、右）锁存的是同值，第二下会被丢掉。
- 实测 `stuck=2~3` ⇒ 状态位是干净脉冲（约 4–6ms 归零），上述判据成立。

### 3.4 必须做成手柄，不能做成键盘

- ES 是 **v5.27-dev / SDL2 2.0.9**，`es_input.cfg` 里**全是 `type="joystick"`**，**没有任何键盘条目**；
  且 ES 启动后不持有任何 event fd ⇒ 键盘设备建了也没人读。
- **必须在 ES 启动之前建好设备**：ES 只在启动时枚举输入设备，**不支持热插拔重扫**。
- 从 SDL 2.0.9 源码（`src/joystick/linux/SDL_sysjoystick.c`）抠出的权威规则：

| 项目 | 规则 |
|---|---|
| 后端 | **evdev**（`/dev/input/event*`），不是 joydev |
| **GUID** | 16 位小端依次写 `bustype, 0, vendor, 0, product, 0, version, 0`，取 16 字节 hex |
| 按键编号 | 先 `BTN_JOYSTICK(288)..KEY_MAX` 升序，再 `0..288` 升序 |
| 轴编号 | `0..ABS_MAX` 升序、**跳过 ABS_HATxx**、且 **min==max 的轴不计入** |
| hat | 连续 ABS_HAT 对，索引从 0 起；值 <0→位置0、0→中、>0→位置2 ⇒ `UP=1 RIGHT=2 DOWN=4 LEFT=8` |
| 手柄门槛 | 必须有 **ABS_X 和 ABS_Y**，否则整个设备被丢弃 |
| 忽略规则 | gamecontrollerdb 里认得的 name+GUID 会被 HIDAPI 接管而**忽略其 evdev 节点** ⇒ **不要冒充 Xbox/PS3** |

- 采用的虚拟手柄身份（自定义 VID/PID，避开忽略名单）：
  `name="A4 IR Remote"`，`bustype=0x0003 vendor=0x0a4d product=0x0001 version=0x0100`
  → **SDL GUID `030000004d0a00000100000000010000`**（`a4-ird guid` 可自打印校验）
- 按键集 `BTN_A..BTN_THUMBR`（11 个）→ 索引 0..10；轴 `ABS_X/Y/Z/RX/RY/RZ`（0..5）+ `ABS_HAT0X/Y`（hat 0）。

### 3.5 ES 配置（追加，原文件已备份）

`/storage/ee/config/.emulationstation/es_input.cfg` 追加一条（`es_input.cfg.a4bak` 为原文件）：

```xml
<inputConfig type="joystick" deviceName="A4 IR Remote" deviceGUID="030000004d0a00000100000000010000">
  up/down/left/right = hat 0 (1/4/8/2)
  a=button0(BTN_A)  b=button1(BTN_B)  start=button7(BTN_START)
  select=button6  hotkeyenable=button8  pageup=button4(BTN_TL)  pagedown=button5(BTN_TR)
</inputConfig>
```

⇒ **确认 = BTN_A，返回 = BTN_B，菜单 = BTN_START，音量± = 整页翻页**。

---

## 4. 键位表（实测学到）

| 按键 | 帧码 | 映射 |
|---|---|---|
| 上 | `0x35ca4db2` | `HAT_UP` |
| 下 | `0x2dd24db2` | `HAT_DOWN` |
| 左 | `0x66994db2` | `HAT_LEFT` |
| 右 | `0x3ec14db2` | `HAT_RIGHT` |
| OK | `0x31ce4db2` | `BTN_A` |
| 返回 | `0x3ac54db2` | `BTN_B` |
| 菜单 | `0x659a4db2` | `BTN_START` |
| 音量 + | `0x7f804db2` | `BTN_TL`（pageup） |
| 音量 − | `0x7e814db2` | `BTN_TR`（pagedown） |

（音量+ `0x7f80` 与音量− `0x7e81` 是相邻值，可交叉印证这两码确实成对。）

配置文件：`/storage/.config/a4-ir/keys.map`，格式 `<帧hex> <spec>`。
**改完不用重启前端**：`kill -HUP $(pidof a4-ird)` 即热重载（重建虚拟手柄会让 ES 丢掉输入设备，所以特意加了 SIGHUP）。

---

## 5. 持久化与开机流程

| 文件 | 作用 |
|---|---|
| `/storage/a4-ird` | 用户态程序（静态 ARM，md5 `6dbd6b877d9512d571cad89ef10f88bb`） |
| `/storage/.config/a4-ir/keys.map` | 键位表 |
| `/etc/init.d/S94a4-ird` | 开机：`unbind hi_ir.0` → `setsid /storage/a4-ird run`，**排在 `S95emuelec` 之前** |

设备节点：`Name="A4 IR Remote"  Bus=0003 Vendor=0a4d Product=0001  H=js1 event1`

> **备份文件绝不能命名为 `S[0-9][0-9]*`** —— rcS 用该通配符遍历 `/etc/init.d`，备份会被当脚本执行（已踩过）。

---

## 6. 顺带修掉的一个严重 bug（我引入的）

**现象**：前端一退出（例如重启前端），盒子就自己重启。

**原因**：ES 里其实有**两套**独立机制，我上一版只看到一半：
| 文件 | 真实语义 |
|---|---|
| `/tmp/reboot.please` | **系统重启请求** |
| `/tmp/shutdown.please` | **系统关机请求** |
| `/var/lock/start.retro` | ES/retroarch 的**"retro 前端正在运行"标记**，**不是**重启请求 |

我把它当成了重启请求，而 `a4-inputwatch`（手柄热插拔守护）一看到新 joystick 就会重启前端
⇒ **每次前端退出都被变成一次系统重启**。

**同时纠正一个更早的错误结论**：`S95emuelec` **不循环**、原厂 supervisor 跑完 `wait` 就 `exit`
⇒ **ES 退出后没有任何东西把它拉起来**，这才是"菜单里重启 → 黑屏 → 只能断电"的**真正根因**
（报告 17 里写的"/var/lock 不存在导致 touch 失败"是错的）。

**修复**：supervisor **从原版备份重新打补丁**（不叠改动），只保留两个补丁：
1. 等输入设备的有界等待（默认 6s，有虚拟手柄时立即返回）；
2. **只认 `/tmp/reboot.please` → `reboot`、`/tmp/shutdown.please` → `poweroff -f`**，完全不碰 `start.retro`。

文件 `emuelec/work/histb-emuelec-supervisor.v5`，md5 `c71d60ddd6e6c6b07c31924cef903e62`。
**实测验证**：重启前端后 uptime 连续（639s）未重启。

---

## 7. 验收证据

| 项 | 证据 |
|---|---|
| 解码正确 | 每帧 `pairs:ok ok`（NEC 反码校验），所有键码稳定复现 |
| 一次按键一步 | `stuck=2~3` 状态位为干净脉冲；`new` 与 `same-key` 判定符合预期 |
| ES 认到设备 | `ES(pid 31230)` 打开 `event0`(USB 手柄) 与 `event1`(A4 IR Remote) |
| 开机自启 | 重启后 `a4-ird` 自动运行、驱动保持 unbind、`input devices ready after 0s` |
| 无误重启 | 重启前端后 uptime 连续 639s |
| 用户实测 | 方向/OK/返回在 ES 菜单中可操作，"看着正常" |

---

## 8. 已知局限

- **不支持长按连滚**（长按不会连续移动）。这是**有意为之**：该控制器的状态位语义无法可靠区分
  "长按重复帧"与"状态位驻留"，做连滚会重新引入误步进。需要长按滚动只能改用更可靠的判据。
- 音量键在 ES 里没有原生动作，现绑为整页翻页；若需要在游戏内调音量，需要另接 EmuELEC 的音量控制。
- 未做 IR 学习/重映射界面：换遥控器需重新 `learn` 并编辑 `keys.map`。

---

## 附：用户按「启动 RetroArch」黑屏 —— 根因与修复（同一轮）

### 现象
在 ES 主菜单选「启动 RetroArch」后屏幕黑掉。日志：

```
EmulationStation cleanly shutting down.
HiSTB EmuELEC exited with status 0
sh: systemctl: not found
```

### 根因：ES 的菜单动作用 systemd 命令实现，而本机没有 systemd

ES 二进制里这几条字符串紧邻，可直接读出调用序列：

```
REALLY START RETROARCH?  →  /var/lock/start.games  →  touch /var/lock/start.retro  →  systemctl start retroarch.service
REALLY RESTART EMULATIONSTATION?  →  systemctl restart emustation
REALLY REBOOT FROM NAND?  →  nand / rebootfromnand / sync / systemctl reboot
```

⇒ 命令失败 + ES 已退出 + **原厂 supervisor 跑完就退出、`S95emuelec` 不循环** ⇒ 没人再拉起前端 ⇒ 黑屏。

> **旁证**：`start.retro` 正是"启动 RetroArch"流程里被 touch 的 —— 坐实它只是"前端在跑"的标记，
> 不是重启请求（本报告第 6 节已纠正）。

### RetroArch 是什么

EmuELEC 里 **ES 只是菜单/启动器**；真正跑游戏的是 **RetroArch（libretro 前端）+ 对应核心**。
`es_systems.cfg` 里每个机种的命令就是 `run-retroarch.sh <core> %ROM%`（cores：fceumm / snes9x2010 /
gambatte / gpsp / mgba / picodrive / mednafen_pce_fast / pcsx_rearmed / fbneo / mame2003_plus）。
菜单里那项"启动 RetroArch"是打开 **RetroArch 自己的界面**（不载入内容）。
注意 `run-retroarch.sh` **强制要求 core + ROM 两个参数**，不能拿它开 UI。

### 修复（三件）

| 文件 | 作用 |
|---|---|
| `/usr/bin/histb-emuelec-supervisor`（v7，md5 `5ec6ab479f6a1b94c1f608d218cbf21a`） | "启动一次就退出" → **循环**：前端退出后，只对 `/tmp/reboot.please` / `/tmp/shutdown.please` 动作；否则**等 RetroArch 退出后重新拉起前端**；带崩溃环保护（连续 5 次 5 秒内退出即放弃） |
| `/usr/bin/systemctl`（垫片） | 实现 ES 需要的那几条命令；`stop/start/restart emustation` **故意 no-op**（前端生命周期归 supervisor 管，避免自我阻塞）；日志 `/storage/ee/logs/systemctl-shim.log` |
| `/storage/a4-retroarch-ui` | 复刻 `run-retroarch.sh` 的运行环境，然后**不带 `-L` 也不带 ROM** 启动 retroarch ⇒ 进 RetroArch 主界面 |

匹配"RetroArch 是否在跑"必须用**精确路径**（`*/opt/emuelec/bin/retroarch*`），
用通配 `*retroarch*` 会误匹配任意含该字样的 shell 命令行 —— 实测因此把一次前端重启拖后了 30 秒。

### 验证

| 项 | 结果 |
|---|---|
| RetroArch 可启动 | 无头冒烟测试（`SDL_VIDEODRIVER=dummy`）**存活 14s+** |
| **黑屏不再需要断电** | `kill -9` 掉 ES → 日志 `exited with status 137` → 立即 `Starting HiSTB EmuELEC from /opt/emuelec` → 新 ES 进程出现 |
| 遥控仍正常 | ES(pid 27086) 持有 `event0`(USB 手柄) 与 `event1`(A4 IR Remote) |
| 无副作用 | 重启前端后 uptime 连续 1089s 未重启 |
