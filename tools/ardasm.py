import struct,sys
from capstone import *
path=sys.argv[1]; start=int(sys.argv[2],16); size=int(sys.argv[3])
if start&1: start-=1
thumb=len(sys.argv)>4 and sys.argv[4]=='t'
d=open(path,'rb').read()
# map vaddr->file offset via program headers
e_phoff,=struct.unpack_from('<I',d,0x1c)
e_phentsize,=struct.unpack_from('<H',d,0x2a)
e_phnum,=struct.unpack_from('<H',d,0x2c)
segs=[struct.unpack_from('<8I',d,e_phoff+i*e_phentsize) for i in range(e_phnum)]
def v2o(v):
    for s in segs:
        if s[1] and s[1]<=v<s[1]+s[4]:
            return s[2]+(v-s[1])
    return v
off=v2o(start)
code=d[off:off+size]
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB if thumb else CS_MODE_ARM); md.detail=False
for i in md.disasm(code,start):
    print('%08x  %-10s %s'%(i.address,i.mnemonic,i.op_str))
