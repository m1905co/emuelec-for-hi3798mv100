#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Surgical repack: copy every entry of the original zip RAW (local header + compressed
bytes verbatim, central-directory fields byte-identical, only the local-header offset
is re-pointed), and only rewrite the entries we actually changed + the 3 signature files.

This removes any suspicion that re-compressing / re-writing the whole archive broke
something for the recovery updater.
"""
import zipfile, hashlib, base64, os, sys, re, struct

ORIG = 'update.zip'
OUT  = 'update_fixed2.zip'
MANIFEST='META-INF/MANIFEST.MF'; CERT_SF='META-INF/CERT.SF'; CERT_RSA='META-INF/CERT.RSA'
PATCH = {
    'baseparam.img'               : 'out/baseparam_fw.img',
    'system/etc/media_codecs.xml' : 'fw/system/etc/media_codecs.xml',
    'system/bin/wifi_recover.sh'  : 'fw/system/bin/wifi_recover.sh',
}
MODE = 'full'
NO_SIG = False
if len(sys.argv) > 1:
    MODE = sys.argv[1]
if MODE == 'resign_only':
    PATCH = {}
elif MODE == 'baseparam_only':
    PATCH = {'baseparam.img': 'out/baseparam_fw.img'}
elif MODE == 'unsigned_full':
    # keep the full PATCH set but emit NO signature files at all:
    # the result must be signed afterwards by AOSP signapk -w (whole-file signature)
    NO_SIG = True
elif MODE == 'sysfiles_only':
    PATCH = {
        'system/etc/media_codecs.xml': 'fw/system/etc/media_codecs.xml',
        'system/bin/wifi_recover.sh' : 'fw/system/bin/wifi_recover.sh',
    }
if len(sys.argv) > 2:
    OUT = sys.argv[2]
KEY_PK8='keys/testkey.pk8'; KEY_PEM='keys/testkey.x509.pem'

def b64(x): return base64.b64encode(x).decode()

# ---------- locate EOCD / central directory ----------
def find_eocd(raw):
    for i in range(len(raw)-22, max(0, len(raw)-66000), -1):
        if raw[i:i+4]==b'PK\x05\x06':
            return i
    raise SystemExit('EOCD not found')

def parse_cd(raw, cd_off, cd_size):
    entries=[]
    p=cd_off
    end=cd_off+cd_size
    while p < end and raw[p:p+4]==b'PK\x01\x02':
        (ver_made, ver_need, flags, method, mtime, mdate, crc, csize, usize,
         fnlen, exlen, cmlen, disk, iattr, eattr, lho) = struct.unpack_from('<HHHHHHIIIHHHHHII', raw, p+4)
        name=raw[p+46:p+46+fnlen]
        extra=raw[p+46+fnlen:p+46+fnlen+exlen]
        cmt=raw[p+46+fnlen+exlen:p+46+fnlen+exlen+cmlen]
        entries.append(dict(raw=raw[p:p+46+fnlen+exlen+cmlen], name=name.decode(),
                            lho=lho, method=method, crc=crc, csize=csize, usize=usize,
                            flags=flags, mtime=mtime, mdate=mdate, fnlen=fnlen,
                            ver_made=ver_made, ver_need=ver_need))
        p += 46+fnlen+exlen+cmlen
    return entries

def local_raw(raw, lho):
    """return (local_header_bytes, compressed_data_bytes) verbatim"""
    assert raw[lho:lho+4]==b'PK\x03\x04', 'bad local header'
    fnlen, exlen = struct.unpack_from('<HH', raw, lho+26)
    start = lho+30+fnlen+exlen
    return raw[lho:start], raw[start:start+struct.unpack_from('<I', raw, lho+18)[0]]

def build_manifest(entries, orig_zip):
    raw=orig_zip.read(MANIFEST)
    hdr_end=raw.index(b'\r\n\r\n')+4
    mf_header=raw[:hdr_end]
    names=[m.group(1).decode() for m in re.finditer(rb'Name: (.*?)\r\n', raw[hdr_end:])]
    out=bytearray(mf_header)
    for n in names:
        data=open(PATCH[n],'rb').read() if n in PATCH else orig_zip.read(n)
        out += b'Name: '+n.encode()+b'\r\n'
        out += b'SHA1-Digest: '+b64(hashlib.sha1(data).digest()).encode()+b'\r\n'
        out += b'\r\n\r\n'
    return bytes(out), names

def build_sf(mf):
    hdr=(b'Signature-Version: 1.0\r\n'
         b'SHA1-Digest-Manifest: '+b64(hashlib.sha1(mf).digest()).encode()+b'\r\n'
         b'Created-By: 1.0 (Android SignApk)\r\n\r\n')
    out=bytearray(hdr)
    body=mf[mf.index(b'\r\n\r\n')+4:]
    pos=0
    while pos < len(body):
        idx=body.find(b'\r\n\r\n\r\n', pos)
        if idx<0:
            if body[pos:].strip(): sec=body[pos:]
            else: break
        else:
            sec=body[pos:idx+6]
        nm=re.search(rb'Name: (.*?)\r\n', sec).group(1)
        out += b'Name: '+nm+b'\r\n'
        out += b'SHA1-Digest: '+b64(hashlib.sha1(sec).digest()).encode()+b'\r\n'
        out += b'\r\n'
        if idx<0: break
        pos=idx+6
    return bytes(out)

def sign_sf(sf):
    from cryptography.hazmat.primitives.serialization import load_der_private_key, Encoding
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes
    from asn1crypto import cms as _cms
    key=load_der_private_key(open(KEY_PK8,'rb').read(), password=None)
    cert=x509.load_pem_x509_certificate(open(KEY_PEM,'rb').read())
    orig=_cms.ContentInfo.load(ZIP_RAW_CERT_RSA)
    orig['content']['signer_infos'][0]['signature']=key.sign(sf, padding.PKCS1v15(), hashes.SHA1())
    return orig.dump()

def raw_entry(name, data, method=8):
    """build a local header + deflated data"""
    comp=zlib_compress(data)
    crc=zipfile.crc32(data) & 0xffffffff
    fn=name.encode('utf-8')
    lh=bytearray()
    lh+=b'PK\x03\x04'
    lh+=struct.pack('<HHHHHIIIHH', 20, 0, method, 0, 0x21, crc, len(comp), len(data), len(fn), 0)
    lh+=fn
    return bytes(lh), comp

def zlib_compress(data):
    import zlib
    co=zlib.compressobj(9, zlib.DEFLATED, -15)
    return co.compress(data)+co.flush()

def cd_entry(name, method, crc, csize, usize, mtime, mdate, lho, ver_made=20, ver_need=20, flags=0):
    fn=name.encode('utf-8')
    b=bytearray()
    b+=b'PK\x01\x02'
    b+=struct.pack('<HHHHHHIIIHHHHHII', ver_made, ver_need, flags, method, mtime, mdate,
                   crc, csize, usize, len(fn), 0, 0, 0, 0, 0, lho)
    b+=fn
    return bytes(b)

def cd_entry_from_raw(rawrec, new_lho):
    """Reuse the original central-directory record verbatim, only re-point the
    local-header offset (bytes 42..46). Keeps extra fields / attributes / comments."""
    b=bytearray(rawrec)
    struct.pack_into('<I', b, 42, new_lho)
    return bytes(b)

if __name__=='__main__':
    ZIP_RAW_CERT_RSA=None
    zin=zipfile.ZipFile(ORIG)
    ZIP_RAW_CERT_RSA=zin.read(CERT_RSA)
    mf, names = build_manifest(None, zin)
    sf = build_sf(mf)
    rsa = sign_sf(sf)

    raw=open(ORIG,'rb').read()
    eocd=find_eocd(raw)
    cd_size, cd_off = struct.unpack_from('<II', raw, eocd+12+0)
    # EOCD: [sig(4)] diskno(2) cddisk(2) entdisk(2) enttotal(2) entsize(4) cdoff(4) commentlen(2)
    ent_total, ent_size, cd_off = struct.unpack_from('<HII', raw, eocd+10)
    comment_len = struct.unpack_from('<H', raw, eocd+20)[0]
    ZIP_COMMENT = raw[eocd+22:eocd+22+comment_len]
    print('original EOCD comment: %d bytes' % len(ZIP_COMMENT))
    entries=parse_cd(raw, cd_off, ent_size)
    print('parsed %d central dir entries' % len(entries))

    out=bytearray()
    cd=[]
    for e in entries:
        nm=e['name']
        if nm in (MANIFEST, CERT_SF, CERT_RSA):
            # control build (PATCH empty): keep the original signature entries verbatim,
            # in their original positions -> byte-identical package.
            # otherwise: skip here, the regenerated ones are appended at the end.
            if not PATCH:
                lh, comp = local_raw(raw, e['lho'])
                cd.append(cd_entry_from_raw(e['raw'], len(out)))
                out+=lh; out+=comp
            continue
        if nm in PATCH:
            data=open(PATCH[nm],'rb').read()
            lh, comp = raw_entry(nm, data)
            crc=zipfile.crc32(data)&0xffffffff
            cd.append(cd_entry(nm, 8, crc, len(comp), len(data), e['mtime'], e['mdate'], len(out)))
            out+=lh; out+=comp
            print('  REWROTE %-34s %8d -> %8d raw bytes' % (nm, e['usize'], len(out)))
        else:
            lh, comp = local_raw(raw, e['lho'])
            cd.append(cd_entry_from_raw(e['raw'], len(out)))
            out+=lh; out+=comp
    # signature entries at the end
    # signature entries: reuse the ORIGINAL ones verbatim (they are already valid);
    # they only get rewritten by build_manifest/build_sf/sign_sf when PATCH is non-empty
    sig_src = {'manifest': mf, 'sf': sf, 'rsa': rsa}
    need_new_sig = bool(PATCH) and not NO_SIG
    if not need_new_sig:
        pass  # all three were raw-copied above in their original positions
    for nm, payload in ((MANIFEST, mf), (CERT_SF, sf), (CERT_RSA, rsa)):
        if not need_new_sig:
            break
        lh, comp = raw_entry(nm, payload)
        crc=zipfile.crc32(payload)&0xffffffff
        cd.append(cd_entry(nm, 8, crc, len(comp), len(payload), 0x21, 0x3a, len(out)))
        out+=lh; out+=comp
        print('  ADDED   %-34s %8d bytes' % (nm, len(payload)))

    cd_off_new=len(out)
    for c in cd: out+=c
    cd_size_new=len(out)-cd_off_new
    eocd_new=bytearray(b'PK\x05\x06')
    if NO_SIG:
        # unsigned staging package: drop the inherited whole-file-signature comment,
        # signapk -w will write a fresh one.
        eocd_new+=struct.pack('<HHHHIIH', 0, 0, len(cd), len(cd), cd_size_new, cd_off_new, 0)
        out+=eocd_new
        print('  (unsigned staging: stripped %d-byte inherited comment)' % len(ZIP_COMMENT))
    else:
        eocd_new+=struct.pack('<HHHHIIH', 0, 0, len(cd), len(cd), cd_size_new, cd_off_new, len(ZIP_COMMENT))
        out+=eocd_new
        out+=ZIP_COMMENT
    open(OUT,'wb').write(bytes(out))
    print('\nwrote %s  %.1f MB  (entries=%d)' % (OUT, len(out)/1048576.0, len(cd)))