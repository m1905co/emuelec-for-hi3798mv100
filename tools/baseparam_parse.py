import sys, re

path = sys.argv[1] if len(sys.argv)>1 else r'E:/A4-work/out/baseparam_device.bak'
d = open(path,'rb').read()

# Structure discovery (from hexdump):
# file header:  '###\0' (4) + total_len? (4)  -> 0x15c0 = 5568 for first block maybe
# then table block: 32-byte table name + 4-byte count/size + ... 
# Entries: 32-byte key + uint32 size + size-byte value (aligned to 4) 

# Let's scan linearly for 32-byte-ish key names starting with 'BASE_'
KEYS = re.compile(rb'BASE_[A-Z0-9_]+')
i = 0
entries = []
# We consider an entry valid if: key at off, key NUL padded to 32; then uint32 size;
# then size bytes value. Try to walk.

def walk(start, end):
    res = []
    p = start
    while p + 36 <= end:
        # key name: printable up to NUL within 32
        chunk = d[p:p+32]
        nul = chunk.find(b'\0')
        if nul <= 0:
            break
        name = chunk[:nul]
        if not name.startswith(b'BASE_'):
            break
        # ensure rest of 32 bytes are NUL
        if chunk[nul:].strip(b'\0') != b'':
            break
        size = int.from_bytes(d[p+32:p+36],'little')
        if size > 4096:
            break
        value = d[p+36:p+36+size]
        res.append((p, name.decode(), size, value))
        step = 36 + ((size+3)//4)*4
        p += step
    return res, p

# find first key
start = d.find(b'BASE_KEY')
res, endp = walk(start, len(d))
print(f"walked {len(res)} entries from {start:#x} to {endp:#x}")
for off, name, size, val in res:
    if size == 4:
        v = int.from_bytes(val,'little')
        print(f"  {off:#08x} {name:34s} size={size} val={v} (0x{v:x})")
    else:
        print(f"  {off:#08x} {name:34s} size={size} val={val[:32].hex()}")
