import struct, hashlib, zlib, os

path = r"E:/A4-work/fw/boot.img"
d = open(path,'rb').read()
print("file size", len(d))
assert d[:8]==b'ANDROID!'
K,KA,R,RA,S,SA,T,PG,HV,OSV = struct.unpack('<10I', d[8:48])
name = d[48:64].split(b'\0')[0]
cmd  = d[64:64+512].split(b'\0')[0]
print(f"kernel_size  = {K} (0x{K:x})")
print(f"kernel_addr  = 0x{KA:x}")
print(f"ramdisk_size = {R} (0x{R:x})")
print(f"ramdisk_addr = 0x{RA:x}")
print(f"second_size  = {S} (0x{S:x})")
print(f"second_addr  = 0x{SA:x}")
print(f"tags_addr    = 0x{T:x}")
print(f"page_size    = {PG}")
print(f"hdr_version  = {HV}")
print(f"os_version   = {OSV}")
print(f"product_name = {name}")
cmds = d[64:64+512]
print(f"cmdline      = {cmds.split(b'\0')[0].decode('latin1')}")
# extra fields offset 576: id(32) 608: extra_cmdline(1024)
print(f"id           = {d[576:576+32].hex()}")
extra = d[608:608+1024].split(b'\0')[0]
print(f"extra_cmdline= {extra.decode('latin1')}")

def pages(n): return (n + PG - 1)//PG
off = PG
kdata = d[off:off+K]; off += pages(K)*PG
rdata = d[off:off+R]; off += pages(R)*PG
sdata = d[off:off+S]; off += pages(S)*PG
print(f"\nkernel  first bytes: {kdata[:32].hex()}")
print(f"ramdisk first bytes: {rdata[:32].hex()}")
# try gunzip ramdisk
for nm,blob in (("kernel",kdata),("ramdisk",rdata),("second",sdata)):
    if not blob: continue
    for tag,fn in ((b'\x1f\x8b',zlib.decompress),):
        if blob[:2]==tag:
            try:
                out = zlib.decompress(blob, 16+zlib.MAX_WBITS)
                print(f"{nm}: gzip decompressed -> {len(out)} bytes")
            except Exception as e:
                print(f"{nm}: gzip fail {e}")
os.makedirs(r"E:/A4-work/out/boot2", exist_ok=True)
open(r"E:/A4-work/out/boot2/kernel.bin",'wb').write(kdata)
open(r"E:/A4-work/out/boot2/ramdisk.bin",'wb').write(rdata)
open(r"E:/A4-work/out/boot2/second.bin",'wb').write(sdata)
print("saved to out/boot2/")
