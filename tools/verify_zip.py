#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify a signed update.zip the way AOSP recovery's JarVerifier does."""
import zipfile, hashlib, base64, re, sys
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes

MANIFEST='META-INF/MANIFEST.MF'; CERT_SF='META-INF/CERT.SF'; CERT_RSA='META-INF/CERT.RSA'

def b64(x): return base64.b64encode(x).decode()

def split_sections(body: bytes):
    secs=[]; pos=0
    while pos < len(body):
        idx=body.find(b'\r\n\r\n\r\n', pos)
        if idx<0:
            if body[pos:].strip(): secs.append(body[pos:])
            break
        secs.append(body[pos:idx+6]); pos=idx+6
    return secs

def main(path):
    z=zipfile.ZipFile(path)
    names=set(z.namelist())
    mf=z.read(MANIFEST); sf=z.read(CERT_SF); rsa=z.read(CERT_RSA)
    fail=0

    hdr_end=mf.index(b'\r\n\r\n')+4
    secs=split_sections(mf[hdr_end:])
    f1=0
    for sec in secs:
        nm=re.search(rb'Name: (.*?)\r\n', sec).group(1).decode()
        dg=re.search(rb'SHA1-Digest: (.*?)\r\n', sec).group(1).decode()
        if nm not in names:
            print('  MISSING in zip:', nm); f1+=1; continue
        if b64(hashlib.sha1(z.read(nm)).digest())!=dg:
            print('  DIGEST MISMATCH:', nm); f1+=1
    print('[1] manifest entries verified : %d  failures=%d' % (len(secs), f1)); fail+=f1

    covered={re.search(rb'Name: (.*?)\r\n', s).group(1).decode() for s in secs}
    unc=[n for n in names if n not in covered and n not in (MANIFEST,CERT_SF,CERT_RSA)]
    print('[2] entries not in manifest   : %d %s' % (len(unc), unc[:5]))
    if unc: fail+=1

    sfh=sf[:sf.index(b'\r\n\r\n')+4]
    sfb=sf[sf.index(b'\r\n\r\n')+4:]
    sfmap={}
    for chunk in sfb.split(b'\r\n\r\n'):
        if not chunk.strip(): continue
        c=chunk+b'\r\n'
        nm=re.search(rb'Name: (.*?)\r\n', c); dg=re.search(rb'SHA1-Digest: (.*?)\r\n', c)
        if nm and dg: sfmap[nm.group(1).decode()]=dg.group(1).decode()
    f3=0
    for sec in secs:
        nm=re.search(rb'Name: (.*?)\r\n', sec).group(1).decode()
        if sfmap.get(nm)!=b64(hashlib.sha1(sec).digest()):
            print('  SF MISMATCH:', nm); f3+=1
    print('[3] CERT.SF section digests   : %d  failures=%d' % (len(secs), f3)); fail+=f3

    m=re.search(rb'SHA1-Digest-Manifest: (.*?)\r\n', sfh).group(1).decode()
    okm = m==b64(hashlib.sha1(mf).digest())
    print('[4] SHA1-Digest-Manifest       : %s' % ('OK' if okm else 'MISMATCH'))
    if not okm: fail+=1

    from asn1crypto import cms
    cert=pkcs7.load_der_pkcs7_certificates(rsa)[0]
    asn1=cms.ContentInfo.load(rsa)
    signer=asn1['content']['signer_infos'][0]
    alg=signer['digest_algorithm']['algorithm'].native
    print('    signer serial : %s' % hex(cert.serial_number))
    print('    subject       : %s' % cert.subject.rfc4514_string())
    print('    digest alg    : %s' % alg)
    print('    content type  : %s' % asn1['content_type'].native)
    HASH={'sha1':hashes.SHA1(),'sha224':hashes.SHA224(),'sha256':hashes.SHA256(),
          'sha384':hashes.SHA384(),'sha512':hashes.SHA512()}
    sa=signer['signed_attrs']
    has_sa = sa is not None and sa.native is not None and len(sa)>0
    if has_sa:
        md=None
        for attr in sa:
            if attr['type'].native=='message_digest': md=attr['values'][0].native
        if hashlib.sha1(sf).digest()!=md:
            print('    message_digest attr MISMATCH'); fail+=1
        else:
            print('    message_digest attr        : OK')
        der=bytearray(sa.dump()); der[0]=0x31   # SET OF tag, not [0] IMPLICIT
        data=bytes(der)
    else:
        print('    no signed_attrs -> sig directly over CERT.SF')
        data=sf
    try:
        cert.public_key().verify(signer['signature'].native, data,
                                 padding.PKCS1v15(), HASH[alg])
        print('    RSA signature              : OK (%s)' % alg)
    except Exception as e:
        print('    RSA signature              : FAILED (%s)' % e); fail+=1

    print()
    print('RESULT:', 'ALL CHECKS PASSED' if fail==0 else '%d FAILURES' % fail)
    return 0 if fail==0 else 1

if __name__=='__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv)>1 else 'update_v2_hdmi4k.zip'))
