import sys, re
path = sys.argv[1]
minlen = int(sys.argv[2]) if len(sys.argv)>2 else 5
d = open(path,'rb').read()
pat = re.compile(rb'[\x20-\x7e]{%d,}'%minlen)
for m in pat.finditer(d):
    print(m.group().decode('latin1'))
