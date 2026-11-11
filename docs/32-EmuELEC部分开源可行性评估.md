# 32 · EmuELEC 部分开源可行性评估（最重要）

> 问题：**当前的 EmuELEC 部分，能不能开源？**
> 结论先行：**部分能，部分不能。** 你的**自有代码与改造**可以且应该开源；
> 但**构建出的二进制镜像（rootfs / 内核 / 整盘固件）不能直接当"开源"发布**，
> 因为它们内嵌了海思/ARM/Mali/OMX 等**专有 blob**和第三方模拟器核心（混合许可证）。
> 正确做法是走 **「源码 + 构建配方」** 模式（和 EmuELEC / LibreELEC 自己一模一样）。
> 日期：2026-11-11 ｜ 置信度：高（以下结论均基于本工作区已核实的文件）

---

## 1. 一句话结论

| 类别 | 能否开源 | 怎么开 |
|---|---|---|
| **A. 你的自有代码/改造**（a4-* 工具、init 脚本、ES 补丁方法、构建/打包脚本、文档） | ✅ **能** | 直接放仓库，0BSD / GPLv2 |
| **B. 构建产物二进制**（rootfs.img、uImage、完整 p1-p9 固件） | ⚠️ **不能直接"开源"** | 只发**源码 + 构建脚本**，专有 blob 让用户自己从设备/SDK 提取，**不入库** |
| **C. 私密/专有内容**（逐机 MAC、recovery host key、海思/ARM 驱动与解码库、运营商安卓） | ❌ **不应/不能发布** | 严禁入库与分发 |

---

## 2. 证据（本工作区已核实）

| 证据 | 路径 / 事实 | 推论 |
|---|---|---|
| 你的移植 LICENSE | `emuelec/emuelec-for-hi3798mv100-main/emuelec-for-hi3798mv100-main/LICENSE` 头两行：`Zero-Clause BSD` / `Copyright (c) 2026 ghkjgod and contributors` | **你自己的 EmuELEC 移植是 0BSD**（极宽松，可任意开源/闭源/商用） |
| 第三方模拟器核心 | `emuelec/.../tf-card/EmuELEC/cores/*.so` 共 10 个（fbneo 54MB、mame2003_plus 28MB、picodrive、pcsx_rearmed、mgba…） | **混合许可证**：GPL/MIT/非商业/各自 BIOS 条款，不能一概当"自由"再分发 |
| 预编译内核 | `emuelec/EC6108V9C-…-optimized/06-kernel-20M.bin`（EmuELEC 内核）是预编译二进制 | 海思 BSP 内核含**专有驱动**（Mali GPU、H264/H265 解码、HDMI），无源码、无再分发权 |
| rootfs 内嵌专有用户态 | EmuELEC rootfs 内 `libMali.so`（ARM 专有）、`libOMX.hisi.video.decoder.so`（海思专有） | 这些**不是你的代码，也没有开源许可**，随镜像走 ≠ 可开源 |
| 整盘固件含私密 | `report/30` 明确：完整 p1-p9 镜像含固定 MAC `00:11:22:33:44:55`、recovery 的 Dropbear host key，"**只适合本地/私有同型号设备，不应原样公开发布**" | 含**逐机私密信息**，公开发布有隐私/运维风险 |
| 双系统依赖专有安卓 | 双系统的另一半是运营商/华为 Android（proprietary），靠 misc 标记切换 | 开源 EmuELEC 半边**不牵连**安卓半边，但整盘固件发布会把两者都带出去 |

**置信度：高** —— 以上均来自本机文件与既有报告，非推测。

---

## 3. 分类详解

### A 类：可开源（你的自有贡献）

这些是 100% 你写的、不含专有代码的部分，可放心开源：

- `tools/` 下的 **a4-* 全家桶**：`a4-switch.c`(写 misc)、`a4-switchd`、`a4-os-switch`、`a4-uv`、`a4-pad`、`a4-wifi`、`a4-menu`、`a4-perf`、`a4-joymap.sh`、`a4-evtest`、`a4-exitd`、`a4-ird`、`a4-hotplug`、`a4-inject`、`a4-vpad`、`a4-keys` 等
- **init 脚本**：`S93wifi`(WiFi 只从安卓导入)、`S94a4-ird`(红外→uinput 桥)、`S96a4-inputrecover`(热插拔)、`S97a4-cpufreq`、`S94a4-menu`、`S96a4-exitd`
- **EmulationStation 选中高亮补丁**（`tools/es-gamelist-highlight.py` + 偏移说明）及 ES 二进制补丁方法
- **HEVC 硬解补丁方法**：`libstagefright.so` 3 处等长覆写（8 字节）的**偏移与原理说明**（注意：发布"怎么改"合法；发布"改好的 .so"仍带 AOSP 许可义务，见下）
- **构建/打包脚本**：`tools/repack_ee3.py`、`tools/build_emuelec_standalone.py`、updater-script 生成逻辑
- **本工作区 39 篇 report/** 文档（你自己的经验总结，可公开）

> ⚠️ **GPLv2 传染性提醒**：EmuELEC 上游是 **GPLv2**。你对这些 GPL 组件的**修改**（如 ES 补丁、retroarch 配置）若随 EmuELEC 分发，按 GPLv2 必须**提供对应源码**（或至少提供补丁 + 指向上游源码）。发布"字节偏移补丁 + 打补丁脚本 + 上游链接"即满足义务。**不要把改好的二进制当闭源卖。**

### B 类：只能"源码 + 构建配方"发布（不能直接开源二进制）

`emuelec_rootfs.img`(340MB)、`uImage`(p10 内核)、`EC6108V9C-…-p1-p9` 整盘固件——
这些**镜像里混装了 A 类（你的）+ 上游 GPL + 第三方 + 专有 blob**，整体无法用一个宽松许可"开源"。

**正确模型（业界标准）**，与 EmuELEC/LibreELEC/Amlogic 社区完全一致：

```
仓库只放：
  - 你的 A 类源码与脚本
  - 一份 build.sh：从官方 EmuELEC 源码拉取 → 打你的补丁 → 产出 rootfs
  - 一份 BLOBS 说明：用户自行从设备 dd 出 / 从海思 SDK 拷出以下专有文件，
    构建脚本把它们放到指定位置（仓库不含这些二进制）：
      * 内核 uImage（海思 BSP，用户自备或自行编译）
      * libMali.so / libOMX.hisi.*（GPU/解码，海思/ARM 专有）
      * 各 libretro core（按需，遵守各自许可证）
```

这样**你发布的是"方法"，专有 blob 由使用者自己提供**——既合法，又和上游做法一致。

### C 类：严禁发布

- **含逐机私密信息的整盘镜像**：固定 MAC、recovery Dropbear host key（`report/30` 已警告）。
  若一定要发"出厂镜像"，必须先脚本化洗掉 MAC/key 并让首启随机生成。
- **海思/ARM 专有驱动与解码库**：`libMali.so`、`libOMX.hisi.*`、内核里的专有模块——你**没有再分发权**，只能让用户自己从设备/SDK 取。
- **运营商安卓专有权**：双系统的安卓半边是华为/运营商固件，绝不可随 EmuELEC 开源。

---

## 4. 推荐发布结构（GitHub 仓库示例）

```
a4-emuelec/
├── LICENSE            # 0BSD（你的移植）
├── README.md          # 说明：本仓只含源码与构建配方，专有 blob 自备
├── src/               # A 类：a4-* 工具、init 脚本、ES 补丁工具（全部 0BSD/GPLv2）
├── patches/           # EmuELEC/RetroArch 的补丁（ diff 形式，满足 GPLv2 提供源码）
├── build/
│   ├── build.sh       # 拉官方 EmuELEC → 打补丁 → 出 rootfs
│   └── fetch-blobs.sh # 从设备/SDK 提取专有 blob 的指引脚本（不落地二进制）
├── packaging/
│   ├── repack_ee3.py
│   └── build_emuelec_standalone.py   # 本次新增的独立 recovery 包构建器
└── docs/              # 本工作区 report/ 中可公开的部分（剔除含私密/设备具体的段落）
```

**许可证选择**：
- 你的纯工具（`a4-*` 不依赖 GPL 代码）→ **0BSD**（你已用，保持）。
- 对 EmuELEC/RetroArch 的**修改**部分 → 必须 **GPLv2**（与上游一致，提供源码）。
- 整仓建议以 **GPLv2** 统一定调（最省事、与 EmuELEC 兼容）；若想让工具更宽松，可把 `src/` 下纯自有工具单独标 0BSD、其余 GPLv2。

---

## 5. 风险与免责（如实）

| 风险 | 说明 | 等级 |
|---|---|---|
| GPLv2 违约 | 发布了改好的 ES/RetroArch 二进制却没给源码 | 中（用 diff+脚本规避即可） |
| 专有 blob 再分发 | 把 libMali/海思 OMX 等随仓库发 → 侵权 | 高（**严禁入库**） |
| 私密信息泄露 | 发了含固定 MAC / host key 的整盘镜像 | 中（发前脚本化清洗） |
| libretro 各核心许可 | 部分核心非商业/需 BIOS，混发可能违规 | 低-中（按需取，遵守各自条款） |
| "EmuELEC" 名称/商标 | 上游对派生项目用名有协调惯例 | 低（注明是 unofficial 派生即可） |

---

## 6. 给用户的直接建议

1. **现在就能做的**：把 A 类源码 + 构建脚本 + 文档推到一个 GitHub 仓库（0BSD/GPLv2），标题写清
   "unofficial EmuELEC port for Hi3798MV100 / EC6108V9C"。
2. **不要做的**：不要把 `update_a4_dual.zip`、`update_a4_emuelec.zip`、`EC6108V9C-…-p1-p9`、
   或任何 `*.img`/`*.so`(专有) 直接丢进公开仓库或网盘。
3. **若一定要分发可刷镜像**：先做 MAC/key 清洗脚本，且**不带** libMali/海思 OMX 等 blob，
   让使用者自行从自己设备提取——并在 README 显著声明"专有组件由使用者自行提供，作者不提供"。
4. **双系统切换的 misc 机制、红外桥、WiFi 从安卓导入、降压逻辑**——这些是你最有价值的原创，
   开源后对其他海思盒子玩家很有用，也最"干净"（无专有依赖），**优先开源这部分**。

> 一句话：**你的脑子（方法、脚本、补丁偏移、切换机制）可以大方开源；
> 你的磁盘（二进制镜像、专有库、私密信息）只能自己留着或让使用者自己造。**
