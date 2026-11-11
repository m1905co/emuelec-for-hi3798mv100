#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Resolve .plt stub addresses -> symbol names, for a given ELF32-ARM .so."""
import sys, struct
sys.path.insert(0,'tools')
import elftool as E

def plt_map():
    plt=[s for s in E.SECTIONS if s[0]=='.plt'][0]
    rel=[s for s in E.SECTIONS if s[0]=='.rel.plt'][0]
    dynsym=[s for s in E.SECTIONS if s[1]==11][0]  # .dynsym (first)
    strtab=E.SECTIONS[dynsym[6]]
    st=E.ELF[strtab[4]:strtab[4]+strtab[5]]
    n=rel[5]//rel[9]
    out={}
    base=plt[3]
    # header 20 bytes, then 12-byte stubs
    for i in range(n):
        off=rel[4]+i*rel[9]
        r_off,r_info=struct.unpack_from('<II',E.ELF,off)
        si=r_info>>8
        so=dynsym[4]+si*16
        name,val,size,info,other,shndx=struct.unpack_from('<IIIBBH',E.ELF,so)
        e=st.index(b'\x00',name); nm=st[name:e].decode('latin1','ignore')
        stub=base+20+i*12
        out[stub]=nm
    return out

if __name__=='__main__':
    E.load(sys.argv[1])
    m=plt_map()
    if len(sys.argv)>2 and sys.argv[2]=='all':
        for a in sorted(m): print('%#08x  %s'%(a,m[a]))
    else:
        for a in sys.argv[2:]:
            v=int(a,16)
            print('%#x -> %s'%(v, m.get(v,'?')))
