#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dexcall.py —— 只读 dex 调用点分析器。

目的：在不完整反编译的前提下，回答
  "谁调用了 HiMediaPlayer 的哪个方法"。

实现要点：
  1. 解析 header / string_ids / type_ids / proto_ids / method_ids / class_defs
  2. 建立 method_id -> (类名, 方法名, 签名) 的反查表
  3. 扫描每个 class_def 的 class_data -> code_item，按 35u/3rc/45cc/4rcc
     指令格式解码出所有 invoke-* 指令，记录 (调用类, 调用方法) -> 被调方法
  4. 只关心目标类名前缀（可过滤），避免全量反编译

只读：不写回 dex，不修改任何文件。
"""
import struct, sys

NO_INDEX = 0xFFFFFFFF


class Dex:
    def __init__(self, path):
        self.d = open(path, 'rb').read()
        d = self.d
        if d[:4] != b'dex\n':
            raise SystemExit('not a dex: %s' % d[:8])
        self.string_ids_size, self.string_ids_off = struct.unpack_from('<II', d, 56)
        self.type_ids_size, self.type_ids_off = struct.unpack_from('<II', d, 64)
        self.proto_ids_size, self.proto_ids_off = struct.unpack_from('<II', d, 72)
        self.field_ids_size, self.field_ids_off = struct.unpack_from('<II', d, 80)
        self.method_ids_size, self.method_ids_off = struct.unpack_from('<II', d, 88)
        self.class_defs_size, self.class_defs_off = struct.unpack_from('<II', d, 96)
        self._strings()
        self._types()
        self._protos()
        self._methods()

    # ---- 低层读 ----
    def u1(self, o): return self.d[o]
    def u2(self, o): return struct.unpack_from('<H', self.d, o)[0]
    def u4(self, o): return struct.unpack_from('<I', self.d, o)[0]
    def uleb(self, o):
        r = 0; s = 0
        while True:
            b = self.d[o]; o += 1
            r |= (b & 0x7f) << s
            if not (b & 0x80):
                return r, o
            s += 7

    # ---- 字符串表 ----
    def _strings(self):
        self.strings = []
        for i in range(self.string_ids_size):
            off = self.u4(self.string_ids_off + 4 * i)
            n, o = self.uleb(off)
            end = self.d.index(b'\x00', o)
            self.strings.append(self.d[o:end].decode('utf-8', 'replace'))

    # ---- 类型表 ----
    def _types(self):
        self.types = [self.strings[self.u4(self.type_ids_off + 4 * i)]
                      for i in range(self.type_ids_size)]

    def type_idx(self, s):
        try:
            return self.types.index(s)
        except ValueError:
            return NO_INDEX

    # ---- 原型表（只关心参数类型列表）----
    def _protos(self):
        self.protos = []
        for i in range(self.proto_ids_size):
            o = self.proto_ids_off + 12 * i
            shorty, ret, params = struct.unpack_from('<III', self.d, o)
            plist = self._type_list(params)
            self.protos.append((ret, plist))

    def _type_list(self, off):
        if off == 0:
            return []
        n = self.u4(off)
        return [self.u2(off + 4 + 2 * i) for i in range(n)]

    # ---- 方法表 ----
    def _methods(self):
        self.methods = []
        for i in range(self.method_ids_size):
            o = self.method_ids_off + 8 * i
            cls, proto, name = struct.unpack_from('<HHI', self.d, o)
            # name 是 string_ids 索引，必须过一遍字符串表
            self.methods.append((cls, self.strings[name], proto))

    def fields(self):
        """返回 [(类名, 字段名, 类型)]"""
        out = []
        for i in range(self.field_ids_size):
            o = self.field_ids_off + 8 * i
            cls, type_idx, name_idx = struct.unpack_from('<HHI', self.d, o)
            out.append((self.types[cls], self.strings[name_idx],
                        self.types[type_idx]))
        return out

    def class_fields(self, cd_off):
        """返回 class_data 里的字段列表 [(字段名, 类型名)]

        DEX 规范要点：
          - static_fields 与 instance_fields 是**两条独立的差分流**，
            各自从 0 重新累加，不能跨列表累加。
          - field_idx / method_idx 都是差分编码(delta)。
        """
        if cd_off == 0:
            return []
        o = cd_off
        sf, o = self.uleb(o)
        inf, o = self.uleb(o)
        dm, o = self.uleb(o)
        vm, o = self.uleb(o)
        out = []
        for count in (sf, inf):          # 两条独立流
            idx = 0
            for _ in range(count):
                diff, o = self.uleb(o)
                a, o = self.uleb(o)
                idx += diff
                cls, t, n = struct.unpack_from('<HHI', self.d,
                                               self.field_ids_off + 8 * idx)
                out.append((self.strings[n], self.types[t]))
        return out

    def method_sig(self, i):
        """返回 'L类;->名(参数)返回' 形式"""
        cls, name, proto = self.methods[i]
        ret, params = self.protos[proto]
        ps = ''.join(self.types[p] for p in params)
        return '%s->%s(%s)%s' % (self.types[cls], name, ps, self.types[ret])

    # ---- class_def ----
    def class_defs(self):
        """class_def_item 共 32 字节 8 个 u4，顺序固定：
        class_idx, access_flags, superclass_idx, interfaces_off,
        source_file_idx, annotations_off, class_data_off, static_values_off
        """
        for i in range(self.class_defs_size):
            o = self.class_defs_off + 32 * i
            f = struct.unpack_from('<IIIIIIII', self.d, o)
            yield {
                'idx': f[0],
                'name': self.types[f[0]],
                'access': f[1],
                'super': self.types[f[2]] if f[2] != NO_INDEX else None,
                'class_data_off': f[6],
                'static_values_off': f[7],
            }

    def class_methods(self, cd_off):
        """返回 class_data 里的方法列表 [(method_idx, access, code_off)]

        DEX 规范要点：direct_methods 与 virtual_methods 是**两条独立的
        差分流**，各自从 0 累加。跨列表累加会导致方法归属错乱。
        """
        if cd_off == 0:
            return []
        o = cd_off
        sf, o = self.uleb(o)
        inf, o = self.uleb(o)
        dm, o = self.uleb(o)
        vm, o = self.uleb(o)
        for count in (sf, inf):          # 跳过两条字段流
            for _ in range(count):
                _, o = self.uleb(o); _, o = self.uleb(o)
        out = []
        for count in (dm, vm):           # 两条独立的 method 差分流
            idx = 0
            for _ in range(count):
                diff, o = self.uleb(o)
                a, o = self.uleb(o)
                c, o = self.uleb(o)
                idx += diff
                out.append((idx, a, c))
        return out

    # ---- 指令扫描：只找 invoke-* 与 const-string* ----
    def scan_code(self, code_off, want_strings=False):
        """解码一个 code_item，返回 ([invoke 方法idx...], [const-string 字符串idx...])

        code_item 结构（注意：全是定长，不是 uleb128）：
          u2 registers_size
          u2 ins_size
          u2 outs_size
          u2 tries_size
          u4 debug_info_off
          u4 insns_size      (以 2 字节 code unit 计)
          u2[] insns
        """
        if code_off == 0:
            return [], []
        o = code_off
        tries = self.u2(o + 6)
        dbg = self.u4(o + 8)
        insns_size = self.u4(o + 12)
        base = o + 16
        end = base + insns_size * 2
        if insns_size == 0 or insns_size > 0x100000:
            return [], []
        invokes = []
        strings = []
        p = base
        while p < end:
            op = self.d[p]
            # invoke-virtual/super/direct/static/interface (35c, 6B)
            # 与其 /range 形式 (3rc, 8B)
            if op in (0x6e, 0x6f, 0x70, 0x71, 0x72):
                invokes.append(self.u2(p + 2))
                p += 6
                continue
            if op in (0x74, 0x75, 0x76, 0x77, 0x78):
                invokes.append(self.u2(p + 2))
                p += 8
                continue
            if op == 0x1a:      # const-string
                strings.append(self.u2(p + 2)); p += 4; continue
            if op == 0x1b:      # const-string/jumbo
                strings.append(self.u4(p + 2)); p += 6; continue
            p += _insn_len(op, self, p)
            if p <= base:      # 安全阀：长度表异常时避免死循环
                break
        return invokes, strings


# 标准 Dalvik 指令长度表（按 opcode 单位数，-1 表示变长需特判）
LEN = [1]*256
for _o in range(0x00, 0x0e): LEN[_o] = 1
LEN[0x0e] = 2; LEN[0x0f] = 2; LEN[0x10] = 2; LEN[0x11] = 2
LEN[0x12] = 2; LEN[0x13] = 2; LEN[0x14] = 3; LEN[0x15] = 2
LEN[0x16] = 2; LEN[0x17] = 3; LEN[0x18] = 5; LEN[0x19] = 2
LEN[0x1a] = 2; LEN[0x1c] = 2; LEN[0x1d] = 1; LEN[0x1e] = 1
LEN[0x1f] = 2; LEN[0x20] = 2; LEN[0x21] = 1; LEN[0x22] = 2
LEN[0x23] = 2; LEN[0x24] = 3; LEN[0x25] = 3; LEN[0x26] = 3
LEN[0x27] = 1; LEN[0x28] = 1; LEN[0x29] = 2; LEN[0x2a] = 3
LEN[0x2b] = 3; LEN[0x2c] = 3
LEN[0x2d] = 2; LEN[0x2e] = 2; LEN[0x2f] = 2; LEN[0x30] = 2
LEN[0x31] = 2
LEN[0x32] = 3; LEN[0x33] = 3; LEN[0x34] = 3; LEN[0x35] = 3
LEN[0x36] = 3; LEN[0x37] = 3
LEN[0x38] = 3; LEN[0x39] = 3; LEN[0x3a] = 3; LEN[0x3b] = 3
LEN[0x3c] = 3; LEN[0x3d] = 3
LEN[0x44] = 2; LEN[0x45] = 2; LEN[0x46] = 2; LEN[0x47] = 2
LEN[0x48] = 2; LEN[0x49] = 2; LEN[0x4a] = 2; LEN[0x4b] = 2
LEN[0x4c] = 2; LEN[0x4d] = 2; LEN[0x4e] = 2; LEN[0x4f] = 2
LEN[0x50] = 2; LEN[0x51] = 2; LEN[0x52] = 2; LEN[0x53] = 2
LEN[0x54] = 2; LEN[0x55] = 2; LEN[0x56] = 2; LEN[0x57] = 2
LEN[0x58] = 2; LEN[0x59] = 2; LEN[0x5a] = 2; LEN[0x5b] = 2
LEN[0x5c] = 2; LEN[0x5d] = 2; LEN[0x5e] = 2; LEN[0x5f] = 2
LEN[0x60] = 2; LEN[0x61] = 2; LEN[0x62] = 2; LEN[0x63] = 2
LEN[0x64] = 2; LEN[0x65] = 2; LEN[0x66] = 2; LEN[0x67] = 2
LEN[0x68] = 2; LEN[0x69] = 2; LEN[0x6a] = 2; LEN[0x6b] = 2
LEN[0x6c] = 2; LEN[0x6d] = 2
LEN[0x7b] = 1; LEN[0x7c] = 1; LEN[0x7d] = 1; LEN[0x7e] = 1; LEN[0x7f] = 1
LEN[0x80] = 1; LEN[0x81] = 1
LEN[0x82] = 1; LEN[0x83] = 1; LEN[0x84] = 1; LEN[0x85] = 1
LEN[0x86] = 1; LEN[0x87] = 1; LEN[0x88] = 1; LEN[0x89] = 1
LEN[0x8a] = 1; LEN[0x8b] = 1; LEN[0x8c] = 1; LEN[0x8d] = 1
LEN[0x8e] = 1; LEN[0x8f] = 1
LEN[0x90] = 2; LEN[0x91] = 2; LEN[0x92] = 2; LEN[0x93] = 2
LEN[0x94] = 2; LEN[0x95] = 2; LEN[0x96] = 2; LEN[0x97] = 2
LEN[0x98] = 3; LEN[0x99] = 3; LEN[0x9a] = 3; LEN[0x9b] = 3
LEN[0x9c] = 3; LEN[0x9d] = 3; LEN[0x9e] = 3; LEN[0x9f] = 3
LEN[0xa0] = 3; LEN[0xa1] = 3; LEN[0xa2] = 3; LEN[0xa3] = 3
LEN[0xa4] = 3; LEN[0xa5] = 3; LEN[0xa6] = 3; LEN[0xa7] = 3
LEN[0xa8] = 3; LEN[0xa9] = 3; LEN[0xaa] = 3; LEN[0xab] = 3
LEN[0xac] = 3; LEN[0xad] = 3; LEN[0xae] = 3; LEN[0xaf] = 3
LEN[0xb0] = 1; LEN[0xb1] = 1; LEN[0xb2] = 1; LEN[0xb3] = 1
LEN[0xb4] = 1; LEN[0xb5] = 1; LEN[0xb6] = 1; LEN[0xb7] = 1
LEN[0xb8] = 1; LEN[0xb9] = 1; LEN[0xba] = 1; LEN[0xbb] = 1
LEN[0xbc] = 1; LEN[0xbd] = 1; LEN[0xbe] = 1; LEN[0xbf] = 1
LEN[0xc0] = 1; LEN[0xc1] = 1; LEN[0xc2] = 1; LEN[0xc3] = 1
LEN[0xc4] = 1; LEN[0xc5] = 1; LEN[0xc6] = 1; LEN[0xc7] = 1
LEN[0xc8] = 1; LEN[0xc9] = 1; LEN[0xca] = 1; LEN[0xcb] = 1
LEN[0xcc] = 1; LEN[0xcd] = 1; LEN[0xce] = 1; LEN[0xcf] = 1
LEN[0xd0] = 2; LEN[0xd1] = 2; LEN[0xd2] = 2; LEN[0xd3] = 2
LEN[0xd4] = 2; LEN[0xd5] = 2; LEN[0xd6] = 2; LEN[0xd7] = 2
LEN[0xd8] = 2; LEN[0xd9] = 2; LEN[0xda] = 2; LEN[0xdb] = 2
LEN[0xdc] = 2; LEN[0xdd] = 2; LEN[0xde] = 2; LEN[0xdf] = 2
LEN[0xe0] = 2; LEN[0xe1] = 2; LEN[0xe2] = 2


def _insn_len(op, dex, p):
    """返回指令长度（字节）。已处理 invoke/const-string 的调用方不走到这里。"""
    if op == 0x18:      # const-wide
        return 10 if (dex.d[p + 1] & 0x10) else 6
    if op in (0x14, 0x17, 0x24, 0x25, 0x26):
        return 6 if (dex.d[p + 1] & 0x10) else 4
    if op in (0x29, 0x2a, 0x2b, 0x2c):
        return 4
    if op in (0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3a, 0x3b,
              0x3c, 0x3d):
        return 4
    if 0x90 <= op <= 0xaf:
        return 4
    if op in (0xd8, 0xd9, 0xda, 0xdb, 0xdc, 0xdd, 0xde, 0xdf,
              0xe0, 0xe1, 0xe2):
        return 4
    if op in (0xfa, 0xfb):   # invoke-polymorphic
        return 8
    if op in (0xfc, 0xfd):   # invoke-custom
        return 6
    if op == 0xfe:           # const-method-handle
        return 4
    if op == 0xff:           # const-method-type
        return 4
    n = LEN[op]
    return n * 2


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else 'out/mc_classes.dex'
    dx = Dex(path)
    print('strings=%d types=%d methods=%d classes=%d'
          % (dx.string_ids_size, dx.type_ids_size, dx.method_ids_size,
             dx.class_defs_size))
