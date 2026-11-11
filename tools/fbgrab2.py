#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Grab the EmuELEC framebuffer over telnet and save it as PNG.

Device side: dump fb0 -> gzip -> base64 text file.
Host side : pull that text file in slices, decode, convert to PNG.

usage: fbgrab2.py <out.png> [host] [port]
"""
import base64
import socket
import struct
import sys
import time
import zlib

OUT = sys.argv[1] if len(sys.argv) > 1 else 'fb.png'
HOST = sys.argv[2] if len(sys.argv) > 2 else '192.168.31.17'
PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 23

SLICE = 18000          # base64 text bytes per transfer


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
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]
    comp = zlib.compress(bytes(raw), 6)

    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data +
                struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))

    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)))
        f.write(chunk(b'IDAT', comp))
        f.write(chunk(b'IEND', b''))


s = connect()
print(run(s, 'dd if=/dev/fb0 bs=1048576 count=16 2>/dev/null | gzip -9 '
             '> /tmp/shot.gz; base64 /tmp/shot.gz > /tmp/shot.b64; '
             'ls -l /tmp/shot.gz /tmp/shot.b64', 8.0))

size = 0
for line in run(s, 'wc -c < /tmp/shot.b64', 1.5).splitlines():
    line = line.strip()
    if line.isdigit():
        size = int(line)
print('b64 size =', size)
if size <= 0:
    print('cannot stat b64 file')
    sys.exit(1)

parts = []
n = 0
while n * SLICE < size:
    cmd = ('echo "@@B@@"; dd if=/tmp/shot.b64 bs=%d skip=%d count=1 2>/dev/null; '
           'echo; echo "@@E@@"' % (SLICE, n))
    txt = run(s, cmd, 1.2)
    p1 = txt.rfind('@@B@@')
    p2 = txt.rfind('@@E@@')
    if p1 < 0 or p2 <= p1:
        print('slice %d: markers missing' % n)
        break
    body = txt[p1 + 5:p2]
    body = ''.join(ch for ch in body
                   if ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')
    parts.append(body)
    print('slice %d: %d chars' % (n, len(body)))
    n += 1

run(s, 'exit', 0.3)
s.close()

b64all = ''.join(parts)
print('total b64 chars', len(b64all))
raw = base64.b64decode(b64all, validate=False)
plain = zlib.decompress(raw, 16 + zlib.MAX_WBITS)
print('framebuffer bytes', len(plain))

W, H = 1920, 1080
for name, order in (('bgra', (2, 1, 0)), ('rgba', (0, 1, 2))):
    for half in (0, 1):
        base = half * W * H * 4
        if base + W * H * 4 > len(plain):
            continue
        rgb = bytearray(W * H * 3)
        src = plain[base:base + W * H * 4]
        for idx in range(W * H):
            p = idx * 4
            q = idx * 3
            rgb[q] = src[p + order[0]]
            rgb[q + 1] = src[p + order[1]]
            rgb[q + 2] = src[p + order[2]]
        path = OUT.replace('.png', '_%s_%d.png' % (name, half))
        write_png(path, W, H, bytes(rgb))
        print('wrote', path)
