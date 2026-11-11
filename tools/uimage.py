import struct, zlib, os
d = open(r"E:/A4-work/out/boot2/kernel.bin",'rb').read()
magic, hcrc, ts, size, load, ep, dcrc, osid, arch, typ, comp, name = struct.unpack('>7I4B32s', d[:64])
print(f"magic   = 0x{magic:08x}  (0x27051956 = uImage)")
print(f"hdr_crc = 0x{hcrc:08x}")
print(f"time    = {ts}")
print(f"size    = {size} (0x{size:x})")
print(f"load    = 0x{load:x}")
print(f"entry   = 0x{ep:x}")
print(f"dcrc    = 0x{dcrc:08x}")
print(f"os/arch/type/comp = {osid}/{arch}/{typ}/{comp}  (comp 0=none 1=gzip 2=bzip2 3=lzma 4=lzo)")
print(f"name    = {name.split(b'\0')[0]}")
body = d[64:64+size]
print("body head:", body[:16].hex())
if comp == 1 or body[:2]==b'\x1f\x8b':
    raw = zlib.decompress(body, 16+zlib.MAX_WBITS)
    print("gzip -> ", len(raw), "bytes")
elif comp==0:
    raw = body
else:
    raw = body
open(r"E:/A4-work/out/boot2/kernel.raw",'wb').write(raw)
print("saved kernel.raw", len(raw))
print("raw head:", raw[:32].hex())
# ARM zImage magic check
for off in (0, 0x8000):
    if len(raw)>off+8:
        m = struct.unpack('<I', raw[off+0x24:off+0x28])[0] if len(raw)>off+0x28 else 0
        if raw[off:off+4]==b'\x1f\x8b\x08\x00': print("gzip at", off)
        print(f"@{off:#x}: {raw[off:off+8].hex()}")
