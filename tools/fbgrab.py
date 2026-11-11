#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Grab the EmuELEC framebuffer over telnet and save it as a PNG.

usage: fbgrab.py <out.png> [host] [port]
"""
import socket
import struct
import sys
import time
import zlib

OUT = sys.argv[1] if len(sys.argv) > 1 else 'fb.png'
HOST = sys.argv[2] if len(sys.argv) > 2 else '192.168.31.17'
PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 23

CHUNK = 16000          # raw bytes per transfer
RAW_SIZE = 1920 * 2160 * 4


def connect():
    s = socket.create_connection((HOST, PORT), timeout=10)
    s.settimeout(0.8)
    time.sleep(1.0)

    def drain():
        out = b''
        while True:
            try:
                d = s.recv(65536)
                if not d:
                    break
                out += d
            except socket.timeout:
                break
            except OSError:
                break
        return out

    drain()
    s.sendall(b'root\n')
    time.sleep(1.2)
    o = drain()
    if b'assword' in o:
        s.sendall(b'emuelec\n')
        time.sleep(1.5)
        drain()
    return s


def run(s, cmd, wait=1.0):
    s.sendall(cmd.encode() + b'\n')
    time.sleep(wait)
    out = b''
    while True:
        try:
            d = s.recv(65536)
            if not d:
                break
            out += d
        except socket.timeout:
            break
        except OSError:
            break
    # strip IAC
    clean = bytearray()
    i = 0
    while i < len(out):
        if out[i] == 255 and i + 2 < len(out):
            i += 3
            continue
        clean.append(out[i])
        i += 1
    return bytes(clean).decode('latin1', 'replace')


def write_png(path, w, h, rgb):
    """rgb: bytes of w*h*3"""
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]
    comp = zlib.compress(bytes(raw), 6)

    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)

    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(chunk(b'IHDR', ihdr))
        f.write(chunk(b'IDAT', comp))
        f.write(chunk(b'IEND', b''))


s = connect()
print(run(s, 'dd if=/dev/fb0 bs=1048576 count=16 2>/dev/null | gzip -9 > /tmp/shot.gz; '
              'ls -l /tmp/shot.gz', 4.0))

data = bytearray()
n = 0
import base64 as b64mod
while n * CHUNK < RAW_SIZE:
    cmd = ('dd if=/dev/fb0 bs=%d skip=%d count=1 2>/dev/null | gzip -9 -c > /tmp/c.gz; '
           'echo "@@B@@"; base64 /tmp/c.gz | tr -d "\\n"; echo "@@E@@"' % (CHUNK, n))
    txt = run(s, cmd, 1.6)
    p1 = txt.rfind('@@B@@')
    p2 = txt.rfind('@@E@@')
    if p1 < 0 or p2 <= p1:
        print('chunk %d: markers missing (p1=%d p2=%d)' % (n, p1, p2))
        break
    body = txt[p1 + 5:p2]
    b64 = ''.join(ch for ch in body if ch in
                  'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')
    try:
        got = b64mod.b64decode(b64, validate=False)
        plain = zlib.decompress(got, 16 + zlib.MAX_WBITS)
    except Exception as e:
        print('chunk %d: decode fail %s (b64len=%d)' % (n, e, len(b64)))
        break
    data += plain
    print('chunk %d: +%d bytes (total %d)' % (n, len(plain), len(data)))
    n += 1

run(s, 'exit', 0.3)
s.close()

if not data:
    print('no data')
    sys.exit(1)

# 假設 BGRA 排列（Hi3798 ARGB8888 小端），取前半屏（可能是当前帧）
W, H = 1920, 1080
for name, order in (('bgra', (2, 1, 0)), ('rgba', (0, 1, 2))):
    for half in (0, 1):
        base = half * W * H * 4
        if base + W * H * 4 > len(data):
            continue
        rgb = bytearray(W * H * 3)
        src = data[base:base + W * H * 4]
        for idx in range(W * H):
            p = idx * 4
            q = idx * 3
            rgb[q] = src[p + order[0]]
            rgb[q + 1] = src[p + order[1]]
            rgb[q + 2] = src[p + order[2]]
        path = OUT.replace('.png', '_%s_%d.png' % (name, half))
        write_png(path, W, H, bytes(rgb))
        print('wrote', path)
