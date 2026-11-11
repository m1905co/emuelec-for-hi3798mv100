#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dex_splitter.py —— 从 classes.dex 中切出指定包的类，生成最小、结构合法的 dex。

设计原则：**只搬运，不重编译**。
  1. 遍历依赖闭包，确定要保留的类集合
  2. 收集这些类引用的所有 string / type / proto / field / method
  3. 复制所有相关数据区（string_data / type_list / class_data / code_item /
     static_values / debug_info / annotation 等）的原始字节
  4. 重建索引表，并把所有索引重映射到新表
  5. 修复所有需要改写的偏移（class_data 内的 code_off、class_def 内的各项 off、
     proto 的 parameters_off、class_data 内的 field/method 索引、指令里的索引…）

指令里的索引（const-string / const-class / sget …）也必须重映射，
这是本工具最复杂的部分。
"""
import struct, sys, zipfile, hashlib

# ---------- 常量 ----------
NO_INDEX = 0xFFFFFFFF
ACC_STATIC_VALUES_PRESENT = 0x00000020

TYPE_HEADER_ITEM = 0x0000
TYPE_STRING_ID_ITEM = 0x0001
TYPE_TYPE_ID_ITEM = 0x0002
TYPE_PROTO_ID_ITEM = 0x0003
TYPE_FIELD_ID_ITEM = 0x0004
TYPE_METHOD_ID_ITEM = 0x0005
TYPE_CLASS_DEF_ITEM = 0x0006
TYPE_CALL_SITE_ID_ITEM = 0x0007
TYPE_METHOD_HANDLE_ITEM = 0x0008


class Reader:
    def __init__(self, d):
        self.d = d

    def u1(self, o):  return self.d[o]
    def u2(self, o):  return struct.unpack_from('<H', self.d, o)[0]
    def u4(self, o):  return struct.unpack_from('<I', self.d, o)[0]
    def i4(self, o):  return struct.unpack_from('<i', self.d, o)[0]

    def uleb(self, o):
        r = sh = 0
        d = self.d
        while True:
            b = d[o]; o += 1
            r |= (b & 0x7f) << sh
            if not (b & 0x80):
                return r, o
            sh += 7

    def uleb_at(self, o):
        return self.uleb(o)

    def sleb(self, o):
        r = sh = 0
        d = self.d
        while True:
            b = d[o]; o += 1
            r |= (b & 0x7f) << sh
            sh += 7
            if not (b & 0x80):
                if (b & 0x40) and sh < 64:
                    r |= -(1 << sh)
                return r, o


class Dex:
    def __init__(self, data):
        self.d = data
        r = Reader(data)
        self.r = r
        self.sid_s, self.sid_o = r.u4(0x38), r.u4(0x3c)
        self.tid_s, self.tid_o = r.u4(0x40), r.u4(0x44)
        self.pid_s, self.pid_o = r.u4(0x48), r.u4(0x4c)
        self.fid_s, self.fid_o = r.u4(0x50), r.u4(0x54)
        self.mid_s, self.mid_o = r.u4(0x58), r.u4(0x5c)
        self.cds_s, self.cds_o = r.u4(0x60), r.u4(0x64)
        self.data_s, self.data_o = r.u4(0x68), r.u4(0x6c)
        self.map_off = r.u4(0x34)

    # ---- 索引访问 ----
    def string(self, i):
        off = self.r.u4(self.sid_o + i * 4)
        n, p = self.r.uleb(off)
        return self.d[p:p + n].decode('utf-8', 'replace')

    def string_off(self, i):
        return self.r.u4(self.sid_o + i * 4)

    def type_str(self, i):
        return self.string(self.r.u4(self.tid_o + i * 4))

    def type_idx_of_str(self, i):
        return self.r.u4(self.tid_o + i * 4)

    def proto_ret(self, i):
        return self.r.u4(self.pid_o + i * 12 + 4)

    def proto_params_off(self, i):
        return self.r.u4(self.pid_o + i * 12 + 8)

    def field_cls(self, i):
        return self.r.u2(self.fid_o + i * 8)

    def field_type(self, i):
        return self.r.u2(self.fid_o + i * 8 + 2)

    def field_name(self, i):
        return self.r.u4(self.fid_o + i * 8 + 4)

    def meth_cls(self, i):
        return self.r.u2(self.mid_o + i * 8)

    def meth_proto(self, i):
        return self.r.u2(self.mid_o + i * 8 + 2)

    def meth_name(self, i):
        return self.r.u4(self.mid_o + i * 8 + 4)

    def cdef(self, i):
        o = self.cds_o + i * 32
        return dict(
            class_idx=self.r.u4(o), access=self.r.u4(o + 4),
            superclass=self.r.u4(o + 8), interfaces=self.r.u4(o + 12),
            source_file=self.r.u4(o + 16), annotations=self.r.u4(o + 20),
            class_data=self.r.u4(o + 24), static_values=self.r.u4(o + 28))

    def all_class_names(self):
        return [self.type_str(self.r.u4(self.cds_o + i * 32)) for i in range(self.cds_s)]


# ---------- class_data 解析 ----------
def parse_class_data(r, off):
    """返回 dict，含字段/方法列表与结束偏移"""
    p = off
    sfs, p = r.uleb(p)
    ifs, p = r.uleb(p)
    dms, p = r.uleb(p)
    vms, p = r.uleb(p)
    sf, p = _read_encoded(r, p, sfs, with_code=False)
    iff, p = _read_encoded(r, p, ifs, with_code=False)
    dm, p = _read_encoded(r, p, dms, with_code=True)
    vm, p = _read_encoded(r, p, vms, with_code=True)
    return dict(sf=sf, iff=iff, dm=dm, vm=vm, end=p)


def _read_encoded(r, p, n, with_code=False):
    """encoded_field: field_idx_diff, access_flags
       encoded_method: method_idx_diff, access_flags, code_off"""
    out = []
    idx = 0
    for _ in range(n):
        diff, p = r.uleb(p)
        idx += diff
        acc, p = r.uleb(p)
        if with_code:
            code, p = r.uleb(p)
            out.append([idx, acc, code])
        else:
            out.append([idx, acc, 0])
    return out, p


def parse_code_item(r, off):
    """返回 code_item 结束偏移（需处理 try/catch）"""
    p = off
    p += 8# registers(u2) ins(u2) outs(u2) tries(u2)
    insns_size = r.u4(p); p += 4
    p += insns_size * 2
    if insns_size % 2 != 0:
        p += 2                        # padding u2
    tries = r.u2(off + 6)
    if tries:
        p += tries * 8                 # try_item[tries]
        handlers_size = r.u4(p); p += 4
        for _ in range(handlers_size):
            size, p = r.sleb(p)        # signed size
            n = abs(size)
            for _ in range(n):
                _, p = r.uleb(p)       # type_idx uleb128p1
                _, p = r.uleb(p)       # addr    uleb128p1
            _, p = r.uleb(p)           # catch_all_addr uleb128p1
    return p


def parse_annotations_item(r, off):
    """annotation_item → 结束偏移"""
    p = off
    visibility, p = r.uleb(p)
    encoded_annotation, p = r.uleb(p)
    for _ in range(encoded_annotation):
        _, p = r.uleb(p)      # type_idx
        _, p = r.uleb(p)      # name_idx
        value, p = parse_encoded_value(r, p)
    return p


def parse_encoded_value(r, p):
    """解析 encoded_value，返回结束偏移"""
    arg, p = r.uleb(p)
    vt = arg & 0x1f
    size = (arg >> 5) & 0x07
    vlen = size + 1
    if vt == 0x1c:      # array
        n, p = r.uleb(p)
        for _ in range(n):
            _, p = parse_encoded_value(r, p)
    elif vt == 0x1d:    # annotation
        _, p = r.uleb(p)
        n, p = r.uleb(p)
        for _ in range(n):
            _, p = r.uleb(p)
            _, p = parse_encoded_value(r, p)
    else:
        p += vlen
    return None, p


def parse_annotations_directory(r, off):
    """annotations_directory_item → 结束偏移"""
    p = off
    ca, p = r.uleb(p)
    fca, p = r.uleb(p)
    mca, p = r.uleb(p)
    pca, p = r.uleb(p)
    def skip_list(p, n):
        p += n * 4
        for _ in range(n):
            _, p = r.uleb(p)
        return p
    p = skip_list(p, ca)
    p = skip_list(p, fca)
    p = skip_list(p, mca)
    p = skip_list(p, pca)
    return p


def parse_static_values(r, off, n):
    """static_values_item：n 个 encoded_value"""
    p = off
    for _ in range(n):
        _, p = parse_encoded_value(r, p)
    return p


def parse_type_list(r, off):
    cnt = r.u4(off)
    return off + 4 + cnt * 2


def parse_debug_info(r, off):
    p = off
    _, p = r.uleb(p)          # line_start
    n, p = r.uleb(p)          # parameters_size
    p += n                    # parameter_names (uleb128p1)
    _, p = r.uleb(p)          # state machine: bytecode count
    last = -1
    while True:
        b = r.d[p]; p += 1
        op = b & 0x7f
        last = -1
        if op == 0x00: break
        if op == 0x01:      # ADVANCE_PC
            n_, p = r.uleb(p)
        elif op == 0x02:    # ADVANCE_LINE
            n_, p = r.sleb(p)
        elif op == 0x03:    # START_LOCAL
            n_, p = r.uleb(p); _, p = r.uleb(p); _, p = r.uleb(p)
        elif op == 0x04:    # START_LOCAL_EXTENDED
            n_, p = r.uleb(p); _, p = r.uleb(p); _, p = r.uleb(p); _, p = r.uleb(p)
        elif op == 0x05:    # END_LOCAL
            _, p = r.uleb(p)
        elif op == 0x06:    # RESTART_LOCAL
            _, p = r.uleb(p)
        elif op == 0x09:    # SPECIAL_FRAME
            n_, p = r.uleb(p)
            for _ in range(n_):
                _, p = r.uleb(p)
        elif op == 0x0a:    # END_SEQUENCE
            n_, p = r.uleb(p)
        elif op == 0x0b:    # RESTART_FRAME
            n_, p = r.uleb(p)
        else:
            raise ValueError('debug_info op %#x' % op)
    return p


if __name__ == '__main__':
    z = zipfile.ZipFile('out/MediaCenter.apk')
    dx = Dex(z.read('classes.dex'))
    r = dx.r
    PRE = ('Lcom/hisilicon/android/mediaplayer/', 'Lcom/hisilicon/android/hibdinfo/')
    n_ok = n_err = 0
    for i in range(dx.cds_s):
        cn = dx.type_str(dx.r.u4(dx.cds_o + i * 32))
        if not cn.startswith(PRE):
            continue
        cd = dx.cdef(i)
        try:
            info = parse_class_data(r, cd['class_data'])
            for lst in (info['dm'], info['vm']):
                for m in lst:
                    if m[2]:
                        parse_code_item(r, m[2])
            if cd['annotations']:
                parse_annotations_directory(r, cd['annotations'])
            if cd['static_values']:
                parse_static_values(r, cd['static_values'], len(info['sf']))
            n_ok += 1
        except Exception as e:
            n_err += 1
            print('  ERR %-50s %s' % (cn.split('/')[-1][:-1], e))
    print('解析成功 %d, 失败 %d' % (n_ok, n_err))