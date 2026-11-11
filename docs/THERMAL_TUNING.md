# Hi3798M V100 盒子 —— CPU 频率/电压曲线标定（全量实测）

> 设备：Hi3798M V100（Hi3798MV100），4×Cortex-A7（`CPU part 0xc07`，28nm LP），Mali-450
> 固件：HiSTBAndroidV600R001C00SPC063（Android 4.4.2，kernel 3.10.84）
> 日期：2026-10-11　方法：`/proc/hisi/msp/pm_cpu` 控制节点 + cpufreq + `cpucheck` 确定性校验和

---

## 0. 一句话结论

| 问题 | 答案 |
|---|---|
| 四档频率的降压边界 | **600M→925mV、1.0G→1030mV、1.2G→1195mV；1.5GHz 不可得** |
| 降压能降多少温度 | 满载 **约 −2°C**；空闲 **约 −3°C** —— **收益有限** |
| 为什么最低 600MHz、能不能到 200MHz | **不能**：OPP 表只有 4 档、cpufreq 硬拒 <600MHz、无内核源码可加档 |
| 空闲为什么还热 | **不是 CPU 频率**：600MHz 空闲仍 68°C，是静态漏电 + 常开多媒体模块 |

---

## 1. 频率-电压曲线（逐档 25mV 下探，AVS 关闭）

| 频点 | 默认电压(AVS) | **最小稳定** | 可省 | 边界性质 |
|---|---|---|---|---|
| 600 MHz | 1040 mV | **925 mV** | 115 mV | **硬件钳位**：写 900 被自动抬回 925，**不会挂机** |
| 1000 MHz | 1130 mV | **1030 mV** | 100 mV | 写 **1005 即硬挂机**（日志停在 `[try] volt=1005`） |
| 1200 MHz | 1270 mV | **1195 mV** | 75 mV | 写 **1170 即硬挂机** |
| 1500 MHz | — | **不可得** | — | OPP 表列出 1500000，但 `scaling_cur_freq` 只到 1200000；`time_in_state` 里 1500000 = **0 tick** |

**判据**：`cpucheck 40` 的 64 位校验和在满负载下是否仍等于基准 `51d9d6c57cd2d58f`。
各稳定档在 4 核负载下连测 3 次，**校验和 100% 一致**。

**推荐值（带 +25mV 余量）**：600M=950 / 1.0G=1055 / 1.2G=1220 mV
**贴边值（激进）**：600M=925 / 1.0G=1030 / 1.2G=1195 mV

---

## 2. 热收益（同热态中途切换，隔离热惯性）

### 4 核满载 @1.0GHz
```
阶段1  1130mV  →  稳态 76~77°C
阶段2  1030mV  →  稳态 74~75°C        Δ ≈ −2°C
```

### 空闲（interactive，实际 load≈11~13：后台常驻）
```
空闲 @1.0GHz  →  稳态 70~71°C
空闲 @600MHz  →  稳态 68~69°C         Δ ≈ −3°C
```

**⇒ 关键**：把空闲频率从 1.0GHz 压到最低档 600MHz，**也只降 2~3°C**；而 600MHz 空闲仍 **68°C**。
这说明空闲高温来自 **SoC 静态漏电 + 常开硬件模块**（内核里 `[OmniVdecTask]DW / [VdecKernelThrea]DW / [HI_VPSS_Process]DW / [AoEngineTask]DW` 常年 D 状态，多媒体硬件块一直在跑），**不是 CPU 频率**。

⇒ 所以「空闲时降到 200MHz 降温」这个思路**不成立** —— 即便能做到，收益也 <1°C。

---

## 3. 为什么不能低于 600MHz（逐条查证）

| 关卡 | 事实 |
|---|---|
| **cpufreq 硬拒** | 写 `scaling_min/max_freq = 300000/400000` → 读回仍是 **600000**（cpufreq 核心按 OPP 表校验） |
| **OPP 表只有 4 档** | `scaling_available_frequencies = 600000 1000000 1200000 1500000`，没有更低档 |
| **无内核源码** | 加 OPP 必须改内核 DVFS/时钟表并重编译。`sdk/source/kernel/linux-3.10.y` 只是 **6 文件残桩**（仅 `cpufreq_interactive.c` 等）；`/home/mxz/aosp` 是 **Android 6 项目**、无 kernel 目录 |
| **无时钟树可查** | 内核未编 `clk` debugfs（`/sys/kernel/debug/` 下无 `clk/`），无法确认 PLL 分频器是否支持更低频率 |
| **裸写 `/proc` 会挂机** | `echo freq=<非合法值>` 走 `clk_set_rate` 直写 PLL，**驱动不做任何校验** → 已复现挂机（写 800000/900000 之类） |

**唯一出路**：拿到完整 3.10 内核源码或直接二进制改 `boot.img` 里的 OPP 表（本机有打包链，但 `boot_a6_v*.img` 属 **A6/Android 6** 项目，不能用于本机）。**且前提是先确认时钟硬件支持**。

---

## 4. `hpmoffset`（AVS 电压偏移）—— **存在但无效**

厂商驱动里有 `hpmoffset` 命令，我做了完整对照：

```
freq=600MHz:  offset = 0 / 4 / 8 / 12 / 16  →  空闲都是 1060mV，负载都是 1070mV
freq=1.0GHz:  offset = 0 / 4 / 8 / 12 / 16  →  空闲都是 1130mV，负载 1150~1160mV（噪声）
```

⇒ 值被**存下来**（`hpm offset = N` 会显示），但**没有接进电压计算**。**它不是可用的降压旋钮。**

⇒ 因此**唯一可用的降压途径就是直写 `volt=`**，而它的代价是 **强制关闭 AVS**（驱动 `CPUDebugCtrl()` 开头即 `CPU_AVS_Enable(HI_FALSE)`）。

---

## 5. 工具与用法

| 文件 | 作用 |
|---|---|
| `undervolt.sh` | `status` / `show`（曲线表）/ `apply`（安全余量）/ `edge`（贴边）/ `stock`（还原） |
| `curve5.device.sh` | 单频点降压扫描（设备端，带钳位检测、便携超时、日志先行） |
| `soak.device.sh` | 热收益对照（满载中途切压） |
| `idle.device.sh` | 空闲频率-温度对照 |
| `hpmtest.device.sh` | `hpmoffset` 有效性对照 |
| `cpucheck.c` / `cpucheck` | 确定性整型+内存负载，输出 64 位校验和（降压的"算错先于死机"判据） |
| `killload.sh` | 清残留在后台的 `while :` 负载进程 |

```bash
cd /e/A4-work/hijack
./undervolt.sh show      # 看曲线
./undervolt.sh apply     # 应用（推荐）
./undervolt.sh stock     # 还原
```

---

## 6. 踩过的坑（重要，避免重复）

1. **`/proc/hisi/msp/pm_cpu` 的 `freq=` 不做校验** —— 写非 600M/1.0G/1.2G/1.5G 的值会直写 PLL → **硬挂机**。v1 脚本用它"定频读默认电压"，结果 600MHz 电压配到 1.5GHz → 挂机。**铁律：永不写 `freq=`，频率一律走 cpufreq。**
2. **本机 busybox 1.16.1 没有 `timeout`，也没有 `seq`** —— 脚本里都得用守护进程 / `while` 循环替代。
3. **`$(func)` 命令替换里启动后台死循环会永久阻塞**（后台进程持有管道写端）。要用全局变量传 PID，并把负载进程的 stdin/stdout/stderr 全重定向到 `/dev/null`。
4. **`pkill -f 'while :'` 会自匹配**（自己的命令行里含该串）→ 把自己也杀掉。用独立脚本执行、用 `$$` 排除自身。
5. **`dumpsys SurfaceFlinger --latency` 的第 1、3 列相同，只有 col0 是可靠节奏**（早前用 col1 得出过"持续 8 分钟 20fps"的伪影结论）。
6. **写 `volt=` 会强制 AVS=Off** —— 之后 `volt` 读数就是设定值（不再被 AVS 覆盖）。所以做电压对照前必须先 `avs off`，否则读回的是 AVS 计算值。
7. **热惯性很大**：同一负载下，冷态 80°C vs 热饱和 98°C，**差 17°C**。做温度对照必须"中途切换"而不是"A/B 两段独立跑"。
8. **关电视（HDMI 无信号）会触发待机**：`persist.hdmi.suspend.enable=1` + `persist.sys.HDMISuspendEnable=true`，待机后网络断开、IP 会变（.18→.16）。测试期间需 `echo <name> > /sys/power/wake_lock` 锁住，并在 `wake_unlock` 写**名字**释放。
9. **设备没有硬件看门狗**（用户确认挂机只能人工断电）。
10. **`0x80001001` 是 `OMX_ErrorUndefined`，不是 `UnsupportedSetting`**（早期结论修正）。

---

## 7. 结论与建议

1. **降压可做，但收益有限**（满载 −2°C、空闲 −3°C）。若目标是"让盒子凉下来"，**降压不是主要手段**。
2. **`apply` 会自动关闭 AVS** —— 失去温度/硅片自适应补偿，所以脚本默认带 +25mV 余量。真要长期用，建议用 `apply`（安全版）。
3. **空闲高温的正解**：排查常开的多媒体/后台服务（`mediaserver`、DLNA/airsharing、当贝推送、`init.bigfish` 里的循环脚本），而不是压 CPU 频率。
4. **要低于 600MHz**：只能改内核（缺源码）。**不建议从裸写 `/proc` 硬试**。
5. **1.5GHz 追不到**：OPP 表列了但硬件/时钟给不出来（`time_in_state` 0 tick）。
6. `/proc` 写入**不持久**，重启即复原 —— 这既是它的安全之处，也意味着"长期降压"需要 boot 脚本（已落地，见 §8.4）。

---

## 8. 【2026-10-11 补充】降压必须"钉住 OPP"—— 否则写进去的电压会被内核抹掉

### 8.1 机制（读 PM 驱动源码 `msp/drv/pm/drv_pmoc_intf.c` 得到）

内核里有个 **`temperature_control_thread`**：温度回落时会执行
`cpu_volt_scale(cpu_freq_hpm_table[i].vsetting)`，把频率和电压**恢复成频压表的默认值**；
并且**任何 cpufreq 的 OPP 切换都会把 AVS 重新置 On**。

实测（`vbehav2.device.sh`）：

| 操作 | 结果 |
|---|---|
| 1.0GHz 下 `avs off` + `volt=1080` | `v=1080, avs=Off` ✅ 生效 |
| 再 `pin 600000`（切一次档） | `v=1040, avs=On` ❌ AVS 被重开 |
| 切回 1.0GHz | `v=1130, avs=On` ❌ 写的 1080 **彻底丢失** |
| 只写 `freq=600000`（不带 volt） | 频率变了但**电压留在原值**（危险路径） |

⇒ **"DVFS 在运行"与"手动降压"互斥。**

### 8.2 ✅ 可用配方（实测 5 分钟零漂移）

```sh
echo performance > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
echo F > /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq    # 钉住 OPP
echo F > /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq
echo avs off > /proc/hisi/msp/pm_cpu
echo volt=V  > /proc/hisi/msp/pm_cpu
```

保守电压（比实测边界高 45~50mV，防高温下硅片需更高电压）：
**600MHz=970 / 1.0GHz=1080 / 1.2GHz=1240 mV**

**代价**：丢掉 DVFS 降频（空闲不再落到 600MHz）。这是硬约束。

### 8.3 为什么不能"带 DVFS 的降压"

`cpu_freq_hpm_table[]` **内建在内核里**（PM 驱动不是 .ko：`/proc/modules` 里没有 pm 模块，
已加载的只有 wifi/fs 类；`/system/lib/modules` 里也没有）。要真正带 DVFS 降压，只能
**改内核镜像（boot.img）里那张频压表**，风险与工作量都大。

### 8.4 已部署到设备（开机自启）

| 位置 | 内容 |
|---|---|
| `/system/bin/daemonize` | 新写的小工具。本机 busybox 1.16.1 **无 nohup / 无 setsid**，adb 会话退出会 SIGHUP 杀掉后台任务 |
| `/system/etc/thermal_monitor.sh` | 长期监控：每 10s 记 `f/v/avs/T/load/GPU频率+util/vid`，每 60s 附 top；日志 `/data/local/tmp/thermal_monitor.log` |
| `/system/etc/uvmode.sh` | `on [freq]` / `off` / `status` |
| `/system/etc/init.thermal.sh` | 开机延 20s → 启动监控 → 若存在 `/data/local/tmp/uv_enable` 才降压（默认不开，避免"开机就挂"） |
| `/system/etc/init.bigfish.sh` | 末尾追加 `/system/etc/init.thermal.sh &`（原文件备份为 `init.bigfish.sh.orig`） |

主机侧：`deploy_thermal.sh {install|uv-on|uv-off|status|log|pull|uninstall}`。

### 8.5 1 小时视频负载 A/B

`exp1h.device.sh`：连续播放 `long4k.mp4`（HEVC 4K30，120s，每 122s 重启播放器不留空档），
4 阶段 × 15 min 交替 **STOCK / UV(1.0GHz@1080mV)**，阶段标记直接写进监控日志。
`watch_exp.sh` 后台守候，结束即拉日志并由 `analyze_exp.py` 输出 STOCK vs UV 温度对比。

### 8.6 ★ 1 小时 A/B 实测结果（2026-10-11）—— 降压收益只有 1~2°C

**协议**：连续播 `long4k.mp4`（HEVC 4K30，120s，每 122s 重启播放器不留空档），4 阶段 × 15min 交替
STOCK / UV(钉 1.0GHz@1080mV)。**播放期间两种模式 CPU 都恒在 1.0GHz ⇒ 同频对照，结论干净。**

| 阶段 | 电压(中位) | 温度 mean | 温度(后 1/3 中位) |
|---|---|---|---|
| P1 STOCK | 1142 mV | 80.1 °C | 82 °C |
| P2 UV | 1080 mV | 81.4 °C | 82 °C |
| P3 STOCK | 1146 mV | **83.9 °C** | **84 °C** |
| P4 UV | 1080 mV | **81.5 °C** | **81 °C** |
| **汇总** | **Δ = −64 mV** | **82.0 vs 81.5** | **Δ ≈ 1 °C** |

⇒ **降压 64mV 只换来 0.5~2°C**（P3→P4 那一下最干净：84→81，≈ −3°C）。
**视频负载下的温度平台 = 80~86°C**，并没有到 90~98°C。

**为什么收益这么小（定量解释）**：同频下降压 64mV → CPU 动态功耗 −11%；
实测温升（相对环境）只降约 1°C / 50°C ⇒ **CPU 仅占整机功耗约 20%**。
旁证：**纯 4 核 CPU 满载 @1.0GHz = 77°C**，而**视频播放（load 仅 14）= 84°C** ⇒
**VDEC / VPSS / DRAM 等视频管线模块的发热比 CPU 更大，降压打不到它们。**
`top` 里 CPU 占用第一是播放器 `com.dangbei.lerad.videoposter`，GPU util 恒 0。

**附带成本**：UV 模式把 OPP 钉在 1.0GHz ⇒ **空闲反而热约 2°C**（空闲 1.0GHz=70~71°C vs 600MHz=68~69°C）。
**⇒ 综合是平账甚至略亏。降压不是这台盒子降温的有效手段。**

### 8.7 开机自启（已真机验证）

**踩坑**：钩子加在 `init.bigfish.sh` **末尾无效** —— 该脚本会**卡在末尾的 `basicService -d`**
（实测重启 5 分钟后 `sh /system/etc/init.bigfish.sh` 仍在运行），末尾代码永远执行不到。
**修法**：钩子插到**开头**（shebang 之后一行）；`init.thermal.sh` 里加"等 /data 挂载"循环，
并在 `/data/local/thermal_boot_early.log` 写调用痕迹便于诊断。

**验证输出**：
```
/data/local/thermal_boot_early.log : 01-01 00:00:04 init.thermal invoked (pid=1443)
/data/local/tmp/thermal_boot.log   : /data ready after 0s
                                     monitor started pid=8868 (daemonize)
                                     uvmode: 未启用（无 /data/local/tmp/uv_enable）
```
