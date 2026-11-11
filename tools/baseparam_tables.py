import sys
path = sys.argv[1] if len(sys.argv)>1 else r'E:/A4-work/out/baseparam_device.bak'
d = open(path,'rb').read()

def dump_table(start):
    p = start
    out = []
    while p+40 <= len(d):
        key = d[p:p+32].split(b'\0')[0]
        if not key.startswith(b'BASE_'):
            break
        sz = int.from_bytes(d[p+32:p+36],'little')
        val = d[p+36:p+40]
        out.append((p, key.decode(), sz, val))
        p += 40
    return out, p

# Find all BASE_TABLE_ markers
import re
tables = [(m.start(), m.group().decode()) for m in re.finditer(rb'BASE_TABLE_[A-Z0-9_]+', d)]
print("=== BASE_TABLE markers ===")
for off,name in tables:
    print(f'  {off:#08x} {name}')
print()

for toff, tname in tables:
    # entry area starts after table name (32 bytes) + 4 byte size + ... from hexdump:
    # table marker at 0x4 (name 'BASE_TABLE_DISP0' padded to 32) -> 0x24, then 4 bytes 0xf807? 
    # Actually 0x04+32=0x24 -> 'f8 07 00 00' at 0x24..0x27, then key at 0x28? but we found key at 0x2c
    # Let's locate first BASE_KEY after this table marker
    p = toff
    while p < len(d):
        nxt = d.find(b'BASE_KEY', p)
        if nxt < 0: break
        # make sure not part of table/other
        # stop if we hit another table marker before next key
        nt = d.find(b'BASE_TABLE_', p+1)
        if nt >=0 and nt < nxt: break
        break
    if nxt < 0: continue
    # header bytes between
    hdr = d[toff+32:nxt]
    entries, endp = dump_table(nxt)
    print(f'=== {tname} @ {toff:#x}  (entry start {nxt:#x}, {len(entries)} entries, end {endp:#x}) ===')
    print(f'    hdr bytes: {hdr.hex()}')
    for off,key,sz,val in entries:
        if sz==4:
            print(f'    {off:#08x} {key:34s} u32={int.from_bytes(val,"little"):<12d} hex={val.hex()}')
        else:
            print(f'    {off:#08x} {key:34s} sz={sz} data={val.hex()}')
    print()
