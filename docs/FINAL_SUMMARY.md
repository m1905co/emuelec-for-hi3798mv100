# Hi3798MV100 盒子改造总结（最终版）

设备：Hi3798MV100 / 291_EC6108V9_2024，Android 4.4.2，kernel 3.10.84
日期：2026-10-08 ～ 10-11
**最终刷机包：`E:\A4-work\update_hisi_full_v2.zip`（311,866,342 字节，AOSP testkey 签名）**

---

## 一、视频解码：第三方播放器硬解 HEVC/4K

**问题**：bilibili/tvbox 等播放器无法硬解 H.265，画面黑屏或走软解。

**根因与修法**（native 路线，OMX shim 路线已废弃——shim 走 HMP VO 层导致 SurfaceView 全黑）：
真正的墙在框架层 `libstagefright.so`（ACodec）：厂商裁掉了 HEVC。

`libstagefright.hevc2.so` 仅 3 处等长覆写补丁：
| 位置 | 原值 | 新值 |
|---|---|---|
| mime 表 | `video/3gpp` | `video/hevc` |
| role 表 | `video_decoder.h263` | `video_decoder.hevc` |
| 编码值表 | 3 (H.263) | **11 (HEVC)** |

关键认知：HEVC 的 OMX 编码常量是 **11** 而非 16；role 槽位 18 字节是硬约束（只能等长覆写）；改 so 后必须同步处理编码值，否则 ACodec 拿 H263 的值 3 去开 HEVC 组件。

**效果**：ijk/MediaCodec → `OMX.hisi.video.decoder` 硬解 HEVC 4K 成功，12/12 有画面 0 崩溃；logcat 实证 `HISI_OMXVDEC` 活跃、无 `HiMediaPlayer`。

## 二、防休眠（测试期工具，已撤除）

**根因**：`persist.hdmi.suspend.enable=1` + `persist.sys.HDMISuspendEnable=true`，HDMI 掉信号 10s 强制 goToSleep → adbd 掉线、实验报废。

测试期用 `nosleep.sh` 开机看守解决（已验证有效），**但实际使用中"该休眠就休眠"是正常行为，此工具不进入最终方案/刷机包**，设备上已撤除。备用通道：`telnet 192.168.31.16:23` 免密 root（工具 `telnet_dev.py`），adb 失联时可进。

## 三、温度监控（测试期工具，已撤除）

`thermal_monitor.sh` + `daemonize` + 自启钩子曾用于标定四档电压边界、双降压稳态等全部实验，**数据已存档（PC 端 out/ 目录 + 各报告），验证完成后从设备与刷机包移除**。

## 四、降压：CPU + core 双域（本轮核心成果）

**物理前提**：`P_dyn=C·V²·f`，降压必降功耗——但视频场景 CPU 只占 ~20% 热量，单独降 CPU 被 VDEC/VPU/GPU 稀释（实测 ≈0，被 1°C 传感器分辨率淹没）。

**突破口**：
1. `pm_gpu` 的 `volt=/freq=/dvfs` 全是空壳（只有 `avs` 有效），GPU 无法直调；
2. **`/proc/hisi/msp/pm_core`（核心域，喂 GPU/VPU/VPSS/DDR）可写、可回读、可恢复** —— 这才是视频发热的正主。

**实测曲线（4K H265 ijk 播放中，core 阶梯下探）**：
| core | 1060 | 1040 | 1020 | **1000** | 980 | 960 |
|---|---|---|---|---|---|---|
| 温度 | 79.3 | 78.7 | 78.0 | **77.0** | 77.0 | 77.0 |

→ **1000mV 是甜点**（−2.3°C），再低进平台纯冒险（core 域含 DDR，挂机需断电）。

**CPU 侧**（钉 1.0GHz + avs off，边界 1030mV）：满载 1155→1080mV 实测 **−1.6°C**（三轮一致 +1.0/+1.8/+2.0）；写法必须"钉 min=max → avs off → 写 volt"，否则被 DVFS/热控还原。

**双降压 15 分钟稳态（4K H265 ijk 硬解，81 样本）**：
| 配置 | 稳态温度 |
|---|---|
| 基线（CPU 1140 Auto + core 1060） | 84°C |
| **CPU 1080mV + CORE 1000mV** | **80.10°C**（80°C 占 81%） |

**净降 ≈ 4°C**；电压 15 分钟零漂移；解码全程不断。

## 五、刷机包内容（update_hisi_full_v2.zip，v3）

基于 10-08 原始 update.zip 重打包 + 签名，**只保留长期有用的改动**：
| 文件 | 改动 |
|---|---|
| `system/lib/libstagefright.so` | HEVC 补丁版（md5 1f6a8757） |
| `system/lib/libOMX.hisi.video.decoder.so` | 原厂（md5 bdad13f2） |
| `userdata/app/com.tvbox.live-1.apk` | TVBox 预装（md5 a523692b）；刷机释放到 `/data/app`，首启由 PM 扫描注册 |
| `baseparam.img` | **出厂默认分辨率改为 1080P50**：DISP1 `FMT` 258→`1`，`VIRSCW/VIRSCH`=1920/1080（md5 838e4f43） |
| `system/build.prop` | **仅第106行** `service.media.hiplayer.graphic=true`（其余保持原值；`optimalfmt.enable=1` / `perfer=native` 本就是出厂默认，未改） |
| `system/etc/uvmode.sh` | 手动降压开关（`sh uvmode.sh on/off/status`，联动 core 域） |
| `system/etc/init.bigfish.sh` | 原厂逻辑 + 开头：全屏 setprop(延迟) + 内联降压块（md5 78d6c44c） |

**内联块内容**（init.bigfish.sh 开头，开机即执行）：
```
( sleep 30
  setprop service.media.hiplayer.graphic true    # 系统播放器全屏（见第六节）
  ... CPU 钉 1.0G@1080mV + core 1000mV ...       # 降压，uv_disable 可关
) &
```
**显示不由脚本管**：出厂默认写进 `baseparam.img`，运行时档位由 设置→分辨率 决定（见第七节）。

**为什么内联/写 build.prop**（实测教训）：recovery 解包**不保留 zip 权限位**——独立脚本刷进 system 后是 644 无执行位，
`钩子 &` 直接执行失败（第一版刷机包降压没生效的根因）。故逻辑内联进 init.bigfish.sh（权限由原包保证）或写 build.prop。

### 5.1 TVBox 为什么不走 `system/preinstall/`（v3.1 修正）

原方案把 TVBox 放 `/system/preinstall/TVBox.apk`，靠原厂 `/system/bin/preinstall.sh`（`pm install -r`）安装 —— **实测在本固件上走不通**：

1. **`init.bigfish.sh` 卡死**：其 `APP_MARK` 段的 `busybox tar -xf /system/media/audio/cp.tar /data/app/` 因
   **`cp.tar` 在本固件不存在**（原包/新包都没有，`find /system -name "*.tar"` 为空）而失败，`until` 循环
   **永久空转** —— 实测 PID 常驻 `R` 态、约 **7% 整机 CPU**（`top` 6.8%），脚本后面所有行
   （`basicService -d`、`sh /system/bin/preinstall.sh`）**永远执行不到**。
2. **备用触发也不行**：`/system/bin/dhcpcd_am.sh`（DHCP 上线时）也调 `preinstall.sh`，但它在最小环境下
   `sh /system/bin/pm install` 失败（PATH/BOOTCLASSPATH 缺失），而脚本**仍无条件 `touch` 标记文件** ⇒ **永不重试**。
   （实测：刷完机只联网，`/data/local/symbol_thirdpart_apks_installed` 被创建，但 `pm list packages` 里没有 `com.tvbox.live`。）

**修正**：TVBox 改放 `userdata/app/com.tvbox.live-1.apk` —— 刷机时 `package_extract_dir("userdata","/data")`
释放到 `/data/app/`，`updater-script` 紧随其后的 `set_perm_recursive(1000,1000,0771,0644,"/data/app")` 修好所有者，
**首次开机由 PackageManager 扫描 `/data/app` 自动注册**。这正是原包自带 bilibili/当贝/JerryLive 三App 的安装方式
（实测它们的 codePath = `/data/app/com.bilibili.tv-1.apk`）。**不依赖任何脚本、不依赖执行位、无时序问题。**

**使用**：recovery 刷入。**恢复原始包**：`update_20261008_2147_orig.zip` 备份在 E:\A4-work\。

### 5.2 删除 `init.bigfish.sh` 里永久空转的 `until` 循环（v3.2）

**删掉的代码**（原厂第 136-155 行）：
```sh
APP_MARK=/data/local/symbol_preinstall
app_success_flag=0
if [ ! -e $APP_MARK ]; then
	until [ $app_success_flag -eq 1 ]
	do
		busybox tar -xf /system/media/audio/cp.tar -C /data/app/   # cp.tar 不存在 ⇒ 永远失败
		if [ $? -eq 0 ]; then ... app_success_flag=1; touch $APP_MARK
		else app_success_flag=0; fi
	done
fi
```
**循环里有什么有用的东西吗？——只有一处**：给 `/data/app/*.apk` 设 `system:system / 644`。
而这一步**刷机时 `updater-script` 的 `set_perm_recursive(1000,1000,0771,0644,"/data/app")` 已经做过**
（也正因如此，原包自带的 3 个 App 权限正常、PM 能扫到）。所以**该动作已保留为一次性兜底**，循环本体删除。

**替换为**：
```sh
APP_MARK=/data/local/symbol_preinstall
if [ ! -e $APP_MARK ]; then
	for file in /data/app/*.apk; do [ -f "$file" ] && chown system:system "$file" && chmod 644 "$file"; done
	touch $APP_MARK
fi
```
**效果（真机实测）**：杀掉该空转进程后 `top` 立刻变化 ——
`idle 69.7% → 95.2%`，`sys 20.9% → 2.3%`（此前该 `sh` 进程常驻 R 态、约 6.9% 整机 CPU）。

**⚠️ 顺带挡掉的（重要）**：循环删掉后脚本会首次走到尾部，那里有三条**从未执行过**的语句，
已全部注释并写明原因，避免凭空改变机器行为：
```sh
#basicService -d        # ← 是「TCP 命令/抓包服务」，binary strings 含
                        #   "Server sock %d is listening on TCP port %d" / "TCPSERVERCMDPARSE"
                        #   / "tcpdump" / "/data/capsrv.log" ⇒ 会开一个可远程下发命令的 TCP 端口
#echo 0x1 0x1 > /proc/msp/pm
#sh /system/bin/preinstall.sh   # 已无用；且其末尾含 `mount -o remount,rw system`
```
（`config.disable_location` / `ro.total.memsize` / `ro.total.flash` 这几条无害 setprop 现在会正常执行。）

## 六、系统播放器画面"只有左上角"的修复（v2.2 新增）

**现象**：tvbox 里用"系统播放器"放视频，画面只占屏幕左上角；换 ijk 就全屏；**与视频源分辨率无关（4K 也一样）**。bilibili 一直正常。

**定位**：抓 `dumpsys SurfaceFlinger` 确认 tvbox 的 SurfaceView 是 **1920x1080 全屏**（应用侧无问题）；
logcat 实锤是 **HiMediaPlayer 自己**调 `HI_UNF_VO_SetWindowAttr w[1280] h[720]` 把 VO 窗口设成了 720p 尺寸：

```
I/HisiMediaPlayer  : OutPut Adapter Mode
V/HisiSurfaceSetting: HI_UNF_VO_SetWindowAttr x[0] y[0] w[1280] h[720] ...
```

**根因**：`build.prop` 里 **`service.media.hiplayer.graphic=false`** —— 该开关决定 HiPlayer 的显示路径，
false 时视频窗口固定 1280x720（约等于 CVBS 那路的虚拟屏尺寸），在 1920x1080 屏上就只占左上 2/3 × 2/3。

**修复**：改 `true` → 窗口立即变为 `Disp=Out=0/0/1920/1080`，**所有分辨率均铺满**（用户实测确认）。

**⚠️ 刷机后仍小窗的二次坑（v2.3 修复）**：`service.media.hiplayer.graphic` 是 **service.\* 属性（不持久）**，
且 **mediaserver 启动时会把属性写回 false**（`libmediaplayerservice.so`/`libhiplayer_adapter.so` 含该属性名）。
只写 build.prop 不够 —— 必须**等 mediaserver 起来后**再 `setprop true`。
故 init.bigfish.sh 里把它放进 `( sleep 30 ... ) &` 延迟块（与降压同块）。
实测：手动 setprop true 后 30 秒不会被重置 ⇒ 覆盖是开机一次性行为。
（md5 897a4cab / 包 311,860,155 B）

**排除过的错误方向**（都有实测数据，供后续参考）：
| 假设 | 实测结果 |
|---|---|
| 物理输出分辨率导致 | 改 `disp1 fmt 720p50` → 窗口更小，无效 |
| Android 显示尺寸导致 | `wm size 1280x720` → 内核 VirtualScreen 不跟随，无效 |
| 视频源分辨率导致 | 用户反证 4K 也是小窗；SF 里 SurfaceView 本就是全屏，无效 |
| `persist.sys.video.adaptformat` | false→true 无效 |
| `persist.sys.cvbs.and.hdmi` | **无需改动**（保持 true 也全屏） |
| `persist.sys.display.4k2k` | 非必需 |

**副作用核查**：`graphic=true` 播放中 GPU 仍 200MHz、PP_util 18~23%、GP_util 0~1%（对比 false 时 PP 12~19%）
⇒ **GPU 负担基本没变，可忽略**。

**bilibili 为何正常**：走 MediaCodec + SurfaceView（SurfaceFlinger/GLES 合成），不经过海思 VO 窗口。

## 七、显示输出：**由系统设置自己持久化**（定论）

**硬件上限**：本机 HDMI 为 **1.4b**（~10.2 Gbps）⇒ **物理上无法输出 4K60**。EDID 里 4K 只有 24/25/30。
实测电视（Mi TV）EDID：1080P60/50、1080i60/50、720P60/50、576P50、480P60、PAL/NTSC、
640x480/800x600/1024x768/1280x1024/1440x900/1920x1200、3840x2160_24/25/30、4096x2160_24，**Native = 1080P60**。

### 7.1 ★ 定论：分辨率由 `settings system display_px` 持久化（实测确认）

**设置 → 分辨率**（`com.android.settings/.c10.ResolutionActivity`）菜单项：
`D1 / 720P / 1080i / 1080P / 4K-24Hz / 4K-25Hz / 4K-30Hz`（**无 1080P60**）。

**调用链**（从 Settings.apk 的 dex 挖出）：`ResolutionActivity` → **`HmtDisplayManager`**（`/system/framework/HMTAdapter.jar`）
→ **`HmtDisplayManagerServer`**（system_server）→ 海思显示 HAL。

**「改前/改后」diff（用户依次点 720P、1080P）**：

| 项 | 初始 | 点 720P | 点 1080P |
|---|---|---|---|
| 实况 `disp1 Formt` | 1080P60* | 720P50 | **1080P50** |
| **`settings system display_px`** | 0 | **8** | **1** |
| `persist.sys.optimalfmt.enable` | 1 | 0 | 0 |
| `persist.sys.screen.w/h` | 1920/1080 | 1280/720 | 1920/1080 |
| `persist.sys.display.customize` | `1,1,...` | `1,0,...` | `1,8,...` |
| **PDM**（`/proc/msp/pdm`） | 1 | **1（不动）** | **1（不动）** |

（*初始的 1080P60 是当时脚本强行下发的结果。）

⇒ **分辨率设置持久化在 Settings 数据库的 `display_px`，与 PDM 无关**（菜单改分辨率时 PDM 纹丝不动）。
**`display_px` 存的就是 `HiDisplayManager.ENC_FMT_*` 常量**：点 720P → `8` = `ENC_FMT_720P_50`；
点 1080P → `1` = `ENC_FMT_1080P_50`（见 `java/com/hisilicon/android/HiDisplayManager.java`）。
选择手动档位时系统会把 `persist.sys.optimalfmt.enable` 置 0（关闭自动协商）。

**踩坑（重要）**：`settings` CLI 在本机**静默失败**（返回空），据此我曾误判"DB 里没有分辨率键"；
必须用 `content query --uri content://settings/system` 才看得到 `display_px`。

### 7.2 本固件的"自动协商"**只算不用**（决定性实验）

把输出强行打到 720P60（电视也支持它）再触发协商 `echo swrst > /proc/msp/hdmi0`：
```
optimum format is 0 / get current format is 7 / final optimum format = 0
optimum format enable is enabled
The TV is support is format, so just use is.     ← 电视支持 720P60 ⇒ 沿用，不升级
```
⇒ 协商**只算不用**，掉到 720P 就回不来（固件多了一条"当前格式被支持就沿用"分支，该串不在本地 SDK 源码里）。
**手动档位（display_px）走的是另一条路，正常生效**，所以用设置即可。另：`hi_adp_hdmi.c` L560-588 在
`getCapRet != HI_SUCCESS`（读不到 EDID）时兜底 `720P_60` 并 `baseparam_save()` —— 自动模式下的另一个坑。

### 7.3 最终方案：**不为显示写任何脚本**

- 早期的 `display_fix.sh`（每 15s 轮询）与 `echo fmt 1080p60`（开机一行）**均已删除**
- **出厂默认 = 包内 `baseparam.img`（1080P50）**；刷机后 `/data` 虽被清，但默认值由 baseparam 保证，**无需手动再点**。
- 想要别的档位：直接去设置里选

### 7.4 协商机制与 binder 接口（保留备查）

**开关（`Hi3798MV100/customer.mk` 出厂默认）**：`persist.sys.optimalfmt.enable=1`、`persist.sys.optimalfmt.perfer=native`。
实现在 SDK 源码 `frameworks/hidisplaymanager/hal/hi_adp_hdmi.c` + `hal/display.c`；运行进程 `/system/bin/displaysetting`。

| perfer | 说明 | 实测选中 |
|---|---|---|
| `native`（默认）| 沿用驱动报的 native 值 | 0 = 1080P60 |
| `max_fmt` | 海思格式表里 EDID 支持的最高 | 258 = 4K30 |
| `p60hz` / `i60hz` | 偏 60Hz（先查 4K30） | 258 = 4K30 |
| `p50hz` / `i50hz` | 偏 50Hz（先查 4K25） | 257 = 4K25 |

**binder 事务码**（`HiDisplay` = `com.hisilicon.android.IHiDisplayManager`，FIRST_CALL_TRANSACTION=1）：
`SETFMT=5`、`GETFMT=6`、`GETRANGE=12`、`SAVEPARAM=30`、`RESET=36`、`RELOAD=41`。
实测 `SETFMT` 能改实况，但 `SAVEPARAM`/`RESET` **写不进 PDM**（`TURN_ON_SD0` 已定义，返回值取自 SD0）——
与本分辨率设置无关，无需再用。

### 7.5 ★ 出厂默认分辨率：`baseparam.img`（刷机包已改）

**开机默认输出存在 `baseparam` 分区**（`/dev/block/mmcblk0p5`，**刷机脚本会写它**）的
**`BASE_TABLE_DISP1`（HDMI 那一路）**，由内核在启动最早阶段展开 —— "这里写多少，开机默认就多少"。

| 键 | 原厂值 | 含义 |
|---|---|---|
| `BASE_KEY_FMT` @0x894 | **258** | `ENC_FMT_3840X2160_30` = **4K30**（⇒ 新刷机默认 4K30）|
| `BASE_KEY_VIRSCW` @0xef4 | 1920 | 虚拟屏（画布）宽 |
| `BASE_KEY_VIRSCH` @0xf1c | 1080 | 虚拟屏（画布）高 |

**★ 历史坑（"无论怎么改都是 720p"）**：只改 `FMT` 而不同时改 `VIRSCW/VIRSCH`，
设备原值 `1280/720` ⇒ 画布不放大，**输出永远是 720p**。必须**三项一起改**。

**与设置菜单的关系（实测同步）**：设备当前 `baseparam DISP1 FMT = 1` 且 `settings display_px = 1` —— 两者一致。
**设置菜单改档位时两处一起改**（`display_px` 记录 + baseparam 落盘）。

**本次改动**：包内 `baseparam.img` 的 DISP1 `FMT`：258 → **`1`（`ENC_FMT_1080P_50`）**，VIRSCW/VIRSCH 保持 1920/1080。
- **为什么用 `1`（1080P50）而不是 `0`（1080P60）**：菜单项与值配对为 `1080P↔1`、`720P↔8`、`4K-30Hz↔258`…，
  **菜单里没有 1080P60 项**；用 `0` 会造成"默认 1080P60、菜单指不出对应项"的不同步。
- 备选文件：`libs/baseparam.1080p60.img`（FMT=0）；解析/校验工具：`tools/bp_parse.py`
- 包内 `baseparam.img` md5 = `838e4f43`（原厂为 `c2cde500`）

## 八、运行时状态（收尾时）

- 双降压生效中：CPU `1.0G@1080 AVS Off`，CORE `1000mV`
- 显示：**由系统设置持久化**（`settings system display_px=1` = 1080P50）；脚本不碰显示
- 温度监控 / 防休眠已撤除，设备恢复原生休眠行为
- 关键工具（PC 端留存）：`core_uv_probe.sh`、`soak_dual.sh`、`watch_net.sh`、`analyze_net.py`、`deploy_thermal.sh`、`deploy_avs.sh`、`telnet_dev.py`
- 报告：`THERMAL_TUNING.md`（CPU 曲线/10 条坑）、`NET_STREAM_AB.md`（网络流 A/B）、本文件

## 九、遗留事项

- 显示分辨率：**出厂默认已写进包内 `baseparam.img`（DISP1 `FMT=1` = 1080P50）**，刷完开机即 1080P50；
  想要别的档位去 设置→分辨率 里选（会同时更新 `display_px` 与 baseparam）。
- ✅ **core=1000mV 的开机自启已通过真实重启验证**：`CORE: volt = 1000(mv)` + CPU `1.0G@1080 AVS Off`。
- 显示分辨率：设置里已选 1080P（`display_px=1`）⇒ 下次重启可复核 `disp1 Formt` 仍是 **1080P50**。
- **出厂默认已固化**：包内 `baseparam.img` DISP1 `FMT=1`（1080P50）⇒ 刷完开机即 1080P50，无需手动设置。
- `persist.sys.display.customize` 是 **PDM 的镜像**（改它无效，`display.c:2008-2015` 会用 PDM 反写）；
  它可能显示 1080P50 之类 —— **以屏幕实况为准**（看 `/proc/msp/disp1` 的 `Formt`）。
- AVS 扩展（VP8 槽位换 AVS，`libstagefright.avs.so`）已备好未部署——无片源，等需要时 `deploy_avs.sh`。
- GPU 频率锁 200MHz 不可调；若要再压温度，下一站是查 core 域与 DDR 频率的联动（有挂机风险）。
