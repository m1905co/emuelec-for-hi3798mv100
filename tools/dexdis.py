#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dexdis.py —— 只读 dex 方法体反汇编（够用即可：invoke/iget/iput/
const/return/move/sget/sput 等），用于核实 MediaCenter 的 Java 调用链。

用法:
  python tools/dexdis.py <dex> <正则匹配 类.方法名>
  python tools/dexdis.py <dex> --findsetdisplay     # 快捷搜索 setDisplay
"""
import struct, sys, re

NO_INDEX = 0xFFFFFFFF


class Dex:
    def __init__(self, path):
        self.path = path
        d = self.d = open(path, 'rb').read()
        if d[:4] != b'dex\n':
            raise SystemExit('not a dex: %r' % d[:8])
        (self.string_ids_size, self.string_ids_off) = struct.unpack_from('<II', d, 56)
        (self.type_ids_size, self.type_ids_off) = struct.unpack_from('<II', d, 64)
        (self.proto_ids_size, self.proto_ids_off) = struct.unpack_from('<II', d, 72)
        (self.field_ids_size, self.field_ids_off) = struct.unpack_from('<II', d, 80)
        (self.method_ids_size, self.method_ids_off) = struct.unpack_from('<II', d, 88)
        (self.class_defs_size, self.class_defs_off) = struct.unpack_from('<II', d, 96)
        self._strings(); self._types(); self._protos(); self._fields(); self._methods()

    def _strings(self):
        d = self.d; out = []
        for i in range(self.string_ids_size):
            off, = struct.unpack_from('<I', d, self.string_ids_off + 4 * i)
            # string_data_item = uleb128 utf16_size, 然后是 MUTF-8 字节（无结尾 0）
            p = off
            size = 0; shift = 0
            while True:
                b = d[p]; p += 1
                size |= (b & 0x7f) << shift; shift += 7
                if not (b & 0x80): break
            out.append(d[p:p + size].decode('utf-8', 'replace'))
        self.strings = out

    def _types(self):
        d = self.d
        self.types = [self.strings[struct.unpack_from('<I', d, self.type_ids_off + 4 * i)[0]]
                      for i in range(self.type_ids_size)]

    def _protos(self):
        d = self.d; self.protos = []
        for i in range(self.proto_ids_size):
            o = self.proto_ids_off + 12 * i
            shorty, ret, params = struct.unpack_from('<III', d, o)
            plist = []
            #注意：parameters_off == 0 表示"无参数列表"（不是 NO_INDEX）
            if params != NO_INDEX and params != 0:
                n, = struct.unpack_from('<I', d, params)
                for k in range(n):
                    t, = struct.unpack_from('<H', d, params + 4 + 2 * k)
                    plist.append(self.types[t])
            self.protos.append('(%s)%s' % (''.join(plist), self.types[ret]))

    def _fields(self):
        d = self.d; self.fields = []
        for i in range(self.field_ids_size):
            o = self.field_ids_off + 8 * i
            c, t, n = struct.unpack_from('<HHI', d, o)
            self.fields.append((self.types[c], self.types[t], self.strings[n]))

    def _methods(self):
        d = self.d; self.methods = []
        for i in range(self.method_ids_size):
            o = self.method_ids_off + 8 * i
            c, p, n = struct.unpack_from('<HHI', d, o)
            self.methods.append((self.types[c], self.strings[n], self.protos[p]))

    # ---- class_def / class_data ----
    def classes(self):
        d = self.d
        for i in range(self.class_defs_size):
            o = self.class_defs_off + 32 * i
            # class_def_item 是 8 个 u4；class_data_off 是**第 7 个**（下标 6）
            cidx, acc, sidx, ifo, sco, anno, cdo, sval = struct.unpack_from('<8I', d, o)
            yield self.types[cidx], sidx, cdo, ifo

    def class_data(self, cdo):
        """返回 [(field_idx, access, code_off), ...], [(method_idx, access, code_off)]"""
        if cdo == 0: return [], []
        d = self.d; p = cdo
        def uleb(p):
            r = 0; s = 0
            while True:
                b = d[p]; p += 1
                r |= (b & 0x7f) << s; s += 7
                if not (b & 0x80): return r, p
        nsf, p = uleb(p); nif, p = uleb(p); ndm, p = uleb(p); nvm, p = uleb(p)
        # static 与 instance 字段是**两条独立差分流**，但字段索引各自从 0 开始
        for _ in range(nsf):
            _, p = uleb(p); _, p = uleb(p)
        for _ in range(nif):
            _, p = uleb(p); _, p = uleb(p)
        flds = []
        idx = 0
        for _ in range(ndm):
            d_, p = uleb(p); a, p = uleb(p); c, p = uleb(p)
            idx += d_; flds.append((idx, a, c))
        mths = []
        idx = 0
        for _ in range(nvm):
            d_, p = uleb(p); a, p = uleb(p); c, p = uleb(p)
            idx += d_; mths.append((idx, a, c))
        return flds, mths


LEN = {}


def insn_len(op):
    # 简化：只用已知表，其余按 2 字节单位猜
    return LEN.get(op, 1) * 2


LEN = {
    0x00: 1, 0x01: 1, 0x02: 2, 0x03: 3, 0x04: 1, 0x05: 2, 0x06: 3, 0x07: 1,
    0x08: 2, 0x09: 3, 0x0a: 1, 0x0b: 1, 0x0c: 1, 0x0d: 1, 0x0e: 1, 0x0f: 1,
    0x10: 1, 0x11: 1, 0x12: 1, 0x13: 2, 0x14: 3, 0x15: 2, 0x16: 2, 0x17: 3,
    0x18: 5, 0x19: 2, 0x1a: 2, 0x1b: 1, 0x1c: 2, 0x1d: 1, 0x1e: 1, 0x1f: 2,
    0x20: 2, 0x21: 1, 0x22: 2, 0x23: 2, 0x24: 3, 0x25: 3, 0x26: 3,
    0x27: 1, 0x28: 1, 0x29: 2, 0x2a: 3, 0x2b: 3, 0x2c: 3,
    0x2d: 2, 0x2e: 2, 0x2f: 2, 0x30: 2, 0x31: 2,
    0x32: 2, 0x33: 2, 0x34: 2, 0x35: 2, 0x36: 2, 0x37: 2, 0x38: 2, 0x39: 2,
    0x3a: 2, 0x3b: 2, 0x3c: 2, 0x3d: 2,
    0x44: 2, 0x45: 2, 0x46: 2, 0x47: 2, 0x48: 2, 0x49: 2, 0x4a: 2, 0x4b: 2,
    0x4c: 2, 0x4d: 2, 0x4e: 2, 0x4f: 2, 0x50: 2, 0x51: 2,
    0x52: 2, 0x53: 2, 0x54: 2, 0x55: 2, 0x56: 2, 0x57: 2, 0x58: 2, 0x59: 2,
    0x5a: 2, 0x5b: 2, 0x5c: 2, 0x5d: 2, 0x5e: 2, 0x5f: 2,
    0x60: 2, 0x61: 2, 0x62: 2, 0x63: 2, 0x64: 2, 0x65: 2, 0x66: 2, 0x67: 2,
    0x68: 2, 0x69: 2, 0x6a: 2, 0x6b: 2, 0x6c: 2, 0x6d: 2, 0x6e: 3, 0x6f: 3,
    0x70: 3, 0x71: 3, 0x72: 3, 0x74: 3, 0x75: 3, 0x76: 3, 0x77: 3, 0x78: 3,
}


def disasm(dx, code_off, maxi=400):
    d = dx.d
    if code_off == 0: return []
    nreg, insn_size, outs_size, tries_size, debug_off, insns_size = \
        struct.unpack_from('<HHHHII', d, code_off)
    base = code_off + 16
    p = base
    end = base + insns_size * 2
    out = []
    while p < end and len(out) < maxi:
        off = p - base
        op = d[p]
        w = struct.unpack_from('<H', d, p)[0]
        ln = insn_len(op)
        txt = fmt(dx, p, op, w, ln)
        out.append((off, op, txt))
        p += ln
    return out


def fmt(dx, p, op, w, ln):
    d = dx.d
    try:
        if op in (0x6e, 0x6f, 0x70, 0x71, 0x72):   # invoke-*
            idx = struct.unpack_from('<H', d, p + 2)[0]
            c, n, sg = dx.methods[idx]
            kind = {0x6e: 'virtual', 0x6f: 'super', 0x70: 'direct',
                    0x71: 'static', 0x72: 'interface'}[op]
            return 'invoke-%s {%s.%s %s}' % (kind, c, n, sg)
        if op in (0x74, 0x75, 0x76, 0x77, 0x78):   # invoke-*/range
            idx = struct.unpack_from('<H', d, p + 2)[0]
            c, n, sg = dx.methods[idx]
            kind = {0x74: 'virtual/range', 0x75: 'super/range', 0x76: 'direct/range',
                    0x77: 'static/range', 0x78: 'interface/range'}[op]
            return 'invoke-%s {%s.%s %s}' % (kind, c, n, sg)
        if 0x52 <= op <= 0x6d:   # iget/iput/sget/sput
            idx = struct.unpack_from('<H', d, p + 2)[0]
            c, t, n = dx.fields[idx]
            kinds = {0x52: 'iget', 0x53: 'iget-wide', 0x54: 'iget-object', 0x55: 'iget-boolean',
                     0x56: 'iget-byte', 0x57: 'iget-char', 0x58: 'iget-short',
                     0x59: 'iput', 0x5a: 'iput-wide', 0x5b: 'iput-object', 0x5c: 'iput-boolean',
                     0x5d: 'sget', 0x5e: 'sget-wide', 0x5f: 'sget-object', 0x60: 'sget-boolean',
                     0x61: 'sget-byte', 0x62: 'sget-char', 0x63: 'sget-short',
                     0x64: 'sput', 0x65: 'sput-wide', 0x66: 'sput-object', 0x67: 'sput-boolean',
                     0x68: 'sput-byte', 0x69: 'sput-char', 0x6a: 'sput-short',
                     0x6b: 'sget', 0x6c: 'sget', 0x6d: 'sget'}[op]
            return '%s v%d, %s.%s:%s   (fld#%d)' % (kinds, w & 0xf, c, n, t, idx)
        if op in (0x1a, 0x1b):   # const-string vAA, string@BBBB
            idx = struct.unpack_from('<H', d, p + 2)[0]
            return 'const-string v%d, "%s"' % (w & 0xff, dx.strings[idx])
        if op == 0x1b:
            idx = struct.unpack_from('<H', d, p + 2)[0]
            return 'const-string/jumbo v%d, "%s"' % (w & 0xff, dx.strings[idx])
        if op == 0x12:   # const/4
            return 'const/4 v%d, #%d' % (w & 0xf, (w >> 8) & 0xf if (w >> 11) & 1 else
                                         (((w >> 8) & 0xf) ^ 0xf) * -1 + (w & 0xf if False else 0))
        if op == 0x13:   # const/16
            v = struct.unpack_from('<h', d, p + 2)[0]
            return 'const/16 v%d, #%d' % (w & 0xff, v)
        if op == 0x14:   # const
            v = struct.unpack_from('<i', d, p + 2)[0]
            return 'const v%d, #%d' % (w & 0xff, v)
        if op == 0x15:   # const/high16
            v = struct.unpack_from('<H', d, p + 2)[0]
            return 'const/high16 v%d, #%d' % (w & 0xff, v << 16)
        if op == 0x16:   # const-wide/16
            v = struct.unpack_from('<h', d, p + 2)[0]
            return 'const-wide/16 v%d, #%d' % (w & 0xff, v)
        if op == 0x0e:   # return-void
            return 'return-void'
        if op == 0x0f:   # return vAA
            return 'return v%d' % (w & 0xff)
        if op == 0x11:   # return-object
            return 'return-object v%d' % (w & 0xff)
        if op == 0x10:   # return-wide
            return 'return-wide v%d' % (w & 0xff)
        if op == 0x22:   # new-instance
            idx = struct.unpack_from('<H', d, p + 2)[0]
            return 'new-instance v%d, %s' % (w & 0xff, dx.types[idx])
        if op == 0x1c:   # class
            idx = struct.unpack_from('<H', d, p + 2)[0]
            return 'const-class v%d, %s' % (w & 0xff, dx.types[idx])
        if op == 0x1f:   # check-cast
            idx = struct.unpack_from('<H', d, p + 2)[0]
            return 'check-cast v%d, %s' % (w & 0xff, dx.types[idx])
    except Exception as ex:
        return '<op %#x len %d err %s>' % (op, ln, ex)
    return 'op-%#x' % op


def main():
    path = sys.argv[1]
    pat = sys.argv[2] if len(sys.argv) > 2 else 'setDisplay'
    dx = Dex(path)
    rx = re.compile(pat)
    for cname, sidx, cdo, ifo in dx.classes():
        if not rx.search(cname) and ifo == 0:
            # 类名不匹配时仍需跳过，但 class_data 必须能安全解析
            pass
        try:
            flds, mths = dx.class_data(cdo)
        except Exception:
            continue
        for midx, acc, coff in mths:
            c, n, sg = dx.methods[midx]
            full = '%s.%s' % (c, n)
            if not rx.search(full) and not rx.search(cname):
                continue
            print('=' * 70)
            print('%s   (class %s, access %#x, code@%#x)' % (full, cname, acc, coff))
            ins = disasm(dx, coff)
            if not ins:
                print('   <no code>')
                continue
            for off, op, txt in ins:
                print('   %04x  %-70s ; %#x' % (off, txt, op))


if __name__ == '__main__':
    main()
