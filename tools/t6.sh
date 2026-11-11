#!/bin/bash
A=/home/mxz/aosp
echo "=== 1. AOSP 树里的 smali/baksmali 源码 ==="
find $A -maxdepth 4 -type d \( -name smali -o -name baksmali -o -name 'dexdump' \) 2>/dev/null | head -10
echo
echo "=== 2. AOSP 的 dx 能做什么（-dex 转存）==="
DXJ=$A/out/host/linux-x86/framework/dx.jar
ls -la $DXJ 2>/dev/null
echo
echo "=== 3. 检查 dalvik 目录下是否有 smali/baksmali 的 Java 源码 ==="
ls $A/dalvik/ 2>/dev/null
echo
echo "=== 4. libcoreutils / jcommander? ==="
find $A -maxdepth 5 -type d -name jcommander 2>/dev/null | head -5
find $A -path '*external/jcommander*' -maxdepth 5 -type d 2>/dev/null | head -5
echo
echo "=== 5. 有没有已构建好的 smali/baksmali jar ==="
find $A -name '*smali*.jar' 2>/dev/null | head -8