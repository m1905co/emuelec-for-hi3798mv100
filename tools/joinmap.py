#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Join: DisplayClient method -> vtable offset  with  onTransact code -> vtable offset."""
import sys, struct
sys.path.insert(0,'tools')
import elftool as E
from capstone import *

def dis_list(va, size):
    off = E.vaddr_to_off(va)
    if off is None: return []
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    return list(md.disasm(E.ELF[off:off+size], va))

def find_vtoff(insns):
    """first ldr.w/ldr rX,[rY,#0xNN] with NN>=0x0c that is followed by blx"""
    for n,i in enumerate(insns):
        if i.mnemonic in ('ldr','ldr.w') and '#0x' in i.op_str and ']' in i.op_str:
            try:
                off=int(i.op_str.split('#0x')[1].split(']')[0],16)
            except: continue
            if off>=0x0c and any(k.mnemonic=='blx' for k in insns[n+1:n+6]):
                return off
    return None

# ---- pass 1: client ----
E.load('out/libhidisplayclient.so')
client={}
for n,v,sz,info,shndx in list(E.SYMS):
    if n.startswith('_ZN7android13DisplayClient') and sz>0:
        ins=dis_list(v, sz+8)
        o=find_vtoff(ins)
        if o is not None:
            client[o]=n.replace('_ZN7android13DisplayClient','').strip()
print('=== client slot -> method (%d) ==='%len(client))
for o in sorted(client): print('  %#04x  %s'%(o,client[o]))

# ---- pass 2: service onTransact codes ----
E.load('out/libhidisplayservice.so')
tbl=0x6c6a
print()
print('=== code -> vtable offset -> method ===')
for code in range(1,0x2d):
    hw=struct.unpack_from('<H', E.ELF, E.vaddr_to_off(tbl+(code-1)*2))[0]
    tgt=tbl+hw*2
    ins=dis_list(tgt, 60)
    o=find_vtoff(ins)
    nm=client.get(o,'?')
    print('  code %2d (0x%02x) -> off %-6s -> %s'%(code,code, hex(o) if o else '?', nm))
