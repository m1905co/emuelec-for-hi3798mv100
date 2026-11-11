import struct,sys
path=sys.argv[1]
targets=[int(x,16) for x in sys.argv[2:]]
d=open(path,'rb').read()
e_phoff,=struct.unpack_from('<I',d,0x1c)
e_phentsize,=struct.unpack_from('<H',d,0x2a)
e_phnum,=struct.unpack_from('<H',d,0x2c)
segs=[struct.unpack_from('<8I',d,e_phoff+i*e_phentsize) for i in range(e_phnum)]
# text range
e_shoff,=struct.unpack_from('<I',d,0x20)
e_shentsize,=struct.unpack_from('<H',d,0x2e)
e_shnum,=struct.unpack_from('<H',d,0x30)
e_shstrndx,=struct.unpack_from('<H',d,0x32)
secs=[struct.unpack_from('<10I',d,e_shoff+i*e_shentsize) for i in range(e_shnum)]
sh=secs[e_shstrndx]
def cstr(o):
    e=d.index(b'\0',o); return d[o:e].decode('utf-8','replace')
nm=lambda x: cstr(sh[4]+x)
text=None
for s in secs:
    if nm(s[0])=='.text': text=s
print('.text vaddr=%08x off=%08x size=%d'%(text[3],text[4],text[5]))
tstart=text[3]; tend=text[3]+text[5]; toff=text[4]; tsize=text[5]
# For each target: find pool words W such that W + (A+4) == target for some A in text
for t in targets:
    print('=== target %08x"%s"'%(t, ''))
    found=set()
    # iterate A over 4-aligned add-instruction candidates
    for A in range(tstart, tend, 2):
        val = (t - (A+4)) & 0xFFFFFFFF
        pat = struct.pack('<I', val)
        # search in pool area (file offset of rodata)
        i = toff
        # limit search to whole file but only aligned
        j = 0
        while True:
            j = d.find(pat, j)
            if j < 0: break
            if j % 4 == 0:
                found.add((A, j, val))
            j += 1
    for (A,fo,val) in sorted(found):
        print('   add-instr vaddr~%08x  pool@file %06x value=%08x'%(A,fo,val))
