# 25 · 双系统跑通：原厂 U-Boot + misc 开关

日期：2026-10-20
平台：Hi3798MV100（mdmo1d，1GB DDR，Android 4.4.2 + EmuELEC 4.4.35）
结论：**不改 U-Boot 的代码路径，只改一个字符串 + 一个 4 字节字段 + 12 字节标记，就实现了 Android / EmuELEC / recovery 三选一。电源键 recovery 全程保留。**

---

## 1. 最终架构

```
上电 → BootROM → U-Boot(p1, 618KB) → 模式判定（读 misc 前 0xC00 做子串匹配）
                                      ├─ 含 "boot-recovery" → mode1 → p3(5MiB) 4MiB → RSA 校验 → recovery
                                      ├─ 含 "product-test"  → mode2 → p10(58MiB) 24MiB → bootm 0x82000000 → EmuELEC
                                      └─ 无标记             → mode0 → p11(82MiB) 10MiB → bootimg → Android
```

| 分区 | 内容 | 说明 |
|---|---|---|
| p1 `fastboot` | 原厂 U-Boot + **cmdline 补丁** | 唯一改动在 `0x79440` 的 314 字节字符串 |
| p3 `recovery` | 原厂 recovery | **未改动**，电源键照常可进 |
| p9 `misc` | 12 字节开关 | 三个值：空 / `product-test` / `boot-recovery` |
| p10 `factory` | `ANDROID!` 头（ramdisk=0）+ `+0x800` EmuELEC uImage | EmuELEC 内核 |
| p11 `kernel` | 原厂 Android boot.img | Android 内核，**未改动** |
| p13 `backup` | EmuELEC rootfs（ext4，340M@102MiB） | EmuELEC 根文件系统 |

---

## 2. 三处改动（全部可回滚）

### 2.1 U-Boot 的 cmdline（p1，偏移 `0x79440`，314 字节槽位）

mode 2 分支用 `setenv("bootargs", <该字符串>)` 把启动参数交给内核。原值是给工厂测试用的 `root=/dev/ram` + `initrd=...`，**没有任何指向磁盘根分区的 root=**，所以塞任何"要从磁盘根启动"的内核都会死。改成海纳思那套验证过的参数（254 字节，余 60 字节填 0）：

```
mem=1G mmz=ddr,0,0,256M vmalloc=500M console=ttyAMA0,115200 root=/dev/mmcblk0p9
rootfstype=ext4 rootwait blkdevparts=mmcblk0:1M(fastboot),4M(bootargs),16M(recovery),
1M(deviceinfo),4M(baseparam),4M(pqparam),4M(logo),68M(fastplay),340M(storage),-(userdata)
```

- 该字符串**只有一个引用点**（`0xC2A948`），只影响 mode 2。
- 产物：`emuelec/work/fastboot_cmdonly_hinas.bin`，md5 `fb850755194cee1a7508f33ad1939cb2`，与镜像差异 216 字节。

### 2.2 p10 头部的 `ramdisk_size`（偏移 `0x10`，4 字节）

原头写着 `ramdisk_size=65`，U-Boot 会当真，塞一个 65 字节假 initrd 给内核 → 内核走 `initrd_load()` 分支 → panic。改成 0。

- 头本身必须保留：vendor 的 `bootm 0x82000000` 靠这个 `ANDROID!` 头找到 `+0x800` 的内核（清零头会报 `Wrong Image Format`）。
- 产物：`emuelec/work/p10_header_nord.bin`（2KB，kernel_size 保持 10,862,647）。

### 2.3 切换实现：接到原有的 APK / ES 菜单上（不是新增一个命令行）

原来那套「刷 env 到 p2」的实现被整条替换，**上层入口不变**：

```
Android 侧（APK 按钮）
  com.a4.switcher  ──写──▶  /data/a4/switch.request
                                  │
  a4-switchd (root, install-recovery.sh 拉起)  │ 每秒轮询
                                  ▼
                  /data/a4/switch-to-emuelec  ┐
                  /data/a4/switch-to-android  ┤ 都改成 exec /data/a4/a4-os-switch <target>
                                  ▼
                  /data/a4/a4-os-switch  ──写 misc + sync + reboot

EmuELEC 侧（ES 菜单「系统切换 / Switch OS」）
  es_systems.cfg  system="switchos"  →  /bin/sh /storage/ee/switch/<ROM>
                                  ▼
  /storage/ee/switch/01-reboot-to-android.sh  →  exec /usr/bin/a4-os-switch android
                                  ▼
                  /usr/bin/a4-os-switch  ──写 /dev/mmcblk0 偏移 50MiB 的标记 + reboot
```

| 位置 | 文件 | 作用 |
|---|---|---|
| Android | `/data/a4/a4-os-switch` | 唯一实现：`status / android / emuelec / recovery`，写 misc(p9) 后重启 |
| Android | `/data/a4/switch-to-emuelec`、`switch-to-android` | 薄包装，`exec a4-os-switch`（供 a4-switchd 调用） |
| EmuELEC | `/usr/bin/a4-os-switch` | 同一实现，但 misc 不在其分区表里，改按整盘偏移 `/dev/mmcblk0` **50MiB=102400 扇区** 写 |
| EmuELEC | `/storage/ee/switch/01-reboot-to-android.sh` | ES 菜单调用的包装脚本（带日志） |

已废弃但保留未删：`/system/xbin/a4-switch`（刷 p2 的 setuid 二进制）、`/data/a4/env-*.bin`、`/storage/ee/env-android.bin`。原厂 U-Boot 会覆盖 env 的 `bootcmd`/`bootargs`，这条路本来就不成立。

**实测**：APK 请求路径 → EmuELEC 25 秒起；ES 菜单路径 → Android 19 秒起。

---

## 3. 使用方法

日常切换**不需要电脑，也不需要敲命令**：

| 场景 | 操作 |
|---|---|
| Android → EmuELEC | 桌面 APK `com.a4.switcher` 点「切到 EmuELEC」 |
| EmuELEC → Android | ES 主菜单 →「系统切换 / Switch OS」→ 重启到 Android |
| 进 recovery | 断电 → 按住遥控电源键 → 上电 |

命令行等价物（调试用）：`/data/a4/a4-os-switch emuelec|android|recovery|status`、`/usr/bin/a4-os-switch ...`。

---

## 4. 恢复与回滚

| 场景 | 做法 |
|---|---|
| 卡住（某个标记对应的系统起不来） | 断电 → 按住电源键 → recovery → 「reboot system now」。**AOSP 退出时会清空 misc 命令字段，开关自动失效**（本轮实测两次） |
| 想彻底回原厂 | p1 写 `emuelec/work/fastboot_stock_v2.img`（618,444B）→ 1MiB md5 回到 `d4d00576`；p10 写 `p10.bak`（24MiB，md5 `a271e241`） |
| 只救内核+env | TF 卡 `/upgrade/update.zip`（8.35MB，只写 p11+p2，不碰 p1、不格盘） |
| 千万别用 | 311MB 全量包——它还会 format system / cache / backup(p13=EmuELEC) / userdata |

---

## 5. 证据链（串口实录）

`emuelec/work/serial/cap_step4.log`：

```
find the product partition...                     ← 标记被识别
MMC read: dev # 0, block # 118784, count 49152 ... OK   ← p10 24MiB 读取
## Booting kernel from Legacy Image at 82000800    ← 无假 initrd，头解析正确
Kernel command line: mem=1G mmz=ddr,0,0,256M vmalloc=500M ... root=/dev/mmcblk0p9 ...
mmcblk0: p1(fastboot) ... p9(storage) p10(userdata)
EXT4-fs (mmcblk0p9): mounted filesystem with ordered data mode
HiSTB EmuELEC supervisor started as PID 1834
login: root  |  RTL871X: assoc success            ← WiFi 连上
```

切换实测：EmuELEC → Android 19 秒起；Android → EmuELEC 约 40 秒（SSH 22 / telnet 23 均可登录，root 免密）。

---

## 6. 本轮踩到的坑（都已解决，供以后参考）

| # | 坑 | 真相 |
|---|---|---|
| 1 | 以为要改 bootcmd 里的 `0x82000000` 地址 | **不用改**。该地址在 1GB 机器上可用，且 vendor 的 bootm 会解析 `ANDROID!` 头自动找 `+0x800` 内核。而且那次补丁实际没生效（真正执行的 bootcmd 是另一份副本） |
| 2 | 以为 DTB 的 `/chosen/bootargs` 会覆盖 bootloader cmdline | **不会**。实测内核用的是 U-Boot 给的 cmdline（report/11 那条结论是错的） |
| 3 | 以为 p11 塞 EmuELEC boot.img 就行 | mode 0 的 cmdline 也没有 `root=`（安卓靠 ramdisk 当根）→ 必死 |
| 4 | 满 13 项分区表 | p8 之后落到 extended devt（major 259）。**但 extended devt 本身能挂根**（p9=259:1 现在就在用），真正致命的是假 initrd |
| 5 | 清零 p10 头去 initrd | 头是 bootm 定位内核的凭据，清了就 `Wrong Image Format`。要改的是头里的 `ramdisk_size` |

---

## 7. 当前状态与遗留

- 设备此刻处于 **Android**（misc 已清空），p1/p10 为上述新配置，p3 recovery 与 p11 内核都是原厂，p13 EmuELEC rootfs 完好。
- EmuELEC 侧 `es_input.cfg` 已恢复为 6 设备版（含 A4 IR Remote / ZhiXu Gamepad / Game USB Joystick），本轮未在电视上实测手柄，需要用遥控+手柄实际验证。
- 串口：板→PC 正常，**PC→板方向不通**（怀疑 TX/RX 接反），因此无法在 U-Boot 提示符下交互；这也是本轮只能靠"改标记 + 重启"推进的原因。
