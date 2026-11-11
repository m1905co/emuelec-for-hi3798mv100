#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import zipfile, hashlib, os
def m(b): return hashlib.md5(b).hexdigest()
for f in ['update.zip', 'diag_resign_only.zip', 'update_fixed2.zip', 'diag_baseparam_only.zip', 'diag_sysfiles_only.zip']:
    if os.path.exists(f):
        print('%-28s %s  %8.1f MB' % (f, m(open(f,'rb').read()), os.path.getsize(f)/1048576.0))
print()
z = zipfile.ZipFile('update.zip')
zb = z.read('baseparam.img')
print('zip 内 baseparam.img      :', m(zb), len(zb))
print('fw/baseparam.img          :', m(open('fw/baseparam.img','rb').read()))
print('设备原 baseparam 备份      :', m(open('out/baseparam_device.bak','rb').read()))
print('我改的 baseparam_fw.img   :', m(open('out/baseparam_fw.img','rb').read()))
print()
print('fw/baseparam.img == zip 内 baseparam.img :', open('fw/baseparam.img','rb').read() == zb)
print('设备备份 == zip 内 baseparam.img        :', open('out/baseparam_device.bak','rb').read() == zb)