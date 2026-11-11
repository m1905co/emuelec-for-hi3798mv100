import struct,sys
path=sys.argv[1]
d=open(path,'rb').read()
def cstr(o):
    e=d.index(b'\0',o); return d[o:e].decode('utf-8','replace')
def lp(a,imm): return ((a+4)&~3)+imm
def ab(a): return a+4
# pairs given as add_addr:ldr_addr:imm
for spec in sys.argv[2:]:
    parts=spec.split(':')
    adda=int(parts[0],16); ldra=int(parts[1],16); imm=int(parts[2],16)
    p=lp(ldra,imm)
    if p+4>len(d): print('%s -> pool %08x OUT OF RANGE'%(spec,p)); continue
    v=ab(adda)+struct.unpack_from('<i',d,p)[0]
    if v<0 or v>=len(d):
        print('%s -> %08x (invalid, raw=%08x)'%(spec,v&0xffffffff,struct.unpack_from('<I',d,p)[0]))
    else:
        try: print('%s -> %08x  %r'%(spec,v,cstr(v)))
        except: print('%s -> %08x  (not string)'%(spec,v))
