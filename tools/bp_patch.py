#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch baseparam: set DISP1 BASE_KEY_VIRSCW/VIRSCH. Offsets auto-located by parsing."""
import sys, struct
sys.path.insert(0,'tools')
from bp_parse import tables

def find(rows, key):
    for nm, vaddr, ln, val in rows:
        if nm == key:
            return vaddr, ln
    return None, None

def main(src, dst, table='BASE_TABLE_DISP1', w=1920, h=1080, also_disp0=False):
    d = bytearray(open(src,'rb').read())
    for off, name, rows in tables(bytes(d)):
        if name != table:
            continue
        va, ln = find(rows, 'BASE_KEY_VIRSCW')
        struct.pack_into('<I', d, va, w)
        print('%s VIRSCW @ %#x -> %d' % (name, va, w))
        va, ln = find(rows, 'BASE_KEY_VIRSCH')
        struct.pack_into('<I', d, va, h)
        print('%s VIRSCH @ %#x -> %d' % (name, va, h))
    if also_disp0:
        for off, name, rows in tables(bytes(d)):
            if name != 'BASE_TABLE_DISP0':
                continue
            va, ln = find(rows, 'BASE_KEY_VIRSCW')
            struct.pack_into('<I', d, va, w)
            print('%s VIRSCW @ %#x -> %d' % (name, va, w))
            va, ln = find(rows, 'BASE_KEY_VIRSCH')
            struct.pack_into('<I', d, va, h)
            print('%s VIRSCH @ %#x -> %d' % (name, va, h))
    open(dst,'wb').write(bytes(d))
    print('wrote', dst, len(d), 'bytes')

if __name__ == '__main__':
    src=sys.argv[1]; dst=sys.argv[2]
    also0 = len(sys.argv)>3 and sys.argv[3]=='disp0'
    main(src, dst, also_disp0=also0)
