# EmuELEC WiFi 修复完成报告

**日期**：2026-10-14
**设备**：Hi3798MV100（mdmo1d，1GB DDR）
**结果**：✅ EmuELEC 开机自动连上 WiFi（wlan0 = 192.168.31.18），PC 可 ping 通、网关 0% 丢包

---

## 一、根因（两个关键点）

### 1. 驱动型号搞错了 —— 是 `rtl8188eu`，不是 `rtl8188fu`

| | rtl8188fu.ko | **rtl8188eu.ko** |
|---|---|---|
| haiNAS 内版本 | v4.3.23.6 | **v4.3.24** |
| ID 表 | `0bda:8177 / 817e / **f179**`（**无 0179**） | `0bda:8179 / **0179**`（**原生支持**） |
| 对 `0bda:0179` | 不匹配 → 需手工改表，改后 probe 成功但 `ndo_open` 返回 EPERM（`SIOCSIFFLAGS: Operation not permitted`） | **直接匹配、开箱即用** |

**验证方式**：切到 Android 实测 —— Android 用的正是 **`rtl8188eu`**（`lsmod: rtl8188eu 935258`），设备 ID 同样是 `0bda:0179`。
→ 说明本机 WiFi 芯片实际由 **8188EU 驱动**负责，之前一路用 `fu` 是方向性错误。

### 2. EmuELEC 没有任何无线用户态工具

- rootfs 里**没有** `wpa_supplicant` / `iw`（只有 `ifconfig` / `udhcpc`）
- EmuELEC = glibc **2.24**；haiNAS(Ubuntu 20.04) = glibc **2.31** → 不能直接搬二进制

**解法**：做「自带 glibc 的便携包」，用 2.31 的 `ld` 显式加载：
```sh
/opt/wifi/lib/ld-2.31.so --library-path /opt/wifi/lib /opt/wifi/bin/wpa_supplicant ...
```

---

## 二、证据链（全部实测）

```
# 驱动加载
RTL871X: rtl8188eu v4.3.24_16705.20160509
RTL871X: build time: Aug 26 2025 13:46:42      ← 与运行内核同批编译
bFWReady == _FALSE call reset 8051...          ← 正常固件复位流程
RTL871X: rtw_ndev_init(wlan0) mac_addr=7c:c7:09:f8:0c:7f

# 接口 up（此前 fu 版在此处报 EPERM）
ip link set wlan0 up  →  IPv6: ADDRCONF(NETDEV_UP): wlan0: link is not ready

# 关联 + 握手
RTL871X: auth success, start assoc
RTL871X: assoc success
RTL871X: set pairwise key camid:4 ... type:AES
IPv6: ADDRCONF(NETDEV_CHANGE): wlan0: link becomes ready

# DHCP
udhcpc: lease of 192.168.31.18 obtained, lease time 43200
route: default via 192.168.31.1 dev wlan0

# 连通性
ping 192.168.31.1 → 0% packet loss
PC ping 192.168.31.18 → 0% packet loss
```

---

## 三、关键前提（沿用之前成果）

1. **haiNAS = Ubuntu 20.04.5 armhf**，藏在 `mv100/www_ecoo_top.ext4`(Android sparse) → `backup-32.gz` → `Ubuntu-...img`(868MB ext4)
2. 其 `/lib/modules/4.4.35_ecoo_81082668/` 与 EmuELEC **运行内核逐字同版本**，模块可直接用
3. 内核**已内建** `cfg80211 / mac80211 / bluetooth / btusb / btintel`（所以 WiFi 协议栈齐全，只缺芯片驱动本体）
4. 传输路径：Android 侧 `adb`(67MB/s) 挂载 `mmcblk0p13` 直接写 EmuELEC rootfs —— 远快于 TTL

---

## 四、落地内容（已固化到 rootfs）

| 路径 | 内容 |
|---|---|
| `/lib/modules/4.4.35_ecoo_81082668/kernel/drivers/wifi/usb_rtl8188eu/rtl8188eu.ko` | 驱动（1,648,736 B，vermagic `4.4.35_ecoo_81082668`） |
| `/opt/wifi/bin/{wpa_supplicant,iw}` | 用户态工具（haiNAS 提取） |
| `/opt/wifi/lib/`（19 个 .so） | 自带 glibc 2.31 + libnl + libssl/libcrypto + libdbus 等依赖闭包 |
| `/opt/wifi/wpa_supplicant.conf` | SSID=`PandoraBox`（从 Android `/data/misc/wifi/` 取出） |
| `/etc/init.d/S87wifi` | 开机自启：insmod → up → wpa_supplicant → udhcpc（789 B，755） |

**已删除**误导性的 `usb_rtl8188fu/` 目录。

---

## 五、验证

**重启后**（无人工干预）：
```
lsmod                    → rtl8188eu 1246805 0
ifconfig wlan0           → inet addr:192.168.31.18  UP BROADCAST RUNNING
ping 192.168.31.1        → 0% packet loss
PC ping 192.168.31.18    → 0% packet loss
```
→ **开机自动联网已验证通过。**

---

## 六、可用通道（WiFi 通后）

| 通道 | 端口 | 说明 |
|---|---|---|
| telnet | 23 | `ecoo.top login:`，**root 免密**（实测可登录） |
| SSH (dropbear) | 22 | 开放；首次登录后建议 `passwd` 改密码 |
| adb | — | 仅 Android 侧 |

---

## 七、待办 / 后续

1. **蓝牙**：内核已内建蓝牙栈；此前 EmuELEC 下 `lsusb` 未见 BT 设备 —— 待确认是否走 UART
2. **红外遥控**：内核无 IR 驱动；`/kmod/hi_ir.ko` 版本为 `4.4.35_s40` 不匹配，待试 `insmod --force`
3. **打包**：把 WiFi（驱动+便携包+S87wifi）与切换 UI 一起打进 release `update.zip`

## 八、本轮产物（Windows 侧）

| 文件 | 说明 |
|---|---|
| `emuelec/work/wifi/rtl8188eu.ko` | **正确的驱动** |
| `emuelec/work/wifi/S87wifi` | 开机自启脚本（完整版） |
| `emuelec/work/wifi_bundle/{bin,lib}` | 便携 wpa_supplicant/iw + glibc 2.31 |
| `emuelec/work/wifi_bundle/wpa_supplicant.conf` | 无线配置 |
| `emuelec/tools/{telnet_push.py,collect_wifi.py,export_ko.py,...}` | 提取/推送脚本 |
