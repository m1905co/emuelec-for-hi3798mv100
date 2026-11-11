# EmuELEC for Hi3798MV100 (EC6108V9C) — 双系统 / 开源子集

把运营商海思 **Hi3798MV100** 机顶盒（EC6108V9C 等）改造成
**EmuELEC 游戏系统 + 原生安卓双系统** 的一套工具、补丁与文档。

> **适用机型：EC6108V9C（板级 `mdmo1d`，即"1D 机型"），Hi3798MV100，1GB DDR。**
> 其它 Hi3798MV100 板型未验证。

> 这是「可开源部分」的子集。专有二进制（内核 / libMali / 海思 OMX / libretro 核心 /
> 整盘固件）**不在此仓库内**，需按 `build/fetch-blobs.sh` 自行从设备/SDK 提取。

---

## 硬件目标
- SoC: HiSilicon Hi3798MV100（Cortex-A53, Mali-450）
- 设备: **EC6108V9C 系列**（板级 `hi3798mdmo1d_hi3798mv100_ddr3_2gbyte_8bitx4_4layers_emmc`，即 **1D 机型**）
- 内存: 1GB DDR3
- 存储: eMMC 9 分区 (p1–p9，双系统用 misc 标记切换) + TF 卡

## 本仓库包含（A 类：可自由使用，0BSD）
| 目录 | 内容 |
|------|------|
| `tools/` | 全部自研工具：双系统切换 (`a4-switch.c` + 脚本)、EmuELEC 输入/热键 (`a4-joymap.sh`, `a4-evinfo.c`, `a4-exitd.c`)、ES 选中高亮补丁 (`es-gamelist-highlight.py`)、RetroArch 映射 (`es2retroarch.py`)、固件打包/整包签名 (`repack_ee3.py`, `build_emuelec_standalone.py`, `sign_*.sh`)，以及通用固件/二进制分析辅助 (`armdis.py`, `make_edid.py`, `uimage.py`, `verify_*.py` …) |
| `ee_files/` | 设备上的 EmuELEC 覆盖文件（init 脚本、RetroArch/手柄配置） |
| `docs/` | 从 0 开始的完整攻关报告（双系统、U-Boot、WiFi/蓝牙/红外、手柄、HDMI、HEVC 硬解、热调优、开源评估） |
| `build/` | 构建配方 (`BUILD.md`) 与专有 blob 获取脚本 (`fetch-blobs.sh`) |

## 本仓库**不包含**（B/C 类，依规不发布）
- ❌ 预编译镜像：`emuelec_rootfs.img` / `uImage` / 整盘 p1–p9 固件 / `*.so` / `*.ko`
- ❌ 专有驱动与解码库：libMali、海思 OMX、预编译内核（芯片厂/ARM 专有）
- ❌ 10 个混合许可证的 libretro 核心（请从设备/SDK 自取）
- ❌ 任何含**固定 MAC / Dropbear host key** 的整盘镜像，以及运营商专有权利文件

## 如何构建
见 [`build/BUILD.md`](build/BUILD.md)。概览：
1. 拉取上游 *EmuELEC for hi3798mv100* 源码；
2. 套用本仓库的补丁与 `ee_files/` 覆盖；
3. 用 `tools/build_emuelec_standalone.py` 生成独立 recovery 刷机包；
4. 用 `signapk.jar -w` 对整个 zip 重新签名（EOCD 注释须保留）。

## 致谢 / Acknowledgments
- 本项目的移植、补丁与双系统改造建立在上游项目 **ghkjgod / emuelec-for-hi3798mv100** 的基础之上：
  <https://github.com/ghkjgod/emuelec-for-hi3798mv100> —— 感谢原作者的开源工作。
- 感谢 **EmuELEC**、**LibreELEC**、**RetroArch** 及其所有 libretro 核心作者。
- 感谢海纳思（ecoo）社区提供的 Hi3798MV100 板级 SDK / U-Boot 基线。
- 双系统切换、U-Boot、WiFi/蓝牙/红外、HEVC 硬解、热调优等具体攻关过程见 `docs/`。

## 许可证
- **本项目原创代码与文档**：0BSD（见 [`LICENSE`](LICENSE)）。
- **对 EmuELEC / RetroArch / LibreELEC 的修改**：遵循上游许可证（主要 GPLv2），
  本仓库以「源码补丁 + 构建配方」形式满足其「提供源码」要求。
- 第三方组件（libretro 核心、libMali、海思 OMX 等）请遵守各自许可证，从上游获取。

> ⚠️ 刷机有变砖风险；本仓库仅供你拥有合法权利的硬件使用。
