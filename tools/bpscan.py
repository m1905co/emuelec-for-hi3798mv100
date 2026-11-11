#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scan .text for Bp-style transact sequences: writeInterfaceToken ... movs r1,#CODE ... blx (transact)."""
import sys, struct
sys.path.insert(0,'tools')
import elftool as E
from capstone import *

WRITE_TOKEN = 0x5dd0+0  # not used
def load(path):
    E.load(path)

def text_range():
    s=[x for x in E.SECTIONS if x[0]=='.text'][0]
    return s[3], s[4], s[5]

def scan():
    va, off, size = text_range()
    code = E.ELF[off:off+size]
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB); md.detail=False
    ins = list(md.disasm(code, va))
    # index by address
    idx = {i.address:n for n,i in enumerate(ins)}
    res=[]
    for n,i in enumerate(ins):
        if i.mnemonic in ('movs','mov') and i.op_str.startswith('r1, #'):
            try: codeval=int(i.op_str.split('#')[1],0)
            except: continue
            # look ahead up to 10 insns for blx reg, and check a ldr rX,[rY,#0x14] before it
            tgt=None
            win=ins[n+1:n+12]
            for j,k in enumerate(win):
                if k.mnemonic=='blx' and k.op_str.startswith('r'):
                    tgt=k
                    break
            if tgt is None: continue
            # verify a "ldr rX, [rY, #0x14]" appears before tgt in the window (transact slot)
            pre=[k for k in win[:win.index(tgt)]]
            has_slot = any(k.mnemonic=='ldr' and '#0x14]' in k.op_str for k in pre)
            # find function start: preceding push
            fstart=None
            for m in range(n, max(0,n-60), -1):
                if ins[m].mnemonic=='push':
                    fstart=ins[m].address; break
            res.append((fstart, i.address, codeval, has_slot, tgt.op_str))
    return res

if __name__=='__main__':
    load(sys.argv[1])
    for fstart,addr,codeval,hs,reg in scan():
        mark='TRANSACT' if hs else ''
        print('func~%#06x  movs r1,#%#x (%d) at %#06x  -> blx %s  %s'%(fstart or 0,codeval,codeval,addr,reg,mark))
