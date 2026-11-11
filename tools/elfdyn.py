import struct,sys
def parse(p):
    d=open(p,'rb').read()
    e_shoff,=struct.unpack_from('<I',d,0x20)
    e_shentsize,=struct.unpack_from('<H',d,0x2e)
    e_shnum,=struct.unpack_from('<H',d,0x30)
    e_shstrndx,=struct.unpack_from('<H',d,0x32)
    secs=[]
    for i in range(e_shnum):
        o=e_shoff+i*e_shentsize
        secs.append(struct.unpack_from('<10I',d,o))
    sh=secs[e_shstrndx]
    def cstr(off):
        e=d.index(b'\0',off); return d[off:e].decode('utf-8','replace')
    nm=lambda x: cstr(sh[4]+x)
    out={}
    for s in secs:
        n=nm(s[0])
        out[n]=s
        if n=='.dynstr': dynstr=s
        if n=='.dynamic': dyn=dynstr
    # find dynstr by scanning dynamic for DT_STRTAB
    strtab=None
    for s in secs:
        if nm(s[0])=='.dynamic':
            o=s[4]; sz=s[5]
            strtabaddr=None
            for i in range(sz//8):
                tag,val=struct.unpack_from('<iI',d,o+i*8)
                if tag==5: strtabaddr=val
                if tag==0: break
            for s2 in secs:
                if s2[3]==strtabaddr and nm(s2[0])=='.dynstr': strtab=s2
    res=[]
    for s in secs:
        if nm(s[0])=='.dynamic':
            o=s[4]; sz=s[5]
            for i in range(sz//8):
                tag,val=struct.unpack_from('<iI',d,o+i*8)
                if tag==0: break
                if tag==1:
                    res.append(cstr(strtab[4]+val))
    return res
for p in sys.argv[1:]:
    print('==== %s'%p)
    for n in parse(p): print('  NEEDED:',n)
