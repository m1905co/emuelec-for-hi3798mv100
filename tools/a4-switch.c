/*
 * a4-switch —— 双系统切换 setuid 助手（重写版）
 *
 * 背景：老版 a4-switch 是"把 /data/a4/env-*.bin 写进 p2(env)"的实现，
 *       而 /data 一刷机就被 format 掉，两个 bin 没了 ⇒ "refusing to switch"，
 *       App 里点切换完全没反应。
 *       更关键的是：这台机器的原厂 U-Boot **不读 env 的 bootcmd**，
 *       即使写进去也切不过去（旧方案已废弃）。
 *
 * 现行方案（与 /data/a4/a4-os-switch 一致）：只改 **misc 分区前 32 字节**
 * （BCB command 字段），U-Boot 看到 "product-test" 就从 p10 起 EmuELEC。
 *
 * 用法（与老版完全兼容，App 不用改）：
 *   a4-switch emuelec   写 product-test，重启进 EmuELEC
 *   a4-switch android   清空标记，重启进安卓
 *   a4-switch reboot    只重启
 *   a4-switch status    打印当前标记
 *
 * 编译：arm-linux-gnueabihf-gcc -static -O2 -o a4-switch a4-switch.c
 * 安装：/system/xbin/a4-switch, chown 0:0, chmod 06755（必须有 setuid，App 无 root）
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <sys/reboot.h>
#include <sys/stat.h>

#define MARK_LEN 32

static const char *misc_paths[] = {
    "/dev/block/platform/hi_mci.1/by-name/misc",
    "/dev/block/mmcblk0p9",
    NULL
};

static const char *usage(void) {
    return "usage: a4-switch emuelec|android|reboot|status\n";
}

static int open_misc(void) {
    int i;
    for (i = 0; misc_paths[i]; i++) {
        int fd = open(misc_paths[i], O_RDWR);
        if (fd >= 0) return fd;
    }
    return -1;
}

static int write_marker(const char *mark) {
    char buf[MARK_LEN];
    int fd, n;

    memset(buf, 0, sizeof(buf));          /* 先清零，剩余字节保持 0 */
    if (mark && mark[0]) {
        n = strlen(mark);
        if (n > MARK_LEN) n = MARK_LEN;
        memcpy(buf, mark, n);
        /* 老脚本用 '%-32s' 空格填充；U-Boot 只认前面这段，补空格更贴近原行为 */
        memset(buf + n, ' ', MARK_LEN - n);
    }

    fd = open_misc();
    if (fd < 0) {
        fprintf(stderr, "a4-switch: open misc: %s\n", strerror(errno));
        return -1;
    }
    if (write(fd, buf, MARK_LEN) != MARK_LEN) {
        fprintf(stderr, "a4-switch: write: %s\n", strerror(errno));
        close(fd);
        return -1;
    }
    fsync(fd);
    close(fd);
    return 0;
}

static void show_status(void) {
    char buf[MARK_LEN + 1];
    int fd, n, i;

    fd = open_misc();
    if (fd < 0) {
        printf("misc: cannot open (%s)\n", strerror(errno));
        return;
    }
    memset(buf, 0, sizeof(buf));
    n = read(fd, buf, MARK_LEN);
    close(fd);
    if (n < 0) { printf("misc: read failed\n"); return; }
    for (i = 0; i < n; i++) if (buf[i] == 0) buf[i] = ' ';
    buf[n] = 0;
    printf("misc[0..32] = \"%s\"\n", buf);
    if (strncmp(buf, "product-test", 12) == 0) printf("=> 下次启动：EmuELEC\n");
    else if (strlen(buf) == 0 || strncmp(buf, "                ", 16) == 0) printf("=> 下次启动：Android\n");
}

static void do_reboot(void) {
    sync();
    if (geteuid() != 0) {
        fprintf(stderr, "a4-switch: reboot needs root (euid=%d)\n", (int)geteuid());
        exit(1);
    }
    sleep(1);
    reboot(RB_AUTOBOOT);
    fprintf(stderr, "a4-switch: reboot() failed: %s\n", strerror(errno));
    exit(1);
}

int main(int argc, char **argv) {
    const char *cmd = (argc > 1) ? argv[1] : "status";

    if (!strcmp(cmd, "status")) { show_status(); return 0; }
    if (!strcmp(cmd, "reboot")) { printf("a4-switch: rebooting\n"); do_reboot(); }

    if (!strcmp(cmd, "emuelec")) {
        if (geteuid() != 0) { fprintf(stderr, "a4-switch: not running as root (euid=%d)\n", (int)geteuid()); return 1; }
        if (write_marker("product-test") != 0) return 1;
        printf("a4-switch: misc marked product-test, rebooting into EmuELEC\n");
        do_reboot();
    }
    if (!strcmp(cmd, "android")) {
        if (geteuid() != 0) { fprintf(stderr, "a4-switch: not running as root (euid=%d)\n", (int)geteuid()); return 1; }
        if (write_marker("") != 0) return 1;
        printf("a4-switch: misc cleared, rebooting into Android\n");
        do_reboot();
    }
    fprintf(stderr, "a4-switch: unknown command '%s'\n%s", cmd, usage());
    return 2;
}
