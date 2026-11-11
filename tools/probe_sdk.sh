#!/bin/bash
B="/home/mxz/A6-Work/01-sdk-overlay/HiSTBAndroid-4.4.2-SPC064/device/hisilicon/bigfish/frameworks/himediaplayer"
echo "=== java 目录树 ==="
find "$B/java" -type f 2>&1 | head -40
echo
echo "=== java 目录结构 ==="
find "$B/java" -type d 2>&1 | head -20
echo
echo "=== 统计 ==="
echo "java 文件数: $(find "$B/java" -name '*.java' 2>/dev/null | wc -l)"
echo "hal 文件数: $(find "$B/hal" -type f 2>/dev/null | wc -l)"
echo "jni 文件数: $(find "$B/jni" -type f 2>/dev/null | wc -l)"
echo
echo "=== 是否有 Android.mk / Android.bp ==="
find "$B/.." -maxdepth 2 -name 'Android.mk' -o -maxdepth 2 -name 'Android.bp' 2>/dev/null | head -10