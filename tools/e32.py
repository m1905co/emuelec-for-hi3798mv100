import struct,capstone
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB,CS_MODE_ARM

def load(path):
    D=open(path,'rb').read()
    e_shoff,=struct.unpack_from('<I',D,0x20); e_shentsize,=struct.unpack_from('<H',D,0x2e)
    e_shnum,=struct.unpack_from('<H',D,0x30); e_shstrndx,=struct.unpack_from('<H',D,0x32)
    raw=[struct.unpack_from('<10I',D,e_shoff+i*e_shentsize) for i in range(e_shnum)]
    sh=raw[e_shstrndx]; shstr=D[sh[4]:sh[4]+sh[5]]
    def nm(x):
        e=shstr.index(b'\x00',x); return shstr[x:e].decode('latin1')
    SEC={nm(r[0]):r for r in raw}
    SYM=[]
    for nmz in ('.dynsym','.symtab'):
        if nmz in SEC:
            r=SEC[nmz]
            if r[9]==0: continue
            sd=D[raw[r[6]][4]:raw[r[6]][4]+raw[r[6]][5]]
            for off in range(r[4],r[4]+r[5],r[9]):
                n,v,sz,info,other,shndx=struct.unpack_from('<IIIBBH',D,off)
                e=sd.index(b'\x00',n)
                SYM.append((sd[n:e].decode('latin1'),v,sz,info&0xf,shndx,nmz))
    SYMBY={}
    for n,v,sz,t,shn,s2 in SYM: SYMBY.setdefault(v&~1,n)
    return D,SEC,SYM,SYMBY

class E:
    def __init__(s,path):
        s.D,s.SEC,s.SYM,s.SYMBY=load(path)
        D,SEC,SYM,SYMBY=s.D,s.SEC,s.SYM,s.SYMBY
        def cstr(o):
            if o<0 or o>=len(D): return '<OOB>'
            e=D.find(b'\x00',o)
            return D[o:(e if e>=0 else len(D))].decode('utf-8','replace')
        s.cstr=cstr
        # PLT
        s.PLT={}
        if '.rel.plt' in SEC and '.plt' in SEC:
            rp,plt=SEC['.rel.plt'],SEC['.plt']
            for i in range(rp[5]//8):
                o,info=struct.unpack_from('<II',D,rp[4]+i*8)
                s.PLT[plt[3]+20+i*12]=SYM[info>>8][0]
        s.GOT={}
        for k in ('.rel.dyn','.rela.dyn'):
            if k in SEC:
                r=SEC[k]
                for i in range(r[5]//(8 if k=='.rel.dyn' else 12)):
                    o,info=struct.unpack_from('<II',D,r[4]+i*(8 if k=='.rel.dyn' else 12))
                    s.GOT[o]=SYM[info>>8][0]
        # strings cache
        s._strs=[]
        import re
        for nmz in ('.rodata','.data.rel.ro','.data'):
            if nmz in SEC and SEC[nmz][5]:
                r=SEC[nmz]
                for m in re.finditer(rb'[\x20-\x7e]{4,}',D[r[4]:r[4]+r[5]]):
                    s._strs.append((r[3]+m.start(),m.group().decode()))
    def v2o(s,va):
        for r in s.SEC.values():
            if r[1]==8 or r[3]==0 or r[5]==0: continue
            if r[3]<=va<r[3]+r[5]: return r[4]+(va-r[3])
        return None
    def findstr(s,sub,limit=6):
        sub=sub.encode() if isinstance(sub,str) else sub
        return [(a,t) for a,t in s._strs if sub in t][:limit]
    def ldrpool(s,va):
        h=struct.unpack_from('<H',s.D,va)[0]
        if (h&0xf800)!=0x4800: return None
        lit=((va+4)&~3)+((h&0xff)*4)
        if lit+4>len(s.D): return None
        return (h>>8)&0xf, struct.unpack_from('<I',s.D,lit)[0], lit
    def pr(s,va,size,thumb=True,label=None):
        off=s.v2o(va)
        if off is None:
            print('  !! no section for %x'%va); return
        md=Cs(CS_ARCH_ARM,CS_MODE_THUMB if thumb else CS_MODE_ARM)
        print('==== %s @ %#x (%s) size=%d ===='%(label or s.SYMBY.get(va&~1,'?'),va,'T' if thumb else 'A',size))
        pend={}
        for i in md.disasm(s.D[off:off+size],va):
            ann=''
            if i.mnemonic.startswith('ldr') and '[pc' in i.op_str:
                r=s.ldrpool(i.address)
                if r:
                    rt,w,lit=r
                    if w&0xff800000==0:
                        tgt=(i.address+8&~3)+w
                        pend[rt]=tgt
                        c=s.cstr(tgt)
                        ann='   ; lit=%08x -> %08x "%s"'%(w,tgt,c[:52]) if all(32<=ord(x)<127 for x in c[:6]) else '   ; lit=%08x -> %08x'%(w,tgt)
                    else:
                        ann='   ; [GOT]@%08x %s'%(w,s.GOT.get(w,''))
            elif i.mnemonic in('add',) and i.op_str.endswith(', pc'):
                try: rt=int(i.op_str.split(',')[0].strip()[1:])
                except ValueError: rt=None
                t=pend.get(rt) if rt is not None else None
                if t is not None:
                    c=s.cstr(t)
                    ann='   ; => %08x "%s"'%(t,c[:52]) if all(32<=ord(x)<127 for x in c[:6]) else '   ; => %08x'%t
            if i.mnemonic in ('bl','blx','b','bx') and i.op_str.startswith('#'):
                try:
                    t=int(i.op_str[1:],0)
                    if t in s.PLT: ann='   ; %s'%s.PLT[t]
                    elif t in s.GOT: ann='   ; [GOT %s]'%s.GOT[t]
                    else:
                        n=s.SYMBY.get(t&~1)
                        if n: ann='   ; %s'%n
                except Exception: pass
            print('  %06x  %-8s %-30s%s'%(i.address,i.mnemonic,i.op_str,ann))