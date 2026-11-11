import struct,re
D=open('out/hidisplay.bigfish.so','rb').read()
SYM_OFF=0x148; STR_OFF=0xd08
def symname(i):
    off=SYM_OFF+i*16
    n=struct.unpack('<I',D[off:off+4])[0]
    e=D.index(b'\x00',STR_OFF+n)
    return D[STR_OFF+n:e].decode('latin1','ignore')
relplt_off=0x217c; cnt=0x258//8
ents=[]
for k in range(cnt):
    off=relplt_off+k*8
    r_off,r_info=struct.unpack('<II',D[off:off+8])
    ents.append(symname(r_info>>8))
pat=bytes.fromhex('07ca8ce2')
idxs=[m.start() for m in re.finditer(re.escape(pat),D[0x23d4:0x23d4+0x398])]
starts=[0x23d4+i-4 for i in idxs]
PLT={s:n for s,n in zip(starts,ents)}
