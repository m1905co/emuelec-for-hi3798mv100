# 海纳思（hinas / haiNAS）U-Boot 源码定位报告

日期：2026-10-15
目标：找到海纳思项目的 U-Boot 源码，并确认它是否具备"按键进 recovery"能力。
结论：**源码已找到并完整落地到本地（可编译）**；**但海纳思这条线从来没有按键 recovery 特性**，它是原厂 Android U-Boot 独有的。

---

## 1. 海纳思是什么

| 项 | 内容 |
|---|---|
| 名称 | 海纳思系统（HiNAS / hinas），用户口述的 "haiNAS" |
| 定位 | 把海思/Amlogic 机顶盒改造成低功耗 Linux NAS（Ubuntu 20.04/22.04 base） |
| 官网 | `ecoo.top`、`hinas.top` |
| 社区 | `bbs.histb.com` |
| 固件下载 | `dl.ecoo.top`、`alist.ecoo.top`、`hinas.top/download` |
| 我们盒子用的包 | `mv100-mdmo1d-usb-flash.zip`（官方页对应的正是 mdmo1d USB 刷机包，本地已有一份解包目录） |

---

## 2. 找到的源码仓库（含实测可达性）

> 本机实测：**GitHub 直连被墙**（`git clone` 到 443 超时），但下面几条通道全部可用：
> - Gitee 直连
> - `https://ghfast.top/https://github.com/...`（也可用 `ghproxy.net`、`gh-proxy.com`）
> - `https://cdn.jsdelivr.net/gh/<user>/<repo>@master/<path>`（可取单文件）

| 用途 | 仓库 | 版本 / 说明 |
|---|---|---|
| **U-Boot 源码（独立）** | `github.com/tegzwn/HiSTB-Uboot`（fork：`glinuz/HiSTB-Uboot`） | HiSTBLinuxV100R005C00SPC050 |
| **完整 SDK（U-Boot + configs + DDR reg + rootfs 脚本）** | `github.com/glinuz/hi3798mv100` | HiSTBLinuxV100R005C00SPC041B020；Gitee 镜像 `gitee.com/fogpine/hi3798mv100`、`gitee.com/dearxjoe/hi3798mv100` |
| 更新版 SDK | `github.com/syl199312/HiSTBLinuxV100R005C00SPC060` | 内核 4.4.35（26 年新版）；Gitee `gitee.com/carollwell/hi3798m` |
| U-Boot 主线 fork | `github.com/histb-mainline/u-boot` | Hi3716/Hi3796/Hi3798 主线化分支 |
| 内核源码 | `github.com/tegzwn/HiSTBLinuxKernel` | 配套内核 |

---

## 3. 已落地到本地（可编译的完整源码）

```
E:\A4-work\emuelec\work\uboot_src\
├── HiSTB-Uboot\                     # 15MB / 1185 文件，独立 U-Boot 树
│   └── include\configs\godbox.h     # 板级配置头（含 CONFIG_AUTOBOOT_KEYED）
├── HiSTBLinux-SDK\                  # Gitee 稀疏克隆，80MB
│   └── HiSTBLinuxV100R005C00SPC041B020\
│       ├── source\boot\fastboot\            # ★ 完整 U-Boot 源码
│       │   └── common\bootstrap.c           # ★ recovery / USB 强刷实现
│       ├── configs\hi3798mv100\
│       │   ├── hi3798mdmo1d_hi3798mv100_cfg.mak   # ★ 我们这块板的官方板级配置
│       │   └── prebuilts\{bootargs.txt, emmc_partitions.xml, baseparam.img, logo.img, pq_param.bin}
│       └── source\boot\sysreg\hi3798mv100\
│           └── hi3798mdmo1d_hi3798mv100_ddr3_2gbyte_8bitx4_4layers_emmc.reg   # ★ 与设备打印值逐字一致
```

编译方式（SDK 侧）：`make hiboot`；独立树侧：`make ARCH=arm CROSS_COMPILE=arm-histbv310-linux- hi3798mx`（或 `godbox`）。工具链 `arm-histbv310-linux`。

---

## 4. 关键技术事实（含对我此前一个错误结论的更正）

### 4.1 设备上那份 U-Boot 是谁编的

`work/p1_new.bin` 里的版本串：

```
Fastboot 3.3.0_ecoo_81082668-dirty (ecoo@ecoo) (Aug 26 2025 - 13:34:16)
Hi3798Mv100
hi3798mdmo1d_hi3798mv100_ddr3_2gbyte_8bitx4_4layers_emmc.reg
```

⇒ **就是海纳思（ecoo）自己编的**，基线正是上面这批 HiSTBLinux SDK 的 fastboot（U-Boot）。官方 `mv100-mdmo1d-usb-flash/mv100/fastboot.bin` 是同一个构建（同样 `Aug 26 2025 13:34`）。

### 4.2 ★更正：当前 U-Boot **是带 recovery 代码的**

我之前说过"当前 U-Boot 没有 recovery"——**那是错的**，来源是我那条 grep 漏写了 `recovery` 关键字。重新实测：

`p1_new.bin` 中**确实包含**：`recovery.img`、`recoverybootargs`、`malloc recovery_boot_args failed !`。

源码位置 `source/boot/fastboot/common/bootstrap.c`：

```c
/* bootargs_change() —— 若 env 有 recoverybootargs 则覆盖 bootargs */
if (getenv("recoverybootargs")) { ... setenv("bootargs", recovery_boot_args); ... }

/* download_process_usbhost() —— USB 恢复路径 */
bootargs_change();
ret = download_image(CONFIG_FILE_RECOVERY_NAME);   /* "recovery.img" */
/* download_image(): usb_file_check() -> usb_file_read() -> "bootm <addr>" */
```

即海纳思 U-Boot 的恢复方式是 **USB 强刷**：把 `recovery.img` / `bootargs.bin` 放 U 盘根目录，进 bootstrap 后它自己读进来 `bootm` 启动。

**触发条件**（`is_bootstrap()`）：

```c
if (CONFIG_START_MAGIC == readl(REG_START_FLAG)) return 1;
```

这是 **SoC 寄存器标志**（由 BootROM / HiTool / 短接或开机键的硬件路径置位），**不是 U-Boot 里的按键扫描**。

### 4.3 海纳思这条线**没有**按键 recovery

对整份 bootloader 源码 grep `sw_ir` / `irdetect` / `ir_detect` / `key_scan` / `gpio_key` / `keypad` / `remotectl`：**只命中无关代码**（`mach-types.h`、`usb_kbd.c`、`twl4030.h`）。mdmo1d 板级配置里也明确：

```
# CFG_HI_BUILD_WITH_IR is not set
```

而原厂 U-Boot 备份 `work/p1p2_backup/p1_cur.bin`（`HiSTBAndroidV600R001C00SPC064_v2016060803`，`Fastboot 3.3.0-00786-g908d79f (root@HW-TV-S3) Aug 06 2016`）里**明确有**：

```
boot-recovery
The recovery verify OK! / The recovery verify failed.
***** boot from first-recovery... ******  /  ***** boot from second-recovery... ******
```

⇒ **"按住遥控键上电 → 进 recovery"是原厂 Android U-Boot 的 `sw_ir_detect_recovery` 独有特性**，海纳思的 U-Boot 从来没有它、也**不是我删掉的**。之前 report/12 §6 那句"按住遥控键上电 → recovery"属于原厂时代残留，在换纯 U-Boot 后就已失效——这点是我当时没有及时更正并提醒。

### 4.4 「按键打断自动引导」是另一件事，而且本来就有

`godbox.h`：

```c
#if 1 /* Enable Ctrl+C to stop autoboot.*/
#  define CONFIG_AUTOBOOT_KEYED      1
#  define CONFIG_AUTOBOOT_PROMPT     "Press Ctrl+C to stop autoboot\n"
#  define CONFIG_AUTOBOOT_DELAY_STR  "hisilicon #"
#  define CONFIG_AUTOBOOT_STOP_STR   "\x03"     /* Ctrl+C */
#endif
```

U-Boot 的 `CONFIG_AUTOBOOT_KEYED` 支持"按键序列"打断自动引导，但它读的是 **stdin**；本机 `stdin=serial` ⇒ **只有串口能打断**，遥控/面板键进不来（若把 stdin 指向 USB 键盘设备理论可行，但本机 USB 侧未使能该路径）。

### 4.5 我们这块板的官方板级参数（mdmo1d）

```
CFG_HI_CHIP_TYPE=hi3798mv100
CFG_HI_BOOT_REG_NAME=hi3798mdmo1d_hi3798mv100_ddr3_2gbyte_8bitx4_4layers_emmc.reg
CFG_HI_OUT_DIR=hi3798mdmo1d
CFG_HI_ARM_TOOLCHAINS_NAME=arm-histbv310-linux
CFG_HI_UBOOT_SUPPORT=y     CFG_HI_BOOT_USB_SUPPORT=y     CFG_HI_EMMC_SUPPORT=y
CFG_HI_BOOT_ENV_STARTADDR=0x100000   CFG_HI_BOOT_ENV_SIZE=0x10000
CFG_HI_IR_TYPE_S2=y        （与之前 IR 研究结论一致：IR 是 S2 型）
# CFG_HI_BUILD_WITH_IR is not set
```

---

## 5. 关于"把按键进 recovery 加回来"，三条可选路径

| 方案 | 做法 | 代价 / 风险 |
|---|---|---|
| **A. 恢复原厂 U-Boot** | 用本地 `p1p2_backup/p1_cur.bin` 刷回 p1 | 按键 recovery 回来了；但**双系统模型作废**（原厂只认 p11 内核槽 + RSA/尺寸校验） |
| **B. 改海纳思 U-Boot 源码加按键检测** | 在 `board/hi3798mx/board.c` 或 `common/board.c` 早期阶段读 GPIO/IR（或复用现有 `CONFIG_AUTOBOOT_KEYED` 的 stop 串机制，把 stdin 指到按键设备）→ 命中则 `setenv bootcmd` 指向 recovery 或置 bootstrap 标志 | **源码齐了、可以自己编**；但需：正确工具链 `arm-histbv310-linux`、正确的 `.reg`、以及**可用的烧写通道**（当前设备只能靠串口/HiTool） |
| **C. 软件级安全网（不碰 U-Boot）** | EmuELEC 侧做启动失败计数器，连续 N 次起不来就改写 env 切到 Android | 覆盖"rootfs/init 坏了"，U-Boot/内核层坏了仍需串口；但**风险最低、不需要刷写 U-Boot** |

**建议**：先 C（低风险、能立刻做），B 作为长期方案在串口可用后再做。A 只在"确定放弃双系统"时选。

---

## 6. 现状限制（必须说明）

不管选哪条，**当前盒子要恢复/重刷 U-Boot，都必须先用 TTL 串口（115200）进入 `fastboot#` 提示符**，或用 HiTool 走 USB/JTAG。源码在手 ≠ 能刷进去——**物理通道仍然卡在串口线上**。

现有可用资产：
- 串口工具：`E:\MGXLVF\Downloads\CH340G下载线资料`、`HITOOL5.3.12`、`海思…HITOOL版本5.3.12.zip`
- 全量分区表：`emuelec\EC6108V9C-…\emmc_Hi3798MV100-full-user-area.xml`、`emuelec\work\portdist\emmc_Hi3798MV100-mdmo1d-rootfs-1G.xml`
- 原厂 U-Boot 备份、两个 env 块（CRC 已验证）、`p1_new.bin`
- 海纳思官方刷机包：`emuelec\mv100-mdmo1d-usb-flash\`（含 `fastboot.bin`、`bootargs.bin`、`hi_kernel.bin`、`baseparam.img`、`logo.img`、`pq_param.bin`、`recoverybox32.ext4`、`www_ecoo_top.ext4`）
