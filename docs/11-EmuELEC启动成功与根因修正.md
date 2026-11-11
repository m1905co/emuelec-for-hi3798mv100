# EmuELEC 双系统 · U-Boot 取证 + 两处真因修复（2026-10-12 深夜，更正版）

> ⚠️ **更正**：本文件先前一版曾写「EmuELEC 已成功启动」——**那是误判**。
> 当时把 `192.168.31.66`（dropbear 0.52 / DHCP / 5555 开放）当成了本机，实际是用户**另一台盒子**；
> 本机 `192.168.31.16` 实测 dead，**仍然卡在第一屏**。
> 本机 rootfs 里没有任何监听 5555 的进程（日志里那些 `5555` 只是 `/etc/services` 文本），当时就该起疑。

---

## 一、确定性结论：U-Boot 内核读取窗口硬编码 **10 MiB**

`mode 0` 分支（VA `0xC2A73C`，ARM 代码）：

```
movw r3,#0xbfc0 / movt r3,#0x1ff   ; dst = 0x01FFBFC0
mov  r0, #0x5200000                ; src = 82 MiB = p11「kernel」
mov  r2, #0xa00000                 ; ★ 长度 = 10 MiB（文件偏移 0x2A74C: 0a 26 a0 e3）
bl   0xC2B024                      ; flash 读
```

| 镜像 | 字节数 | 是否在窗口内 |
|---|---|---|
| 原厂 boot.img | 10,486,020（= 10 MiB + 260 B 签名记录） | 内容部分刚好在内 |
| 第一版自建镜像 | 10,868,736 | ✗ 超 382,976 B（**主因之一**） |
| 现在这版 | 10,471,424 | ✓ 余 14,336 B |

同时确认：**内核路径不验签**（验签函数 `0xC2A4AC` 唯一 BL 调用者在 `mode1` recovery 分支，
读记录地址 = 参数+0x500000；若内核路径也验，原厂镜像在 87 MiB 处读到的是内核数据，早就起不来了）。

## 二、★ 真正被遗漏的点：DT 启动时 **DTB 的 `/chosen/bootargs` 覆盖引导器 cmdline**

EmuELEC 的 zImage 尾部（偏移 `0xA59D10`，8,935 B，`d00dfeed`）是 **appended DTB**，
内容为 **EC6108V9C 九分区**布局：

```
compatible = "Hisilicon","hi3798mv100-series"
/chosen bootargs = "mem=1G mmz=ddr,0,0,60M console=ttyAMA0,115200 root=/dev/mmcblk0p9
                    rootfstype=ext4 rootwait blkdevparts=…20M(kernel),64M(busybox),…-(ubuntu)"
```

0x32 ARM 的 `early_init_dt_scan_chosen()` 会用 DTB 的 `/chosen/bootargs` **覆盖** `boot_command_line`
⇒ **boot.img 头里嵌的 cmdline、env `bootargs` 全部被忽略**，内核只会去挂 `mmcblk0p9`（本机是 misc）→ 必然失败。

- DTB 里**没有 `/memory` 节点**（靠 `mem=1G`/ATAGS 补），`/chosen` 只有 `bootargs`。
- 上一版把它 **NOP 掉是错的**：DT 模式下 ATAGS 的 cmdline 未必会补进 DTB，内核可能拿到空 cmdline。

### 正确做法（已实现）
把 DTB 的 `/chosen/bootargs` **原地改成我们的 cmdline**，并且**保持属性等长（216 B）+ 空格补齐**
⇒ DTB 结构零位移，桩内/尾部所有指向 DTB 内部的地址常量（含 `DTB+0x1020` = `0xA5AD30`）无需改动。

写进 DTB 与 boot.img 头的新 cmdline（198 B ≤ 216）：

```
mem=1G mmz=ddr,0,0,60M console=ttyAMA0,115200 root=/dev/mmcblk0p13 rootfstype=ext4 rootwait
blkdevparts=mmcblk0:1M(a),4M(b),16M(c),1M(d),4M(e),4M(f),4M(g),16M(h),8M(i),24M(j),12M(k),8M(l),340M(m),340M(n),520M(o),-(p)
```
（分区分名用单字母只为压到 216 B；**偏移/大小严格照本机 16 分区**，`p13 = 340M@102MiB` 就是我们的 EmuELEC rootfs。）

## 三、为塞进 10 MiB 所做的内核手术（`tools/rebuild_emu_small.py`，全部离线自证）

1. **zopfli 重压 zImage 内 gzip 流**：10,825,965 → **10,431,660**（省 394,305）。
   U-Boot 的 bootm 只实现 `comp=none/gzip`（分派在 `0xC2B4CC`），所以 LZMA/LZO/LZ4/bzip2 包装内核不可行；
   `gzip -9` 只省 0.08% 不够，xz 能到 7.9 MB 但格式不被支持。
2. **保留 appended DTB 并重建到 8 字节对齐**（新址 `0x9F98D0`，%8=0，需 1 字节 pad）。
3. **统一平移 7 个内部绝对地址常量**（桩内 + 尾部数据表里指向 `[旧流末尾, 文件末)` 的值）：
   `0x2c`(★zImage 头 `_edata`=DTB 地址，不能写成文件长度)、`0x308`、`0x30c`、`0x310`、`0x318`、`0x31c`、`0x320`。
4. 自证：换流后解压 = 原始 vmlinux 24,616,960 B **逐字节一致**；DTB 解析正常且 bootargs = 我们的；
   uImage hcrc/dcrc 全部重算并通过；`boot.img = 10,471,424 ≤ 0xa00000`。
5. 另修 mkbootimg 头偏移 bug（原来把 `name` 写到 offset 44，覆盖了 `header_version`/`os_version`）：
   现在 `40..48` 归零、`name` 写回 `48`。

## 四、其它已确认事实

- 原厂 boot.img 头：`kernel_addr=0x3e08000`、`ramdisk_addr=0x4e00000`、`tags_addr=0x3e00100`、`page=2048`。
  EmuELEC 按其 EC 版设计用 **`kernel_addr=0x02000000`**（= uImage `load`；EC 包的 `bootcmd` 也是把镜像放
  `0x1FFFFC0` 再 `bootm`）→ 本版沿用 `0x02000000`（注意它与 U-Boot 放镜像的 `0x1FFBFC0` 只差 64 B，靠前向 memmove 过关）。
- 两个内核 zImage 都在 `stub+0x86c` 含 `0x00008000` ⇒ 解压目标 = `0x00008000`（zImage 在其上方，无需自搬迁）。
- 原厂 boot.img 头 `offset 576` 的 `id[32]`（= `12220643…`）**不等于**任何试过的 SHA-1 组合；
  我们镜像继承了该值。判定 U-Boot 不校验它，列为待观察项。
- 设备访问：Android 侧 telnet `192.168.31.16:23`（免密 root）/ adb `5555`；EmuELEC 侧 SSH 需先在
  rootfs 的 `/etc/default/histb-ssh` 设 `HISTB_SSH_ALLOW_PASSWORD=1`（`S82dropbear` 默认 `-s` 禁密码登录）。
- 回安卓保底通道：recovery 刷 `E:\A4-work\update.zip`（把 `boot.img` 写回 `by-name/kernel` = p11）。

## 五、交付物与下一步

| 文件 | 说明 |
|---|---|
| `emuelec\work\emuelec_boot.img` | 本版镜像（10,471,424 B，含 DTB cmdline 修正） |
| `emuelec\tools\rebuild_emu_small.py` | 重建脚本（换流 + DTB cmdline 原位改写 + 常量平移 + boot.img 生成） |
| `emuelec\tools\ub_func_str.py` | U-Boot（PIE）按函数解析字符串的工具，用于追启动路径 |
| `emuelec\tools\ub_xrefva.py`、`find_bl.py`、`dtb_nodes2.py` | xref / 调用者 / DTB 结构解析 |

**下一步（按顺序）**
1. 先把盒子救回来：recovery 刷 `E:\A4-work\update.zip`。
2. 部署本版镜像到 p11 → 重启，观察是否仍卡第一屏。
3. 若仍失败：优先怀疑 (a) 我的 zImage 手术（用 Unicorn 模拟解压桩做离线验证），
   或 (b) U-Boot 侧其它隐含要求（如头 `id`）。届时应给盒子接 **UART(115200)** 拿真实报错。
