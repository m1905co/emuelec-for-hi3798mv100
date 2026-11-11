import struct,sys
D=open('out/libhimediaplayer_jni.so','rb').read()
e_shoff,=struct.unpack_from('<I',D,0x20); e_shentsize,=struct.unpack_from('<H',D,0x2e)
e_shnum,=struct.unpack_from('<H',D,0x30); e_shstrndx,=struct.unpack_from('<H',D,0x32)
raw=[struct.unpack_from('<10I',D,e_shoff+i*e_shentsize) for i in range(e_shnum)]
sh=raw[e_shstrndx]; shstr=D[sh[4]:sh[4]+sh[5]]
def nm(x):
    e=shstr.index(b'\x00',x); return shstr[x:e].decode('latin1')
SEC={nm(r[0]):r for r in raw}
def cstr(o):
    if o<0 or o>=len(D): return '<OOB>'
    e=D.find(b'\x00',o)
    if e<0: e=len(D)
    return D[o:e].decode('utf-8','replace')
ds=SEC['.dynsym']; dstr=D[SEC['.dynstr'][4]:SEC['.dynstr'][4]+SEC['.dynstr'][5]]
SYM=[]
for off in range(ds[4],ds[4]+ds[5],16):
    n,v,sz,info,other,shndx=struct.unpack_from('<IIIBBH',D,off)
    e=dstr.index(b'\x00',n); SYM.append((dstr[n:e].decode('latin1'),v,sz,info&0xf,info>>4,shndx))
SYMBY={}
for n,v,sz,t,b,shn in SYM: SYMBY.setdefault(v,n)
PLT={}
rp=SEC['.rel.plt']; plt=SEC['.plt']
PLT0=plt[3]+20           # ARM PLT header = 5 words = 20 bytes
for i in range(rp[5]//8):
    r_off,r_info=struct.unpack_from('<II',D,rp[4]+i*8)
    PLT[PLT0+i*12]=SYM[r_info>>8][0]
JMP={}
for i in range(SEC['.rel.dyn'][5]//8):
    r_off,r_info=struct.unpack_from('<II',D,SEC['.rel.dyn'][4]+i*8)
    JMP.setdefault(r_off,SYM[r_info>>8][0])
def sym(va):
    va&=~1
    return SYMBY.get(va)
def ldrpool(va,thumb=True):
    """resolve Thumb-1 `ldr rX,[pc,#imm8]` -> (rt, word_at_literal, literal_addr)"""
    h=struct.unpack_from('<H',D,va)[0]
    if (h&0xf800)!=0x4800: return None
    imm=(h&0xff)*4          # Thumb-1 T1 scales imm8 by 4
    rt=(h>>8)&0xf
    tgt=((va+4)&~3)+imm
    w=struct.unpack_from('<I',D,tgt)[0]
    return rt,w,tgt
def poolstr(va):
    """for ldr rX,[pc,#imm] where word is PC-relative offset -> string"""
    r=ldrpool(va)
    if not r: return None
    rt,w,tgt=r
    if rt!=4: return None
    s=((tgt+4)&~3)+w
    return cstr(s)
import capstone
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_ARM
def dis(va,size,thumb=True):
    off=SEC['.text'][4]+(va-(SEC['.text'][3]))
    md=Cs(CS_ARCH_ARM, CS_MODE_THUMB if thumb else CS_MODE_ARM)
    md.detail=False
    return list(md.disasm(D[off:off+size],va))
def pr(va,size,thumb=True,label=None):
    print('==== %s @ %#x (%s) size=%d ===='%(label or sym(va) or '?',va,'THUMB' if thumb else 'ARM',size))
    pending={}
    for i in dis(va,size,thumb):
        ann=''
        if i.mnemonic.startswith('ldr') and '[pc' in i.op_str:
            r=ldrpool(i.address)
            if r:
                rt,w,tgt=r
                if w&0xff800000==0:
                    # `add rX, pc` at pc_addr uses (pc_addr+4)+w
                    dest=(i.address+8)&~3
                    s=(dest)+w
                    pending[rt]=s
                    ann='   ; lit=%08x -> %08x "%s"'%(w,s,cstr(s)[:56])
                else:
                    ann='   ; [abs/GOT] @%08x'%w
        elif i.mnemonic=='add' and i.op_str.endswith(', pc'):
            rt=int(i.op_str.split(',')[0][1:])
            s=pending.get(rt)
            if s is not None:
                ann='   ; => %08x "%s"'%(s,cstr(s)[:60])
        if i.mnemonic in ('bl','blx','b','bx') and i.op_str.startswith('#'):
            try:
                t=int(i.op_str[1:],0)
                if t in PLT: ann='   ; %s'%PLT[t]
                elif (t&~1) in PLT: ann='   ; %s'%PLT[t&~1]
                elif t in JMP: ann='   ; [GOT %s]'%JMP[t]
                else:
                    s2=sym(t) or sym(t&~1)
                    if s2: ann='   ; %s'%s2
            except Exception: pass
        print('  %06x  %-8s %-30s%s'%(i.address,i.mnemonic,i.op_str,ann))