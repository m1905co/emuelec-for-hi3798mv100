# 让 EmuELEC 读写安卓存储空间放 ROM（Loop 偏移 + Bind 隔离）

> 日期：2026-10-21
> 目标：用上 eMMC 里原本"够不着"的 1.9 GB 空间，同时**不碰安卓一个字节的数据**
> 状态：✅ 已部署并双向验证（开机自动挂、关机自动卸、连续 restart 不泄漏 loop）

---

## 1. 先说清楚：为什么不能直接用 EmuELEC 的 p10

这是整件事最关键的一步，之前的结论"p10 会毁安卓"是对的，但只对了一半。

eMMC 实测量 3.64 GB。两套分区表对同一块盘有**完全不同的切法**：

| 物理偏移 (MiB) | 安卓（16 项） | EmuELEC（10 项） |
|---|---|---|
| 0 – 102 | p1…p12（fastboot…iptv_data） | p1…p8（…fastplay 合并为 68M） |
| 102 – 442 | **p13 `backup` 340M** | **p9 `storage` 340M** ← EmuELEC 根 |
| **442 – 782** | **p14 `cache` 340M** | ← **p10 `userdata` 从这里开始** |
| **782 – 1302** | **p15 `system` 520M** | ← 被 p10 覆盖 |
| **1302 – 末尾** | **p16 `userdata` 2.3G** | ← 被 p10 覆盖 |

- `p13 ≡ p9`：同一块区域，两套编号。EmuELEC 根文件系统就在这里。
- **EmuELEC 的 p10 起点是 442 MiB**，一路盖到盘尾 —— 用它就等于抹掉安卓的 `cache + system + userdata`。
- 但**安卓真正的 userdata 在 1302 MiB**，比 p10 起点晚了 860 MiB。

所以正确做法不是"用 p10"，而是**用整盘偏移精确对准 1302 MiB**，绕开一切 p10 的坑。

---

## 2. 实现方案

```
/dev/mmcblk0                       ← 整块 eMMC
   │
   ├─ losetup -o 1365245952        ← 偏移 1302 MiB（不是 442 MiB！）
   │     ↓ /dev/loop0
   ├─ mount -t ext4 -o rw,noatime  →  /mnt/android
   │        （整盘挂载，但代码只走下面这一个子树）
   │
   └─ bind mount  /mnt/android/media/0/EmuELEC  →  /storage/android-roms
            ES 只看得见这一个目录
```

关键偏移（务必记牢）：

```
1302 MiB = 1302 × 1048576 = 1365245952 字节
```

> 我第一次算成 `1365260288`（多 14336 字节），mount 直接 `Invalid argument`。差一个字节都不行。

---

## 3. 安全边界 —— "别的完全不动"具体怎么做

| 措施 | 作用 |
|---|---|
| **bind mount 只暴露一个子树** | ES / RetroArch 看到的只有 `/storage/android-roms`，`/mnt/android` 下的 `app/`、`dalvik-cache/`、`system/` 一律不在视野里 |
| **代码路径只 mkdir 自己的目录** | 脚本里唯一写操作是 `mkdir -p $MNT/$SUB`，其余全部只读判断 |
| **rw 失败自动降级只读** | 若 ext4 需要修复（上次硬断电），脚本不强制 fsck，改为 `-o ro` 挂载，绝不冒险 |
| **关机显式 sync + umount + detach loop** | inittab 加了一条 shutdown 钩子，在 `umount -a -r` 之前跑 |
| **loop 句柄记在 `/tmp/a4-androidroms.loop`** | stop 时只 detach 自己那一个，不误伤别人的 loop |

### 唯一无法避免的副作用（必须知道）

ext4 是**日志型文件系统**。写入 `media/0/EmuELEC` 时，journal 区域会在**文件系统层**被更新——这是机制，不是数据改动，安卓的任何文件内容都不受影响。

风险点是**硬断电**：如果正在写游戏时直接拔电，journal 会脏，安卓下次启动需要 replay。ext4 的 replay 是幂等的，通常自愈；但极小概率出现目录项损坏。

**缓解**：
- 正常关机 / 重启 / 切回安卓，都会走 `umount -a -r`，干净收尾；
- 拷贝大批游戏时不要断电；
- 实在怕，可以只在安卓侧拷贝，EmuELEC 侧只读（见 §6 方案 B）。

---

## 4. 部署清单

| 文件 | 内容 |
|---|---|
| `/etc/init.d/S93a4-androidroms` | 4233 B，开机挂载 / 关机卸载，`start\|stop\|restart\|status` |
| `/etc/inittab` | 新增 `::shutdown:/etc/init.d/S93a4-androidroms stop`（在 `umount -a -r` 之前） |
| `/storage/ee/config/.emulationstation/es_systems.cfg` | 新增 `andr-fbneo` 系统（28 → 29 项），备份 `.bak-1021` |
| `/etc/inittab.bak-1021` | 原 inittab 备份 |
| `/storage/ee/logs/a4-androidroms.log` | 挂载日志 |
| 本地源文件 | `tools/S93a4-androidroms`、`tools/andr-fbneo.xml` |

启动顺序：`S93` 在 `S95emuelec`（启动 ES）之前，所以 ES 启动时目录已经就绪。

---

## 5. 使用方法

### 放游戏（两个位置，任选）

| 从哪里放 | 目标路径 | 说明 |
|---|---|---|
| **安卓系统** | `/sdcard/EmuELEC/roms/fbneo/` | 用文件管理器 / MTP，最稳 |
| **EmuELEC** | `/storage/android-roms/roms/fbneo/` | SCP / SMB 直接推 |

BIOS 放 **`/storage/roms/bios/`**（内部 p9，24MB 够用）：
- `neogeo.zip` —— 拳皇 / 合金弹头 / 月华剑士 / 双截龙格斗必需
- `pgm.zip` —— 三国战记必需

### ES 里看到什么

放进去 zip 后（重启 ES 或等 hotplug），ES 会多出一个系统：

```
Android Storage - Arcade (FinalBurn Neo)     →  /storage/android-roms/roms/fbneo
```

现在为空所以被隐藏（日志 `System "andr-fbneo" has no games! Ignoring it.`），一旦有 zip 就出现。

### 手动检查

```sh
/etc/init.d/S93a4-androidroms status
# mounted: /storage/android-roms
# /dev/loop0   2.3G  348.0M  1.9G  15% /mnt/android
```

---

## 6. 两种用法（按风险偏好选）

**A. 读写（当前已部署）**
- EmuELEC 可以直接往 `/storage/android-roms/` 拷
- 空间来自安卓 userdata 的 1.9 GB
- 代价：ext4 journal 会更新；硬断电有极小概率需要 replay

**B. 只读（更保守）**
- 把 S93 里 `mount -t ext4 -o rw,noatime` 改成 `-o ro`
- 游戏只在安卓侧拷贝
- 安卓分区**一个字节都不写**，零风险
- 代价：EmuELEC 里的存档要另存到 `/storage/savefiles/`

> 当前是 A。要切 B 就说一声，一行改动。

---

## 7. 验证记录

| 项 | 结果 |
|---|---|
| rw 挂载 | ✅ `rw,noatime,data=ordered` |
| bind 隔离 | ✅ `/storage/android-roms` 下只有 `bios`、`roms` |
| 写入 | ✅ 写→sync→读回→删除，多次通过 |
| 开机自动挂载 | ✅ 两次整机重启，日志均有 `start: bind OK ... free=1.9G` |
| 关机自动卸载 | ✅ 改 inittab 后首次关机，日志出现 `stop: umounted ... stop: done` |
| 连续 restart | ✅ 两次 restart 后仍复用 `/dev/loop0`，无 loop 泄漏 |
| ES 识别 | ✅ 日志 `System "andr-fbneo" has no games!` 说明配置已解析 |

> 注意：inittab 是 init 启动时读入内存的，改完**当次不生效**，下一次启动才用新版。我第一次验证时白等了一轮，就是这个原因。

---

## 8. 回滚

```sh
# 1) 停用挂载
/etc/init.d/S93a4-androidroms stop
mv /etc/init.d/S93a4-androidroms /storage/S93a4-androidroms.disabled

# 2) 恢复 inittab
cp -f /etc/inittab.bak-1021 /etc/inittab

# 3) 恢复 ES 配置
cp -f /storage/ee/config/.emulationstation/es_systems.cfg.bak-1021 \
      /storage/ee/config/.emulationstation/es_systems.cfg

reboot
```

安卓数据完全不受影响（我们只创建了 `/data/media/0/EmuELEC/` 这一个目录）。

---

## 9. 容量账

| 位置 | 总 | 可用 | 备注 |
|---|---|---|---|
| 内部 p9（EmuELEC 根） | 227 MB | 24.7 MB | 只够放 BIOS |
| TF 卡 | 1.8 GB | 1.2 GB | 已有 `tf-fbneo` 系统 |
| **安卓 userdata（新）** | 2.3 GB | **1.9 GB** | `andr-fbneo` 系统 |
| 合计可用于 ROM | — | **≈3.1 GB** | 你说的那 6 个系列约 600 MB，富余很大 |
| EmuELEC 的 p10 | 3.2 GB | — | ❌ **绝对不能用**，会毁安卓 |

---

## 10. 存档 / 截图 / 播放列表也一并重定向（2026-10-21 追加）

### 发现的问题

`run-retroarch.sh` 每次启动游戏都会重新生成 `retroarch-histb-runtime.cfg`，里面四个路径**硬编码**为 `${STORAGE_ROOT}/xxx`，而 `STORAGE_ROOT=/storage`：

```
savefile_directory    = "/storage/savefiles"      存档 .srm
savestate_directory   = "/storage/savestates"     即时存档 .state
screenshot_directory  = "/storage/screenshots"    截图
playlist_directory    = "/storage/playlists"      最近游玩 / 收藏
```

而 `/storage`（p9）**只剩 24.7 MB**。玩起来很快就会写满，写满后存档失败甚至影响系统。

### 解决方式：软链接（不改任何系统脚本）

```sh
mkdir -p /storage/android-roms/{savefiles,savestates,screenshots,playlists}
mv /storage/savefiles /storage/savefiles.local-1021     # 原为空目录
ln -sfn /storage/android-roms/savefiles  /storage/savefiles
# 其余三个同理
```

选软链接而不是改 `run-retroarch.sh` 的理由：
- 系统脚本升级会被覆盖，软链接不会；
- `run-retroarch.sh` 里的路径字符串不用动，RetroArch 会自然跟随链接；
- 一旦安卓分区挂载失败，S93 会自动把软链接还原成普通本地目录（`unlink_save_dirs`），存档不会写到空路径。

实测：

```
$ echo t > /storage/savefiles/_probe.srm
$ ls -l /storage/android-roms/savefiles/_probe.srm
-rw------- 1 root root 2 ... _probe.srm        ← 确实落在安卓分区
```

### 现在的写入全景

| 动作 | 写哪里 | 大小 |
|---|---|---|
| 拷游戏（一次性） | `/storage/android-roms/roms/fbneo` | 每游戏几十 MB |
| 游戏内存档 `.srm` | `→ android-roms/savefiles` | 几 KB ~ 几十 KB |
| 即时存档 `.state` | `→ android-roms/savestates` | 几百 KB |
| 截图 | `→ android-roms/screenshots` | ~1 MB |
| 最近游玩 / 收藏 | `→ android-roms/playlists` | 几 KB |
| ES 设置 / 手柄配置 | `/storage/ee/config`（p9） | 固定几十 KB |
| BIOS | `/storage/roms/bios`（p9） | 几 MB |

**结论：只要不玩游戏，放完游戏就是纯静态；一旦开玩，写入全部落在 1.9 GB 那边，不会撑爆 /storage。**

### 回滚

```sh
for d in savefiles savestates screenshots playlists; do
    rm -f /storage/$d && mkdir -p /storage/$d
done
```

（本地源文件：`tools/S93a4-androidroms` 已含 `link_save_dirs` / `unlink_save_dirs`）

---

## 11. 【2026-10-29】游戏已搬到 TF 卡 —— 刷机不再丢游戏

### 11.1 为什么要搬

`format userdata` 会清空安卓 `/data` ⇒ `/storage/android-roms`（= `<userdata>/media/0/EmuELEC` 的 bind）
变成空目录，**`andr-fbneo` 里的游戏全没**。而 TF 卡是独立分区（`/dev/mmcblk1p1`），刷机**完全不碰**。

### 11.2 放哪里（ES 已有对应系统，不用改配置）

TF 上对应的目录是 **`/media/emuelec-tf/EmuELEC/roms/fbneo`**，
`es_systems.cfg` 里早有这个系统（2026-10-21 建的）：

```xml
<system>
  <name>tf-fbneo</name>
  <fullname>TF Card - Arcade (FinalBurn Neo)</fullname>
  <path>/media/emuelec-tf/EmuELEC/roms/fbneo</path>
  <extension>.zip .ZIP</extension>
  <command>${HISTB_EE_ROOT}/bin/run-retroarch.sh fbneo %ROM%</command>
```

BIOS 也要跟过去：`run-retroarch.sh` 会**按 ROM 所在盘**选 BIOS 目录，
用 TF 上的 ROM 时它读的是 **`/media/emuelec-tf/EmuELEC/bios`**
（日志实测：`HiSTB launch BIOS path=/media/emuelec-tf/EmuELEC/bios`），
所以 `neogeo.zip` + `bios/fbneo/` 整个子树都复制了一份过去。

### 11.3 已完成的复制（实测）

```
源：/storage/android-roms/roms/fbneo/*.zip   （10 个 zip，337.7 MB）
目标：/media/emuelec-tf/EmuELEC/roms/fbneo   （同样 10 个，337.7 MB）
md5 抽检：mslug3.zip 25694621 / mslug4.zip 399e8d46 / kof97pls.zip f57f65f4  ← 与源一致
BIOS：/media/emuelec-tf/EmuELEC/bios/{neogeo.zip, fbneo/}
```

### 11.4 冷启动实测

```
uptime=108s
/dev/mmcblk1p1 /media/emuelec-tf vfat rw,...      ← S91histb-tf-storage 挂好
/media/emuelec-tf/EmuELEC/roms/fbneo  10 个 zip
ES 日志：tf-fbneo 的 "has no games" 告警数 = 0（其余 13 个空的 tf-* 系统正常被隐藏）
```

直接从 TF 路径启动游戏（与 ES 调用同一条命令）：

```
run-retroarch.sh fbneo /media/emuelec-tf/EmuELEC/roms/fbneo/mslug3.zip
→ RA 进程起来，画面 Metal Slug 3 标题，FPS 50.00，CREDIT 00
```

### 11.5 刷机后的表现

| 入口 | ES 里显示名 | 路径 | 刷机后 |
|---|---|---|---|
| TF 卡 | **TF Card - Arcade (FinalBurn Neo)** | `/media/emuelec-tf/EmuELEC/roms/fbneo` | ✅ **保留**（TF 不被刷） |
| 安卓存储 | Android Storage - Arcade | `/storage/android-roms/roms/fbneo` | ❌ 空（userdata 被 format），系统自动隐藏 |
| 内置 | Arcade (FinalBurn Neo) | `/storage/roms/fbneo` | 空（镜像里就是空的），隐藏 |

⇒ 全新刷完开机，ES 里能看到的街机入口就是 **TF Card - Arcade**，游戏直接可玩。

### 11.6 以后加游戏放哪

- **首选 TF**：`/media/emuelec-tf/EmuELEC/roms/fbneo/`（EmuELEC 里推，或把卡插电脑放 `EmuELEC/roms/fbneo/`）
- 新增 BIOS 同样放 `/media/emuelec-tf/EmuELEC/bios/`
- 放完重启前端（`/etc/init.d/S95emuelec restart`）或整机重启，ES 才重新扫目录

> TF 剩余空间：852 MB（复制前），可继续放。整包 4.0 GB 的 FBNeo 全集放不下，
> 需要挑着放或换大卡。
