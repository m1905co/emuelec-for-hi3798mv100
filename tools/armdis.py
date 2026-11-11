import struct
from capstone import *

D = open('out/hidisplay.bigfish.so','rb').read()
TEXT_ADDR=0x276c
SYM_OFF=0x148; SYM_SZ=0xbc0; STR_OFF=0xd08

def symname(i):
    off=SYM_OFF+i*16
    n=struct.unpack('<I',D[off:off+4])[0]
    e=D.index(b'\x00',STR_OFF+n)
    return D[STR_OFF+n:e].decode('latin1','ignore')

SYMS=[]
for i in range(SYM_SZ//16):
    off=SYM_OFF+i*16
    nm,val,sz,info,other,shndx=struct.unpack('<IIIBBH',D[off:off+16])
    SYMS.append((i,symname(i),val,sz,shndx,info&0xf))

def dis_func(addr, mode=CS_MODE_THUMB, maxn=400):
    md=Cs(CS_ARCH_ARM,mode)
    # addr has thumb bit possibly; use raw
    a=addr&~1
    for ins in md.disasm(D[a:a+maxn*4],a):
        print('  %06x  %-8s %s'%(ins.address,ins.mnemonic,ins.op_str))

if __name__=='__main__':
    import sys
    for i,n,v,sz,sh,t in SYMS:
        if sh==8 and sz>0:
            print(i,n,hex(v),sz)
