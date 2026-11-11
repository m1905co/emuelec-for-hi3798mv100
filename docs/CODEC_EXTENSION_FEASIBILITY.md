# 用改 so 的方式给 ACodec 加编解码格式 —— 可行性与最终方案

日期：2026-10-11
结论先行：**可行。采用"永久占用 VP8 槽位 → AVS"，HEVC 已占用原 H.263 槽位。**

---

## 一、先分清"两个 so、三张表"

| 文件 | 表 | 作用 | 槽位数（实测） |
|---|---|---|---|
| `libOMX.hisi.video.decoder.so`（**组件**，原厂 38092，未改） | `codec_trans_list[]` | 角色 → (compress_fmt, codec_type) | **15 个角色** |
| `libstagefright.so`（**框架**，1,031,304） | `kMimeToRole[]` | mime → decoder / encoder 角色 | **17 条**（音频 12 + 视频 5） |
| 同上 | `kVideoCodingMapEntry[]` | mime → OMX 编码值 | **6 条** |

原厂视频解码 role 只有 5 个：`avc / mpeg4 / h263 / vp8 / vp9`
（补丁后：`avc / mpeg4 / hevc / vp8 / vp9`）

---

## 二、组件侧：硬件实际支持 **15** 种

`orig.so` 里 `video_decoder.*` 字面量：
```
avc avs divx3 h263 hevc mpeg1 mpeg2 mpeg4 mvc rv sorenson vc1 vp6 vp8 wmv
```
组件按 `strncmp(codec_trans_list[i].role_name, cRole, OMX_MAX_STRINGNAME_SIZE)` 匹配角色
⇒ **递对角色它就认**；认了以后端口格式（`m_dec_fmt`）自动跟着角色走。

实测 `codec_trans_list`（`compress_fmt` = OMX 编码值）：

| role | compress_fmt | STD |
|---|---|---|
| avc | 7 | 0 |
| mpeg2 | 2 | 3 |
| mpeg4 | 4 | 2 |
| h263 | 3 | 4 |
| wmv | 5 | 1 |
| vp8 | 9 | 13 |
| hevc | 11 | 16 |
| **avs** | **0x6F000005** | 6 |
| vc1 | 0x6F000001 | 1 |
| divx3 | 0x6F000002 | 5 |
| vp6 | 0x6F000003 | 10 |
| mpeg1 | 0x6F000004 | 3 |
| sorenson | 0x6F000006 | 14 |
| mvc | 0x6F000007 | 15 |

> 标准 `OMX_VIDEO_CODINGTYPE` 枚举只到 **HEVC = 11**
> （0=Unused,1=AutoDetect,2=MPEG2,3=H263,4=MPEG4,5=WMV,6=RV,7=AVC,8=MJPEG,9=VP8,10=VP9,11=HEVC）
> **AVS/VC-1/MVC 走 Khronos 厂商扩展区 0x6F0000xx** —— AVS 是 `0x6F000005`。

**关键**：`ACodec::setupVideoDecoder` 里**没有**按编码类型分支（只有**编码器**侧 `setupVideoEncoderParameters` 有 switch）
⇒ **解码路径是通用的**，塞新编码值不需要改代码，只改那两张表。

---

## 三、框架侧：槽位是"编译期常量"，不能真新增

```c
for (size_t i = 0; i < sizeof(kMimeToRole) / sizeof(kMimeToRole[0]); ++i)
```
`sizeof/sizeof` 编译期折叠成常量（反汇编可见 `cmp r4,#6` 之类立即数）
⇒ **往文件里追加一条不会被遍历到**；**只能"征用"已有条目**。

**字符串长度是硬约束**（就地覆写，新串必须 ≤ 原串）：

| 槽位 | 原字符串 | 长度 | 可写成 |
|---|---|---|---|
| mime | `video/x-vnd.on2.vp8` | 17 | 任何 ≤17 的 mime |
| mime | `video/x-vnd.on2.vp9` | 17 | 任何 ≤17 的 mime |
| role | `video_decoder.vp8` | 17 | 任何 ≤17 的角色 |
| role | `video_decoder.vp9` | 17 | 任何 ≤17 的角色 |
| role | `video_decoder.mpeg4` | 18 | 任何 ≤18 的角色 |
| role | `video_decoder.h263` | 18 | 任何 ≤18 的角色 |

⇒ `video_decoder.avs`(17) 与 `video_decoder.hevc`(18) 的差别正好决定了：
**AVS 可以占 VP8/VP9（17 字节），HEVC 必须占 mpeg4 或 h263（18 字节）。**

---

## 四、最终方案（已实现）

### ① HEVC —— 占用原 H.263 槽位（早先已做）
```
0xD7087  "video/3gpp"          -> "video/hevc"
0xCA883  "video_decoder.h263"  -> "video_decoder.hevc"
0xFB0E4  编码值 3(H263)        -> 11(CodingHEVC)
```

### ② AVS —— 占用原 VP8 槽位（本次，`patch_stagefright_avs.py`）
```
0xD70BE  "video/x-vnd.on2.vp8"  -> "video/avs"            ( 9 ≤ 17)
0xCA8A9  "video_decoder.vp8"    -> "video_decoder.avs"    (17 = 17)  ★长度完全相等
0xFB0F4  编码值 9(VP8)          -> 0x6F000005(AVS)        ★厂商私有编码值
```
共 **18 字节**改动。

### ③ `media_codecs.xml` 需同步加一行（否则 `MediaCodecList` 不广告）
```xml
<MediaCodec name="OMX.hisi.video.decoder" >
    <Type name="video/mp4v-es" />
    <Type name="video/3gpp" />
    <Type name="video/avc" />
    <Type name="video/hevc" />
    <Type name="video/x-vnd.on2.vp9" />
    <Type name="video/avs" />          <!-- ★ 新增 -->
</MediaCodec>
```

### 结果
| | 补丁前 | 补丁后 |
|---|---|---|
| 视频解码 role | avc / mpeg4 / h263 / vp8 / vp9 | **avc / mpeg4 / hevc / avs / vp9** |
| kVideoCodingMapEntry | 7, 4, 3, 2, 9, 10 | **7, 4, 11, 2, 0x6F000005, 10** |

**代价**：VP8 硬解槽位让出。
**风险很低**：硬解器**从来没广告过 VP8**（XML 里只有 `video/mp4v-es/3gpp/avc/hevc/vp9`），
而**软解 `OMX.google.vp8.decoder` 仍在**（`media_codecs.xml` 第 104 行）⇒ VP8 内容仍有兜底。

---

## 五、产物

| 文件 | 说明 |
|---|---|
| `libs/libstagefright.avs.so` | 最终成品，md5 `127bc67996d9f6696bdd4702d0f96c0f`，1031304 字节 |
| `xml/media_codecs.avs.xml` | 加了 `video/avs` 的 XML |
| `patch_stagefright_avs.py` | 补丁脚本（从 HEVC 版生成，含 3 重校验 + 自检） |
| `deploy_avs.sh` | 部署 / 回滚脚本（`./deploy_avs.sh` / `./deploy_avs.sh restore`） |

---

## 六、还剩什么没验证（诚实清单）

1. **没有任何 AVS 片源可测** —— 解码器槽位已就绪，但"能不能真的放出 AVS"取决于：
   - `MediaExtractor` 能否把 AVS 从容器里解出来。
     **好消息**：`libstagefright.so` 的媒体扩展名列表里**有 `.avs` 和 `.avsts`**
     （`.m2ts .flv .m1v .m2v .tp .trp .m2p .avsts .divx ... .avs .ps .dv ...`），说明这套框架**认这个扩展名**。
   - **但**框架里没有 `video/avs` 这个 mime 常量，也没有 AVS 的 TS/PS stream_type 分支（需实测确认）。
2. **MPEG-TS 里的 AVS**（stream_type 0x42）能否被识别 —— 未验证。
3. 若要真用起来，最稳的路径是**自己写个小播放器**：直接给 MediaCodec 喂 AVS 裸 ES（`createDecoderByType("video/avs")` + 手动喂 Annex-B），绕开容器提取。

> 一句话：**"把格式加进解码器"这一步已经做完并可验证；"从片源里把 AVS 流拿出来"这一步取决于容器，需要一片真实 AVS 素材才能定论。**
