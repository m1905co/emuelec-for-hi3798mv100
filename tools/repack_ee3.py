#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
repack_ee3.py —— 双系统 OTA 打包（标准流程：signapk -w 整包签名）

与原 repack_ee2.py 的关键区别：
  旧版自己拼 MANIFEST/SF/RSA（jar 逐条目签名），**没有 jared 整包签名**，
  EOCD 注释长度为 0 → 海思 recovery 的 verify_file() 直接判"整包签名失败"，刷入立即失败。
  原厂 update.zip 的 EOCD 注释是 1738 字节，以 "signed by SignApk\\0" 开头。

  本脚本改成标准做法：
    1) 只写数据条目（不含 META-INF 签名文件），保持原包顺序与压缩方式
    2) 交给 AOSP 的 signapk -w 生成 MANIFEST/SF/RSA + 整包签名

用法：
  python tools/repack_ee3.py            # 正式出包
  python tools/repack_ee3.py --unsigned # 只生成未签名包（调试）
"""
import sys, os, zipfile, subprocess, hashlib

SRC = 'update.zip'
UNSIGNED = 'update_a4_dual.unsigned.zip'
OUT = 'update_a4_dual.zip'

# 替换（原包里已存在）
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

# 新增
NEW = {
    'emuelec_rootfs.img'                : 'emuelec/work/rootfs_img/emu_rootfs.clean.img',
    'system/xbin/a4-uv'                 : 'pack/ota/a4-uv',
    'system/xbin/a4-switch'             : 'tools/a4-switch',        # 新版：写 misc 标记，不依赖 /data 的 env bin
    'system/xbin/a4-switchd'            : 'tools/a4-switchd',
    'system/xbin/a4-os-switch'          : 'emuelec/work/a4-os-switch',
    'system/xbin/switch-to-android'     : 'emuelec/work/switch-to-android',
    'system/xbin/switch-to-emuelec'     : 'emuelec/work/switch-to-emuelec',
    'system/etc/uvmode.sh'              : 'fw/system/etc/uvmode.sh',
    'system/app/A4DualBoot.apk'         : 'fw/system/app/A4DualBoot.apk',
    'userdata/app/com.a4.tune-1.apk'    : 'pack/ota/A4Tune.apk',
    'userdata/app/com.a4.switcher-1.apk': 'apk/A4Switch/build/A4Switch.apk',   # 遥控器版切换 App（vc10 > 系统版 vc4，会覆盖显示）
    'userdata/a4/a4-os-switch'          : 'emuelec/work/a4-os-switch',
    'userdata/a4/a4-switchd'            : 'tools/a4-switchd',
    'userdata/a4/switch-to-android'     : 'emuelec/work/switch-to-android',
    'userdata/a4/switch-to-emuelec'     : 'emuelec/work/switch-to-emuelec',
    'ee_files/etc/init.d/S93wifi'       : 'pack/ee_files/etc/init.d/S93wifi',
    'ee_files/usr/bin/a4-menu'          : 'tools/a4-menu',
    'ee_files/usr/bin/a4-es-restart'    : 'tools/a4-es-restart',
    'ee_files/etc/init.d/S94a4-menu'    : 'pack/ee_files/etc/init.d/S94a4-menu',
    # ---- 手柄/热键（2026-10-29 标定）----
    # 热键原来=6(LB)，与 l_btn=6 撞车 ⇒ LB 永远不能当 L1 用；R2 也不该走轴（BTN_TR2=9 才是它）
    'ee_files/opt/emuelec/etc/retroarch.cfg'                              : 'pack/ee_files/opt/emuelec/etc/retroarch.cfg',
    'ee_files/opt/emuelec/share/retroarch/autoconfig/sdl2/ZhiXu Gamepad.cfg' : 'pack/ee_files/opt/emuelec/share/retroarch/autoconfig/sdl2/ZhiXu Gamepad.cfg',
    'ee_files/storage/.config/retroarch/autoconfig/ZhiXu-Gamepad.cfg'      : 'pack/ee_files/storage/.config/retroarch/autoconfig/ZhiXu-Gamepad.cfg',
    # ---- 手柄设置入口（ES 里可点：重跑官方向导 / 清掉 RA 预置 / 还原）----
    'ee_files/storage/ee/padcfg/pad-es-config.sh'                        : 'pack/ee_files/storage/ee/padcfg/pad-es-config.sh',
    'ee_files/storage/ee/padcfg/pad-ra-clear.sh'                         : 'pack/ee_files/storage/ee/padcfg/pad-ra-clear.sh',
    'ee_files/storage/ee/padcfg/pad-restore.sh'                          : 'pack/ee_files/storage/ee/padcfg/pad-restore.sh',
    'ee_files/storage/ee/padcfg/default/ZhiXu-Gamepad.cfg'               : 'pack/ee_files/storage/ee/padcfg/default/ZhiXu-Gamepad.cfg',
    # ---- 退出游戏守护（RA 1.9 的 hotkey+exit 在这台上失灵，改在 evdev 层 kill）----
    'ee_files/usr/bin/a4-exitd'                                          : 'pack/ee_files/usr/bin/a4-exitd',
    'ee_files/etc/init.d/S96a4-exitd'                                    : 'pack/ee_files/etc/init.d/S96a4-exitd',
}

META = ('META-INF/MANIFEST.MF', 'META-INF/CERT.SF', 'META-INF/CERT.RSA')


def build_unsigned():
    zin = zipfile.ZipFile(SRC)
    order = [i.filename for i in zin.infolist()]
    with zipfile.ZipFile(UNSIGNED, 'w', zipfile.ZIP_DEFLATED) as zout:
        for name in order:
            if name in META:
                continue
            info = zin.getinfo(name)
            if name in PATCH:
                data = open(PATCH[name], 'rb').read()
                print('  [替换] %-42s %9d B' % (name, len(data)))
            else:
                data = zin.read(name)
            ni = zipfile.ZipInfo(name, date_time=info.date_time)
            ni.compress_type = zipfile.ZIP_DEFLATED
            ni.external_attr = info.external_attr
            ni.create_system = info.create_system
            zout.writestr(ni, data)
        for name, path in NEW.items():
            data = open(path, 'rb').read()
            ni = zipfile.ZipInfo(name, date_time=(2026, 10, 29, 0, 0, 0))
            ni.compress_type = zipfile.ZIP_DEFLATED
            ni.external_attr = 0o644 << 16
            zout.writestr(ni, data)
            print('  [新增] %-42s %9d B' % (name, len(data)))
    print('未签名包：%s (%.1f MB)' % (UNSIGNED, os.path.getsize(UNSIGNED) / 1048576))


def sign():
    aosp = '/home/mxz/aosp'
    signapk = aosp + '/out/host/linux-x86/framework/signapk.jar'
    pem = 'keys/testkey.x509.pem'
    pk8 = 'keys/testkey.pk8'
    cmd = ['wsl', '-e', 'bash', '-lc',
           'cd /mnt/e/A4-work && java -jar %s -w %s %s %s %s'
           % (signapk, '/mnt/e/A4-work/' + pem, '/mnt/e/A4-work/' + pk8,
              '/mnt/e/A4-work/' + UNSIGNED, '/mnt/e/A4-work/' + OUT)]
    print('signapk -w ...')
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:])
        sys.exit('signapk 失败')


def verify():
    import struct
    d = open(OUT, 'rb').read()
    i = d.rfind(b'PK\x05\x06')
    clen = struct.unpack('<H', d[i + 20:i + 22])[0]
    head = d[i + 22:i + 22 + 20]
    print('输出 %s  %.1f MB' % (OUT, len(d) / 1048576))
    print('EOCD 注释长度 = %d  (原厂 1738)' % clen)
    print('注释开头 = %r' % head)
    ok = clen > 0 and head.startswith(b'signed by SignApk')
    print('整包签名(jared):', 'PASS' if ok else 'FAIL')
    z = zipfile.ZipFile(OUT)
    print('条目数 =', len(z.namelist()))
    print('updater-script 含写镜像:', b'emuelec_rootfs.img' in z.read('META-INF/com/google/android/updater-script'))
    print('libstagefright md5 =', hashlib.md5(z.read('system/lib/libstagefright.so')).hexdigest()[:8], '(应 1f6a8757)')
    return ok


if __name__ == '__main__':
    build_unsigned()
    if '--unsigned' in sys.argv:
        sys.exit(0)
    sign()
    verify()
