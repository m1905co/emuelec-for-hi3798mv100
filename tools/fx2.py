import struct, sys, re
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

path = sys.argv[1]
targets = set(int(x, 16) for x in sys.argv[2:])
d = open(path, 'rb').read()

e_shoff, = struct.unpack_from('<I', d, 0x20)
e_shentsize, = struct.unpack_from('<H', d, 0x2e)
e_shnum, = struct.unpack_from('<H', d, 0x30)
e_shstrndx, = struct.unpack_from('<H', d, 0x32)
secs = [struct.unpack_from('<10I', d, e_shoff + i * e_shentsize) for i in range(e_shnum)]
sh = secs[e_shstrndx]


def cstr(o):
    e = d.index(b'\0', o)
    return d[o:e].decode('utf-8', 'replace')


def nm(x):
    return cstr(sh[4] + x)


dynstr = None
for sec in secs:
    if nm(sec[0]) == '.dynstr':
        dynstr = sec

funcs = []
for sec in secs:
    if nm(sec[0]) == '.dynsym':
        for i in range(sec[5] // sec[9]):
            o = sec[4] + i * sec[9]
            n, v, sz = struct.unpack_from('<III', d, o)
            if v and sz:
                try:
                    funcs.append((v, sz, cstr(dynstr[4] + n)))
                except Exception:
                    pass
funcs.sort()

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
LDR = re.compile(r'^(\w+),\s*\[pc,\s*#?(0x[0-9a-f]+|[0-9]+)\]')
ADD2 = re.compile(r'^(\w+),\s*pc$')
ADD3 = re.compile(r'^(\w+),\s*(\w+),\s*pc$')
WR1 = re.compile(r'^(\w+),')
KEEP = ('str', 'strb', 'strh', 'cmp', 'stm', 'push', 'nop')

res = []
for fv, fsz, fname in funcs:
    start = fv & ~1
    ins = list(md.disasm(d[start:start + fsz], start))
    cur = {}
    for i in ins:
        m = i.mnemonic
        ops = i.op_str
        if m == 'ldr':
            g = LDR.match(ops)
            if g:
                pv = ((i.address + 4) & ~3) + int(g.group(2), 0)
                if pv + 4 <= len(d):
                    cur[g.group(1)] = ('pool', pv)
                else:
                    cur.pop(g.group(1), None)
                continue
        if m == 'add':
            g2 = ADD2.match(ops)
            g3 = ADD3.match(ops)
            if g2:
                dst = src = g2.group(1)
            elif g3:
                dst, src = g3.group(1), g3.group(2)
            else:
                w = WR1.match(ops)
                if w:
                    cur.pop(w.group(1), None)
                continue
            if src in cur and cur[src][0] == 'pool':
                val = struct.unpack_from('<i', d, cur[src][1])[0]
                cur[dst] = ('abs', (i.address + 4 + val) & 0xFFFFFFFF)
                for r, info in cur.items():
                    if info[0] == 'abs' and info[1] in targets:
                        res.append((i.address, m, ops, info[1], r, fname))
            else:
                cur.pop(dst, None)
            continue
        if m in ('pop', 'ldm') and 'pc' in ops:
            cur.clear()
            continue
        w = WR1.match(ops)
        if w and m not in KEEP:
            cur.pop(w.group(1), None)
        for r, info in cur.items():
            if info[0] == 'abs' and info[1] in targets:
                res.append((i.address, m, ops, info[1], r, fname))

seen = set()
for a, m, o, v, r, f in res:
    if (a, v) in seen:
        continue
    seen.add((a, v))
    print('%08x %-6s %-26s => %08x via %-4s  in %s()' % (a, m, o, v, r, f))