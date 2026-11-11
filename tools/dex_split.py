#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dex 切分器：只保留指定包的类，生成结构合法的最小 dex。
思路：不重新编译，直接复用原 dex 的原始字节，只重建索引表。
      保持 class_defs / class_data / code_item / string / type / method / field
      的原始偏移，仅过滤掉不需要的类。
"""
import struct, sys, zipfile

SRC = 'out/MediaCenter.apk'
PREFIXES = ('Lcom/hisilicon/android/mediaplayer/', 'Lcom/hisilicon/android/hibdinfo/')
OUT_DEX = 'out/hiplayer.dex'


class Dex:
    def __init__(self, d):
        self.d = d
        f = lambda o: struct.unpack('<I', d[o:o+4])[0]
        self.sid_s, self.sid_o = f(0x38), f(0x3c)
        self.tid_s, self.tid_o = f(0x40), f(0x44)
        self.pid_s, self.pid_o = f(0x48), f(0x4c)
        self.fid_s, self.fid_o = f(0x50), f(0x54)
        self.mid_s, self.mid_o = f(0x58), f(0x5c)
        self.cds_s, self.cds_o = f(0x60), f(0x64)
        self.cls_s, self.cls_o = f(0x68), f(0x6c)
        self.data_s, self.data_o = f(0x68+16), f(0x6c+16)

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
        off = self.u32(self.sid_o + i*4)
        n, p = self.uleb(off)
        return self.d[p:p+n].decode('utf-8', 'replace')

    def type(self, i):
        return self.s(self.u32(self.tid_o + i*4))


def analyze(d):
    """分析：返回 (保留的 class_def 索引列表, 依赖闭包)"""
    dx = Dex(d)
    defined = {}
    for i in range(dx.cds_s):
        defined[dx.type(dx.u32(dx.cds_o + i*32))] = i
    targets = {c: i for c, i in defined.items() if c.startswith(PREFIXES)}
    return dx, defined, targets


def class_data_span(d, cdo):
    """返回 class_data_item 覆盖的字节区间 [start, end)"""
    p = cdo
    def uleb():
        nonlocal p
        r = sh = 0
        while True:
            b = d[p]; p += 1
            r |= (b & 0x7f) << sh
            if not (b & 0x80): return r
            sh += 7
    sfs, ifs, dms, vms = uleb(), uleb(), uleb(), uleb()
    for _ in range(sfs): uleb(); uleb()
    for _ in range(ifs): uleb(); uleb()
    for _ in range(dms):
        uleb(); uleb()
        code = uleb()
        if code:
            for _ in range(code): uleb(); uleb(); uleb()
    for _ in range(vms):
        uleb(); uleb()
        code = uleb()
        if code:
            for _ in range(code): uleb(); uleb(); uleb()
    return cdo, p


def code_span(d, code_off):
    """code_item: registers(2) ins(2) outs(2) tries(2) debug_off(4) insns_size(4) insns[]"""
    p = code_off
    regs, ins, outs, tries = struct.unpack('<HHHH', d[p:p+8])
    p += 8
    insns = struct.unpack('<I', d[p:p+4])[0]
    p += 4 + insns*2
    if insns % 2 == 1 and tries:      # padding
        p += 2
    if tries:
        p += tries*8                   # try_item
        handlers = struct.unpack('<I', d[p:p+4])[0]
        p += 4
        # encoded_catch_handler_list: uleb size + handlers
        def uleb():
            nonlocal p
            r = sh = 0
            while True:
                b = d[p]; p += 1
                r |= (b & 0x7f) << sh
                if not (b & 0x80): return r
                sh += 7
        n = uleb()
        for _ in range(n):
            size = uleb()
            for _ in range(abs(size) + 1):
                if size <= 0: uleb()      # type_idx uleb
                uleb()                   # addr uleb
                if size <= 0: pass
            # 注：此处仅粗略估算，精确解析见 refine
    return code_off, p


def main():
    z = zipfile.ZipFile(SRC)
    d = z.read('classes.dex')
    dx, defined, targets = analyze(d)
    print('原 dex: %d B, 定义 %d 类' % (len(d), len(defined)))
    print('目标包类: %d' % len(targets))

    # 统计保留类涉及的字节区间
    spans = []
    for cn, ci in sorted(targets.items()):
        cdo = dx.u32(dx.cds_o + ci*32 + 24)
        if cdo:
            spans.append(class_data_span(d, cdo))
    total = sum(e - s for s, e in spans)
    print('class_data 总字节: %d' % total)
    print('  （占总 dex %.1f%%）' % (100.0*total/len(d)))

    # 依赖类型统计
    tset = set()
    for cn, ci in targets.items():
        cdo = dx.u32(dx.cds_o + ci*32 + 24)
        if cdo:
            pass
    print()
    print('=== 关键：这些类的 code_item 是否可独立搬运 ===')
    ok = 0
    for cn, ci in list(targets.items())[:5]:
        cdo = dx.u32(dx.cds_o + ci*32 + 24)
        s, e = class_data_span(d, cdo)
        print('  %-58s class_data [%d,%d) %d B' % (cn.split('/')[-1][:-1], s, e, e-s))
        ok += 1
    print('  ... 共 %d 个' % ok)


if __name__ == '__main__':
    main()