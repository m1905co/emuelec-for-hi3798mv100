#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dump a vtable by symbol name; resolve entries to nearest exported symbol."""
import sys, struct
sys.path.insert(0,'tools')
import elftool as E

def vread(va,n=4):
    for s in E.SECTIONS:
        if s[3] and s[5] and s[3]<=va<s[3]+s[5] and s[1]!=8:
            o=s[4]+(va-s[3]); return E.ELF[o:o+n]
    return None

def resolve(val):
    best=''; bv=-1
    for n,v,sz,info,shndx in E.SYMS:
        if n and v and v<=val and v>bv:
            bv=v; best=n
    return best

if __name__=='__main__':
    E.load(sys.argv[1])
    vt=sys.argv[2]
    hit=False
    for n,v,sz,info,shndx in E.SYMS:
        if n==vt:
            hit=True
            print('%s @ %#x size %d'%(n,v,sz))
            for i in range(sz//4):
                d=vread(v+i*4,4)
                if d:
                    val=struct.unpack('<I',d)[0]
                    print('  [%2d] %#x  %s'%(i,val,resolve(val)))
    if not hit:
        print('vtable not found:',vt)
