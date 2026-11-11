# U-Boot「开机按键 → 恢复」+「启动失败自动回退」实现报告

日期：2026-10-16
目标：在已获得的 U-Boot 源码里**实现功能**（暂不上盒子）。
结论：**功能已完整实现并编译出可链接的 U-Boot 镜像 `fastboot-burn.bin`（248,752 B，md5 `e58985c9…`），main_loop 调用点已在反汇编中确认。**

---

## 1. 交付内容

### 1.1 新增文件

| 文件 | 内容 |
|---|---|
| `.../source/boot/fastboot/include/a4_bootguard.h` | 功能说明 + API（68 行） |
| `.../source/boot/fastboot/common/a4_bootguard.c` | 全部实现 + 4 条命令（463 行） |

### 1.2 修改文件（最小侵入）

| 文件 | 改动 |
|---|---|
| `common/Makefile` | `COBJS-$(CONFIG_A4_BOOTGUARD) += a4_bootguard.o` |
| `common/main.c` | 3 处：`#include`；`main_loop` 里调用 `a4_bootguard_early()`；自动引导判定前面加 `if (a4_recovery) { enter_recovery(); } else` |
| `include/configs/hi3798mx.h` | `#define CONFIG_A4_BOOTGUARD 1` |
| `arch/arm/config.mk` | 构建兼容：`-mfpu=vfpv3-d16`（见 §4） |
| `include/linux/compiler-gcc.h` | 构建兼容：GCC>4 时固定用 `compiler-gcc4.h`（见 §4） |
| `include/configs/hi3798mx_config.h` | **验证构建**用：注释掉 `CONFIG_PRODUCT_WITH_BOOT`（见 §5） |

### 1.3 产物

```
E:\A4-work\emuelec\work\uboot_src\
├── a4-bootguard.patch          # 全量改动补丁（8 文件 / +600 行 / 22.9 KB）
└── build-out\
    ├── fastboot-burn.bin       # 248,752 B  md5 e58985c91d2c44b36c757bb58b3290b0
    ├── u-boot                  # 带符号 ELF
    └── u-boot.map
```

---

## 2. 功能设计：三个触发源 → 一个恢复动作

### 2.1 触发源（优先级从高到低）

1. **按住按键开机**（本次要"加回来"的那个特性）
   - `a4key_gpio` 指定候选引脚，格式 `bank_bit`，可多个用逗号分隔，例如 `0_3,9_6`
   - 开机时轮询 `a4key_hold_ms`（默认 **800 ms**），要求**整段时间持续按下**；中途松手即放弃
   - 有效电平由 `a4key_active` 决定（默认 `low`，按键通常对地）
   - 引脚被配置成输出时自动跳过（不会误判）
   - **未设置 `a4key_gpio` 时不引入任何延时**，默认启动路径零影响
2. **强制标志**：`a4_recovery=1`（脚本/OS 侧也可用，`a4recovery on` 设置）
3. **启动失败计数**（安全网）：`a4_bootlimit` > 0 时启用，每次启动计数 +1 并落盘；超过阈值自动进恢复
   - 专门对付"内核/rootfs 坏了 → 看门狗复位 → 无限重启"这类没有串口就救不回来的情况

### 2.2 恢复动作

`a4_bootguard_enter_recovery()`：

- 打印醒目标识横幅
- **清零失败计数**（有人接手了）
- 若 `a4_recovery_cmd` 有定义则执行它（例如去 U 盘取 `recovery.img` 引导，或写 env 切到安卓）
- **默认行为：跳过自动引导、停在 `fastboot#` 提示符** —— 这正是原厂按遥控键能进、换 U-Boot 后丢掉的那个交互入口

### 2.3 新增命令

| 命令 | 作用 |
|---|---|
| `a4bootinfo` | 显示计数/阈值/强制标志/按键配置全貌 |
| `a4bootok` | 清零失败计数（供 OS/脚本调用） |
| `a4recovery on\|off` | 武装/解除下次强制恢复 |
| **`a4keytest`** | **上机找引脚用的**：对配置的引脚采样 3 秒，实时打印 `base / DIR 位 / 电平变化`，按键一试就知道哪个 pin 动 |

### 2.4 环境变量一览

| 变量 | 默认 | 说明 |
|---|---|---|
| `a4key_gpio` | 空 | 候选按键引脚 `bank_bit[,...]`，空=关闭 |
| `a4key_active` | `low` | `low` / `high` |
| `a4key_hold_ms` | `800` | 需持续按住的时长（上限 5000） |
| `a4_recovery` | 空 | `1` = 下次强制恢复 |
| `a4_recovery_cmd` | 空 | 恢复模式下先执行的命令，空=只停提示符 |
| `a4_bootcount` | `0` | 失败计数（持久） |
| `a4_bootlimit` | `0` | `>0` 才启用计数；超过就强制恢复 |

---

## 3. 集成点（`common/main.c`，两处）

```c
	s = getenv ("bootcmd");

#ifdef CONFIG_A4_BOOTGUARD
	a4_recovery = a4_bootguard_early ();
	if (a4_recovery)
		bootdelay = -1;          /* 顺手屏蔽 hibernate/snapshot 与倒计时 */
#endif
	...
#ifdef CONFIG_A4_BOOTGUARD
	if (a4_recovery) {
		a4_bootguard_enter_recovery ();
	} else
#endif
	if (bootdelay >= 0 && s && !abortboot (bootdelay)) {
		... 原有自动引导路径 ...
	}
```

**反汇编实证**（`u-boot`）：

```
c192dc:  ebffd1a2  bl  c0d96c <a4_bootguard_early>
c19580:  ebffd188  bl  c0dba8 <a4_bootguard_enter_recovery>
```

命令表符号 4 条全部就位：`__u_boot_cmd_{a4bootinfo,a4bootok,a4recovery,a4keytest}`。

---

## 4. 构建过程中踩到的 3 个老代码/GCC11 兼容问题（与功能无关，均已修）

| # | 报错 | 根因 | 修法 |
|---|---|---|---|
| 1 | `main.c:56 'show_boot_progress' aliased to external symbol '__show_boot_progress'` | 原码用 `void inline __show_boot_progress(){}`，新 GCC 不外发未使用的 inline 函数体，weak alias 指向了不存在的符号 | 去掉 `inline`，恢复"空实现 + weak 别名"的原意 |
| 2 | `linux/compiler-gcc11.h: No such file or directory` | 该树只带 `compiler-gcc4.h`，而 `compiler-gcc.h` 按 `__GNUC__` 自动选头 | `__GNUC__ > 4` 时固定 include `compiler-gcc4.h` |
| 3 | `libgcc.a(_udivmoddi4.o) uses VFP register arguments, u-boot does not` | 交叉工具链默认 hard-float，libgcc 也是 hard；而 `-march=armv7-a` 不带 FPU 会与 hard 冲突 | 用 `-mfpu=vfpv3-d16`（而不是强制 `-mfloat-abi`）——对 hf 工具链保持 hard 并与其 libgcc 匹配，对海思 soft-float 工具链则被忽略 |

另外一个**纯构建流程**的坑：早期 hard-float 报错时生成了一个**空的 `include/autoconf.mk`**，make 认为它是最新的，导致所有 make 层配置开关（含 `CONFIG_DDR_TRAINING_V2`）全部失效、链接时找不到 DDR training 目标文件。删掉重新生成即可（145 行，`CONFIG_A4_BOOTGUARD=y` 在其中）。

---

## 5. 本次验证构建的配置与局限（必须说明）

- 工具链：WSL 的 `arm-linux-gnueabihf-gcc` 11（非官方 `arm-histbv310-linux`）
- 命令：
  ```bash
  cp ../sysreg/hi3798mv100/hi3798mdmo1d_hi3798mv100_ddr3_2gbyte_8bitx4_4layers_emmc.reg .reg
  make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- hi3798mx_config
  make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j8
  ```
- **局限**：我们只稀疏克隆了 `source/boot` 与 `configs`，没有 `source/boot/product` + `source/common`，因此 `CONFIG_PRODUCT_WITH_BOOT`（product_init / fastapp_entry，负责 logo/keyled/adp 等）**在验证构建里被关掉**，产物 248,752 B，比官方 `fastboot.bin`（539,272 B）小。
- **这是验证"功能编得过、链得上、进了二进制"，不是可直接刷的成品**。真正要刷的镜像应当用完整 SDK 跑 `make hiboot` 产出（`fastboot.mak` 会在构建时**重新生成** `hi3798mx_config.h`，所以这里的改动不影响 SDK 构建）。

---

## 6. 待上机才能确定的事

1. **按键到底是哪个 GPIO**——这是唯一还需要硬件的一步。上机后：
   ```
   setenv a4key_gpio 0_3,9_6      # 试几个候选
   a4keytest                       # 按面板键，看哪个 pin 跳变
   setenv a4key_gpio <选中的>      # 固定下来
   saveenv
   ```
   `a4keytest` 会把每个引脚的 `base 地址 / 方向位 / 电平变化`打出来，不用猜。
2. **`a4_recovery_cmd` 的最终形态**：是"停提示符"就够，还是要自动去 U 盘 `recovery.img`（可复用现成的 `download_process_usbhost()`），或写成"切回安卓"。
3. 上机仍需 **TTL 串口（115200）** 作为刷写/回滚通道。

---

## 7. 建议的上机顺序（待盒子恢复后）

1. 串口进 `fastboot#`，`printenv` 存一份当前 env 备份
2. 在**不改默认行为**的前提下先验证：`setenv a4key_gpio …; a4keytest` 找出按键引脚
3. 只设 `a4key_gpio`，重启验证"按住开机键 → 进恢复"；验证"不按 → 正常启动、无额外延时"
4. 再设 `a4_bootlimit 3`，人为制造 3 次启动失败，验证自动回退
5. 全部确认后才把新 `fastboot-burn.bin` 写进 p1（并保留 `p1_new.bin` / `p1_cur.bin` 两个可回滚镜像）
