#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""依赖闭包分析 v2 —— 用「type_ids 全表 + class_data 引用」双路交叉，
避免逐字段解析 class_data 时的边界 bug。
核心思路：目标包 53 个类 → 它们的 class_data 里引用的 type → 判断是否在 jar 内。
"""
import zipfile, struct, sys

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
        self.cls_o = self.u32(0x6c)

    def u32(self, o):
        return struct.unpack('<I', self.d[o:o+4])[0]

    def u16(self, o):
        return struct.unpack('<H', self.d[o:o+2])[0]

    def uleb(self, p):
        r = sh = 0
        while True:
            b = self.d[p]; p += 1
            r |= (b & 0x7f) << sh
            if not (b & 0x80): return r, p
            sh += 7

    def s(self, i):
        off = self.u32(self.sid_o + i*4)
        n, p = self.uleb(off)
        return self.d[p:p+n].decode('utf-8', 'replace')

    def type(self, i):
        return self.s(self.u32(self.tid_o + i*4))


def class_data_span(dx, ci):
    """返回 class_data_item 的字节区间 (start, end) —— 用 code_off 排序法"""
    off = dx.cds_o + ci*32
    cdo = dx.u32(off + 24)
    if cdo == 0:
        return None
    return cdo


def main():
    z = zipfile.ZipFile(APK)
    dx = Dex(z.read('classes.dex'))

    defined = {}
    for i in range(dx.cds_s):
        defined[dx.type(dx.u32(dx.cds_o + i*32))] = i
    print('dex 内定义的类: %d' % len(defined))

    targets = {c: i for c, i in defined.items()
               if c.startswith('Lcom/hisilicon/android/mediaplayer/')
               or c.startswith('Lcom/hisilicon/android/hibdinfo/')}
    print('目标包类数: %d' % len(targets))

    # ---- 路1：method_ids / field_ids 的 owner 是目标类 → 其 proto/field 的类型 ----
    ext = {}
    pkg = {}
    for mi in range(dx.mid_s):
        off = dx.mid_o + mi*8
        cidx = dx.u16(off)
        pidx = dx.u16(off+2)
        cname = dx.type(dx.u32(dx.cls_o_eff + cidx*4)) if False else None
        # class_idx 指向 class_defs 的 type
        ctype = dx.type(dx.u32(dx.tid_o + 0))  # placeholder
        # 直接用 class_defs[type_idx] 的 type
        ct = dx.type(cidx) if cidx < dx.tid_s else None
        if ct not in targets:
            continue
        po = dx.pid_o + pidx*12
        rt = dx.type(dx.u32(po + 4))
        for t in (rt,):
            if t.startswith('['): t = t[1:]
            if t in ('V',) or t in defined: continue
            (pkg if t.startswith('Lcom/hisilicon/') else ext).setdefault(t, set()).add(ct.split('/')[-1][:-1])
        # 参数类型
        par = dx.u32(po + 8)
        if par:
            n, p = dx.uleb(par)
            for _ in range(n):
                ti, p = dx.uleb(p)
                t = dx.type(ti)
                if t.startswith('['): t = t[1:]
                if t in ('V',) or t in defined: continue
                (pkg if t.startswith('Lcom/hisilicon/') else ext).setdefault(t, set()).add(ct.split('/')[-1][:-1])

    for fi in range(dx.fid_s):
        off = dx.fid_o + fi*8
        cidx = dx.u16(off)
        tidx = dx.u16(off+2)
        if cidx >= dx.tid_s: continue
        ct = dx.type(cidx)
        if ct not in targets: continue
        t = dx.type(tidx)
        if t.startswith('['): t = t[1:]
        if t in defined: continue
        (pkg if t.startswith('Lcom/hisilicon/') else ext).setdefault(t, set()).add(ct.split('/')[-1][:-1])

    # ---- 路2：class_data 里的 superclass / interfaces ----
    for ct, ci in targets.items():
        off = dx.cds_o + ci*32
        scidx = dx.u32(off + 8)
        if scidx != 0xFFFFFFFF:
            sc = dx.type(dx.u32(dx.tid_o + scidx*4)) if False else dx.type(scidx)
            if sc not in defined:
                (pkg if sc.startswith('Lcom/hisilicon/') else ext).setdefault(sc, set()).add(ct.split('/')[-1][:-1])
        # access_flags & interfaces_off(12)
        ifc_off = dx.u32(off + 12)
        if ifc_off:
            n, p = dx.uleb(ifc_off)
            for _ in range(n):
                ti, p = dx.uleb(p)
                it = dx.type(ti)
                if it not in defined:
                    (pkg if it.startswith('Lcom/hisilicon/') else ext).setdefault(it, set()).add(ct.split('/')[-1][:-1])

    print('\n=== A. 依赖的【com.hisilicon.* 包外】类型（★说明 jar 不完整）===')
    hp = {t: v for t, v in ext.items() if t.startswith('Lcom/hisilicon/')}
    if not hp:
        print('  （无）')
    for t in sorted(hp):
        print('  %-70s <- %s' % (t, sorted(hp[t])[:2]))

    print('\n=== B. 依赖的【同包】类型（会随 jar 一起带走）===')
    for t in sorted(pkg):
        mark = '' if t in defined else '  ★不在 dex 内'
        print('  %-70s%s' % (t, mark))

    print('\n=== C. 依赖的外部类型统计（framework 必须提供）===')
    cats = {'android/': [], 'java/': [], 'com/huawei/': [], '其他': []}
    for t in ext:
        for k in cats:
            if t[1:].startswith(k):
                cats[k].append(t); break
    for k, v in cats.items():
        print('  %-14s %d' % (k, len(v)))
    for t in sorted(cats['android/']) + sorted(cats['java/']):
        print('     ', t)

    print('\n=== D. com.huawei.* 依赖（可能来自 MediaCenter 其他类）===')
    for t in sorted(cats['com/huawei/']):
        inn = '在dex内' if t in defined else '★dex内没有'
        print('  %-60s %s' % (t, inn))


if __name__ == '__main__':
    main()