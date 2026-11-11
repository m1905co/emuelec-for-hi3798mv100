#!/bin/bash
set -e
W=/home/mxz/hijack
cd $W
cp /mnt/e/A4-work/out/RealTest.java .
rm -rf rc && mkdir rc
javac -source 1.6 -target 1.6 -d rc RealTest.java 2>&1 | grep -v 'bootstrap class path' | head -5 || true
ls rc/
AOSP=/home/mxz/aosp
rm -f RealTest.dex
$AOSP/out/host/linux-x86/bin/dx --dex --output=RealTest.dex rc 2>&1 | head -3
ls -la RealTest.dex
cp RealTest.dex /mnt/e/A4-work/out/
echo COPIED