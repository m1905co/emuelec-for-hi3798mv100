#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify an AOSP recovery update package produced by `signapk -w`.

Conclusive checks:
  1) whole-file signature: RSA/SHA1 over raw[0 : eocd+20)  <- what the HiSi recovery checks
  2) JAR signature: every MANIFEST.MF entry digest matches the real file,
     SHA1-Digest-Manifest matches, CERT.RSA verifies over CERT.SF
  3) payload diff vs the original package
"""
import zipfile, hashlib, base64, re, struct, sys, os
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from asn1crypto import cms

ORIG = 'update.zip'
MANIFEST = 'META-INF/MANIFEST.MF'
CERT_SF = 'META-INF/CERT.SF'
CERT_RSA = 'META-INF/CERT.RSA'
HASHES = {'sha1': hashes.SHA1(), 'sha256': hashes.SHA256(),
          'sha384': hashes.SHA384(), 'sha512': hashes.SHA512()}


def b64(x):
    return base64.b64encode(x).decode()


def unfold(x):
    """JAR manifests wrap long lines at 72 chars with a leading-space continuation."""
    return x.replace(b'\r\n ', b'')


def whole_file(path):
    raw = open(path, 'rb').read()
    eocd = raw.rindex(b'PK\x05\x06')
    clen = struct.unpack_from('<H', raw, eocd + 20)[0]
    print('=== [1] whole-file signature (signapk -w) ===')
    if clen == 0:
        print('  comment_len=0 -> NO whole-file signature  [FAIL]')
        return False
    c = raw[eocd + 22:]
    nul = c.index(b'\x00')
    print('  comment_len = %d ; signer name = %r ; ends at EOF = %s'
          % (clen, c[:nul].decode('latin1'), eocd + 22 + clen == len(raw)))
    der = c[nul + 1:]
    ci = cms.ContentInfo.load(der)
    full = ci.dump()
    si = ci['content']['signer_infos'][0]
    alg = si['digest_algorithm']['algorithm'].native
    cert = pkcs7.load_der_pkcs7_certificates(der)[0]
    print('  PKCS7 = %d bytes ; trailer = %s' % (len(full), der[len(full):].hex(' ')))
    print('  signer cert serial = %s ; digest = %s' % (hex(cert.serial_number), alg))
    signed = raw[:eocd + 20]
    try:
        cert.public_key().verify(si['signature'].native, signed,
                                 padding.PKCS1v15(), HASHES[alg])
        print('  RSA over raw[0:%d] -> OK  (%d bytes)' % (eocd + 20, len(signed)))
        return True
    except Exception as e:
        print('  RSA verify FAILED: %s' % e)
        return False


def jar(path):
    print()
    print('=== [2] JAR signature ===')
    z = zipfile.ZipFile(path)
    names = set(z.namelist())
    mf = z.read(MANIFEST)
    sf = z.read(CERT_SF)
    rsa = z.read(CERT_RSA)
    mf_p = unfold(mf)
    sf_p = unfold(sf)
    body = mf_p[mf_p.index(b'\r\n\r\n') + 4:]
    entries = []
    for blk in body.split(b'\r\n\r\n'):
        m = re.match(rb'Name: (.*)\r\nSHA1-Digest: (.*)', blk.strip(b'\r\n'))
        if m:
            entries.append((m.group(1).decode(), m.group(2).decode()))
    bad = 0
    for n, d in entries:
        if n not in names:
            print('  MISSING in zip: %s' % n)
            bad += 1
            continue
        if b64(hashlib.sha1(z.read(n)).digest()) != d:
            print('  DIGEST MISMATCH: %s' % n)
            bad += 1
    print('  manifest entries verified : %d  failures=%d' % (len(entries), bad))
    m = re.search(rb'SHA1-Digest-Manifest: (.*?)\r\n', sf_p).group(1).decode()
    ok_m = (m == b64(hashlib.sha1(mf).digest()))   # digest over the RAW (folded) manifest
    print('  SHA1-Digest-Manifest      : %s' % ('OK' if ok_m else 'MISMATCH'))
    ci = cms.ContentInfo.load(rsa)
    si = ci['content']['signer_infos'][0]
    cert = pkcs7.load_der_pkcs7_certificates(rsa)[0]
    alg = si['digest_algorithm']['algorithm'].native
    try:
        cert.public_key().verify(si['signature'].native, sf,
                                 padding.PKCS1v15(), HASHES[alg])
        ok_r = True
    except Exception:
        ok_r = False
    print('  CERT.RSA over CERT.SF     : %s (%s, cert serial %s)'
          % ('OK' if ok_r else 'FAIL', alg, hex(cert.serial_number)))
    return bad == 0 and ok_m and ok_r


def diff(path):
    print()
    print('=== [3] payload diff vs original ===')
    a = zipfile.ZipFile(ORIG)
    b = zipfile.ZipFile(path)
    na = list(a.namelist())
    nb = list(b.namelist())
    print('  entries: %d -> %d ; order preserved: %s ; testzip=%s'
          % (len(na), len(nb), na == nb, b.testzip()))
    ch = [n for n in na if not n.startswith('META-INF/') and n in set(nb)
          and hashlib.sha1(a.read(n)).digest() != hashlib.sha1(b.read(n)).digest()]
    print('  changed payload files (%d): %s' % (len(ch), ch))
    miss = [n for n in na if n not in set(nb)]
    print('  missing vs original: %s' % (miss if miss else 'none'))
    return ch


if __name__ == '__main__':
    p = sys.argv[1] if len(sys.argv) > 1 else 'update_signed.zip'
    print('### verifying %s (%.1f MB) ###' % (p, os.path.getsize(p) / 1048576.0))
    a = whole_file(p)
    b = jar(p)
    diff(p)
    print()
    print('RESULT:', 'ALL CHECKS PASSED' if (a and b) else 'FAILED')