# Hi3798MV100 双系统 · WiFi / 蓝牙 / 红外 分析与取证

**日期**：2026-10-13
**设备**：Hi3798MV100（mdmo1d，1GB DDR）；当前运行 EmuELEC，内核 `Linux ecoo.top 4.4.35_ecoo_81082668 armv7l`
**取证方式**：TTL 串口（COM4/115200）+ 离线解析原厂包与 haiNAS 镜像

---

## 一、结论速览

| 问题 | 结论 | 置信度 |
|---|---|---|
| 安卓是否还从 kernel 分区启动？U-Boot 改了吗？ | **只换了 p1 的 U-Boot；安卓仍从 p11（kernel 分区）读原厂 boot.img，内容未改动** | 高（bootcmd 实测） |
| WiFi 驱动 | **已找到与运行内核完全同版本的 `rtl8188fu.ko`（来自 haiNAS 的 Ubuntu），可直接 insmod** | 高（vermagic 逐字匹配） |
| 蓝牙 | 内核**已内建** `bluetooth/btusb/btintel`；硬件侧待设备在线确认（Android 侧为 MTK `mtkbt`+`rtk_btusb` 双栈） | 中高 |
| 红外遥控 | 内核**无 IR 驱动**；`/kmod/hi_ir.ko` 版本为 `4.4.35_s40`，与运行内核不匹配 | 高 |

---

## 二、Q1：安卓启动链（澄清"从 boot 还是 kernel 启动"）

分区表里**没有名为 boot 的分区**；安卓的 boot 镜像就放在名为 **`kernel`(p11)** 的分区里。

```
物理分区（Android 模式 blkdevparts，实测 /proc/partitions）：
  p1  fastboot    1M   @0        ← U-Boot（本次唯一被替换的东西）
  p2  bootargs    4M   @1M       ← env（bootcmd/bootargs 决定启动谁）
  ...
  p10 factory    24M   @58M
  p11 kernel     12M   @82M      ← 安卓原厂 boot.img（内核+ramdisk），未改动
  p12 iptv_data   8M   @94M
  p13 backup    340M   @102M     ← EmuELEC rootfs（见下）
  p14 cache     340M   @442M
  p15 system    520M   @782M
  p16 userdata   —     @1302M
```

**Android 模式的 bootcmd（实测）**：
```
mmc read 0 0x10000000 0x29000 0x6000      # 0x29000 扇区 = 82MiB = p11(kernel) 起点，读 12MiB
mmc read 0 0x11000000 0x23000 0x400       # 0x23000 扇区 = 70MiB = 安卓 ramdisk 的 uImage 包装
bootm 0x10000800 0x11000000               # 0x10000000+0x800 = boot.img 里 kernel 的起点
```

- `0x29000` 扇区 × 512 = **82 MiB = p11 起点** → **安卓依旧从 kernel 分区读 boot.img**。
- 差别只在"**谁来读**"：原厂 U-Boot 的 `Android_Main` 硬编码从 p11 读；换成通用 U-Boot 后由 `bootcmd` 显式读**同样的偏移和大小**。
- 唯一额外之处：安卓的 ramdisk 被单独包成 uImage 存在 p10 区域的 70 MiB 处，作为 `bootm` 的第二个参数（因为通用 `bootm` 不像原厂那样会自己拆 boot.img）。
- **结论：p11 的内容（原厂 boot.img）没有动过；不存在"从别处启动"的情况。**

### 2.1 EmuELEC 用了哪些分区（顺带澄清）

| EmuELEC 视角 | 大小 | 物理位置 | 实为原厂哪个分区 |
|---|---|---|---|
| rootfs `mmcblk0p9`(storage) | 340M | @102M | **backup(p13)** —— 不是 cache |
| 内核 uImage（0x1D000） | — | @58M | factory 起点（归 EmuELEC 的 p8 fastplay） |
| `mmcblk0p10` userdata | 3286M | @442M | cache+system+userdata 合并（EmuELEC 未挂载） |

---

## 三、Q2/Q3-①：WiFi —— 已找到可直接使用的驱动

### 3.1 硬件
`lsusb` 实测：`Bus 001 Device 003: ID 0bda:0179`，product `802.11n NIC`，manufacturer `Realtek`
→ **RTL8188FU（USB）**，已枚举但**无驱动**（`driver -> .../usb/drivers/usb`，通用；无 wlan0）。

### 3.2 内核侧现状（`/sys/module/` 实测）
运行内核**已内建**：
```
kernel/net/wireless/cfg80211.ko
kernel/net/mac80211/mac80211.ko
kernel/net/bluetooth/bluetooth.ko
kernel/drivers/bluetooth/btusb.ko
kernel/drivers/bluetooth/btintel.ko
```
→ 协议栈齐全，**只差 rtl8188fu 本体**。系统内既没有该模块，也没有 `/lib/firmware` 固件。

### 3.3 关键突破：haiNAS 里有同版本模块
`emuelec/mv100-mdmo1d-usb-flash/mv100/www_ecoo_top.ext4`（Android sparse，512MB）
→ 解开后是一个 `backup-32.gz`（283MB）
→ 再解开是 **`Ubuntu-20.04.5-armhf-20260101-36b11.img`**（868MB ext4）—— 即 haiNAS 系统。

其 `/lib/modules/` 目录名与 EmuELEC 运行内核**逐字相同**：
```
/lib/modules/4.4.35_ecoo_81082668/kernel/drivers/wifi/usb_rtl8188fu/
    rtl8188FU_linux_v4.3.23.6_20964.20170110/rtl8188fu.ko     1,344,328 B
/lib/modules/4.4.35_ecoo_81082668/kernel/drivers/wifi/usb_rtl8188eu/
    rtl8188EUS_linux_v4.3.24_16705.20160509/rtl8188eu.ko      1,648,736 B
```

实测 `rtl8188fu.ko` 的 vermagic：
```
vermagic=4.4.35_ecoo_81082668 SMP mod_unload ARMv7 p2v8
```
**与运行内核完全一致**；且 `modules.dep` 中它无依赖（cfg80211/mac80211 已内建）。
`.ko` 引用的只是可选的射频参数表（`PHY_REG_PG.txt`/`TXPWR_LMT.txt` 等），**固件为内嵌，不需要额外 fw.bin**。

### 3.4 落地步骤（设备在线时执行）
```sh
# 1) 放入模块目录
mkdir -p /lib/modules/4.4.35_ecoo_81082668/kernel/drivers/wifi/usb_rtl8188fu
cp rtl8188fu.ko  /lib/modules/4.4.35_ecoo_81082668/kernel/drivers/wifi/usb_rtl8188fu/
# 2) 加载
insmod /lib/modules/4.4.35_ecoo_81082668/kernel/drivers/wifi/usb_rtl8188fu/rtl8188fu.ko
# 3) 应出现 wlan0
ifconfig wlan0 up
# 4) 连接（wpa_supplicant + udhcpc）
```

已提取到本地：`emuelec/work/wifi/{rtl8188fu.ko, rtl8188eu.ko, modules.dep, modules.alias, modules.builtin}`

---

## 四、Q3-②：蓝牙

- 内核**已内建蓝牙栈**（见 3.2），`btusb` 是 USB HCI 通用驱动 → **只要有 USB 蓝牙硬件就能工作**。
- 原厂 Android 包里同时带两套蓝牙方案：
  - MTK：`system/bin/mtkbt`、`system/app/HmtBluetooth.apk`、固件 `system/etc/firmware/mt7662_firmware_e3_tvbox.bin`、`mt7662_patch_e3_hdr.bin`
  - Realtek：`init.bigfish.rc` 中 `chmod/chown /dev/rtk_btusb`（Realtek USB BT 设备节点）
- 但 EmuELEC 下 `lsusb` **未见任何蓝牙 USB 设备**（只有 8188FU 与 `f766:0007` 手柄/接收器）
  → 蓝牙硬件要么走 UART（MTK 常见）、要么需专用驱动触发枚举。
- **待办**：设备在线时查 `dmesg | grep -i -E "bt|blue"`、`/dev/rtk_btusb`、`/dev/ttyS*`，确定 BT 走 USB 还是 UART。

---

## 五、Q3-③：红外遥控

- 运行内核 `modules.builtin` 中**没有任何 IR/遥控驱动**（无 `rc-core`/`gpio-ir`/`hi_ir`）；`/proc/bus/input/devices` 只有 `f766:0007 "Game USB Joystick"`。
- EmuELEC rootfs 的 `/kmod/hi_ir.ko`（107,323 B）vermagic = **`4.4.35_s40`**，与运行内核 `4.4.35_ecoo_81082668` **不匹配**，S90modules 亦明确拒绝加载。
- 已从原厂 Android 包提取遥控键映射备用：
  - `emuelec/work/ir_android/Vendor_0001_Product_0001.kl`（9241 B，海思 IR 遥控标准键表）
  - `emuelec/work/ir_android/Generic.kl`
- **可行路径（待设备）**：① 尝试 `insmod --force` 加载 `hi_ir.ko`（同 4.4.35，风险中等）；② 或获取 4.4.35_ecoo 版 `hi_ir.ko`；③ 无驱动则红外不可用。

---

## 六、打包（Q4）

- 现成流程：`build_v11.py` 造 boot.img → AOSP `signapk.jar -w`(testkey) 签名 `update.zip`（recovery 直刷）。
- WiFi 落地只需在 EmuELEC rootfs 里增加：
  1. `lib/modules/4.4.35_ecoo_81082668/kernel/drivers/wifi/usb_rtl8188fu/rtl8188fu.ko`
  2. 一个开机自动 `insmod` 的脚本（并入既有 `S90modules` 或 `histb-*` 链）
  3. `wpa_supplicant.conf`（可参考 `work/stock_wpa_supplicant.conf`）
- `update.zip` 必须正好命名 `update.zip`，且用 JDK7 + `signapk.jar -w` 本地盘签名。

---

## 七、下一步

1. **设备上线** → 实测 `insmod rtl8188fu.ko` → 确认 wlan0 与上网；确认蓝牙走 USB/UART；试 `hi_ir.ko` force。
2. 切换 GUI：EmuELEC 侧加 `/storage/roms/ports/` 图标；Android 侧做 APK（调用既有 `/data/a4/switch-to-emuelec`）。
3. 把 WiFi + 切换 UI 一并打进 release `update.zip`。

## 八、本轮新增产物

| 文件 | 说明 |
|---|---|
| `emuelec/work/wifi/rtl8188fu.ko` | **vermagic 4.4.35_ecoo_81082668**，可直接加载 |
| `emuelec/work/wifi/rtl8188eu.ko` | 备用（同版本） |
| `emuelec/work/wifi/modules.{dep,alias,builtin}` | haiNAS 的模块依赖/内建清单 |
| `emuelec/work/stock_rtl8188fu.ko` 等 | 原厂 Android(3.10) 驱动与固件（供 Android 侧参考） |
| `emuelec/work/ir_android/Vendor_0001_Product_0001.kl` | 红外遥控键映射 |
| `emuelec/tools/probe_*.py` / `export_ko.py` | 取证与提取脚本 |
