import os,sys,struct,re
# scan all .so under a dir for symbols matching regex over .dynsym/.symtab
def scan(path,rx):
    try: d=open(path,'rb').read()
    except Exception: return []
    if d[:4]!=b'\x7fELF': return []
    try:
        e_shoff,=struct.unpack_from('<I',d,0x20); e_shentsize,=struct.unpack_from('<H',d,0x2e)
        e_shnum,=struct.unpack_from('<H',d,0x30); e_shstrndx,=struct.unpack_from('<H',d,0x32)
        if e_shoff==0 or e_shnum==0: return []
        raw=[struct.unpack_from('<10I',d,e_shoff+i*e_shentsize) for i in range(e_shnum)]
        sh=raw[e_shstrndx]; shstr=d[sh[4]:sh[4]+sh[5]]
        def nm(x):
            e=shstr.index(b'\x00',x); return shstr[x:e].decode('latin1')
        out=[]
        for r in raw:
            t=nm(r[0])
            if t not in ('.dynsym','.symtab'): continue
            if r[1]!=2 and r[1]!=11: continue
            if r[9]==0: continue
            st=d[r[6+0]*0:]  # noop
            link=r[6]
            strd=raw[link]
            sdata=d[strd[4]:strd[4]+strd[5]]
            for off in range(r[4],r[4]+r[5],r[9]):
                n,v,sz,info,other,shndx=struct.unpack_from('<IIIBBH',d,off)
                if n==0: continue
                e=sdata.index(b'\x00',n)
                nmv=sdata[n:e].decode('latin1')
                if rx.search(nmv):
                    out.append((nmv,v,sz,t,shndx,info&0xf))
        return out
    except Exception as ex:
        return []

if __name__=='__main__':
    root=sys.argv[1]; rx=re.compile(sys.argv[2])
    for dp,dn,fn in os.walk(root):
        for f in sorted(fn):
            p=os.path.join(dp,f)
            r=scan(p,rx)
            if r:
                print('### %s  (%d)'%(p,len(r)))
                for n,v,sz,t,shn,ty in r[:400]:
                    print('   %-8s %08x sz=%-7d %s %s'%(t,v,sz,'GLOBAL' if ty==1 else ('WEAK' if ty==2 else 'LOCAL'),n))