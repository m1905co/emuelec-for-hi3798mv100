#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse Hisilicon baseparam base_table image: list tables/keys/values with file offsets."""
import sys, struct

def rd_str(d, off):
    e = d.index(b'\x00', off)
    return d[off:e].decode('latin1')

def parse(d, off, verbose=True):
    name = rd_str(d, off)
    size = struct.unpack_from('<I', d, off+32)[0]
    end = off + 36 + size
    rows = []
    ent = off + 36
    while ent + 36 <= end:
        nm = rd_str(d, ent)
        if not nm.startswith('BASE'):
            break
        ln = struct.unpack_from('<I', d, ent+32)[0]
        vaddr = ent + 36
        val = d[vaddr:vaddr+ln]
        rows.append((nm, vaddr, ln, val))
        stride = (32 + 4 + (ln if ln > 0 else 0) + 3) & ~3
        ent += stride
    if verbose:
        print('TABLE %-18s @ %#08x size=%d  (%d entries)' % (name, off, size, len(rows)))
        for nm, vaddr, ln, val in rows:
            u32 = struct.unpack_from('<I', val, 0)[0] if ln >= 4 else int.from_bytes(val, 'little')
            print('    %#08x  %-28s len=%-3d u32=%-8d hex=%s' % (vaddr, nm, ln, u32, val.hex()))
    return name, rows

def tables(d):
    # walk from 0x8 while table name starts with BASE_TABLE_
    out = []
    off = 0x8
    guard = 0
    while off + 36 < len(d) and guard < 64:
        try:
            nm = rd_str(d, off)
        except ValueError:
            break
        if not nm.startswith('BASE_TABLE_'):
            # scan forward for next BASE_TABLE_
            idx = d.find(b'BASE_TABLE_', off+1)
            if idx < 0:
                break
            off = idx
            continue
        name, rows = parse(d, off, verbose=False)
        out.append((off, name, rows))
        size = struct.unpack_from('<I', d, off+32)[0]
        off = off + 36 + size
        guard += 1
    return out

if __name__ == '__main__':
    path = sys.argv[1]
    d = open(path, 'rb').read()
    want = sys.argv[2] if len(sys.argv) > 2 else None
    for off, name, rows in tables(d):
        if want and want not in name:
            continue
        print('=== %s @ %#08x (%d entries) ===' % (name, off, len(rows)))
        for nm, vaddr, ln, val in rows:
            u32 = struct.unpack_from('<I', val, 0)[0] if ln >= 4 else int.from_bytes(val, 'little')
            print('    %#08x  %-28s len=%-3d u32=%-8d hex=%s' % (vaddr, nm, ln, u32, val.hex()))
