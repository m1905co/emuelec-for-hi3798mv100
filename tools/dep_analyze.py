#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精确分析 MediaCenter.apk 中 com.hisilicon.android.mediaplayer/hibdinfo 包的依赖闭包。
输出：① 目标类集合 ② 依赖的外部（android.*/java.*）类型 ③ 依赖的同包类型
"""
import zipfile, struct

APK = 'out/MediaCenter.apk'

class Dex:
    def __init__(self, d):
        self.d = d
        self.sid_s, self.sid_o = self.u32(0x38), self.u32(0x3c)
        self.tid_s, self.tid_o = self.u32(0x40), self.u32(0x44)
        self.pid_s, self.pid_o = self.u32(0x48), self.u32(0x4c)
        self.fid_s, self.fid_o = self.u32(0x50), self.u32(0x54)
        self.mid_s, self.mid_o = self.u32(0x58), self.u32(0x5c)
        self.cds_s, self.cds_o = self.u32(0x60), self.u32(0x64)
        self.cls_s, self.cls_o = self.u32(0x68), self.u32(0x6c)

    def u32(self, o):
        return struct.unpack('<I', self.d[o:o+4])[0]

    def uleb(self, p):
        r = sh = 0
        while True:
            b = self.d[p]; p += 1
            r |= (b & 0x7f) << sh
            if not (b & 0x80): return r, p
            sh += 7

    def s(self, i):
        """string_data_item: uleb128 utf16_size + MUTF-8 bytes"""
        off = self.u32(self.sid_o + i*4)
        n, p = self.uleb(off)
        return self.d[p:p+n].decode('utf-8', 'replace')

    def type(self, i):
        return self.s(self.u32(self.tid_o + i*4))

    def cls(self, i):
        return self.type(self.u32(self.cls_o + i*4))

    def proto(self, i):
        """proto_id_item: shorty_idx(4) return_type_idx(4) parameters_off(4) = 12 bytes"""
        off = self.pid_o + i*12
        return self.type(self.u32(off + 4))

    def meth_class(self, i):
        """method_id_item: class_idx(u16) proto_idx(u16) name_idx(u32)"""
        off = self.mid_o + i*8
        return struct.unpack('<H', self.d[off:off+2])[0]

    def field_type(self, i):
        """field_id_item: class_idx(u16) type_idx(u16) name_idx(u32)"""
        off = self.fid_o + i*8
        return self.type(struct.unpack('<H', self.d[off+2:off+4])[0])


def read_class_data(dx, ci, refs_type, refs_meth, refs_field, refs_proto):
    """解析 class_data_item，收集引用的 type/proto/method/field 索引"""
    off = dx.cds_o + ci*32
    cdo = dx.u32(off + 24)
    if cdo == 0:
        return False
    p = cdo
    sfs, p = dx.uleb(p); ifs, p = dx.uleb(p)
    dms, p = dx.uleb(p); vms, p = dx.uleb(p)
    # static fields
    fidx = 0
    for _ in range(sfs):
        d, p = dx.uleb(p); fidx += d
        _, p = dx.uleb(p)
    # instance fields
    fidx = 0
    for _ in range(ifs):
        d, p = dx.uleb(p); fidx += d
        _, p = dx.uleb(p)
    # direct methods
    midx = 0
    for _ in range(dms):
        d, p = dx.uleb(p); midx += d
        refs_meth.add(midx)
        _, p = dx.uleb(p)
        code, p = dx.uleb(p)
        if code:
            for _ in range(code):
                _, p = dx.uleb(p)      # method_idx_diff
                _, p = dx.uleb(p)      # access_flags
                co, p = dx.uleb(p)     # code_off
    # virtual methods
    midx = 0
    for _ in range(vms):
        d, p = dx.uleb(p); midx += d
        refs_meth.add(midx)
        _, p = dx.uleb(p)
        code, p = dx.uleb(p)
        if code:
            for _ in range(code):
                _, p = dx.uleb(p)
                _, p = dx.uleb(p)
                _, p = dx.uleb(p)
    return True


def main():
    z = zipfile.ZipFile(APK)
    dx = Dex(z.read('classes.dex'))

    # 1) 收集所有已定义类
    defined = {}
    for i in range(dx.cds_s):
        defined[dx.type(dx.u32(dx.cds_o + i*32))] = i

    targets = {c: i for c, i in defined.items()
               if c.startswith('Lcom/hisilicon/android/mediaplayer/')
               or c.startswith('Lcom/hisilicon/android/hibdinfo/')}
    print('=== 目标包类数: %d ===' % len(targets))

    # 2) 依赖闭包（只看类型/方法签名引用的类型，不追代码内部指令）
    ext_types = {}     # 外部类型 -> 被谁引用
    pkg_types = {}     # 同包/hibdinfo 类型 -> 被谁引用
    for cname, ci in sorted(targets.items()):
        rt, rm, rf, rp = set(), set(), set(), set()
        read_class_data(dx, ci, rt, rm, rf, rp)
        for mi in rm:
            off = dx.mid_o + mi*8
            proto_idx = struct.unpack('<H', dx.d[off+2:off+4])[0]
            t = dx.proto(proto_idx)
            if t.startswith('['):
                t = t[1:]
            if t not in ('V',) and t not in defined:
                ext_types.setdefault(t, set()).add(cname.split('/')[-1][:-1])
            elif t.startswith('Lcom/hisilicon/'):
                pkg_types.setdefault(t, set()).add(cname.split('/')[-1][:-1])
        for fi in rf:
            ft = dx.field_type(fi)
            if ft.startswith('['): ft = ft[1:]
            if ft not in defined:
                ext_types.setdefault(ft, set()).add(cname.split('/')[-1][:-1])

    print('\n=== 依赖的【同包/兄弟包】类型（会随jar 一起带走）: %d ===' % len(pkg_types))
    for t in sorted(pkg_types):
        mark = '' if t in defined else '  ★外部!'
        print('  %s%s' % (t, mark))

    print('\n=== 依赖的【外部】类型（必须 framework 提供）: %d ===' % len(ext_types))
    android = sorted(t for t in ext_types if t.startswith('Landroid/'))
    java   = sorted(t for t in ext_types if t.startswith('Ljava/'))
    hisi   = sorted(t for t in ext_types if t.startswith('Lcom/hisilicon/'))
    other  = sorted(t for t in ext_types if not t.startswith(('Landroid/','Ljava/','Lcom/hisilicon/')))
    print('  android.*: %d' % len(android))
    print('  java.*   : %d' % len(java))
    print('  com.hisilicon.*(包外): %d' % len(hisi))
    for t in hisi: print('      ', t, '<--', sorted(ext_types[t])[:3])
    print('  其他: %d' % len(other))
    for t in other: print('      ', t, '<--', sorted(ext_types[t])[:3])

    # 3) 检查是否有 com.huawei 依赖（同厂商，可能也在 apk 内）
    hw = sorted(t for t in ext_types if t.startswith('Lcom/huawei/'))
    print('\n=== com.huawei.* 依赖: %d ===' % len(hw))
    for t in hw:
        inn = '在dex内定义' if t in defined else '★dex内也没有(来自其他apk/framework)'
        print('  ', t, '->', inn)


if __name__ == '__main__':
    main()