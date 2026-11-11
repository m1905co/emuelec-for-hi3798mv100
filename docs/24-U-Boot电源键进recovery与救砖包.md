# 24 — U-Boot 电源键检测 + 引导原厂安卓 recovery + 救砖包

日期：2026-10-16 ｜ 平台：Hi3798MV100 (mdmo1d) ｜ 状态：**离线验证完成，待上机**

---

## 0. 需求澄清（本轮用户纠正）

- 需求是"**多按几次电源键 → 进安卓的 recovery**"，**不是修改安卓 recovery**。
- `work/recovery_android.img` 是从 p3 分区**原样 dump 的只读副本**，仅用于解析验证（ANDROID! 头、page=2048、kernel uImage、ramdisk 偏移），证明原厂 recovery 具备 `adb sideload` 刷机能力。**未做任何字节修改，也不会回写它**（除非 p3 本身损坏，README 已单列兜底路径）。
- 本包改动范围：**p1（U-Boot）+ p2（env）**。p3 recovery 分区保持原样。

## 1. 实现

### 1.1 IR 电源键检测（Task 15）

复用 EmuELEC 用户态 daemon `a4-ird` 已验证的同一套裸寄存器操作（寄存器值来自安卓原厂 build）：

| 项 | 值 |
|---|---|
| IR 块基址 | `0xF8001000` |
| 时钟门控 | CRG `0xF8000048`，bit4=on / bit5=off（读-改-写，只动这两位） |
| 配置序列 | `IR_EN=1`（先，会重置内部默认）→ 等 2ms → `CFG=0x1F17`(NEC/32bit/fdiv23) → LEADS/LEADE/SLEADE/B0/B1 → INTM=0 → INTC=0xF |
| 活性检测 | 写 CFG 后回读，必须读到 `0x1F17`，否则判定 IR 块不可达并禁用检测 |
| 帧有效性 | NEC 互补校验 `b0^b1==0xFF && b2^b3==0xFF`（噪声拒绝） |
| 新帧判定 | `IR_INTS` 非零且自上次事件后曾观察到清零（该控制器 ack 后状态位仍保持，直接沿会重复计数） |
| 电源键码 | `0x23dc4db2`（与 learn 结果一致，且与原厂 U-Boot `sw_ir_detect_recovery` 的五个魔数之一相同） |
| 去抖 | 同码 350ms 内只计一次 |

窗口逻辑（env 可调）：

- 无操作 → 等 `a4key_ir_ms`（默认 3000ms）后放行，**正常启动只损失这 3 秒**；
- 检测到第 1 次有效按键 → 总窗口放宽到 `a4key_ir_tmo`（默认 10000ms）凑够 `a4key_ir_count`（默认 3）次；
- 达到次数 → 返回 recovery 触发；窗口耗尽 → 正常启动。

现场验证命令：`a4irtest [秒]`（轮询打印所有解码帧，标记电源键）。

### 1.2 引导原厂 recovery（Task 16）

依据（离线确认的三条证据链）：

1. **分区表**（安卓内核 cmdline 实测）：`1M(fastboot),4M(bootargs),16M(recovery),1M(deviceinfo),4M(baseparam),4M(pqparam),4M(logo),16M(fastplay),8M(misc),24M(factory),12M(kernel),8M(iptv_data),340M(backup),340M(cache),520M(system),-(userdata)` → **recovery = p3 @ sector 0x2800**。
2. **recovery 镜像头**（本地 dump 解析）：magic `ANDROID!`、page=2048、kernel_size=2,563,176（**uImage 格式**，magic 0x27051956 @ +0x800，与原厂 `bootm 0x10000800` 可用互为印证）、ramdisk_size=957,395 @ 镜像内偏移 0x272800、ramdisk_addr=0x04E00000、镜像总 5,243,140 B。
3. **SDK bootm 路径**（源码）：`bootm <kernel> <initrd>` 两参数走 ATAG INITRD2 标准交接（原厂安卓 bootcmd 同款）；SDK 的 `bootimg_get_ramfs` 也是把 ramdisk memmove 到头的 `ramdisk_addr`。

执行序列（`a4_boot_recovery_android()`，全部 env 可覆盖）：

```
mmc read 0 0x10000000 0x2800 0x3000     # 读 p3 前 6 MiB（镜像 5 MiB，留余量）
校验 ANDROID! 魔数 → 解析 kernel_size / ramdisk_size / ramdisk_addr / page_size
memcpy(ramdisk_addr, img + roundup(page+kernel_size), ramdisk_size)   # 同 SDK 行为
保存现场 bootargs → a4_bootargs_prev
setenv bootargs = recoverybootargs（原厂值，已写入新 env）
bootm 0x10000800 0x04E00000
```

失败（魔数不符 / mmc read 失败 / bootm 返回）→ 打印原因并**落回 U-Boot 提示符**，不会卡死。

### 1.3 触发器汇总（a4_bootguard_early）

| # | 触发源 | 默认 |
|---|---|---|
| 1 | env `a4_recovery=1` | 关 |
| 2 | GPIO 长按（`a4key_gpio`） | 关（未配引脚） |
| 3 | **IR 电源键连按 3 次**（本轮新增） | **开** |
| 4 | 启动失败计数超 `a4_bootlimit` | 关（limit=0） |

## 2. 构建与离线验证（Task 17）

构建：`source/boot && make CFG_HI_ARM_TOOLCHAINS_NAME=arm-linux-gnueabihf`（WSL Ubuntu，交叉 gcc 11.4.0，与上次同工具链）。

| 验证项 | 方法 | 结果 |
|---|---|---|
| 镜像大小/CRC | `fastboot-burn.bin` 481,284 B，CRC32 `f23d8380`，md5 `25ee466f…` | ✅ |
| 厂商头一致性 | 头 16 B `190800ea14f09fe5…` 与设备 p1 原厂备份逐字节一致 | ✅ |
| A4 字符串 | `a4irtest`、`a4key_ir_code`、`a4_recovery_boot`、`23dc4db2`、`A4: IR power-key check`、`A4: reading Android recovery` 等 18 项全部命中 | ✅ |
| 符号 | `a4_bootguard_early`(c0def8) / `a4_bootguard_enter_recovery`(c0e2d4) / `a4_ir_setup`(c0d500) / `a4_ir_poll`(c0d470) / `a4_env_ulong_hex` 在 ELF 符号表 | ✅ |
| 调用链 | `main_loop`(c19c9c) → `bl a4_bootguard_early`@c19cfc；→ `bl a4_bootguard_enter_recovery`@c19fa0；early 内含 `bl a4_ir_setup`/`bl a4_ir_poll`（key_hit 被内联）；enter_recovery 内 3× `run_command`（recovery_cmd / mmc read / bootm） | ✅ |
| env 生成 | CRC 算法 `crc32(d[4:])==hdr` 在既有 env 上验证通过；新 env round-trip 逐键一致 | ✅ |
| recovery 头解析 | Python 复算 ramdisk 偏移 0x272800 / uImage magic / 镜像覆盖，与 C 逻辑一致 | ✅ |

## 3. 救砖包（Task 18）

`work/rescue-kit/`：

| 文件 | 作用 |
|---|---|
| `01-fastboot-uboot.bin` | 新 U-Boot（481,284 B） |
| `02-env-android.bin` / `02-env-emuelec.bin` | 两份 env，已含 A4 默认键 + `recoverybootargs`（原厂值） |
| `03-recovery-fallback.img` | p3 原厂 dump（**兜底**，README 第 5 节） |
| `99-uboot-stock-backup.bin` | 原厂 U-Boot 回滚件 |
| `flash.sh` | 安卓 root 侧刷入（只写 p1/p2，自动备份） |
| `README.md` | 刷入 / 验证 / 救砖操作 / 兜底 / env 参数表 / 已知边界 |

救砖流程：**断电 → 上电 → 3 秒内连按电源键 3 次 → 原厂安卓 recovery → `adb sideload update.zip`**。

## 4. 置信度分级

| 结论 | 等级 | 依据 |
|---|---|---|
| IR 寄存器序列有效 | **高** | 与 EmuELEC 上已实测的 a4-ird 逐寄存器一致 |
| 电源键码 0x23dc4db2 | **高** | learn 实测 + 与原厂 U-Boot 魔数交叉印证 |
| recovery 头解析/引导参数 | **高** | 本地 dump 解析 + SDK bootm 源码路径 |
| 3 秒窗口可接受 | 中 | 未实测用户体感；`a4key_ir_ms=0` 可关 |
| 端到端（按键→recovery 界面） | **待上机** | 无运行时证据 |
| 上电 3 秒内 IR 块可达（冷启时钟状态） | **待上机** | CRG 读-改-写理论覆盖冷/热启，未实测 |

## 5. 负向结果与风险（如实记录）

- **每次正常启动多约 3 秒**（IR 首键窗口）。这是"无硬件 GPIO 触发源"的代价；可 `setenv a4key_ir_ms 0` 关闭 IR 检测。
- **误触风险**：上电 3 秒内连按 3 次电源键会进 recovery。正常开机不会这样按，但需告知用户。
- `bootm` 的 ramdisk 加载用镜像头里的 `ramdisk_addr=0x04E00000`——该地址在 1 GiB RAM 内且不与加载区（0x10000000 暂存 / 0x2000000 kernel）重叠，但**未经运行时验证**。
- **sideload 包已确认**：用户提供的 `update_hisi_full_v2.zip`（297 MB）就是本机原厂安卓完整包。其 `recovery.img` 与设备 p3 dump **md5 逐字节一致**（`75eea454…`），`boot.img` 与设备 stock boot 一致，`fastboot.img` 与设备 p1 前 618,444 B 一致——即"本机原厂包"无疑。
- ⚠️ **该包 updater-script 末尾会 `package_extract_file("fastboot.img", by-name/fastboot)`——sideload 后 U-Boot 刷回原厂，电源键 recovery 能力消失**。标准流程两步：sideload 救砖 → 安卓起来后重跑 `flash.sh` 刷回新 U-Boot。不建议改包内 fastboot.img（新 U-Boot 未上机 + 全包刷机两个未验证变量叠加）。

## 6. 下一步

1. 上机：`flash.sh` 刷 p1/p2 → 重启 → 串口看 `A4: IR power-key check` 行 → `a4irtest` 验证键码 → 实测连按 3 次进 recovery。
2. sideload 包用用户持有的 `update_hisi_full_v2.zip`（原厂全包，已验证与本机镜像一致）；恢复后需重跑 flash.sh 刷回新 U-Boot。
