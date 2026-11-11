# ★ 终极方案：让原厂 OMX 解码器原生支持 HEVC 4K（真机已验证）

> 2026-10-10 凌晨。**这是本项目的正确解**——不是写 shim 转发 HiMediaPlayer，
> 而是**修好框架层缺的那两处**，让海思原厂硬件解码器自己解 HEVC，
> 解码帧写进 App 自己的 gralloc buffer（与 H.264 完全同一条路）。

---

## 0. 一句话结论

设备上 `/system/lib/libstagefright.so`（ACodec 所在）**被海思裁掉了 HEVC**。
只要把两处补回来，`MediaCodec` 就能把 HEVC 请求送到原厂 OMX 组件，
而**原厂组件其实早就支持 HEVC**（角色/端口格式/缓冲分配实测全过）。
**我们的 OMX shim 在这个方案里完全不需要。**

---

## 1. 为什么之前的 OMX shim 白做（层的错位）

```
App(ijk/当贝)
 └─ MediaCodec (Java)            ← App 直接调
     └─ ACodec → OMXNode → OMX 服务 → OMX 组件 (libOMX.hisi.video.decoder.so)
                ↑ 墙在这里：厂商 ACodec 里没有 HEVC
```

我们一天多都在**组件层**（`.decoder.so`）做工，而墙在**上一层的 ACodec**：
ACodec 不认识 `video/hevc` → 直接 `-1010` 失败 → **根本走不到组件**。
所以组件改得再好都无效。

---

## 2. 根因（两处，都在 libstagefright.so 里）

### 2.1 角色表 `kMimeToRole` 缺 `video/hevc`
`ACodec::setComponentRole("video/hevc")` 在表里查不到 → `ERROR_UNSUPPORTED(-1010)`
→ `configureCodec returning error -1010`。

### 2.2 mime→编码值表缺 HEVC 行
`ACodec::setupVideoDecoder` @**0x4e774**（反汇编）：
```asm
movs r4, #0                      ; i = 0
ldr.w r8, [pc,#116] / add r8, pc ; r8 = 表基址 = 0xFC0D0
loop:
  ldr.w r1, [r8, r4, lsl #3]     ; table[i].mime  (8 字节/条)
  strcasecmp(mime, r1)
  if match: coding = [table+4] → setVideoPortFormatType(0, coding, Unused); return
  i++; cmp i,#6; bne loop
```
该表在 **0x0FB0D0**，6 条 `{const char* mime; int coding}`，coding 明文：
`7,4,3,2,9,10`（AVC / MPEG4 / H263 / MPEG2 / VP8 / VP9 —— **没有 HEVC**）。

实测（`out/dep_hv4.logcat.txt`，上一轮 shim 版本）ACodec 就是拿着 **3** 来枚举端口的：
```
GetParameter(VideoPortFormat port=0) nIndex=0..7
SetParameter(VideoPortFormat port=0) comp=3      ← coding==3 那条 = 我们借壳的 H263 行
```

---

## 3. 补丁（`patch_stagefright_hevc.py`，共 8 字节）

| # | 偏移 | 原 → 新 | 说明 |
|---|---|---|---|
| 1 | 0x0D7087 | `"video/3gpp"` → `"video/hevc"` | 等长 11 字节覆写（H263 的 mime 串） |
| 2 | 0x0CA883 | `"video_decoder.h263"` → `"video_decoder.hevc"` | 等长 18 字节覆写（H263 的 role 串） |
| 3 | 0x0FB0E4 | `3` → `11`（`OMX_VIDEO_CodingHEVC`） | 让 ACodec 为 `video/hevc` 请求编码 11 |

- 文件长度不变、不动指针、不重排表；脚本自带 3 重校验（原串必须命中、
  原串全文件唯一、编码表序列必须 == `[7,4,3,2,9,10]`），不符即拒绝。
- 副作用：**H.263 / video/3gpp 解码失效**（机顶盒上无实际用途）。
- 备份：`/data/media/stfbak/libstagefright.so`（原厂）。

### 为什么原厂组件不用改
`omx_vdec.c` 源码 + 探针实测（`orig.so`，即设备上那份，MD5 与 A6 工程 prebuilt 一致）：

```
SetParameter(StandardComponentRole="video_decoder.hevc") -> 0x00000000   ← 接受
GetParameter(PortDefinition port0)  → coding=11 (HEVC)                   ← 默认就是 HEVC
SetParameter(VideoPortFormat port=0 comp=11) -> 0x00000000               ← 接受
AllocateBuffer port0 ×3 / port1 4K -> 0                                  ← 全过
```
其 `codec_trans_list`（文件 0x8DA0 起，12 字节/条）：
```
0x8DA0 "video_decoder.avc"  | compress_fmt=7  | codec_type=0
0x8DD0 "video_decoder.h263" | compress_fmt=3  | codec_type=4
0x8E30 "video_decoder.hevc" | compress_fmt=11 | codec_type=16(STD_HEVC)  ★
```
且源码里 `m_dec_fmt` **只用于上报**，真正解码走 `eVidStd = STD_HEVC`。
**⇒ 组件侧本来就支持 HEVC，缺的只是框架层把请求送进来。**

---

## 4. 真机验证（2026-10-10，干净重启后）

`test_native_hevc.sh`：装【原厂解码器 + 补丁版 libstagefright】→ 整机重启 → 校验 → 播放 → 抓屏。

| 用例 | configureCodec 失败 | 软解回落 | Fatal | 画面（App 内 SurfaceView） |
|---|---|---|---|---|
| **HEVC 720p** (`hevc720.mp4`) | **0** | **0** | **0** | ✅ 彩条 + 进度条 00:02/00:06 |
| **HEVC 4K** (`4k.mp4`)         | **0** | **0** | **0** | ✅ 彩条 + 进度条 00:01/00:06 |
| H.264 回归 (`t.mp4`)           | **0** | **0** | **0** | ✅ 彩条 + 进度条 00:02/00:06 |

日志铁证（4K）：
```
I/OMXClient      : Using client-side OMX mux.
D/HISI_OMXVDEC   : Init OMX component OMX.hisi.video.decoder
D/HISI_OMXVDEC   : [OmxState] Loaded→Idle→Executing      ← 真的在硬件解码，持续 8s
I/MediaDecoder::open: open success: video/hevc hevc_mp4toannexb
（无 ffpipenode_create_video_decoder_from_ffmpeg / 无 FFAVDecoder::open）
```

**画面能被 `screencap` 抓到** ⇒ 帧是写进 **App 自己的 Surface**，不是硬件 VO 层。
这正是 shim→HiMediaPlayer 那条路做不到的（那条路 App 的 SurfaceView 永远是黑的）。

---

## 5. 部署 / 回滚

```bash
cd /e/A4-work/hijack
# 部署 + 验证（含整机重启）
./test_native_hevc.sh /data/local/tmp/4k.mp4 t1

# —— 手工部署 ——
adb push libs/orig.so                    /data/local/tmp/o && adb shell "cp /data/local/tmp/o /system/lib/libOMX.hisi.video.decoder.so"
adb push libs/libstagefright.hevc2.so    /data/local/tmp/s && adb shell "cp /data/local/tmp/s /system/lib/libstagefright.so"
adb reboot

# —— 回滚 ——
adb shell "cp /data/media/stfbak/libstagefright.so /system/lib/"
adb shell "cp /data/media/omxbak/libOMX.hisi.video.decoder.so /system/lib/"
adb reboot
```

## 6. 遗留 / 后续可做
- **seek / 暂停**：现在走的是原生 OMX 语义，App 的 seek/pause 由 ACodec 正常映射
  （不再是 shim 那种"只改自己 state"），建议实测确认。
- **音画同步**：视频/音频都在 App 自己的时钟域内（MediaCodec + AudioTrack），
  不再有 shim 时代"视频归 HMP、音频归 App"的双时钟问题。
- H.263 失效是否可接受（已确认可接受）。
- 可选：把 H.263 的 mime/role 串改回来 + 另找一条空壳行借位，彻底不影响任何现有编码。
