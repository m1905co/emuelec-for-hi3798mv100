import os,sys
src=sys.argv[1]; base=os.path.abspath(sys.argv[2])
d=open(src,'rb').read()
os.makedirs(base,exist_ok=True)
def a4(x): return (x+3)&~3
i=0; files=[]
while i < len(d)-110:
    if d[i:i+6] not in (b'070701',b'070702'):
        print('bad magic at', i, d[i:i+6]); break
    f=tuple(int(d[i+6+8*k:i+14+8*k],16) for k in range(13))
    mode,filesize,namesize=f[1],f[6],f[11]
    name=d[i+110:i+110+namesize-1].decode('latin1','replace')
    hdrlen=a4(110+namesize)
    body=d[i+hdrlen:i+hdrlen+filesize]
    files.append((mode,filesize,name))
    if name and not name.endswith('/') and name!='TRAILER!!!':
        rel=name.lstrip('/').replace('/',os.sep)
        p=os.path.normpath(os.path.join(base,rel))
        if not p.startswith(base): p=os.path.join(base,os.path.basename(name))
        dd=os.path.dirname(p)
        if dd:
            try: os.makedirs(dd,exist_ok=True)
            except Exception: pass
        try:
            open(p,'wb').write(body)
            if mode&0o111: os.chmod(p,0o755)
        except Exception as e:
            print('skip',name,e)
    i += hdrlen + a4(filesize)
    if name=='TRAILER!!!': break
print('entries',len(files))
for mode,fsize,name in files:
    t='d' if mode&0o40000 else ('l' if (mode&0o120000)==0o120000 else '-')
    print(f'{t}{mode&0o7777:04o} {fsize:8d} {name}')
