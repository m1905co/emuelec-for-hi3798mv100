# 这台盒子上「谁支持哪些编码」— 实测清单

> 依据：设备上在用的 `libstagefright.so`(md5 `1f6a87576834091566fa59f3a3da8e2f`，补丁版)
> 与 `/system/lib/libOMX.hisi.video.decoder.so`(md5 `bdad13f2d770e41c2f9ecd704ce7e7db`，**原厂未改**)，
> 以及 `/system/etc/media_codecs.xml`。

---

## 1. 补丁到底动了什么（字符串级对比，实测）

```
原版 decoder roles : video_decoder.avc  video_decoder.h263  video_decoder.mpeg4  video_decoder.vp8  video_decoder.vp9
补丁 decoder roles : video_decoder.avc  video_decoder.hevc  video_decoder.mpeg4  video_decoder.vp8  video_decoder.vp9
                                          ↑ H.263 的位置被 HEVC 占了

原版/补丁 encoder roles : video_encoder.avc  video_encoder.h263  video_encoder.mpeg4  video_encoder.vp8  video_encoder.vp9
                          ↑ 编码侧完全没动，H.263 编码仍可用

原版 mime : ... video/3gpp ...     （无 video/hevc）
补丁 mime : ... video/hevc ...     （无 video/3gpp）
```

**结论：损失的只有「MediaCodec 解码 H.263」这一项。编码 H.263、以及其他任何东西都没动。**

改动位置（`patch_stagefright_hevc.py`，全部等长覆写，共 3 处）：

| 偏移 | 原 | 新 |
|---|---|---|
| `0x0D7087` | `"video/3gpp"` | `"video/hevc"` |
| `0x0CA883` | `"video_decoder.h263"` | `"video_decoder.hevc"` |
| `0x0FB0E4` | 编码值 `0x03`(H263) | `0x0B`(OMX_VIDEO_CodingHEVC) |

> 前两处 = ACodec 的 **mime→role 表**；第三处 = ACodec 的 **mime→编码值表**。
> 所以"改了 so"和"改了两张表"是同一件事。

---

## 2. 三层各自支持什么

### 2.1 ACodec（`libstagefright.so`，已打补丁）
可用的解码 role 共 **5 个**：

| mime | role | 编码值 |
|---|---|---|
| `video/avc` | `video_decoder.avc` | 7 |
| `video/mp4v-es` | `video_decoder.mpeg4` | 4 |
| **`video/hevc`** | **`video_decoder.hevc`** | **11**（借原 H.263 的位置） |
| `video/x-vnd.on2.vp8` | `video_decoder.vp8` | 9 |
| `video/x-vnd.on2.vp9` | `video_decoder.vp9` | 10 |

- 编码值表里还有 MPEG-2 那一条（值 2），但 **没有 `video_decoder.mpeg2` 这个角色串**
  ⇒ MPEG-2 很可能仍然不可用。
- **H.263 解码已不可用**（mime 与 role 都被覆写了）。

### 2.2 OMX 硬解组件（原厂，**未改动**）
- 对外**只广告 1 条**端口格式，内容**跟着 role 走**（源码 `GetParameter(VideoPortFormat)` 里
  `case 0: f->eCompressionFormat = m_dec_fmt; default: return NoMore;`）。
- 厂商角色表（源码 `codec_trans_list` + `Hi3798OMXPlugin.cpp`）含：
  **avc / hevc / mpeg1 / mpeg2 / mpeg4 / h263 / vc1 / wmv / avs / vp6 / vp8 / sorenson / divx3 / mvc**，
  分辨率上限 4096×2304。
- 实测：设 `role=video_decoder.hevc` → port0 `coding=11`；
  `SetParameter(VideoPortFormat comp=11)` → `0`（接受）；
  4K `PortDefinition` 与 `AllocateBuffer`（port1 `bufSize=12441600`）→ `0`。
  ⇒ **组件本来就能解 HEVC，只是 ACodec 以前不去问它。**

### 2.3 `media_codecs.xml`（`MediaCodecList` 广告的清单）
```
硬解 : OMX.hisi.video.decoder : video/mp4v-es  video/3gpp  video/avc  video/hevc  video/x-vnd.on2.vp9
软解 : OMX.google.mpeg4.decoder / h263 / h264 / vp8 / vp9
       + 音频 mp3, amrnb, amrwb, aac, g711alaw, g711mlaw, vorbis, gsm, flac …
编码 : OMX.google.h264.encoder / OMX.hisi.video.encoder(video/avc) / OMX.google.h263.encoder …
```
⚠️ XML 里仍写着 `video/3gpp`，但 ACodec 已不认识它 ⇒ **这条声明现在是空壳**（会被广告、但用不了）。

---

## 3. 一句话总结

| 层 | 状态 |
|---|---|
| OMX 硬解组件 | **本来就会解 HEVC**，未改动 |
| ACodec（框架） | 补丁后**才肯去问 OMX 的 HEVC**；代价是**丢了 H.263 解码** |
| 最终效果 | `MediaCodec("video/hevc")` 现在能走通 → 4K HEVC 硬解可用 |
| 未受影响 | H.263 **编码**、AVC、MPEG-4、VP8、VP9、所有音频、所有其他组件 |

---

## 4. 频率相关（与画质/流畅度分开看）

**温度控制**：`/proc/hisi/msp/pm_temp` 输出
```
Temperature control is On
Temperature down threshold:  115 degree
Temperature up threshold:    100 degree
Temperature reboot threshold: 125 degree
```
- **当前温度值读不到**（该节点只给阈值）⇒ 超频后无法实时监控，只能靠长时间稳定性验证。
- 阈值偏高（100/115/125℃），说明厂商**不是靠降频控温**，而是**直接把上限设死**（CPU 1.0G/1.5G、GPU 400M）。

**可调点**（root 可写，重启即复原）：见 `FRAME_ANALYSIS.md` §7.2。

**重要边界**：放开频率改善的是 **流畅度/掉帧/起播**，**不会改善画质** ——
画质由「4K 被 GLES(GPU) 缩放」这条路径决定，与频率无关。
