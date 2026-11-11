import struct

src = 'clips/t_hevc_4k_fix.mp4'
dst = 'clips/t_hevc_4k_long.mp4'
REP = 12                       # mdat 重复次数 → 6s * 12 = 72s

d = bytearray(open(src, 'rb').read())

MDAT_HDR = 0x28                # mdat box 的 size 字段位置
mdat_type = bytes(d[0x2c:0x30])
print('mdat type:', mdat_type)

moov = d.find(b'moov')
payload = d[0x30:moov]
print('mdat payload: %d 字节 (%.1f 秒)' % (len(payload), len(payload)/1024/1024))

head = d[:0x30]                # ftyp + mdat header
print('原 mdat box size:', struct.unpack_from('>I', d, MDAT_HDR)[0])

# ---- 构造新 mdat ----
new_payload = bytes(payload) * REP
new_mdat_size = 8 + len(new_payload)
new_head = bytearray(head)
struct.pack_into('>I', new_head, MDAT_HDR, new_mdat_size)
print('新 mdat box size: %d (%.1f MB)' % (new_mdat_size, new_mdat_size/1048576))

# ---- 改 moov：mvhd.duration / trak tkhd duration / stts sample count ----
moov_bytes = bytearray(d[moov:])
orig_moov = bytes(moov_bytes)

def find_box(buf, name):
    i = buf.find(name)
    return i - 4 if i >= 0 else -1

# mvhd: version(1)+flags(3) → v0: ctime(4) mtime(4) timescale(4) duration(4)
i = moov_bytes.find(b'mvhd')
base = i + 4
ver = moov_bytes[base]
if ver == 0:
    ts_off = base + 4 + 4 + 4
    dur_off = ts_off + 4
else:
    ts_off = base + 4 + 8 + 8
    dur_off = ts_off + 4
ts = struct.unpack_from('>I', moov_bytes, ts_off)[0]
dur = struct.unpack_from('>I', moov_bytes, dur_off)[0]
print('mvhd: timescale=%d duration=%d → %.1f 秒' % (ts, dur, dur/ts))

new_dur = dur * REP
struct.pack_into('>I', moov_bytes, dur_off, new_dur)
print('mvhd 新 duration=%d → %.1f 秒' % (new_dur, new_dur/ts))

# tkhd（两个 trak 都要改）
for _ in range(2):
    j = moov_bytes.find(b'tkhd')
    if j < 0:
        break
    b = j + 4
    v = moov_bytes[b]
    if v == 0:
        d_off = b + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4   # ctime,mtime,trackID,reserved,dur
    else:
        d_off = b + 4 + 8 + 8 + 4 + 4 + 8
    if d_off + 4 <= len(moov_bytes):
        old = struct.unpack_from('>I', moov_bytes, d_off)[0]
        struct.pack_into('>I', moov_bytes, d_off, old * REP)
        print('tkhd duration: %d → %d' % (old, old * REP))
    moov_bytes = moov_bytes[:j+4] + bytes(moov_bytes[j+4:])   # no-op, keep search pos

# stts: time-to-sample —— sample_count 要同步放大
j = 0
while True:
    k = moov_bytes.find(b'stsz', j)
    if k < 0:
        break
    b = k + 4
    v = moov_bytes[b]
    off = b + 4 + (8 if v == 1 else 4) + 4   # ver/flags, [ctime,mtime], sample_size
    cnt = struct.unpack_from('>I', moov_bytes, off)[0]
    struct.pack_into('>I', moov_bytes, off, cnt * REP)
    print('stsz sample_count: %d → %d' % (cnt, cnt * REP))
    j = k + 4

# stts
j = 0
while True:
    k = moov_bytes.find(b'stts', j)
    if k < 0:
        break
    b = k + 4
    entry_cnt = struct.unpack_from('>I', moov_bytes, b + 4)[0]
    p = b + 8
    for e in range(entry_cnt):
        sc = struct.unpack_from('>I', moov_bytes, p)[0]
        struct.pack_into('>I', moov_bytes, p, sc * REP)
        p += 8
    print('stts: %d 个 entry 的 sample_count 已放大' % entry_cnt)
    j = k + 4

out = bytes(new_head) + new_payload + bytes(moov_bytes)
open(dst, 'wb').write(out)
print()
print('已写出 %s' % dst)
print('大小: %d 字节 (%.1f MB)' % (len(out), len(out)/1048576))
