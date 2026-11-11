#!/bin/sh
# fetch-blobs.sh — 从你“自己合法拥有”的设备/SDK 提取专有二进制到本地 blobs/。
# 这些文件是芯片厂/ARM 专有，绝不被本仓库分发（已在 .gitignore 排除）。
#
# 用法:  bash build/fetch-blobs.sh <设备挂载点或SDK根> <输出目录>
#   例:  bash build/fetch-blobs.sh /media/emuelec-tf blobs
#   或:  bash build/fetch-blobs.sh /path/to/hi3798_sdk blobs
set -e

SRC="${1:?用法: $0 <设备挂载点或SDK根> <输出目录>}"
DST="${2:-blobs}"
mkdir -p "$DST"

# ---------- 1) 图形/解码专有库 (libMali / 海思 OMX) ----------
# 路径按你设备实际情况调整；以下为常见位置示例
for p in \
  "$SRC/lib/libMali.so" \
  "$SRC/lib/libOMX_Core.so" \
  "$SRC/lib/libOmxH264Dec.so" \
  "$SRC/lib/libOmxHevcDec.so" \
  "$SRC/opt/emuelec/lib/libMali.so" \
  "$SRC/usr/lib/libMali.so" ; do
  [ -f "$p" ] && cp -v "$p" "$DST/" && echo "提取(图形/解码): $(basename $p)"
done

# ---------- 2) 预编译内核与模块 ----------
[ -f "$SRC/boot/uImage" ]        && cp -v "$SRC/boot/uImage"        "$DST/" && echo "提取: uImage"
[ -f "$SRC/lib/modules" ] && cp -rv "$SRC/lib/modules" "$DST/" && echo "提取: kernel modules"

# ---------- 3) libretro 核心 (10 个, 混合许可证) ----------
# 它们在 TF 卡的 EmuELEC/cores 下；请遵守各自许可证
if [ -d "$SRC/EmuELEC/cores" ]; then
  mkdir -p "$DST/cores"
  cp -v "$SRC/EmuELEC/cores/"*.so "$DST/cores/" 2>/dev/null && echo "提取: libretro cores"
fi

echo
echo "已提取专有 blob 到: $DST"
echo "该目录已在 .gitignore 中排除，不会被提交。"
echo "请确认你对这些文件拥有合法的使用/分发权利后再用于构建。"
