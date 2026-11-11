import struct
from capstone import *
d=open('out/hidisplay.bigfish.so','rb').read()
SYM_OFF=0x148; STR_OFF=0xd08
def symname(i):
    off=SYM_OFF+i*16
    n=struct.unpack('<I',d[off:off+4])[0]
    e=d.index(b'\x00',STR_OFF+n)
    return d[STR_OFF+n:e].decode('latin1','ignore')
relplt_off=0x217c; cnt=0x258//8
got2sym={}
for k in range(cnt):
    off=relplt_off+k*8
    r_off,r_info=struct.unpack('<II',d[off:off+8])
    got2sym[r_off]=symname(r_info>>8)
md=Cs(CS_ARCH_ARM,CS_MODE_ARM)
plt_addr=0x23d4; plt_end=0x23d4+0x398
PLT={}
a=plt_addr
while a<plt_end:
    insns=list(md.disasm(d[a:a+16],a))
    # find add ip,pc,#... ; ldr pc,[ip,#imm]!
    ipbase=None; gotaddr=None
    for ins in insns:
        if ins.mnemonic=='add' and ins.op_str.startswith('ip, pc'):
            ipbase=ins.address+8
        if ins.mnemonic=='ldr' and ins.op_str.startswith('pc, [ip'):
            # parse imm
            s=ins.op_str
            imm=s.split('#')[1].rstrip(']')
            imm=int(imm,0)
            if ipbase is not None:
                gotaddr=ipbase+imm
    if gotaddr is not None:
        PLT[a]=got2sym.get(gotaddr,'?%s'%hex(gotaddr))
    a+=4
if __name__=='__main__':
    for a in sorted(PLT):
        print(hex(a),PLT[a])
