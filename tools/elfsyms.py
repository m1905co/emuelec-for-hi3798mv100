#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析 ARM32 ELF 的 .dynsym，列出真实导出符号（GLIBC style）"""
import struct, sys

path = sys.argv[1]
d = open(path, 'rb').read()

assert d[:4] == b'\x7fELF', 'not ELF'
is32 = d[4] == 1
endian = '<' if d[5] == 1 else '>'
e_machine = struct.unpack_from(endian + 'H', d, 18)[0]

e_shoff = struct.unpack_from(endian + 'I', d, 32)[0]
e_shentsize = struct.unpack_from(endian + 'H', d, 46)[0]
e_shnum = struct.unpack_from(endian + 'H', d, 48)[0]
e_shstrndx = struct.unpack_from(endian + 'H', d, 50)[0]

print('machine = %d  section count = %d' % (e_machine, e_shnum))

def sec(i):
    o = e_shoff + i * e_shentsize
    name, typ, flags, addr, off, size, link, info, align, entsize = \
        struct.unpack_from(endian + '10I', d, o)
    return dict(name=name, type=typ, off=off, size=size, link=link, entsize=entsize)

sh = [sec(i) for i in range(e_shnum)]

# 找 .dynsym / .dynstr
dynsym = dynstr = None
for s in sh:
    # SHT_DYNSYM = 11
    if s['type'] == 11:
        dynsym = s
    # SHT_STRTAB = 3，且被 dynsym 指向的
    if s['type'] == 3 and s['size'] > 0 and s['size'] < 0x10000:
        pass

if not dynsym:
    print('没有 .dynsym（可能是静态链接或被 strip）')
    raise SystemExit

strtab = sh[dynsym['link']]
str_off, str_size = strtab['off'], strtab['size']

n = dynsym['size'] // dynsym['entsize'] if dynsym['entsize'] else dynsym['size'] // 16
print('.dynsym 条目数 = %d' % n)
print()

out = []
for i in range(n):
    o = dynsym['off'] + i * 16
    st_name, st_value, st_size, st_info, st_other, st_shndx = \
        struct.unpack_from(endian + 'IIIBBH', d, o)
    if st_name == 0 or st_name >= str_size:
        continue
    end = d.find(b'\x00', str_off + st_name)
    name = d[str_off + st_name:end].decode('utf-8', 'replace')
    bind = st_info >> 4
    typ = st_info & 0xf
    if typ not in (1, 2):        # STB_GLOBAL / STB_WEAK
        continue
    b = {0:'LOCAL',1:'GLOBAL',2:'WEAK'}.get(bind, str(bind))
    out.append((name, st_value, st_size, b, st_shndx))

print('导出符号 (%d):' % len(out))
for name, val, sz, b, shndx in sorted(out):
    mark = '' if shndx != 0 else '  (UND/import)'
    print('  0x%08x %-6s %-45s size=%-6d%s' % (val, b, name, sz, mark))
