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
text=[s for s in secs if nm(s[0])=='.text'][0]
code=d[text[4]:text[4]+text[5]]
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
ins=list(md.disasm(code,text[3]))
# split into functions using symbols
funcs=[]
strtab=secs[e_shstrndx]
secs2=secs
sy=[]
for s in secs2:
    if nm(s[0]) in ('.dynsym','.symtab'):
        linked=strtab if nm(s[0])=='.dynsym' else secs2[s[6]]
        for i in range(s[5]//s[9]):
            o=s[4]+i*s[9]
            st_name,st_value,st_size=struct.unpack_from('<III',d,o)
            if st_value and st_size:
                try: sy.append((st_value,st_size,cstr(linked[4]+st_name)))
                except: pass
sy.sort()
def whichfunc(a):
    for v,sz,n in sy:
        if v<=a<v+sz: return n
    return '?'
res=[]
cur={}  # reg -> value(absolute addr) ; None = unknown clobbered
NOPS=set()
for i in ins:
    m=i.mnemonic; ops=i.op_str
    wrote=False
    if m=='ldr' and '[pc' in ops:
        mm=re.match(r'^(\w+),\s*\[pc,\s*#?(0x[0-9a-f]+|[0-9]+)\]',ops)
        if mm:
            dest=mm.group(1)
            imm=int(mm.group(2),0)
            pcv=((i.address+4)&~3)+imm
            cur[dest]=('pool',pcv)   # value = contents at pool (could be offset)
    elif m=='add' and ops.endswith('pc'):
        mm=re.match(r'^(\w+),\s*(\w+)(?:,\s*pc)?$',ops)
        if mm:
            dst,src=mm.group(1),mm.group(2)
            if src in cur and cur[src][0]=='pool':
                pv=cur[src][1]
                val=struct.unpack_from('<i',d,pv)[0] if pv+4<=len(d) else 0
                cur[dst]=('abs',(i.address+4+val)&0xFFFFFFFF)
    elif m in ('pop','bx') and 'pc' in ops:
        pass
    else:
        # clobber first operand
        mm=re.match(r'^(\w+),',ops)
        if mm and m not in ('str','cmp','strb','strh'):
            cur.pop(mm.group(1),None)
    for r,info in list(cur.items()):
        if info[0]=='abs' and info[1] in targets:
            res.append((i.address,m,ops,info[1],r,whichfunc(i.address)))
for a,m,o,v,r,f in res:
    print('%08x %-6s %-26s => %08x via %-4s  in %s'%(a,m,o,v,r,f))
