# EmuELEC 双系统 · U-Boot 反汇编取证与「10 MiB 读取窗口」根因

日期：2026-10-12（晚）
二进制：`update.zip` 内 `fastboot.img`（618,444 B）= 设备 p1 前 618,444 字节（md5 一致）
工作副本：`E:\A4-work\emuelec\work\uboot_src\fastboot.img`

---

## 1. 反汇编方法（本轮修正了上一轮的错误结论）

- **基址 0xC00000**：靠「字面量 = base + 字面量池地址」反推，并使用下列工具复核。
- **本镜像是 PIE（位置无关）**：字符串不是用绝对指针取，而是
  `ldr rX,[pc,#imm]` 取一个**偏移**，再 `add r4, pc, rX` 得到 GOT 基址，之后 `add r0, r4, <偏移>` 取串。
  → **上一轮「无绝对指针 ⇒ 串是死串 ⇒ 没有签名校验」的结论作废**，那是方法错了。
- 正确方法：对目标字符串 VA 计算 `offset = VA - GOT`，再在字面量池里搜这个 32 位值。
  - `bootimg` 命令所在函数的 **GOT 基址 = 0xC93808**（`0xC2B1C8 + 0x68640`）。
  - 该法一次性命中了 `[HMT] RSA Verify…`/模数/指数/`%.2x`/`kick` 等全部相关串，验证模型正确。

工具：`tools/ub_dis2.py`（区间反汇编，可选 arm/thumb）、`tools/find_bl.py`（BL/BLX 调用者）、
`tools/ub_xrefva.py`（ldr/adr 引用）、`tools/find_movwt.py`、`tools/ub_ptrs.py`。

## 2. 命令表与入口

`cmd_tbl_t` = `{name, maxargs, repeatable, cmd, usage, help}`，位于 0xC93E40 起：

| 表项 VA | name | cmd 实现 |
|---|---|---|
| 0xC93EA8 | `setproflag` | 0xC2B12C |
| **0xC93EC4** | **`bootimg`** | **0xC2B1A4** |

## 3. ★ U-Boot 确实有「内核 RSA 签名校验」的代码与公钥

- **模数**：文件 `0x7F8BC` 处是 **512 个 ASCII 十六进制字符 = 2048-bit RSA 模数**；
  紧跟其后 `0x7FAC0` 是 **指数 `010001`**（同为 ASCII）。
- 这三条串同一簇：`0x7F878 [HMT] read the kernel failed.` / `0x7F898 The kernel size is [%d]` / `0x7F8B4 %.2x`。
- **验签函数 = `0xC2A4AC`**（ARM）。逻辑：

```
bl 0xC2B024            ; 从 flash 读 0x400 字节「记录」到缓冲
ldr r7,[r5,#0x208]     ; r7 = 记录偏移 +0x208 处的长度字段
printf("The kernel size is [%d]", r7)
bl 0xC30EB4            ; SHA-256 上下文初始化 (ctx=sp+0x114)
movw r6,#0xbfc0 ; movt r6,#0x1ff   ; 源地址 = 0x01FFBFC0
循环: 每 0x100000 字节喂入一次
bl 0xC34788            ; SHA-256 收尾 -> 32 字节摘要
printf("%.2x" ×32)     ; 把摘要打成十六进制
memcpy(sig, buf+0x20C, 0x100)      ; 取 256 字节签名
用 16 字符一组把模数/指数 ASCII 转成大数
bl 0xC30230(mode=0xb)  ; RSA 验签
cmp r0,#0 ; bne 失败 → 打印 [HMT] RSA Verify the kernel Error. + [HMT] Check RSA ERROR!!
返回 1=通过 / 0=失败
```

- **离线验证（决定性）**：`tools/verify_sig.py`
  取设备 p11 里 `0xA00004..0xA00104` 的 256 字节，做 `pow(sig, 65537, n)` 得
  `00 01 FF…FF 00 || 3031300d060960864801650304020105000420 || 0fb0ad9735347a6e0d99156aafc97f6dc52804b7abfb1a92f88eb17376d621f9`
  → **完整合法的 PKCS#1 v1.5 / SHA-256 签名**。所以模数与签名是一对真货，验签代码是活代码。

## 4. ★★ 但验签**不在内核启动路径上**

- 记录结构：`[长度:4 字节 LE][签名:256 字节]`。原厂 `boot.img` 末尾 260 字节就是它，位于
  镜像偏移 `0xA00000`（= 10 MiB），且在 `0xA00224` 还有**同一份重复**记录（`tools/sig_range_brute.py` 证明两份逐字节相同）。
- 验签函数读记录的地址是 `参数 + 0x500000`。
- **验签函数全镜像只有一个调用者：`0xC2A850`**，位于分派器 `0xC2A704` 内，属于 **mode==1 分支**：

| mode | 行为（分派器 0xC2A704） |
|---|---|
| **1** | 从 flash `0x3600000` 读 4 字节标志；再从 **`0x500000` 或 `0xD00000`** 读 **4 MiB** 到 `0x01FFBFC0`；**调用验签**；然后引导 |
| **0** | **从 `0x5200000`(=82 MiB=p11「kernel」) 读 `0xa00000`(10 MiB) 到 `0x01FFBFC0`；不验签**，设 `bootargs` 后返回 1 |
| **2** | 另一分支（recovery 相关） |

- 模式判定在 `0xC2A284`：先取一个「启动标志」与魔数
  `0x23DC4DB2 / 0x639CFF00 / 0x23DC4EB1 / 0x23DC4CB3 / 0x23DCDD22` 比较（命中 ⇒ mode 1）；
  否则读 **misc 分区（p9，50 MiB 起）0xC00 字节** 再判定 mode 2/0。

**⇒ 结论：内核（p11）不参与 RSA 验签；被验签的是 4 MiB 的 recovery 镜像。**

## 5. ★★ 真凶候选：内核读取窗口被**硬编码为 10 MiB**

分派器 mode 0 分支（`0xC2A73C`）：

```
movw r3,#0xbfc0 / movt r3,#0x1ff   ; dst = 0x01FFBFC0
mov  r0, #0x5200000                ; src = 82 MiB = p11
mov  r1, r6                        ; 0
mov  r2, #0xa00000                 ; ★ 长度 = 10 MiB（硬编码，字节 0a 26 a0 e3 @ 文件 0x2A74C）
bl   0xC2B024                      ; flash 读取
```

对照实测尺寸：

| 镜像 | 字节数 | 说明 |
|---|---|---|
| 原厂 `boot.img` | 10,486,020 = 0xA00104 = 10 MiB + 260 | 内核 uImage 结束于 0x779930，**远在 10 MiB 内** |
| **自建 `emuelec_boot.img`** | **10,868,736 = 10 MiB + 382,976** | **超出窗口 382,976 字节** |

⇒ U-Boot 只读 10 MiB，我们的镜像从 10 MiB 处被**截断**，p11 里存放的 EmuELEC 内核 uImage
（起始 0x800、声明长度 10,862,583）必然不完整 → `bootm` 校验/格式判定失败 → **卡第一屏**。
这同时解释了 2026-10-08 那次「重打包 boot.img → 卡第一屏」。

## 6. U-Boot 支持的压缩算法（决定可行解法）

`bootm` 的压缩分派（`0xC2B4CC` 起）：

```
cmp ip,#0  ; comp=0(none)  -> 0xC2B608
cmp ip,#1  ; comp=1(gzip)  -> 0xC2B534
否则      : "Unimplemented compression type %d" -> 报错返回
```

⇒ **只实现了 none 与 gzip**。压缩串名表里虽然列了 `bzip2/gzip/lzma/lzo`，但分派只有两路，
**LZMA/LZO/LZ4/bzip2 包装内核这条路走不通**。

## 7. 解法

### 方案 A（不动 U-Boot，首选）
把内核 zImage 内部那段 **gzip 流用 zopfli 重压**（仍是 gzip 格式，内核自带 inflate 照样能解）：
- 需要 `zImage ≤ 10,483,648`（= 10 MiB − 2048 头 − 64 uImage 头），即 **gzip 流 ≤ 10,456,024**。
- 现状：原流 10,834,959；`gzip -9` 重压 = 10,825,985（**只省 0.08%，不够**）。
- **xz -9 = 7,909,132（够，但格式不被支持）**；zopfli（gzip 最优解析）通常再省 3–6%，**需要 3.49%**。
- 构建方式：`[原 zImage 头部/自解压桩 0..0x6BE8] + [新 gzip 流]`，并回填 zImage 头 `0x2C` 处的 end 偏移；
  再重建 uImage（dcrc = crc32(新载荷)、hcrc）与 boot.img（构建器已过字节级自证）。

### 方案 B（改 U-Boot，1 字节）
文件偏移 **`0x2A74C`：`0x0A` → `0x0C`**，把读取窗口从 `mov r2,#0xa00000`(10 MiB) 提到
`mov r2,#0xc00000`(12 MiB，p11 全分区)。指令 `0xE3A0260A → 0xE3A0260C`，唯一命中。
- 代价：要写 p1。**风险**：若 BootROM 对 p1 也有校验/熔丝，写坏即无法网络救援，
  需 USB/HiTool（或 SD）恢复。p1 已备份（`backup/bk/p01.bin`，md5 已核对）。
- 附带发现：p1 在 618,444 字节之后还有 **2,200 个非零字节**（未分析完）。

## 8. 其它已固化事实

- 安卓 3.10 内核**不支持 kexec**（0 命中），绕开 U-Boot 的 kexec 路线排除。
- U-Boot 全量 ARM 反汇编 154,611 条；本区代码为 ARM（不是 Thumb）。
- 设备 p2（env）仍是原厂 16 分区布局 + `bootargs_1G` 尾部 `a4os=…` 标记；该标记**不影响选内核**。
- recovery 刷 `update.zip` 会把 `boot.img` 写回 `by-name/kernel` = **p11**，且不动 p2/p8/p10/p13。
