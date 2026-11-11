#!/bin/bash
R="/home/mxz/A6-Work/01-sdk-overlay/HiSTBAndroid-4.4.2-SPC064/device/hisilicon/bigfish"
echo "=== 全 SDK overlay 搜 HiMediaPlayer.java / HiVideoView.java ==="
find "$R" -name 'HiMediaPlayer.java' -o -name 'HiVideoView.java' -o -name 'HiMediaPlayerDefine.java' 2>/dev/null
echo
echo "=== 全 SDK overlay 的 .java 文件统计 ==="
echo "java 总数: $(find "$R" -name '*.java' 2>/dev/null | wc -l)"
find "$R" -name '*.java' 2>/dev/null | head -20
echo
echo "=== 全盘（mxz 目录）搜 HiMediaPlayer.java ==="
find /home/mxz -name 'HiMediaPlayer.java' 2>/dev/null | head -5
echo "（以上为空则源码未提供）"
echo
echo "=== aosp 树内搜 ==="
find /home/mxz/aosp -name 'HiMediaPlayer.java' 2>/dev/null | head -5
echo
echo "=== himediaplayer/hal 与 jni 内容 ==="
ls -la "$R/frameworks/himediaplayer/hal/" "$R/frameworks/himediaplayer/jni/"
echo
echo "=== 是否存在预编译的 jar ==="
find "$R" -name '*.jar' 2>/dev/null | head -10