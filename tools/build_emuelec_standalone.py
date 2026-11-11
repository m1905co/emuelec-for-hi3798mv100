#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_emuelec_standalone.py —— 生成「独立 EmuELEC recovery 刷机包」

用途：
    只刷新/安装盒子上「EmuELEC 那一半」，不碰安卓 /system、cache、userdata。
    写入的分区：
      - backup(p13)  ← emuelec_rootfs.img（EmuELEC 系统盘，340MB ext4）
      - 在 backup 挂载后覆盖 ee_files/ 下少量更新文件（免重导整包）
    不写入：p1 U-Boot、p10 内核(factory)、安卓任何分区。

适用场景：
      A) 双系统盒子上重刷/救回 EmuELEC（安卓侧完全不受影响）
      B) 已处于双系统 U-Boot + p10 内核的盒子，刷新 EE 系统

注意：
    - 本包不写 p1（双系统 U-Boot）也不写 p10（EE 内核），因此假定这两者在设备上已正确。
      fastboot_a4.img 当前工作区缺失，故未纳入；如需一并写 p1，把该文件放到
      emuelec/work/ 下并在 UPDATER 里加一行即可（见脚本底部注释）。
    - 整包签名走 AOSP signapk.jar -w；本机 Windows 侧无 java，脚本尝试用 wsl 调 WSL 里的
      AOSP 工具链。若 wsl 不可用，会保留未签名包并打印手动签名命令。

用法：
    python3 tools/build_emuelec_standalone.py            # 构建 + 尝试签名
    python3 tools/build_emuelec_standalone.py --unsigned # 只出未签名包
"""
import sys, os, zipfile, hashlib, subprocess, struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOTFS = os.path.join(ROOT, "emuelec/work/rootfs_img/emu_rootfs.clean.img")
EEFILES = os.path.join(ROOT, "pack/ee_files")
OUT_UNSIGNED = os.path.join(ROOT, "update_a4_emuelec.unsigned.zip")
OUT_SIGNED = os.path.join(ROOT, "update_a4_emuelec.zip")
PEM = os.path.join(ROOT, "keys/testkey.x509.pem")
PK8 = os.path.join(ROOT, "keys/testkey.pk8")
AOSP_SIGNAPK = "/home/mxz/aosp/out/host/linux-x86/framework/signapk.jar"

UPDATER = r'''show_progress(1.0, 40);
ui_print("======================================");
ui_print(" A4 EmuELEC standalone update");
ui_print(" 只安装 EmuELEC 一半，不碰安卓");
ui_print("======================================");
ui_print("writing EmuELEC rootfs -> backup(p13) ...");
package_extract_file("emuelec_rootfs.img", "/dev/block/platform/hi_mci.1/by-name/backup");
ui_print("mount backup & overlay ee_files ...");
mount("ext4", "EMMC", "/dev/block/platform/hi_mci.1/by-name/backup", "/backup");
package_extract_dir("ee_files", "/backup");
set_perm(0, 0, 0755, "/backup/etc/init.d/S93wifi");
set_perm(0, 0, 0755, "/backup/etc/init.d/S94a4-menu");
set_perm(0, 0, 0755, "/backup/etc/init.d/S96a4-exitd");
set_perm(0, 0, 0755, "/backup/usr/bin/a4-exitd");
unmount("/backup");
show_progress(0.1, 0);
ui_print("done. reboot to EmuELEC.");
'''


def ext4_magic_ok(path):
    with open(path, "rb") as f:
        f.seek(0x438)
        return f.read(2) == b"\x53\xef"


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_unsigned():
    assert os.path.exists(ROOTFS), "缺少 rootfs: " + ROOTFS
    assert ext4_magic_ok(ROOTFS), "rootfs 不是 ext4 镜像（魔数校验失败）"
    print("rootfs: %d B  md5=%s  ext4 OK" % (os.path.getsize(ROOTFS), md5(ROOTFS)))

    with zipfile.ZipFile(OUT_UNSIGNED, "w", zipfile.ZIP_DEFLATED) as z:
        # 1) EmuELEC rootfs 镜像
        with open(ROOTFS, "rb") as f:
            data = f.read()
        z.writestr("emuelec_rootfs.img", data)
        print("  [写入] emuelec_rootfs.img        %9d B" % len(data))

        # 2) ee_files 树 -> 加 ee_files/ 前缀
        for dirpath, _, files in os.walk(EEFILES):
            for fn in files:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, EEFILES).replace(os.sep, "/")
                entry = "ee_files/" + rel
                with open(full, "rb") as f:
                    data = f.read()
                zi = zipfile.ZipInfo(entry, date_time=(2026, 11, 11, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = 0o755 << 16 if os.access(full, os.X_OK) else 0o644 << 16
                z.writestr(zi, data)
                print("  [写入] %-42s %9d B" % (entry, len(data)))

        # 3) updater-script
        zi = zipfile.ZipInfo("META-INF/com/google/android/updater-script",
                             date_time=(2026, 11, 11, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_DEFLATED
        zi.external_attr = 0o644 << 16
        z.writestr(zi, UPDATER.encode("utf-8"))
        print("  [写入] META-INF/com/google/android/updater-script")

    print("未签名包: %s (%.1f MB)" %
          (OUT_UNSIGNED, os.path.getsize(OUT_UNSIGNED) / 1048576))


def sign():
    cmd = ["wsl", "-e", "bash", "-lc",
           "cd /mnt/e/A4-work && java -jar %s -w %s %s %s %s"
           % (AOSP_SIGNAPK, "/mnt/e/A4-work/" + "keys/testkey.x509.pem",
              "/mnt/e/A4-work/" + "keys/testkey.pk8",
              "/mnt/e/A4-work/update_a4_emuelec.unsigned.zip",
              "/mnt/e/A4-work/update_a4_emuelec.zip")]
    print("signapk -w (via wsl) ...")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=420)
    except subprocess.TimeoutExpired:
        print("签名超时（>7min），保留未签名包。")
        return False
    except FileNotFoundError:
        print("wsl 不可用，保留未签名包。")
        return False
    if r.returncode != 0:
        print("signapk 失败：")
        print((r.stdout or "")[-1500:], (r.stderr or "")[-1500:])
        return False
    return True


def verify(path):
    d = open(path, "rb").read()
    i = d.rfind(b"PK\x05\x06")
    clen = struct.unpack("<H", d[i + 20:i + 22])[0]
    head = d[i + 22:i + 22 + 20]
    print("输出 %s  %.1f MB" % (path, len(d) / 1048576))
    print("EOCD 注释长度 = %d  (原厂 1738)" % clen)
    print("注释开头 = %r" % head)
    ok = clen > 0 and head.startswith(b"signed by SignApk")
    print("整包签名(jared):", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    build_unsigned()
    if "--unsigned" in sys.argv:
        print("\n未签名包已生成（按要求不签名）。手动签名：")
        print('  wsl -e bash -lc "cd /mnt/e/A4-work && java -jar %s -w %s %s %s %s"'
              % (AOSP_SIGNAPK, PEM, PK8, OUT_UNSIGNED, OUT_SIGNED))
        sys.exit(0)
    if sign():
        verify(OUT_SIGNED)
        print("\nsha256(已签名):", hashlib.sha256(open(OUT_SIGNED, "rb").read()).hexdigest())
    else:
        print("\n保留未签名包：", OUT_UNSIGNED)
        print("手动签名命令：")
        print('  wsl -e bash -lc "cd /mnt/e/A4-work && java -jar %s -w %s %s %s %s"'
              % (AOSP_SIGNAPK, PEM, PK8, OUT_UNSIGNED, OUT_SIGNED))
