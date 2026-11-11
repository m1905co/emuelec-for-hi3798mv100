# 为什么是"改 so 字节"而不是"重新编译 libstagefright"？—— 可行性核查

日期：2026-10-10
问题：既然要让 ACodec 支持 HEVC（乃至 OMX 组件实际支持的更多格式），为什么不直接重新编译 `libstagefright.so`，而是改文件里的几个字节？

---

## 一、先确认一件事：源码是对得上的

| 版本源 | 路径 | 状态 |
|---|---|---|
| 厂商 4.4.4 参考 | `A6-Work/05-aosp-ref/frameworks_av_4.4.4/media/libstagefright/ACodec.cpp` | **git 检出，但只有 4 个 .cpp + 2 个 .h，无 Android.mk** |
| SDK overlay 4.4.2 | `A6-Work/01-sdk-overlay/HiSTBAndroid-4.4.2-SPC064/frameworks/av/media/libstagefright/ACodec.cpp` | 5156 行，**含 Android.mk（`LOCAL_MODULE := libstagefright`）** |
| 设备上的成品 | `/system/lib/libstagefright.so` | 1,031,304 B，md5 `45ad25f1…`（与 `A6-Work/08-stage0-output` 里的 frozen-lib **完全一致**） |

**两份 4.4 源码里 HEVC 都是被删掉的**（`grep -c MEDIA_MIMETYPE_VIDEO_HEVC` = **0**），而且它们的 `kVideoCodingMapEntry` 顺序是：

```c
{ AVC, CodingAVC }, { MPEG4 }, { H263 }, { MPEG2 }, { VP8 }, { VP9 }   // ← 就是 7,4,3,2,9,10
```

**与从设备二进制里反推出的编码值序列 `7,4,3,2,9,10` 逐条对应。**
⇒ 结论：**我们手上的源码就是设备这份 so 的源码**，我们的字节补丁 = 源码级改动的等价物（把 H263 那两行的值换成 HEVC）。

厂商相对 AOSP 原版的删除清单（`diff` 统计 4297 行差异），与格式相关的部分是：

```
- { MEDIA_MIMETYPE_VIDEO_HEVC,  "video_decoder.hevc",  "video_encoder.hevc" }   ← 删了
- { MEDIA_MIMETYPE_VIDEO_HEVC,  OMX_VIDEO_CodingHEVC }                            ← 删了
- { MEDIA_MIMETYPE_VIDEO_MPEG2, "video_decoder.mpeg2", ... }                      ← 删了（mime→coding 表里 mpeg2 还在，但没有 role，等于废条）
- { MEDIA_MIMETYPE_AUDIO_OPUS, ... } / AC3 / EAC3                                 ← 删了
+ "audio_decoder.ffmpeg", "audio_encoder.ffmpeg"                                  ← 把 MP2 换成 ffmpeg
```

---

## 二、为什么没有直接重编译 —— **本机没有可编译的 Android 4.4 树**

| 需求 | 本机现状 |
|---|---|
| 完整 4.4 源码基座 | ❌ **没有**。全盘 `build/core/version_defaults.mk` 只找到两处，**都是 `PLATFORM_VERSION := 6.0.1`** |
| 4.4 的 build 系统 | ❌ overlay 的 `build/core/` 只有 **1 个文件**（`dex_preopt.mk`） |
| 4.4 的工具链 / prebuilts | ❌ overlay 里**没有 `prebuilts/`** |
| 4.4 的 frameworks/av | ⚠️ 只有**片段**：`05-aosp-ref/frameworks_av_4.4.4`（4 cpp + 2 h）与 overlay 的 `frameworks/av` |
| **唯一完整的编译树** | ⚠️ `/home/mxz/aosp` = **Android 6.0.1**（A6 项目），`/tmp/spd` 也是 6.0.1 |

**关键矛盾**：本机唯一能"make"的树是 **6.0.1**，它 `out/` 里已经有一份 `libstagefright.so`（**1,416,036 B**）。但设备是 **4.4.2**（1,031,304 B）。
- 6.0 与 4.4 的 `libstagefright` **ABI 不兼容**（依赖的 `libc/libutils/libcutils` 版本不同，`ACodec` 的 `AudioTrack` 构造签名在 6.0 也变了 —— 这一点在同机的 A6 项目 log 里被明确记录过：`cannot locate symbol _ZN7android10AudioTrackC1E19audio_stream_type_tj... (A6 changed AudioTrack ctor signature)`）。
- ⇒ **把 6.0 编出来的 so 塞进 4.4 设备 = 必崩**。

**所以要重编译 4.4 版，必须先补齐前置条件**：
1. 拉一份**完整 AOSP 4.4.2/4.4.4 源码树**（含 `build/`、`prebuilts/`、`external/` 等，约 30~50 GB；4.4 现在已不在 AOSP 主流镜像上，需走 `aosp-clone-in-china` 里那套镜像方案）；
2. 把厂商的 overlay + 4.4.4 patch set 合上去（`ACodec.cpp` 单文件就差 4297 行）；
3. 用匹配的 GCC 4.8/4.9 工具链编译，与设备其它 4.4 组件保持 ABI 一致。

⇒ 这是一个"先花几小时到几天把环境搭起来"的前置工程，**不是当场能做的一个命令**。所以当时选了**字节补丁**这条**等价但零前置成本**的路。

---

## 三、就算重编译了，"支持 OMX 所有格式"也拿不到

OMX 组件的角色表（厂商源码 `codec_trans_list`）确实有：
`avc / hevc / mpeg1 / mpeg2 / mpeg4 / h263 / vc1 / wmv / avs / vp6 / vp8 / sorenson / divx3 / mvc`

但**上限在框架和 App，而不在 ACodec**：

1. **Android 4.4 没有这些 mime 常量**。`MediaDefs.h` 里只有 `video/avc`、`video/mp4v-es`、`video/3gpp`、`video/mpeg2`、`video/x-vnd.on2.vp8`、`video/x-vnd.on2.vp9`、`video/hevc`。
   **没有 VC-1 / WMV / AVS / VP6 / Sorenson / DivX3 / MVC 的 mime** ⇒ `MediaExtractor`/`MediaCodec` 层**根本表达不出**"我要 VC-1 硬解"。
2. **`setupVideoDecoder` 需要逐个 coding 的分支**，AOSP 只写了标准几种。
3. **App 只说标准 mime**。bilibili / tvbox 走 ijk，请求的是 `video/avc` / `video/hevc`，不会去请求自定义 mime。

⇒ **重编译能真正多拿到的其实只有**：
| 收益 | 说明 |
|---|---|
| **保住 H.263 解码** | 字节补丁占了 H.263 的槽位，重编译可以把 HEVC **新增**而不是**替换** |
| 恢复 MPEG-2 角色 | 厂商把 `video_decoder.mpeg2` 从 role 表删了 |
| 恢复音频 AC3/EAC3/OPUS | 厂商删掉了这几行 |
| 无需改二进制 | 干净、可复核、可 diff |

而"VC-1/WMV/AVS/VP6/DivX3/MVC"这类**加了也用不上**（没有 mime 通道）。

---

## 四、结论

| 问题 | 答案 |
|---|---|
| 源码在不在？ | **在**，而且**能对上设备二进制**（编码值序列 7,4,3,2,9,10 逐条吻合） |
| 当时为什么不编译？ | 本机**没有 4.4 的完整编译树**（只有 6.0.1 的，ABI 不兼容），重编译要先拉 30~50GB 源码 + 重建厂商 patch set |
| 字节补丁算不算"捷径/隐患"？ | 不算。它是**源码级改动的等价物**，只动了 3 处（2 个字符串 + 1 个整数），可校验、可回滚 |
| 重编译值得做吗？ | **值得，但不是为了"支持所有格式"**，而是为了：① 不再牺牲 H.263；② 顺手恢复 MPEG-2/AC3/EAC3/OPUS；③ 得到可维护的源码基线 |
| 前提 | 先备好完整的 **Android 4.4** 源码树 + 工具链；否则同样只能用字节补丁 |

---

## 五、如果将来真要重编译，建议的最小改动

改 `ACodec.cpp`（4.4.4 基线），**只加不删**：

```c
// ① kMimeToRole[] 里补回
{ MEDIA_MIMETYPE_VIDEO_HEVC,  "video_decoder.hevc",  "video_encoder.hevc"  },

// ② kVideoCodingMapEntry[] 里补回
{ MEDIA_MIMETYPE_VIDEO_HEVC,  OMX_VIDEO_CodingHEVC },

// ③ 可选：补回 MPEG2 的 role
{ MEDIA_MIMETYPE_VIDEO_MPEG2, "video_decoder.mpeg2", "video_encoder.mpeg2" },
```

这样 HEVC 是**新增**的，H.263 保留；再编 `libstagefright.so` 即可。
（注意：`omx_vdec` 组件的端口格式列表"跟着 role 走"，role 设成 `video_decoder.hevc` 时它自己就会广告 HEVC —— 这条已在真机验证过。）
