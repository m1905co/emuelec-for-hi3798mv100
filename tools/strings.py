import sys, re
args=sys.argv[1:]
pat=None
if '-e' in args:
    i=args.index('-e'); pat=args[i+1].lower(); args=args[:i]+args[i+2:]
for p in args:
    try:
        data=open(p,'rb').read()
    except Exception as e:
        print('ERR',p,e); continue
    for m in re.finditer(rb'[\x20-\x7e]{4,}', data):
        s=m.group().decode('ascii','replace')
        if pat and pat not in s.lower(): continue
        print('%08x %s'%(m.start(),s))
