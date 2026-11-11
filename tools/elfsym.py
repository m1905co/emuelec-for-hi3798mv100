import struct,sys
p=sys.argv[1]
d=open(p,'rb').read()
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
out=[]
for s in secs:
    if nm(s[0]) in ('.dynsym','.symtab'):
        linked=strtab if nm(s[0])=='.dynsym' else secs[s[6]]
        for i in range(s[5]//s[9]):
            o=s[4]+i*s[9]
            st_name,st_value,st_size,st_info,st_other,st_shndx=struct.unpack_from('<IIIBBH',d,o)
            if st_value and st_name:
                try: n=cstr(linked[4]+st_name)
                except: continue
                out.append((st_value,st_size,n,st_info&0xf))
out.sort()
filt=sys.argv[2] if len(sys.argv)>2 else None
for v,sz,n,t in out:
    if filt and filt.lower() not in n.lower(): continue
    print('%08x %5d %-50s type=%d'%(v,sz,n,t))
