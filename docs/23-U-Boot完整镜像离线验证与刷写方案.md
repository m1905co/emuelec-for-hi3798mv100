# 23 · U-Boot 完整镜像离线验证 + 刷写方案

日期：2026-10-16
镜像：`emuelec/work/uboot_src/build-out/fastboot-burn-sdk-full.bin`
来源：**HiSTBLinux SDK 原生构建**（`source/boot && make CFG_HI_ARM_TOOLCHAINS_NAME=arm-linux-gnueabihf`），
含 `source/boot/product` 产品库（区别于早前 248 KB 的"验证件"）。

---

## 1. 离线验证结果：全部通过

### 1.1 改动确实进了这棵树

| 项 | 结果 |
|---|---|
| 源文件 | `common/a4_bootguard.c`（11,525 B）、`include/a4_bootguard.h`（3,127 B）存在 |
| 构建接入 | `common/Makefile:46  COBJS-$(CONFIG_A4_BOOTGUARD) += a4_bootguard.o` |
| 调用钩子 | `common/main.c:423 a4_bootguard_early()`、`:441 a4_bootguard_enter_recovery()` |
| 配置开关 | `include/configs/hi3798mx.h:483 CONFIG_A4_BOOTGUARD 1`；`include/autoconf.mk:71 CONFIG_A4_BOOTGUARD=y` |

### 1.2 产物属性

| 项 | 值 |
|---|---|
| 大小 | **477,104 B**（0x747B0） |
| md5 | `bef60c9302925dac4708a5d16d77bfb3` |
| CRC32 | `0x94271f7a`（按 512 字节对齐补 0xFF 后为 `0xc0744461`） |
| 版本串 | `Fastboot 3.3.0-dirty (mxz@) (Oct 16 2026 - 07:18:47)` |
| SDK 版本 | `HiSTBLinuxV100R005C00SPC041B020_20161028` |
| DDR reg | `hi3798mdmo1d_hi3798mv100_ddr3_2gbyte_8bitx4_4layers_emmc.reg`（**与设备 U-Boot 启动打印逐字一致**） |

### 1.3 A4 功能字符串（镜像内实测）

全部命中：`a4key_gpio`、`a4key_active`、`a4_recovery`、`a4_bootlimit`、`a4_recovery_cmd`、
`a4bootinfo`、`a4bootok`、`a4recovery`、`a4keytest`、
`A4 boot guard:`、`A4:   RECOVERY MODE - autoboot skipped`、
`A4: hold-key check on %d pin(s), %d ms, active-%s`、
`A4: bootlimit %lu exceeded (count %lu), forcing recovery`、`A4: key test done ...` 等。

（早前我按 `A4: entering recovery` 检索显示"缺失"，那是我检索词写错了，源码里的横幅是上面这几条，实际都在。）

### 1.4 符号与调用点（反汇编确认"真的被调用"）

```
00c0d97c T a4_bootguard_early
00c0dbb8 T a4_bootguard_enter_recovery
00c0dc88 T a4_bootguard_keytest
00c70d50 D __u_boot_cmd_a4keytest      00c70d6c D __u_boot_cmd_a4recovery
00c70d88 D __u_boot_cmd_a4bootok       00c70da4 D __u_boot_cmd_a4bootinfo

c192ec: ebffd1a2  bl  c0d97c <a4_bootguard_early>        ← main_loop 内
c19590: ebffd188  bl  c0dbb8 <a4_bootguard_enter_recovery>  ← main_loop 内
```

### 1.5 与原厂 hinas 镜像的结构对比

| | 大小 | 头 16 字节 | 尾 16 字节 |
|---|---|---|---|
| 我们构建 | 477,104 | `190800ea14f09fe514f09fe514f09fe5` | `696c2e00...08000000` |
| 原厂 | 539,272 | `190800ea14f09fe514f09fe514f09fe5` | `696c2e00...08000000` |

**头/尾 16 字节完全一致**（ARM 向量表 + 镜像尾部结构），说明产物是格式正确的 U-Boot 镜像。
大小差异来自编译器不同（WSL `arm-linux-gnueabihf-gcc` 11 vs 官方 `arm-histbv310-linux`），属预期。

### 1.6 命令集可用性（两份 U-Boot 都有）

`bootm  cp  crc32  fatload  go  loadb  loady  mmc  mw  printenv  reset  saveenv  setenv  usb`
（`mmc` 带 read/write 子命令；`loady` = 串口 YMODEM）

---

## 2. 分区表（HiTool XML 解析得到）

| # | 名称 | 起始 | 长度 | 说明 |
|---|---|---|---|---|
| 1 | **fastboot** | **0 MiB** | 1 MiB | **U-Boot 所在分区（p1）** |
| 2 | bootargs | 1 MiB | 1 MiB | env 分区（p2），env 在其内偏移 `0x100000` |
| 3 | baseparam | 2 MiB | 4 MiB | |
| 4 | pqparam | 6 MiB | 4 MiB | |
| 5 | logo | 10 MiB | 4 MiB | |
| 6 | kernel | 14 MiB | 20 MiB | |
| 7 | recovery | 34 MiB | 64 MiB | |
| 8 | backup | 98 MiB | 512 MiB | Android 编号里的 p13 = EmuELEC rootfs |
| 9 | rootfs | 610 MiB | 6846 MiB | EmuELEC rootfs（p9） |

env 偏移 `0x100000` 与设备启动打印的 `Env Offset: 0x00100000` 吻合，分区表可信。

---

## 3. 刷写方案（全程从 TTL 串口的 U-Boot 提示符操作）

### 3.0 前置条件

- CH340 TTL 接好，**COM3 / 115200 8N1**
- 本地准备好：`fastboot-burn-sdk-full.bin`、`p1_new.bin`（当前设备 U-Boot，回滚用）、`p1_cur.bin`（原厂 U-Boot，回滚用）
- PC 侧需一个 **YMODEM 发送器**（我可以用 Python 写）

### 3.1 精确数字

| 项 | 值 |
|---|---|
| 镜像大小 | 477,104 B = `0x747B0` |
| 扇区数 | **932** = `0x3A4` |
| 镜像 CRC32 | `0x94271f7a` |
| p1 起始扇区 | **0**（0 MiB） |
| RAM 基址 | 新镜像 `0x40000000`；备份 `0x42000000`；回读校验 `0x43000000` |

### 3.2 步骤

```sh
# 1) 上电，3 秒内串口发 Ctrl+C 打断自动引导 → 进入 fastboot#
fastboot# mmc dev 0

# 2) 先把当前 U-Boot 读出来备份（1 MiB = 2048 扇区）
fastboot# mmc read 0x42000000 0 0x800
fastboot# crc32 0x42000000 0x80000        # 记下，和本地 p1_cur.bin/p1_new.bin 比对，确定本地哪份是回滚基准

# 3) 用 YMODEM 把新镜像传到内存
fastboot# loady 0x40000000                # 然后在 PC 侧发送 fastboot-burn-sdk-full.bin

# 4) 校验上传内容
fastboot# crc32 0x40000000 0x747b0        # 必须等于 0x94271f7a，不等就重传

# 5) 写入 p1（扇区 0 起，932 扇区；分区有 2048 扇区，不会越界）
fastboot# mmc write 0x40000000 0 0x3a4

# 6) 回读校验（写成功的唯一可靠证据）
fastboot# mmc read 0x43000000 0 0x3a4
fastboot# crc32 0x43000000 0x747b0        # 必须仍等于 0x94271f7a

# 7) 重启
fastboot# reset
```

### 3.3 回滚

重跑 3.2，把第 3 步的文件换成 `p1_new.bin`（当前 U-Boot）或 `p1_cur.bin`（原厂 U-Boot）即可。
`p1_cur.bin` 是 1 MiB 全分区备份，写入用 `mmc write 0x42000000 0 0x800`。

### 3.4 风险与兜底

| 风险 | 兜底 |
|---|---|
| 扇区算错 / 写坏 | **HiTool USB 全量刷回**（`HITOOL5.3.12` + `emmc_Hi3798MV100-full-user-area.xml` 分区表 + `01-fastboot-1M.bin` 都在本地）；也可 JTAG |
| 新 U-Boot 引导失败 | 串口 Ctrl+C 进 `fastboot#` 回滚；若连提示符都进不去 → HiTool |
| 新 U-Boot 与 env 不兼容 | env 未动（`a4_*` 全是新变量，缺省即关闭），最坏情况是不生效，不影响启动 |

---

## 4. ★ 刷了到底买到什么（诚实评估）

| 功能 | 本机是否可用 |
|---|---|
| **按住物理键开机 → 停在 `fastboot#` 提示符** | **不可用** —— 用户已确认**这台盒子没有实体按键**，U-Boot 里也没有 IR 驱动，没有按键源可判 |
| **连续 N 次启动失败 → 自动回退** | 可用（需设 `a4_bootlimit`） |
| `a4_recovery=1` / `a4recovery on` 强制进恢复 | 可用 |
| 串口 `fastboot#` 交互入口 | **当前 U-Boot 本来就有**（`bootdelay=3` + `stdin=serial`），刷不刷都有 |

**结论**：本机没有物理按键，所以"按键进 recovery"这个最初的目标在这台盒子上**没有可用的触发源**。
刷新的主要收益只剩"启动失败自动回退"和几条诊断命令，而风险是可能变砖（需要 HiTool 兜底）。
**建议：除非要做启动失败自动回退，否则不刷。**

若决定要这个功能，还需在上机后配置：
```sh
setenv a4_bootlimit 3        # 连续 3 次启动失败才回退
setenv a4_recovery_cmd 'echo use: bootm / mmc read to boot manually'
saveenv
```

---

## 5. 本地资产清单

| 文件 | 说明 |
|---|---|
| `build-out/fastboot-burn-sdk-full.bin` | 完整 SDK 构建产物（477,104 B，md5 `bef60c93…`） |
| `build-out/fastboot-burn.bin` | 早前验证件（248,752 B，缺 product 库，**不建议刷**） |
| `build-out/u-boot-sdk-full` | 对应 ELF（带符号，供反汇编） |
| `a4-bootguard.patch` | 改动补丁（8 文件 / +600 行） |
| `HiSTBLinux-SDK/.../source/boot/fastboot/` | 已打补丁的完整 U-Boot 源码树 |
| `work/p1_new.bin` | 当前设备 U-Boot（557,056 B，CRC32 `0xadb43150`） |
| `work/p1p2_backup/p1_cur.bin` | 原厂 U-Boot 全分区备份（1 MiB，CRC32 `0xe00d4850`） |
| `emuelec/mv100-mdmo1d-usb-flash/mv100/fastboot.bin` | 原厂 hinas 版 U-Boot（539,272 B） |
| `HITOOL5.3.12` + `emmc_Hi3798MV100-full-user-area.xml` | USB 全量刷回工具与分区表 |
