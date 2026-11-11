import sys
sys.path.insert(0,'tools')
from armdis import dis_func, D, SYMS
from capstone import *
def run(name):
    for i,n,v,sz,sh,t in SYMS:
        if n==name:
            print('===== %s @ %#x size %d ====='%(n,v,sz))
            dis_func(v, CS_MODE_THUMB, sz//2+4)
            return
    print('not found',name)
for nm in sys.argv[1:]:
    run(nm)
