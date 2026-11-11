import struct,sys
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
rodata=[s for s in secs if nm(s[0]) in ('.rodata',)]
print('.text %08x+%d'%(text[3],text[5]))
code=d[text[4]:text[4]+text[5]]
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.detail=True
ins=list(md.disasm(code,text[3]))
# emulate ldr rX,[pc,#imm] -> value; and add rX, pc ; and ldr=+str patterns
reg={}   # reg -> absolute addr known
out=[]
window={}
for i in ins:
    m=i.mnemonic; ops=i.op_str
    if m=='ldr' and '[pc' in ops:
        # parse dest reg and imm
        try:
            dest=ops.split(',')[0].strip()
            imm_txt=ops.split('#')[1].rstrip(']').strip()
            imm=int(imm_txt,16) if imm_txt.startswith('0x') else int(imm_txt)
        except: continue
        pcv=((i.address+4)&~3)+imm
        reg[dest]=pcv
    elif m=='add' and ops.endswith('pc'):
        p=ops.split(',')
        if len(p)==3:
            dst=p[0].strip(); src=p[1].strip()
            base=reg.get(src)
            if base is not None:
                # add rd, pc  => pc = i.address+4 (thumb)
                val=(i.address+4+base)&0xFFFFFFFF
                reg[dst]=val
    elif m=='mov' and ops.endswith('pc'):
        pass
    else:
        # any write to reg invalidates
        p=ops.split(',')
        if p and p[0].strip() in reg and m in ('mov','ldr','add','sub','str','pop','bl','blx') and m!='str':
            if m=='str': pass
            else: reg.pop(p[0].strip(),None)
    for r,v in list(reg.items()):
        if v in targets:
            out.append((i.address,i.mnemonic,i.op_str,v,r))
        elif not (text[3]<=v<text[3]+text[5]):
            reg.pop(r,None)
seen=set()
for a,m,o,v,r in out:
    k=(a,v)
    if k in seen: continue
    seen.add(k)
    print('%08x  %-8s %-24s  => %08x (via %s)'%(a,m,o,v,r))
