# 16 · EmuELEC 手柄失效修复 + 蓝牙硬件确认

日期：2026-10-14
设备：Hi3798MV100 / mdmo1d / EmuELEC（kernel `4.4.35_ecoo_81082668`）
通道：WiFi telnet 23（root`/`emuelec`）+ SSH 22，备用 TTL COM4

---

## 一、问题现象

用户反馈（三条）：

1. **EmuELEC 不读游戏手柄了**，界面卡在第一屏不动
2. 用原来的手柄卡住，**换另一个手柄长按也没反应**
3. 追问：**WiFi 和蓝牙会不会在同一颗芯片上？**
4. （已确认）红外遥控是通用的，随便找个红外遥控器就能用

---

## 二、根因（手柄失效）

### 2.1 直接证据链

| 检查项 | 命令 | 结果 | 含义 |
|---|---|---|---|
| ES 进程存在 | `ps w` | PID 1877 `ld-linux.so.3 … /opt/emuelec/bin/emulationstation` | 前端**没崩溃** |
| ES 打开的设备 | `ls -l /proc/1877/fd/` | `6→/dev/mali` `7→/dev/fb0` `10→/dev/snd/controlC0`，**无任何 `/dev/input/event*`** | **ES 从未打开输入设备** |
| 内核识别手柄 | `cat /proc/bus/input/devices` | `f766:0007 Game USB Joystick`(js0/event0)、`045e:028e Microsoft X-Box 360 pad`(js1/event1) | **内核侧手柄正常** |
| ES 日志 | `cat /storage/ee/logs/es_log.txt` | 停在 `VolumeControl::init() … mixername : Master`，**无 "Configuring device"** | ES 启动瞬间**枚举到 0 个手柄** |
| 启动脚本 | `cat /etc/init.d/S95emuelec` | 只检查 `enable-autostart`、`storage guard`，**不检查输入设备** | — |
| supervisor | `cat /usr/bin/histb-emuelec-supervisor` | 启动 ES 前只等 `${FB_DEVICE}`(/dev/fb0) 与 `${MALI_DEVICE}`(/dev/mali) | **完全不关心手柄** |
| 节点时间 | `ls -l /dev/input/` | `event0` 与 `js0` 同为 `00:06`，而 ES 于 `00:00:28` 启动 | **手柄晚于 ES 出现** |

### 2.2 机理

```
BootROM → U-Boot → kernel → init(S01…S95)
                                   │
                        S95emuelec → supervisor
                                   │  等 fb0 + mali 就绪（立即满足）
                                   ▼
                        run-emulationstation.sh → histb-runtime-exec → ES
                                   │
                     ES 启动时扫描 /dev/input/event*  ← 此刻手柄可能还没枚举
                                   │
                        ES 只在启动时枚举一次，不支持热插拔重扫
                                   │
                    手柄之后出现 → ES 永远不知道 → 界面无输入响应
                            （用户观感 =「卡第一屏不动」）
```

**关键结论：EmuELEC 的 EmulationStation 不做 USB 热插拔重扫**（不是驱动问题，内核层手柄一直正常）。

### 2.3 复现与判别实验

对运行中的前端执行 `/etc/init.d/S95emuelec restart`（此时手柄已在）：

```
# 重启后立即生效
pid 2521 fd: 9 -> /dev/input/event0   10 -> /dev/input/event1
es_log: Configuring device 0 (Game USB Joystick).
        Mapping [Axis 1-] -> Up ; … ; Mapping [Button 7] -> RightTrigger
```

→ **重启 ES 后手柄立即可用**，证实「时序 + 无热插拔」是唯一根因。

---

## 三、修复方案（两层，均已部署验证）

### 修复 A — supervisor 启动 ES 前等待输入设备

改文件：`/usr/bin/histb-emuelec-supervisor`（备份 `…a4bak`）

在 `trap terminate_frontend HUP INT TERM` 之后、`echo "Starting HiSTB EmuELEC …"` 之前插入：

```sh
INPUT_WAIT_SECONDS=${HISTB_INPUT_WAIT_SECONDS:-30}
input_attempt=0
while [ "${input_attempt}" -lt "${INPUT_WAIT_SECONDS}" ]; do
    if ls /dev/input/event* >/dev/null 2>&1; then
        break
    fi
    input_attempt=$((input_attempt + 1))
    sleep 1
done
if ls /dev/input/event* >/dev/null 2>&1; then
    echo "HiSTB input devices ready after ${input_attempt}s: $(ls /dev/input/event* 2>/dev/null | tr '\n' ' ')"
else
    echo "HiSTB no input device after ${INPUT_WAIT_SECONDS}s; starting frontend anyway"
fi
```

- 大小 4477 → 5593 字节，`sh -n` 通过
- 推送后设备 md5 = 本地 md5 = `e8c868b15222326eedcb35f5e9c29a80`
- 可用 `HISTB_INPUT_WAIT_SECONDS` 覆盖（默认 30 s）

### 修复 B — 热插拔兜底守护

新增 `/etc/init.d/S96a4-inputrecover`（1595 B，755）：

启动后（后台，不阻塞 init）最多盯 10 分钟；**仅当**「`/dev/input/event*` 已存在」且「运行中的 ES 的 `/proc/<pid>/fd` 里没有任何 `input/event`」时，重启一次前端，然后退出。

- 健康会话（ES 已握住手柄）→ 不动作
- 完全没有手柄 → 不动作
- 已验证：守护运行前后 ES PID 均为 2937，未误触发

> `rcS` 执行方式为 `for i in /etc/init.d/S[0-9][0-9]*; do $i; done`（无参数），脚本用 `${1:-start}` 兜底，S96 会被正常执行。

---

## 四、验证结果（全部实测）

| 场景 | 结果 |
|---|---|
| 手动 `S95emuelec restart` | `input devices ready after 0s: event0 event1`；ES 持有 2 个 input/event |
| 冷重启后开机路径 | supervisor.log：`HiSTB input devices ready after 0s` → `Starting …` → `passed the 30s process health window` |
| ES 持有的设备 | PID 1910：`6→/dev/mali` `7→/dev/fb0` **`8→/dev/input/event0`** **`9→/dev/input/event1`** |
| 手柄配置 | `es_input.cfg` inputConfig 条目 2 → **6**（ES 自动写入 Game USB Joystick / X-Box pad） |
| 守护不误触发 | 前后 ES PID 相同，supervisor.log 无 `a4-inputrecover` |

**当前状态：EmuELEC 前端正常，两个 USB 手柄均被识别并完成映射。**

---

## 五、蓝牙：确认**无蓝牙硬件**（用户猜测证伪）

用户猜测「WiFi 和蓝牙可能在同一芯片上」，实测**不成立**：

| 检查 | 命令 | 结果 |
|---|---|---|
| USB 接口数 | `ls -l /sys/bus/usb/devices/1-2:1.*` | **只有 `1-2:1.0` 一个接口** |
| USB 设备总表（EmuELEC） | `lsusb` | 仅 `0bda:0179`(WiFi) + 两个手柄，**无任何蓝牙控制器** |
| 蓝牙 class | `ls /sys/class/bluetooth/` | 空（无 `hci0`） |
| 蓝牙节点 | `ls -l /dev/rtk_btusb` | 不存在 |
| Android 侧 | `dmesg \| grep -i bluetooth` | 只有 `RFCOMM/BNEP/HIDP layer initialized` 协议栈，**无控制器** |

**判定依据**：WiFi+BT combo 芯片（如 RTL8723BU `0bda:b720`、RTL8821CU `0bda:c820`）会以**多接口**出现在 USB 上。本机 WiFi 只有 **1 个接口**，且 `0bda:0179` 属 RTL8188 纯 WiFi 系列（8188EU 驱动 ID 表原生含 `0179`）。**Android 自己也从未把蓝牙跑起来。**

> 结论：**这颗 WiFi 与蓝牙不同芯片 —— 因为整机根本没有蓝牙硬件**。`init.bigfish.rc` 里的 `mtkbt`/`rtk_btusb` 只是海思 SDK 通用配置，不代表本机有对应硬件。

---

## 六、红外：用户确认通用；差最后一环

- 硬件：SoC 内建 IR 接收器（Android `/proc/bus/input/devices` 有 `Hi keyboard`，`Bus=0000`）
- EmuELEC 内核**已内建 `hi_ir`**：`/sys/module/hi_ir` 存在、`/proc/kallsyms` 有 `ir_first_read_key`、`/proc/msp/ir` 全部协议（NEC/RC6/TC9012/Sony…）均为 `Enabled`、`/dev/hi_ir` 字符设备在
- 缺的只是**用户态读取程序**（Android 的 `ir_user` 是 bionic 二进制，移植到 glibc 会段错误）
- EmuELEC 自带 `/usr/lib/libhi_msp.so`，导出完整 `HI_UNF_IR_*` API → 可自研一个小的 glibc 程序读 `/dev/hi_ir` 并用 `uinput` 喂出输入事件

> 由于**红外遥控器通用**，只要补上这个用户态程序，任意 NEC 遥控器即可操作。

---

## 七、改动清单（已落盘，重启后保持）

| 路径 | 说明 |
|---|---|
| `/usr/bin/histb-emuelec-supervisor` | 补丁：启动 ES 前等待输入设备（备份 `.a4bak`） |
| `/etc/init.d/S96a4-inputrecover` | 新增：热插拔兜底守护 |
| `/storage/ee/config/.emulationstation/es_input.cfg` | ES 自动写入的手柄映射（6 条） |
| 本地 `emuelec/work/histb-emuelec-supervisor.orig/.new` | 原始与修补版脚本 |
| 本地 `emuelec/work/S96a4-inputrecover` | 守护脚本 |

回滚方法：`cp /usr/bin/histb-emuelec-supervisor.a4bak /usr/bin/histb-emuelec-supervisor && rm -f /etc/init.d/S96a4-inputrecover`
