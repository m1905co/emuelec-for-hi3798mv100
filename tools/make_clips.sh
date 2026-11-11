#!/bin/bash
# 生成测试用长视频（真实 HEVC 4K，带音频）
set -e
OUT=/mnt/e/A4-work/clips

echo "=== [1] 检查 ffmpeg 的 HEVC 编码器 ==="
ffmpeg -hide_banner -encoders 2>/dev/null | grep -iE "hevc|libx265" || true

echo
echo "=== [2] 生成 120 秒 4K HEVC 测试片（带音轨）==="
# 测试图源（内置，不需要外部文件）+ 正弦音频
ffmpeg -hide_banner -y \
  -f lavfi -i "testsrc2=size=3840x2160:rate=30:duration=120" \
  -f lavfi -i "sine=frequency=440:sample_rate=48000:duration=120" \
  -c:v libx265 -preset ultrafast -profile:v main -level:v 4.0 \
  -x265-params "log-level=none" \
  -c:a aac -b:a 128k \
  -pix_fmt yuv420p \
  -movflags +faststart \
  "$OUT/t_hevc_4k_120s.mp4" 2>&1 | tail -5

echo
echo "=== [3] 校验生成结果 ==="
ls -la "$OUT/t_hevc_4k_120s.mp4"
ffprobe -hide_banner -v error -show_streams -show_format \
  "$OUT/t_hevc_4k_120s.mp4" 2>&1 | grep -iE \
  "^codec_name|^profile|^width|^height|^level|^duration|^nb_streams|^codec_type"

echo
echo "=== [4] hvcC 校验（确认 profile/level 合法）==="
python3 - <<'PY'
import struct
d = open('/mnt/e/A4-work/clips/t_hevc_4k_120s.mp4','rb').read()
j = d.find(b'hvcC')
if j < 0:
    print('  ★ 无 hvcC'); raise SystemExit
c = j + 4
print('  configVersion =', d[c])
print('  profile_idc   = %d  (1=Main, 2=Main10)' % (d[c+1] & 0x1f))
print('  level_idc     = %d  (>=30 合法)' % d[c+7])
PY
