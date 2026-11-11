# 两条路线 A/B 稳定性对比（2026-10-10 真机实测）

> 变量只有一个：`/system/lib/libOMX.hisi.video.decoder.so` 装哪个。
> 其余完全相同，含**同一份补丁版 `libstagefright.so`**（HEVC 的 mime/role/编码值三处补丁）。
> 判据客观化：`imgsig.py` 对 `screencap` 原始帧做**归一化纯色条检测**
> （对播放器淡入不敏感；桌面基准 0.004，彩条 0.76~0.91，阈值 0.30）。

---

## 1. 结果总表

| 指标 | **native**（原厂 orig.so 38092） | **shim**（我们的 so 67228） |
|---|---|---|
| **App 内画面达标** | **12 / 12** ✅ | **0 / 12** ❌ |
| 抓屏 bar（越高越好） | 0.7629 ~ 0.9066 | 0.0002（`mean_lum=6`，**纯黑**） |
| `configureCodec` 失败 | 0 | 0 |
| 回落软解（ffmpeg 视频解码器） | 0 | 0 |
| 解码器真的在跑 | `HISI_OMXVDEC` 活跃 12/12 | `OMXHijack … start -> 0` 12/12，HMP 帧计数有值 |
| mediaserver / 播放器崩溃 | **0** | 0（日志里的 `Fatal signal 13 (SIGPIPE)` 来自进程 **`ip`**，噪声） |
| mediaserver pid 漂移 | 无 | 无 |
| **整机卡死** | 无 | **1 次**（首轮第 7 场：adbd 无响应、ping 仍通、mediaserver pid 未变 ⇒ 用户态卡死；复测 6 场未复现） |
| **画面出口** | App 自己的 gralloc buffer → SurfaceView | `VO_CreateWindow`（硬件视频层），App 拿不到 |

片源：`t.mp4`(H.264 720p) / `hevc720.mp4`(HEVC 720p) / `4k.mp4`(HEVC 3840x2160)；
每场 force-stop → 清 logcat → 播放 → 5s 抓屏（不够再补 6.5s）→ 收尾。
native 4 轮（12 场）、shim 4 轮（前 6 场完成后卡死）+ 复测 2 轮（6 场，跑完）。

---

## 2. 为什么差异是结构性的

```
native:  App ─ MediaCodec ─ ACodec ─ OMXNode ─ [原厂 libOMX.hisi.video.decoder.so]
                                                        │
                                        channel_bind_buffer(App 的 gralloc buffer)
                                                        │
                                              硬件解码帧直接写回 App 的 buffer
                                                        │
                                        ACodec 在 App 侧 queueBuffer → SurfaceView   ★ 截得到

shim:    App ─ MediaCodec ─ ACodec ─ OMXNode ─ [我们的 shim]
                                                        │
                                          ES ─(本机 HTTP 流)─► HiMediaPlayer
                                                        │
                                         HMP 解出帧 → 输出到【自己的硬件 VO 窗口】
                                                        │
                                     App 的 SurfaceView 一帧都拿不到 → 全黑      ★ 截不到
```

- **native 的帧走在 App 自己的 buffer 上**（和 H.264 完全同一条路），所以
  `screencap` 能看到画面、App 的渲染/时钟/暂停/seek 天然自洽。
- **shim 的帧走在 HMP 自己的 VO 层**：机顶盒上可能直接在电视上出图，
  但**第三方播放器的 SurfaceView 永远拿不到帧** ⇒ 黑屏。
  实测 12 场全部 `bar=0.0002 / mean_lum=6`，即 App 画面区域是纯黑。

---

## 3. 稳定性结论

| | 判定 |
|---|---|
| **native** | ✅ **稳定可用**。12 场连续播放 H.264/HEVC/HEVC-4K，无崩溃、无软解回落、pid 不漂移、画面全部达标。 |
| **shim** | ⚠️ **不可用（对"第三方播放器能看"这个目标）**，且**存在低频整机卡死风险**。解码本身能跑（HMP 有帧输出），但画面送不进 App。 |

> 卡死那次的现场：日志停在 `HisiMediaPlayer: First video frame read` 之后，
> adbd 无响应但内核网络栈仍通（ping 正常）、mediaserver pid 未变
> ⇒ 典型的"用户态线程被阻塞住"（与历史记录里 `rb_write` 无限阻塞那次同源）。

---

## 4. 复现方式

```bash
cd /e/A4-work/hijack
./stability_test.sh native 4     # 原厂解码器：应 12/12 PASS
./stability_test.sh shim   4     # 我们的 shim：应 0/12（画面全黑），且有卡死风险
```
脚本已内置：整机重启清状态、所有 adb 调用 25s 超时（防卡死把脚本也挂住）、
设备失联自动判 `★设备失联（卡死）`、崩溃只统计 mediaserver/播放器（排除 `ip` 噪声）。

---

## 5. 当前设备状态

**已恢复为 native 配置**（可用状态）：
```
/system/lib/libOMX.hisi.video.decoder.so  38092   原厂
/system/lib/libstagefright.so            1031304  含 HEVC 三处补丁
```
备份：`/data/media/omxbak/libOMX.hisi.video.decoder.so`、`/data/media/stfbak/libstagefright.so`。

## 6. 建议
1. **采用 native 方案**，`shim` 路线退役（保留代码与文档作为技术记录）。
2. native 下 App 的暂停/seek 走的是**原生 OMX 语义**（不再是 shim 那种"只改自己 state"），
   建议顺手实测一遍确认。
3. 若将来某颗 SoC 的原厂解码器**真的**不支持 HEVC，再考虑 shim 那条路，
   并且必须同时解决"帧送回 App buffer"（否则必然黑屏）。
