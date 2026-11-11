import struct,sys,re
path=sys.argv[1]
targets=[int(x,16) for x in sys.argv[2:]]
d=open(path,'rb').read()
# collect 4-byte aligned words equal to target
pool={}
for t in targets:
    hits=[]
    pat=struct.pack('<I',t)
    i=0
    while True:
        i=d.find(pat,i)
        if i<0: break
        if i%4==0: hits.append(i)
        i+=1
    pool[t]=hits
    print('target %08x literal-pool hits: %s'%(t,['%08x'%h for h in hits]))
# scan thumb LDR Rd,[pc,#imm]
e_phoff,=struct.unpack_from('<I',d,0x1c)
e_phentsize,=struct.unpack_from('<H',d,0x2a)
e_phnum,=struct.unpack_from('<H',d,0x2c)
segs=[struct.unpack_from('<8I',d,e_phoff+i*e_phentsize) for i in range(e_phnum)]
def o2v(o):
    for s in segs:
        if s[2] and s[2]<=o<s[2]+s[4]: return s[1]+(o-s[2])
    return None
def v2o(v):
    for s in segs:
        if s[1] and s[1]<=v<s[1]+s[4]: return s[2]+(v-s[1])
    return v
print('--- code refs ---')
allpool={}
for t,hits in pool.items():
    for h in hits: allpool[h]=t
# scan code region: find thumb LDR literal
for s in segs:
    if s[1]!=0 and (s[0]&1)==0 or True:
        pass
for o in range(0,len(d)-4,2):
    hw=struct.unpack_from('<H',d,o)[0]
    # Thumb LDR Rd,[pc,#imm8*4]: 0100 1xxx xxxx xxxx
    if (hw & 0xF800)==0x4800:
        imm=(hw&0xFF)*4
        pc=((o+4)&~3)+imm
        v=o2v(pc)
        if v is None: continue
        fo=v2o(v)
        if fo is None: continue
        if fo in allpool:
            addr=o2v(o)
            print('  code %08x (file %06x): ldr lit -> %08x  == target %08x  [%s]'%(addr,o,v,allpool[fo],sys.argv[1].split('/')[-1]))
