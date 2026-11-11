#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 class_data_item 解析是否正确：与 dexdump 的输出对照。"""
import struct, zipfile

z = zipfile.ZipFile('out/MediaCenter.apk')
d = z.read('classes.dex')
u32 = lambda o: struct.unpack('<I', d[o:o+4])[0]


def uleb_at(p):
    r = sh = 0
    while True:
        b = d[p]; p += 1
        r |= (b & 0x7f) << sh
        if not (b & 0x80):
            return r, p
        sh += 7


sid_s, sid_o = u32(0x38), u32(0x3c)
tid_s, tid_o = u32(0x40), u32(0x44)
cds_s, cds_o = u32(0x60), u32(0x64)


def S(i):
    off = u32(sid_o + i*4)
    n, p = uleb_at(off)
    return d[p:p+n].decode('utf-8', 'replace')


def T(i):
    return S(u32(tid_o + i*4))


def parse_class_data(cdo):
    """返回 (sfs, ifs, dms, vms, 各数组)"""
    p = cdo
    sfs, p = uleb_at(p)
    ifs, p = uleb_at(p)
    dms, p = uleb_at(p)
    vms, p = uleb_at(p)
    sfields, ifields, dmethods, vmethods = [], [], [], []
    idx = 0
    for _ in range(sfs):
        diff, p = uleb_at(p); idx += diff
        acc, p = uleb_at(p)
        sfields.append((idx, acc))
    idx = 0
    for _ in range(ifs):
        diff, p = uleb_at(p); idx += diff
        acc, p = uleb_at(p)
        ifields.append((idx, acc))
    idx = 0
    for _ in range(dms):
        diff, p = uleb_at(p); idx += diff
        acc, p = uleb_at(p)
        code, p = uleb_at(p)
        dmethods.append((idx, acc, code))
    idx = 0
    for _ in range(vms):
        diff, p = uleb_at(p); idx += diff
        acc, p = uleb_at(p)
        code, p = uleb_at(p)
        vmethods.append((idx, acc, code))
    return (sfs, ifs, dms, vms, sfields, ifields, dmethods, vmethods), p


# 找 HiMediaPlayer
for i in range(cds_s):
    off = cds_o + i*32
    ci = u32(off)
    if T(ci) == 'Lcom/hisilicon/android/mediaplayer/HiMediaPlayer;':
        cdo = u32(off + 24)
        svdo = u32(off + 28)
        print('HiMediaPlayer class_def:')
        print('  class_data_off  =', cdo)
        print('  static_values_off=', svdo)
        res, end = parse_class_data(cdo)
        sfs, ifs, dms, vms, sf, iff, dm, vm = res
        print('  parsed: sfs=%d ifs=%d dms=%d vms=%d  (end offset=%d)' % (sfs, ifs, dms, vms, end))
        print('  static fields found: %d (前3)' % len(sf))
        for x in sf[:3]: print('     ', x)
        break

print()
print('=== 对照：dexdump 报告的字段数 ===')
print('  HiMediaPlayer 的 static fields 数量（dexdump 至少 9+）')
print()
print('=== 统计全部目标类的解析 ===')
PREFIX = ('Lcom/hisilicon/android/mediaplayer/', 'Lcom/hisilicon/android/hibdinfo/')
ok = fail = 0
tot_sf = tot_im = 0
for i in range(cds_s):
    off = cds_o + i*32
    cn = T(u32(off))
    if not cn.startswith(PREFIX):
        continue
    cdo = u32(off + 24)
    if cdo == 0:
        continue
    try:
        res, end = parse_class_data(cdo)
        if end > len(d):
            fail += 1
        else:
            ok += 1
            tot_sf += len(res[4])
            tot_im += len(res[5])
    except Exception:
        fail += 1
print('  解析成功 %d, 失败 %d' % (ok, fail))
print('  目标包 static fields 总数=%d, instance fields=%d' % (tot_sf, tot_im))