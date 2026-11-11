# A4 双系统（Android / EmuELEC）阶段报告 — 2026-10-12

## 0. 当前状态（先看这段）

**盒子卡在开机第一屏，需要 recovery 刷机救援。** 不是硬砖：`update.zip` 的 updater-script 会
`package_extract_file("boot.img", ".../by-name/kernel")`，而 **by-name/kernel = p11**，
刷一次就还原成安卓。本次事故与 2026-10-08 那次「重打包 boot.img 写 p11 → 卡第一屏」**现象完全一致**。

### 救援步骤（用你 10-08 用过的同样方式）
1. 把 **`E:\A4-work\update.zip`**（306,139,006 B）拷到 U 盘 / SD 卡根目录，**文件名必须正好是 `update.zip`**。
   （想带你自己的改动就换 `E:\A4-work\update_hisi_full_v2.zip`；两个包我都验过：testzip 通过、都写 p11。）
2. 插卡，进 recovery，刷入，等它自动重启。
3. 回到安卓后 adb/telnet 会恢复（`192.168.31.16:23` 免密 root；adbd 若没起可 `setprop service.adb.tcp.port 5555; stop adbd; start adbd`）。

**p2 的 env 不挡救援**：它仍是合法 stock 布局（blkdevparts 16 分区未改），只在 `bootargs_1G`
尾巴多了个 `a4os=` 标记；recovery 用的是自己的 cmdline。

---

## 1. 为什么卡第一屏（已取证的硬结论）

在设备上做了 3 组对照实验，结论是硬事实不是猜测：

| 实验 | 做法 | 结果 |
|---|---|---|
| A | 把 p11 内容写进 p8（这正是 env `bootcmd` 指向的位置）后重启 | cmdline 无任何变化 → **U-Boot 没执行 env 的 bootcmd** |
| B | 把「安卓 zImage+ramdisk」打成 uImage 放进 p8 | 仍不从 p8 启动 |
| C | 把 env `bootargs` **和** `recoverybootargs` 里的 `16M(fastplay)…12M(kernel)` 改名成 `16M(kernel)…12M(android)` | 仍从 **p11** 启动 → **名字不参与决策** |
| D | 只改 `bootargs_1G` 加标记 | 标记出现在 `/proc/cmdline` → env 被读，**只有 bootargs_<DRAM> 会被追加进内核 cmdline** |

⇒ **这台盒子的 U-Boot 从固定偏移（p11，82MiB..94MiB）加载内核，env 无法把它指到别处。**

U-Boot（= update.zip 里的 `fastboot.img`，
`Fastboot 3.3.0-00786-g908d79f-dirty`, HiSTBAndroidV600R001C00SPC064）里的相关字符串，
说明它自带内核校验/加载逻辑：

```
Enter fun Android_Main / bootcmd / bootimg 0x1FFBFC0
read misc failed / boot-recovery / find the boot-recovery flag... / sw_ir_detect_recovery
[HMT] read the kernel failed. / The kernel size is [%d]
[HM T] RSA Verify the kernel Error. / [HMT] Check RSA ERROR!!      ← 256 字节 hex RSA 模数内嵌
******** boot from kernel...******** / first-recovery / second-recovery / bootimg recovery/normal
bootargs.bin /  bootargs crc failed !                              ← env CRC 是 U-Boot 在校验
```

把自建 EmuELEC 镜像（Android! 头 + EmuELEC 4.4 内核 uImage + 最小 ramdisk + rootfs cmdline，
构造方式已用「原厂 boot.img 重建 → 逐字节完全一致」证明结构无误）写进 p11 后卡第一屏，
最合理的解释就是 **U-Boot 的内核校验（尺寸/RSA）不接受外来内核**。
`verify=n` 只关 uImage 头/数据 CRC，管不住这条。

---

## 2. 已经做完并且**仍然留在盒子上**的东西（这次不算白干）

| 位置 | 内容 | 说明 |
|---|---|---|
| p8 (16MiB@34MiB) | 原厂 Android boot.img 备份 | 回去的路 |
| p10 (24MiB@58MiB) | 自建 EmuELEC boot.img（10,868,736 B） | 出去的路 |
| p13 (340MiB@102MiB) | **EmuELEC rootfs**（ext4，340MiB，用 300MB，余 ~54MB） | 由移植包 1G 镜像缩容，S89games-storage 已改成 17B 存根防它 mkfs p10 |
| /system/xbin/a4-switch | 安卓侧切换器（自检全绿，切前后都做 md5 校验，任一侧镜像损坏就拒绝切） | |
| /data/app/com.a4.switcher-1.apk | **APK「A4 DualBoot」已安装成功**（AOSP testkey，jarsigner 签） | 界面两按键 + 状态 |
| EmuELEC rootfs 内 | `/usr/bin/switch-to-android`、`/usr/share/a4/`、`/storage/.config/emuelec/scripts/10-reboot-to-android.sh` | 回安卓 |

即：**除了「U-Boot 肯不肯引导 EmuELEC 内核」这一关，其余双系统要素都已就位并验证过**
（切换动作本身用「p8→p11 重写 + env 改写」实测过一轮：重写后重启，安卓正常起来，
cmdline 出现 `a4os=android`，p11 md5 与预期一致）。

---

## 3. 下一步的三条路线

### 路线 1：先拿串口看清 U-Boot 到底报什么（最该先做，成本最低）
UART 115200 接上看第一屏那句错误。若是 `Check RSA ERROR` / `kernel size` 之类，
就能立刻确定是不是校验卡住了；同时串口下可以直接在 U-Boot 里手工 `mmc read`+`bootm` 试引导，
不用反复刷机。

### 路线 2：离线反汇编 U-Boot，找出那条校验的**开关**
U-Boot 二进制我手上就有（`update.zip` 内 `fastboot.img`，与设备 p1 前 618444 B **md5 完全一致**）。
目标有两个：
- 找它是否被某个 **env 变量 / deviceinfo / baseparam 里的标志** 控制 —— 如果是，那**不用动 p1**，
  改 env（我们已验证能写、且 CRC 能被接受）或 deviceinfo 就能关掉，风险最低。
- 如果没有开关，则做**最小字节补丁**（把校验跳过去，或把「内核分区偏移」从 82MiB 改成指向
  EmuELEC 镜像处），随 `update.zip` 里的 `fastboot.img` 一起刷进去 —— 这条路能成，
  但**p1 刷坏就必须串口 + HiTool**，务必先有串口再动。

### 路线 3：绕开 U-Boot 引导
- **kexec**：若安卓 3.10 内核带 CONFIG_KEXEC，安卓内直接 kexec 到 EmuELEC 内核即可，完全不碰 U-Boot。
- **recovery 槽**：U-Boot 认 misc 里的 `boot-recovery` 标志去引导 p3(recovery)。若 recovery 那条
  校验与内核不同（字符串里有 `The recovery verify OK!/failed`，说明另有一套），把 EmuELEC 镜像放
  p3 + 置 misc 标志就可能成 —— 但那要再冒一次卡屏风险，且需要 recovery 进入手段可用。

---

## 5. U-Boot 反汇编结论（2026-10-12 补）

分析目标：`update.zip` 内 `fastboot.img`（618,444 B，与设备 p1 前 618,444 B md5 一致）。

### 5.1 二进制形态（已确认，非猜测）
| 项 | 结论 | 依据 |
|---|---|---|
| 架构 | **ARM32 小端裸镜像**（无 ELF 头/无符号表） | 偏移 0 是 ARM 异常向量 `b reset` + `ldr pc,[pc,#…]` |
| **链接基址** | **0xC00000** | 用「字面量 = base+字符串偏移」反推，0xC00000 得 988 命中，次名仅 9；并由 `bootm` 命令表指针（存于文件 0x93a64，值 0xC87A2B）交叉验证 |
| 规模 | ARM 全量 154,611 条；本区代码是 **Thumb-2** | ARM 9.6% 无法解码 vs Thumb 1.5% |
| 字符串引用 | 大量字符串**不在**字面量池里（既非 `ldr pc-relative` 也非 `movw/movt`） | 说明该 build 用「基址寄存器+偏移」方式取串；只有部分串有绝对指针 |

### 5.2 已定位的引导/加载代码区：**0xC7E000 – 0xC81500**
通过「字面量池 → 字符串」清单锁定代码地址（这些 ldr 就是取串的指令）：

| 代码地址 | 取的字符串 | 含义 |
|---|---|---|
| 0xC80264 | `…1C4A99C6DEE664765DC588DED48CD2B2C4CE5D5635097EF3D1C9B52DBB8A` | **内嵌 RSA-1024 模数字符串** |
| 0xC8073C | `nel  @ %x (%d bytes)` | `kernel  @ addr (size)` 打印 → **boot.img 的 kernel 段定位** |
| 0xC8075C | `@ %x (%d bytes)` | `ramdisk @ addr (size)` |
| 0xC807BC | `ng kernel from Legacy Image at %08lx` | **内核是 uImage → 走 legacy 引导路径** |
| 0xC802F4 | `C064_v2016060803` | SDK 版本串 |
| 0xC80C20 | `pkcs1_encrypt POLARSSL_ERR_RSA_RNG_FAILED` | **RSA 是 `encrypt`（不是 verify）** |
| 0xC81474/0xC814A0 | `…bleByName!` / `…FromMem!` | baseparam/playparam 读取 |

### 5.3 两个重要（且反直觉）的结论
1. **没有活动的「内核签名校验」。** `[HMT] RSA Verify the kernel Error.`、`[HMT] Check RSA ERROR!!`、
   `Enter fun Android_Main`、`boot-recovery`、`bootcmd`、`verify` 这些串**在整份镜像里没有任何引用**
   （既无绝对指针，也无字面量/PC 相对引用）→ 属于该 build 里的**死串**（为别的产品线编译进去的）。
   真正被引用的 RSA 代码是 `pkcs1_encrypt`（**加密**，属华为 deviceinfo/MAC 产品认证），不是内核验签。
   ⇒ **所以「外来内核被签名挡住」这个假设不成立**，U-Boot 不需要为 EmuELEC 打补丁。
2. **引导器确实会解析 boot.img 并引导里面的 uImage**：
   `kernel @ addr (size)` / `ramdisk @ addr (size)` / `Booting kernel from Legacy Image`
   三条串都被引用且挨在同一个函数区 → 流程 = 解析 `ANDROID!` 头 → 取 kernel（本机原厂内核本身就是
   uImage）→ 按 uImage 头里的 load/entry 重定位引导 ✓。我们的 EmuELEC 镜像同样是「Android! 头 +
   uImage 内核」，**格式上是被支持的**。

### 5.4 那卡第一屏的真因在哪？
候选（按可能性排序，均需串口确认）：
1. **内核交接参数**：`machid`。U-Boot 里有 `Using machid 0x%x from environment` 且**该串被引用** →
   machid 可由 env 变量 `machid` 指定，我们现在的 env 里没有 → 用默认值。EmuELEC 内核（来自
   「海纳斯」NAS 固件）与安卓内核虽然都是 hi3798mv100/Hisilicon/bigfish 同族
   （两个 vmlinux 都含 `Hi3798MV100`/`hi3798mv100`/`bigfish`），但期望的 machid 未必相同 →
   不匹配时内核打印 `Error: unrecognized/unsupported machine ID` 后停住 = 卡第一屏。
2. **我们塞的 65 字节迷你 ramdisk**：安卓 kernel 的 initrd 是 329,180 B 的 gzip cpio 没问题；
   EmuELEC 内核如果按「老式 initrd」处理这个几十字节的东西，可能 unpack 失败 → panic。
   → 可改成 **`ramdisk_size=0`（不传 initrd）** 再试，这更干净。
3. DTB/ATAGS 交接差异、或 root 分区/文件系统层面的早期失败。
4. 安卓 3.10 内核**不支持 kexec**（已确认 0 命中）→ 「安卓内 kexec 引导 EmuELEC」这条绕开 U-Boot 的
   路线走不通。

⇒ **下一步必须有串口（UART 115200）**，看内核到底停在哪一句；有串口的话 10 分钟就能定位。
没有串口时就只能盲试上面第 1/2 条（每次盲试都要 recovery 兜底）。

---

## 6. 交付物位置

- 构建/工具脚本：`E:\A4-work\emuelec\tools\`（`mkenv.py` 造 p2 env、`mkbootimg.py` 造 boot.img、
  `dsh.py`/`adbx.sh` 连设备、`ub_*.py` 反汇编/定位 U-Boot 字符串与代码、
  `check_uimg_crc.py` 验 uImage CRC、`check_kexec.py` 查 kexec、`cmp_kernels.py` 比对两个内核）
- 反汇编产物：`E:\A4-work\emuelec\work\ub_thumb.asm`、`ub_arm.asm`、`ub_android_main.asm`；
  解压出的内核 `work/vmlinux_3.10.bin`、`work/vmlinux_emuelec.bin`
- 镜像：`E:\A4-work\emuelec\work\`（`rootfs_final.raw` 340M、`emuelec_boot.img`、`env_*_mode.bin`）
- 备份：`E:\A4-work\emuelec\backup\bk\`（p1/p2/p3/p5/p8/p9/p10/p11/p12/p13头 32M，**md5 全核对**）
- APK：`E:\A4-work\emuelec\work\apk\A4DualBoot.apk`
- 切换器源码：`E:\A4-work\emuelec\work\switcher\`
