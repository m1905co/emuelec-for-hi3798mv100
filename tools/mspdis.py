import struct
from capstone import *
D=open('out/libhi_msp.so','rb').read()
SYM_OFF=0x148; SYM_SZ=0x8c80; STR_OFF=0x8dc8
def symname(i):
    o=SYM_OFF+i*16; nn=struct.unpack('<I',D[o:o+4])[0]
    e=D.index(b'\x00',STR_OFF+nn); return D[STR_OFF+nn:e].decode('latin1','ignore')
SYMS=[]
for i in range(SYM_SZ//16):
    o=SYM_OFF+i*16
    nm,val,sz,info,other,shndx=struct.unpack('<IIIBBH',D[o:o+16])
    SYMS.append((i,symname(i),val,sz,shndx,info&0xf))
def find(name):
    return [s for s in SYMS if s[1]==name]
def dis(name,maxn=300):
    for i,n,v,sz,sh,t in SYMS:
        if n==name:
            print('===== %s @ %#x size %d ====='%(n,v,sz))
            a=v&~1
            md=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
            c=0
            for ins in md.disasm(D[a:a+(sz+8 if sz else maxn*4)],a):
                print('  %06x  %-8s %s'%(ins.address,ins.mnemonic,ins.op_str))
                c+=1
                if c>maxn: break
            return
    print('NOT FOUND',name)
