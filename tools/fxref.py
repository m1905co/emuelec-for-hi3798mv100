import struct,sys,re
from capstone import *
path=sys.argv[1]; targets=set(int(x,16) for x in sys.argv[2:])
d=open(path,'rb').read()
e_shoff,=struct.unpack_from('<I',d,0x20)
e_shentsize,=struct.unpack_from('<H',d,0x2e)
e_shnum,=struct.unpack_from('<H',d,0x30)
e_shstrndx,=struct.unpack_from('<H',d,0x32)
secs=[struct.unpack_from('<10I',d,e_shoff+i*e_shentsize) for i in range(e_shnum)]
sh=secs[e_shstrndx]
def cstr(o):
    e=d.index(b'\0',o); return d[o:e].decode('utf-8','replace')
nm=lambda x: cstr(sh[4]+x)
strtab=None
for s in secs:
    if nm(s[0])=='.dynstr': strtab=s
sy=[]
for s in secs:
    if nm(s[0]) in('.dynsym','.symtab'):
        linked=strtab if nm(s[0])=='.dynsym' else secs[s[6]]
        for i in range(s[5]//s[9]):
            o=s[4]+i*s[9]
            n,v,sz=struct.unpack_from('<III',d,o)
            if v and sz:
                try: sy.append((v,sz,cstr(linked[4]+n)))
                except: pass
sy.sort()
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
LDR=re.compile(r'^(\w+),\s*\[pc,\s*#?(0x[0-9a-f]+|[0-9]+)\]')
ADD=re.compile(r'^(\w+),\s*(\w+)(?:,\s*pc)?$')
res=[]
for fv,fsz,fname in sy:
    body=d[fv:fv+fsz]
    ins=list(md.disasm(body,fv))
    cur={}
    for i in ins:
        m=i.mnemonic; ops=i.op_str
        if m=='ldr':
            mm=LDR.match(ops)
            if mm:
                pv=((i.address+4)&~3)+int(mm.group(2),0)
                if pv+4<=len(d): cur[mm.group(1)]=('pool',pv)
                else: cur.pop(mm.group(1),None)
                continue
        if m=='add':
            mm=ADD.match(ops)
            if ops.rstrip().endswith('pc'):
                mm2=re.match(r'^(\w+),\s*pc$',ops)
                if mm2: dst=src=mm2.group(1)
                else:
                    mm=ADD.match(ops)
                    if not mm: continue
                    dst,src=mm.group(1),mm.group(2)
                if src in cur and cur[src][0]=='pool':
                    val=struct.unpack_from('<i',d,cur[src][1])[0]
                    cur[dst]=('abs',(i.address+4+val)&0xFFFFFFFF)
                continue
            if mm: cur.pop(mm.group(1),None)
            continue
        mm=re.match(r'^(\w+),',ops)
        if mm and m not in ('str','strb','strh','cmp','stm','push'):
            cur.pop(mm.group(1),None)
        if m in ('pop','ldm') and 'pc' in ops:
            cur.clear()
        for r,info in cur.items():
            if info[0]=='abs' and info[1] in targets:
                res.append((i.address,m,ops,info[1],r,fname))
for a,m,o,v,r,f in res:
    print('%08x %-6s %-26s => %08x via %-4s  in %s()'%(a,m,o,v,r,f))
