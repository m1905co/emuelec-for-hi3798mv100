#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rebuild update.zip with patched files and re-sign using the AOSP testkey,
reproducing EXACTLY the JAR signing convention of the original package.

Verified rules (reverse-engineered from the original update.zip):
  MANIFEST.MF : "Manifest-Version: 1.0\r\nCreated-By: 1.0 (...)\r\n\r\n"
                then per entry:  "Name: <n>\r\nSHA1-Digest: <b64 sha1(file)>\r\n\r\n\r\n"
                (note: TWO blank lines between sections)
  CERT.SF     : "Signature-Version: 1.0\r\nSHA1-Digest-Manifest: <b64 sha1(MANIFEST.MF)>\r\n
                Created-By: 1.0 (Android SignApk)\r\n\r\n"
                then per entry:  "Name: <n>\r\nSHA1-Digest: <b64 sha1(manifest section incl. trailing \r\n\r\n)>\r\n\r\n"
                (ONE blank line between sections)
  CERT.RSA    : PKCS#7 detached signature over CERT.SF bytes
"""
import zipfile, hashlib, base64, os, sys, re, shutil

ORIG = 'update.zip'
OUT  = 'update_v2_fixed.zip'
MANIFEST = 'META-INF/MANIFEST.MF'
CERT_SF  = 'META-INF/CERT.SF'
CERT_RSA = 'META-INF/CERT.RSA'

# files to replace: {zip entry name: local path}
PATCH = {
    'baseparam.img'                : 'out/baseparam_fw.img',
    'system/etc/media_codecs.xml'  : 'fw/system/etc/media_codecs.xml',
    'system/bin/wifi_recover.sh'   : 'fw/system/bin/wifi_recover.sh',
}
KEY_PK8 = 'keys/testkey.pk8'
KEY_PEM = 'keys/testkey.x509.pem'

def b64(x): return base64.b64encode(x).decode()

def parse_manifest_order(mf: bytes):
    """Return (header_bytes, [entry names in order]) from an existing MANIFEST.MF."""
    hdr_end = mf.index(b'\r\n\r\n') + 4
    header = mf[:hdr_end]
    body = mf[hdr_end:]
    names = [m.group(1).decode('utf-8')
             for m in re.finditer(rb'Name: (.*?)\r\n', body)]
    return header, names

def main():
    from cryptography.hazmat.primitives.serialization import pkcs7, Encoding
    from cryptography.hazmat.primitives.serialization import load_der_private_key
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    import datetime

    zin = zipfile.ZipFile(ORIG, 'r')
    orig_mf = zin.read(MANIFEST)
    mf_header, names = parse_manifest_order(orig_mf)
    print('original manifest entries: %d' % len(names))

    # sanity: the set of manifest names must equal the set of zip entries minus the 3 sig files
    zip_names = [n for n in zin.namelist()
                 if n not in (MANIFEST, CERT_SF, CERT_RSA)]
    missing = set(zip_names) - set(names)
    extra = set(names) - set(zip_names)
    print('in zip but not in manifest: %d' % len(missing))
    if missing: print('  e.g.', list(missing)[:5])
    print('in manifest but not in zip: %d' % len(extra))
    if extra: print('  e.g.', list(extra)[:5])
    if missing:
        sys.exit('ABORT: manifest/zip entry mismatch')

    # ---- build new MANIFEST.MF ----
    out_mf = bytearray(mf_header)
    for n in names:
        if n in PATCH:
            data = open(PATCH[n], 'rb').read()
            print('  [patched] %-34s %8d bytes' % (n, len(data)))
        else:
            data = zin.read(n)
        out_mf += b'Name: ' + n.encode('utf-8') + b'\r\n'
        out_mf += b'SHA1-Digest: ' + b64(hashlib.sha1(data).digest()).encode() + b'\r\n'
        out_mf += b'\r\n\r\n'
    out_mf = bytes(out_mf)

    # ---- build new CERT.SF ----
    sf_header = (b'Signature-Version: 1.0\r\n'
                 b'SHA1-Digest-Manifest: ' + b64(hashlib.sha1(out_mf).digest()).encode() + b'\r\n'
                 b'Created-By: 1.0 (Android SignApk)\r\n\r\n')
    out_sf = bytearray(sf_header)
    # re-walk the manifest we just wrote, digesting each section exactly as the original signer did
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
    print('new CERT.SF sections: %d (manifest entries %d)' % (cnt, len(names)))

    # ---- sign CERT.SF -> CERT.RSA (PKCS#7 detached) ----
    key = load_der_private_key(open(KEY_PK8, 'rb').read(), password=None)
    cert = x509.load_pem_x509_certificate(open(KEY_PEM, 'rb').read())
    # Match the original signer exactly: plain detached RSA/SHA-1 signature over the
    # CERT.SF bytes, with NO signed attributes. (The original package's CERT.RSA is
    # also a signed_data with digest_algorithm=sha1 and no signed_attrs.)
    from cryptography.hazmat.primitives.asymmetric import padding
    sig = key.sign(out_sf, padding.PKCS1v15(), hashes.SHA1())

    from asn1crypto import cms as _cms
    sig = key.sign(out_sf, padding.PKCS1v15(), hashes.SHA1())
    # Reuse the ORIGINAL package's CMS structure verbatim and only swap the
    # signature bytes. This guarantees byte-for-byte format compatibility with
    # whatever the original signer (and therefore the device's recovery) expects.
    orig_cms = _cms.ContentInfo.load(zin.read(CERT_RSA))
    si = orig_cms['content']['signer_infos'][0]
    print('    original signer: digest_alg=%s sid=%s' % (
        si['digest_algorithm']['algorithm'].native, si['sid'].name))
    si['signature'] = sig
    rsa = orig_cms.dump()
    print('CERT.RSA built: %d bytes (structure copied from original, RSA/SHA1)' % len(rsa))

    # self-check: verify the cert in our CERT.RSA matches the original package's
    orig_certs = pkcs7.load_der_pkcs7_certificates(zin.read(CERT_RSA))
    same = orig_certs[0].public_bytes(Encoding.DER) == cert.public_bytes(Encoding.DER)
    print('certificate identical to original package: %s' % same)
    if not same:
        sys.exit('ABORT: certificate mismatch with original package')

    # ---- write the new zip, preserving entry order & compression ----
    if os.path.exists(OUT):
        os.remove(OUT)
    zout = zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED)

    # 签名文件必须保持在原包中的**原始位置**（顺序敏感），
    # 且必须用 DEFLATE 压缩（与原厂一致）——
    # 若用 ZipInfo() 的默认 STORED，部分 recovery 的 JarVerifier 会判签名损坏。
    sigdata = {MANIFEST: out_mf, CERT_SF: out_sf, CERT_RSA: rsa}
    orig_order = [i.filename for i in zin.infolist()]

    for info in zin.infolist():
        fn = info.filename
        if fn in sigdata:
            data = sigdata[fn]
            ni = zipfile.ZipInfo(fn, date_time=info.date_time)
            # ★ 关键：显式设为 DEFLATE，绝不能留 STORED
            ni.compress_type = zipfile.ZIP_DEFLATED
            ni.external_attr = info.external_attr
            ni.create_system = info.create_system
            zout.writestr(ni, data)
            continue
        if fn in PATCH:
            data = open(PATCH[fn], 'rb').read()
        else:
            data = zin.read(fn)
        ni = zipfile.ZipInfo(fn, date_time=info.date_time)
        ni.compress_type = info.compress_type
        ni.external_attr = info.external_attr
        ni.create_system = info.create_system
        zout.writestr(ni, data)
    zout.close()
    zin.close()
    print('wrote %s (%.1f MB)' % (OUT, os.path.getsize(OUT) / 1048576.0))

    # ---- 自检：签名文件压缩方式与条目顺序 ----
    zc = zipfile.ZipFile(OUT)
    names = zc.namelist()
    assert names == orig_order, 'entry order changed!'
    for s in (MANIFEST, CERT_SF, CERT_RSA):
        ct = zc.getinfo(s).compress_type
        assert ct == zipfile.ZIP_DEFLATED, '%s compress_type=%d (must be 8/DEFLATE)' % (s, ct)
        print('  [ok] %-26s compress_type=%d size=%d' % (s, ct, zc.getinfo(s).file_size))
    print('  [ok] entry order identical to original (%d entries)' % len(names))

if __name__ == '__main__':
    main()
