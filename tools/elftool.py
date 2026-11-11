#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generic ELF32-ARM (little endian) tool: sections, dynsym, disasm by symbol/addr."""
import struct, sys, os
from capstone import *

ELF = None
SECTIONS = []   # (name, type, offset, size, addr, link, entsize)
SYMS = []       # (name, value, size, info, shndx)
SHN = {}

def load(path):
    global ELF, SECTIONS, SYMS, SHN
    ELF = open(path,'rb').read()
    assert ELF[:4]==b'\x7fELF', 'not ELF'
    SECTIONS = []
    SYMS = []
    SHN = {}
    e_shoff, = struct.unpack_from('<I', ELF, 0x20)
    e_shentsize, = struct.unpack_from('<H', ELF, 0x2e)
    e_shnum, = struct.unpack_from('<H', ELF, 0x30)
    e_shstrndx, = struct.unpack_from('<H', ELF, 0x32)
    raw=[]
    for i in range(e_shnum):
        o=e_shoff+i*e_shentsize
        name,typ,flags,addr,off,size,link,info,align,entsize = struct.unpack_from('<IIIIIIIIII', ELF, o)
        raw.append([name,typ,flags,addr,off,size,link,info,align,entsize])
    # shstrtab
    sh = raw[e_shstrndx]
    shstr = ELF[sh[4]:sh[4]+sh[5]]
    def nm(x):
        e=shstr.index(b'\x00',x); return shstr[x:e].decode('latin1','ignore')
    for r in raw:
        r[0]=nm(r[0])
        SECTIONS.append(tuple(r))
    SHN={s[0:i+1] and 0 or 0 for i,s in enumerate(SECTIONS)}
    SYMS=[]
    for s in SECTIONS:
        if s[1] in (2,11):  # SYMTAB / DYNSYM
            strtab=SECTIONS[s[6]]
            st=ELF[strtab[4]:strtab[4]+strtab[5]]
            for off in range(s[4], s[4]+s[5], s[9]):
                name,val,size,info,other,shndx=struct.unpack_from('<IIIBBH',ELF,off)
                e=st.index(b'\x00',name); n=st[name:e].decode('latin1','ignore')
                SYMS.append((n,val,size,info,shndx))
    return ELF

def sec_by_name(n):
    for s in SECTIONS:
        if s[0]==n: return s
    return None

def find_sym(pat):
    res=[]
    for n,v,sz,info,shndx in SYMS:
        if pat in n: res.append((n,v,sz,info,shndx))
    return res

def vaddr_to_off(va):
    for s in SECTIONS:
        if s[3] and s[5] and s[3]<=va<s[3]+s[5] and s[1]!=8:
            return s[4]+(va-s[3])
    return None

def dis(va, mode=CS_MODE_THUMB, maxn=2000, raw_bytes=None):
    if mode==CS_MODE_THUMB and (va & 1):
        va &= ~1            # clear Thumb bit0 marker
    if raw_bytes is not None:
        code=raw_bytes
    else:
        off=vaddr_to_off(va)
        if off is None:
            print('  !! no section for',hex(va)); return
        code=ELF[off:off+maxn*4]
    md=Cs(CS_ARCH_ARM, mode); md.detail=False
    a=va
    for ins in md.disasm(code, a):
        print('  %06x  %-8s %s'%(ins.address,ins.mnemonic,ins.op_str))

if __name__=='__main__':
    path=sys.argv[1]; load(path)
    cmd=sys.argv[2]
    if cmd=='sec':
        for s in SECTIONS:
            print('%-18s type=%2d addr=%08x off=%08x size=%08x link=%d entsz=%d'%(s[0],s[1],s[3],s[4],s[5],s[6],s[9]))
    elif cmd=='sym':
        pat=sys.argv[3] if len(sys.argv)>3 else ''
        for n,v,sz,info,shndx in SYMS:
            if pat in n:
                print('%-70s %08x sz=%d info=%02x shn=%d'%(n,v,sz,info,shndx))
    elif cmd=='dis':
        va=int(sys.argv[3],16)
        mode=CS_MODE_ARM if (len(sys.argv)>4 and sys.argv[4]=='arm') else CS_MODE_THUMB
        n=int(sys.argv[5]) if len(sys.argv)>5 else 400
        print('==== disasm %s @ %#x (%s) ===='%(path,va,'ARM' if mode==CS_MODE_ARM else 'THUMB'))
        dis(va, mode, n)
