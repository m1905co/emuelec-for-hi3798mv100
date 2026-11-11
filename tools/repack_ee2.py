#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
repack_ee2.py —— 生成「安卓 + EmuELEC 双系统」OTA 更新包

基于 update.zip（原厂 AOSP testkey 签名包）：
  1) 替换 updater-script：把 format("...by-name/backup") 改成写入 EmuELEC rootfs 镜像
     （backup 分区 = EmuELEC rootfs，原厂那一步正是抹掉 EmuELEC 的元凶）
  2) 替换 baseparam.img / media_codecs.xml / wifi_recover.sh（历史优化，从设备回收）
  3) 新增 emuelec_rootfs.img（340MB ext4，从设备导出）
  4) 按原包的确切格式重算 MANIFEST.MF / CERT.SF，并用 testkey 重签 CERT.RSA

已验证的原包格式（反推得到）：
  MANIFEST.MF  头： "Manifest-Version: 1.0\\r\\nCreated-By: ...\\r\\n\\r\\n"
                段： "Name: <n>\\r\\nSHA1-Digest: <b64>\\r\\n\\r\\n"
                    （段与段之间是**一个空行**，段本身含末尾 \\r\\n\\r\\n）
  CERT.SF      头： "Signature-Version: 1.0\\r\\nCreated-By: ...\\r\\nSHA1-Digest-Manifest: <b64 sha1(MANIFEST.MF)>\\r\\n\\r\\n"
                段： "Name: <n>\\r\\nSHA1-Digest-Manifest: <b64 sha1(MANIFEST 中该段完整字节)>\\r\\n\\r\\n"
  CERT.RSA     原包的 CMS 结构原样复用，只替换 signature 值（RSA/SHA1，无 signed attrs）

用法：
    python repack_ee2.py            # 正式打包 -> update_a4_dual.zip
    python repack_ee2.py --dry      # 回放校验：不替换任何文件，输出应与原包 MANIFEST/SF 完全一致
"""

import zipfile, hashlib, base64, os, sys, re

ORIG = 'update.zip'
OUT  = 'update_a4_dual.zip'

# 要被替换的条目：{zip 内路径: 本地文件}
PATCH = {
    'META-INF/com/google/android/updater-script': 'pack/ota/updater-script',
    'baseparam.img'                : 'out/baseparam_fw.img',
    'system/lib/libstagefright.so' : 'fw/system/lib/libstagefright.so',
    'system/build.prop'            : 'fw/system/build.prop',
    'system/etc/media_codecs.xml'  : 'fw/system/etc/media_codecs.xml',
    'system/etc/init.bigfish.sh'   : 'pack/ota/init.bigfish.sh',
    'system/etc/install-recovery.sh': 'fw/system/etc/install-recovery.sh',
    'system/bin/wifi_recover.sh'   : 'fw/system/bin/wifi_recover.sh',
}

# 要新增的条目
NEW = {
    'emuelec_rootfs.img'                : 'emuelec/work/rootfs_img/emu_rootfs.img',
    'system/xbin/a4-uv'                 : 'pack/ota/a4-uv',
    'system/xbin/a4-switch'             : 'fw/system/xbin/a4-switch',
    'system/etc/uvmode.sh'              : 'fw/system/etc/uvmode.sh',
    'system/app/A4DualBoot.apk'         : 'fw/system/app/A4DualBoot.apk',
    'userdata/app/com.a4.tune-1.apk'    : 'pack/ota/A4Tune.apk',
    'userdata/a4/a4-os-switch'          : 'emuelec/work/a4-os-switch',
    'userdata/a4/a4-switchd'            : 'emuelec/work/a4-switchd',
    'userdata/a4/switch-to-android'     : 'emuelec/work/switch-to-android',
    'userdata/a4/switch-to-emuelec'     : 'emuelec/work/switch-to-emuelec',
    'ee_files/etc/init.d/S93wifi'       : 'pack/ee_files/etc/init.d/S93wifi',
}

KEY_PK8 = 'keys/testkey.pk8'
KEY_PEM = 'keys/testkey.x509.pem'

MANIFEST = 'META-INF/MANIFEST.MF'
CERT_SF  = 'META-INF/CERT.SF'
CERT_RSA = 'META-INF/CERT.RSA'


def b64(x):
    return base64.b64encode(x).decode()


def split_manifest(body):
    """把 MANIFEST 主体切成段（每段含末尾 \\r\\n\\r\\n）。返回 [(段bytes, 名称), ...]"""
    out = []
    for part in body.split(b'\r\n\r\n'):
        if not part.strip():
            continue
        sec = part + b'\r\n\r\n'
        # 取名称行（第一行，去掉 'Name: '）
        first = part.split(b'\r\n')[0]
        if not first.startswith(b'Name: '):
            continue
        name = first[6:]
        # 处理折行：后续以空格开头的行
        for ln in part.split(b'\r\n')[1:]:
            if ln.startswith(b' '):
                name += ln[1:]
            else:
                break
        out.append((sec, name))
    return out


def digest_of(sec):
    m = re.search(rb'SHA1-Digest: ([A-Za-z0-9+/=]{28})', sec)
    return m.group(1) if m else None


def main():
    dry = '--dry' in sys.argv

    from cryptography.hazmat.primitives.serialization import (
        pkcs7, Encoding, load_der_private_key)
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from asn1crypto import cms as _cms

    zin = zipfile.ZipFile(ORIG, 'r')
    mf = zin.read(MANIFEST)
    hdr_end = mf.index(b'\r\n\r\n') + 4
    header = mf[:hdr_end]
    body = mf[hdr_end:]

    secs = split_manifest(body)
    print('MANIFEST 段数：%d' % len(secs))

    # ---- 重建 MANIFEST ----
    out_body = bytearray()
    patched = 0
    for sec, name in secs:
        nm = name.decode('utf-8')
        if not dry and nm in PATCH:
            data = open(PATCH[nm], 'rb').read()
            nd = b64(hashlib.sha1(data).digest()).encode()
            old = digest_of(sec)
            if old:
                sec = sec.replace(b'SHA1-Digest: ' + old, b'SHA1-Digest: ' + nd, 1)
            patched += 1
            print('  [替换] %-42s %8d B' % (nm, len(data)))
        out_body += sec

    if not dry:
        for nm, path in NEW.items():
            data = open(path, 'rb').read()
            nd = b64(hashlib.sha1(data).digest()).encode()
            out_body += b'Name: ' + nm.encode() + b'\r\n'
            out_body += b'SHA1-Digest: ' + nd + b'\r\n\r\n'
            print('  [新增] %-42s %8d B' % (nm, len(data)))

    out_mf = header + bytes(out_body)

    # ---- 回放校验：不替换时应当与原包逐字节一致 ----
    if dry:
        same = out_mf == mf
        print('MANIFEST 回放一致：%s' % same)
        if not same:
            # 定位第一处差异
            for i in range(min(len(out_mf), len(mf))):
                if out_mf[i] != mf[i]:
                    print('  首个差异 @%d: 原 %r / 新 %r' % (i, mf[i-40:i+40], out_mf[i-40:i+40]))
                    break
            sys.exit(1)
        # 继续校验 SF
        orig_sf = zin.read(CERT_SF)
        head_end = orig_sf.index(b'\r\n\r\n') + 4
        my_sf_head = (b'Signature-Version: 1.0\r\n'
                      b'Created-By: 1.0 (Android SignApk)\r\n'
                      b'SHA1-Digest-Manifest: ' + b64(hashlib.sha1(out_mf).digest()).encode() + b'\r\n\r\n')
        print('SF 头一致：%s' % (my_sf_head == orig_sf[:head_end]))
        # 逐段比对
        mine = split_manifest(bytes(out_body))
        ok = 0
        for sec, name in mine:
            want = b64(hashlib.sha1(sec).digest()).encode()
            # 在原 SF 中找同名段
            pat = re.escape(b'Name: ' + name + b'\r\nSHA1-Digest-Manifest: ')
            m = re.search(pat + rb'([A-Za-z0-9+/=]{28})', orig_sf)
            if m and m.group(1) == want:
                ok += 1
            elif m:
                print('  段摘要不符：%s' % name[:60])
        print('SF 段摘要一致：%d / %d' % (ok, len(mine)))
        return 0 if ok == len(mine) else 1

    # ---- 重建 CERT.SF ----
    sf = bytearray()
    sf += (b'Signature-Version: 1.0\r\n'
           b'Created-By: 1.0 (Android SignApk)\r\n')
    sf += b'SHA1-Digest-Manifest: ' + b64(hashlib.sha1(out_mf).digest()).encode() + b'\r\n\r\n'

    for sec, name in split_manifest(bytes(out_body)):
        sf += b'Name: ' + name + b'\r\n'
        sf += b'SHA1-Digest-Manifest: ' + b64(hashlib.sha1(sec).digest()).encode() + b'\r\n\r\n'
    out_sf = bytes(sf)
    print('CERT.SF 生成：%d 字节' % len(out_sf))

    # ---- 签名：复用原 CMS 结构，只换 signature ----
    key = load_der_private_key(open(KEY_PK8, 'rb').read(), password=None)
    sig = key.sign(out_sf, padding.PKCS1v15(), hashes.SHA1())
    orig_cms = _cms.ContentInfo.load(zin.read(CERT_RSA))
    orig_cms['content']['signer_infos'][0]['signature'] = sig
    rsa = orig_cms.dump()
    print('CERT.RSA：%d 字节（结构沿用原包）' % len(rsa))

    cert = x509.load_pem_x509_certificate(open(KEY_PEM, 'rb').read())
    orig_certs = pkcs7.load_der_pkcs7_certificates(zin.read(CERT_RSA))
    if orig_certs[0].public_bytes(Encoding.DER) != cert.public_bytes(Encoding.DER):
        sys.exit('ABORT: 证书与原包不一致')

    # ---- 写新 zip ----
    if os.path.exists(OUT):
        os.remove(OUT)
    zout = zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED)
    sigdata = {MANIFEST: out_mf, CERT_SF: out_sf, CERT_RSA: rsa}
    order = [i.filename for i in zin.infolist()]

    for info in zin.infolist():
        fn = info.filename
        if fn in sigdata:
            data = sigdata[fn]
            ni = zipfile.ZipInfo(fn, date_time=info.date_time)
            ni.compress_type = zipfile.ZIP_DEFLATED
            ni.external_attr = info.external_attr
            ni.create_system = info.create_system
            zout.writestr(ni, data)
            continue
        data = open(PATCH[fn], 'rb').read() if fn in PATCH else zin.read(fn)
        ni = zipfile.ZipInfo(fn, date_time=info.date_time)
        ni.compress_type = info.compress_type
        ni.external_attr = info.external_attr
        ni.create_system = info.create_system
        zout.writestr(ni, data)

    for nm, path in NEW.items():
        data = open(path, 'rb').read()
        ni = zipfile.ZipInfo(nm, date_time=(2026, 10, 29, 0, 0, 0))
        ni.compress_type = zipfile.ZIP_DEFLATED
        ni.external_attr = 0o644 << 16
        zout.writestr(ni, data)
    zout.close()
    zin.close()

    print('输出 %s (%.1f MB)' % (OUT, os.path.getsize(OUT) / 1048576.0))

    # ---- 自检 ----
    zc = zipfile.ZipFile(OUT)
    names = zc.namelist()
    assert names[:len(order)] == order, '原有条目顺序被改变'
    for s in (MANIFEST, CERT_SF, CERT_RSA):
        assert zc.getinfo(s).compress_type == zipfile.ZIP_DEFLATED
    print('  [ok] 原有 %d 条目顺序不变，签名文件仍为 DEFLATE' % len(order))
    print('  [ok] 新增条目：%s' % list(NEW))
    return 0


if __name__ == '__main__':
    sys.exit(main())
