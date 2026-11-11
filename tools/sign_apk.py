#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 APK 签名（AOSP testkey），逻辑与 repack.py 完全一致（已验证可被recovery 接受）。"""
import sys, zipfile, hashlib, base64, os, re

SRC = sys.argv[1]
DST = sys.argv[2]
KEY_PK8 = 'keys/testkey.pk8'
KEY_PEM = 'keys/testkey.x509.pem'
MANIFEST = 'META-INF/MANIFEST.MF'
CERT_SF = 'META-INF/CERT.SF'
CERT_RSA = 'META-INF/CERT.RSA'


def b64(x):
    return base64.b64encode(x).decode()


def main():
    from cryptography.hazmat.primitives.serialization import pkcs7, Encoding, load_der_private_key
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes

    zin = zipfile.ZipFile(SRC, 'r')
    names = [n for n in zin.namelist()
             if n not in (MANIFEST, CERT_SF, CERT_RSA)]
    print('entries to sign: %d' % len(names))

    # ---- MANIFEST.MF（与原签名者约定一致：每节尾部两个 CRLF）----
    mf_header = b'Manifest-Version: 1.0\r\nCreated-By: 1.0 (Android)\r\n\r\n'
    out_mf = bytearray(mf_header)
    for n in names:
        data = zin.read(n)
        out_mf += b'Name: ' + n.encode('utf-8') + b'\r\n'
        out_mf += b'SHA1-Digest: ' + b64(hashlib.sha1(data).digest()).encode() + b'\r\n'
        out_mf += b'\r\n\r\n'
    out_mf = bytes(out_mf)

    # ---- CERT.SF ----
    sf_header = (b'Signature-Version: 1.0\r\n'
                 b'SHA1-Digest-Manifest: ' + b64(hashlib.sha1(out_mf).digest()).encode() + b'\r\n'
                 b'Created-By: 1.0 (Android SignApk)\r\n\r\n')
    out_sf = bytearray(sf_header)
    hdr_end = out_mf.index(b'\r\n\r\n') + 4
    body = out_mf[hdr_end:]
    pos = 0
    cnt = 0
    while pos < len(body):
        idx = body.find(b'\r\n\r\n\r\n', pos)
        if idx < 0:
            if body[pos:].strip():
                sec = body[pos:]
            else:
                break
        else:
            sec = body[pos:idx + 6]
        nm = re.search(rb'Name: (.*?)\r\n', sec).group(1)
        out_sf += b'Name: ' + nm + b'\r\n'
        out_sf += b'SHA1-Digest: ' + b64(hashlib.sha1(sec).digest()).encode() + b'\r\n'
        out_sf += b'\r\n'
        cnt += 1
        if idx < 0:
            break
        pos = idx + 6
    out_sf = bytes(out_sf)
    print('CERT.SF sections: %d' % cnt)

    # ---- CERT.RSA：复用 update.zip（原厂包）里的 CERT.RSA 结构，只换签名字节 ----
    # 该结构已被 recovery 验证可接受（repack.py 产出过），比从零构造可靠。
    from cryptography.hazmat.primitives.asymmetric import padding as _pad
    from asn1crypto import cms as _cms
    from asn1crypto import x509 as _x509

    key = load_der_private_key(open(KEY_PK8, 'rb').read(), password=None)
    cert = x509.load_pem_x509_certificate(open(KEY_PEM, 'rb').read())
    sig = key.sign(out_sf, _pad.PKCS1v15(), hashes.SHA1())

    # 从原厂固件取 CMS 骨架
    with zipfile.ZipFile('update.zip', 'r') as zf:
        orig_cms = _cms.ContentInfo.load(zf.read(CERT_RSA))
    si = orig_cms['content']['signer_infos'][0]
    print('    骨架 signer: digest_alg=%s sid=%s' % (
        si['digest_algorithm']['algorithm'].native, si['sid'].name))
    si['signature'] = sig
    rsa = orig_cms.dump()
    print('CERT.RSA: %d bytes (骨架来自 update.zip)' % len(rsa))

    zo = zipfile.ZipFile(DST, 'w', zipfile.ZIP_DEFLATED)
    for it in zin.infolist():
        if it.filename in (MANIFEST, CERT_SF, CERT_RSA):
            continue
        zo.writestr(it, zin.read(it.filename))
    zo.writestr(MANIFEST, out_mf)
    zo.writestr(CERT_SF, out_sf)
    zo.writestr(CERT_RSA, rsa)
    zo.close()
    zin.close()
    print('signed -> %s (%d bytes)' % (DST, os.path.getsize(DST)))


if __name__ == '__main__':
    main()