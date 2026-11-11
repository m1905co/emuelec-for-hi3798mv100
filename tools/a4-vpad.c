/* a4-vpad - 虚拟手柄注入（用于无人值守自验证 ES/RetroArch 按键）
 *
 * usage: a4-vpad <delay_secs> <btn> [<btn> ...]
 *   btn: a b x y lb rb select start up down left right
 *        组合键用 '+' 连接，例如 lb+start（同时按住 0.35s 再松开）
 *
 * 设备名故意叫 "A4 Vctl" —— 不含 X-Box/ZhiXu/Joystick/Gamepad/Pad 关键字，
 * 这样 a4-joymap.sh 不会把它当成玩家手柄。
 *
 * 用法要点：设备必须在目标程序(ES/RetroArch)启动**之前**创建，否则 SDL 可能不枚举它。
 *   例：nohup /storage/a4-vpad 14 a > /tmp/vpad.log 2>&1 &
 *       （然后重启 ES；14 秒后自动按一次 A）
 */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <linux/uinput.h>
#include <sys/ioctl.h>

static int fd;

static void emit(int type, int code, int val)
{
    struct input_event ie;
    memset(&ie, 0, sizeof(ie));
    ie.type = type;
    ie.code = code;
    ie.value = val;
    write(fd, &ie, sizeof(ie));
}

static int btn_code(const char *s)
{
    if (!strcmp(s, "a"))      return BTN_SOUTH;
    if (!strcmp(s, "b"))      return BTN_EAST;
    if (!strcmp(s, "x"))      return BTN_NORTH;
    if (!strcmp(s, "y"))      return BTN_WEST;
    if (!strcmp(s, "lb"))     return BTN_TL;
    if (!strcmp(s, "rb"))     return BTN_TR;
    if (!strcmp(s, "select")) return BTN_SELECT;
    if (!strcmp(s, "start"))  return BTN_START;
    return -1;
}

int main(int argc, char **argv)
{
    int delay = argc > 1 ? atoi(argv[1]) : 10;
    int i;

    fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
    if (fd < 0) { perror("open /dev/uinput"); return 1; }

    ioctl(fd, UI_SET_EVBIT, EV_KEY);
    ioctl(fd, UI_SET_EVBIT, EV_ABS);
    ioctl(fd, UI_SET_EVBIT, EV_SYN);

    int keys[] = {BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST, BTN_TL, BTN_TR,
                  BTN_SELECT, BTN_START, BTN_MODE, BTN_THUMBL, BTN_THUMBR};
    for (i = 0; i < (int)(sizeof(keys)/sizeof(keys[0])); i++)
        ioctl(fd, UI_SET_KEYBIT, keys[i]);

    struct uinput_abs_setup abs;
    int axes[] = {ABS_X, ABS_Y, ABS_HAT0X, ABS_HAT0Y};
    for (i = 0; i < 4; i++) {
        memset(&abs, 0, sizeof(abs));
        abs.code = axes[i];
        if (axes[i] == ABS_HAT0X || axes[i] == ABS_HAT0Y) {
            abs.absinfo.minimum = -1; abs.absinfo.maximum = 1;
        } else {
            abs.absinfo.minimum = -32768; abs.absinfo.maximum = 32767;
        }
        ioctl(fd, UI_ABS_SETUP, &abs);
        ioctl(fd, UI_SET_ABSBIT, axes[i]);
    }

    struct uinput_user_dev dev;
    memset(&dev, 0, sizeof(dev));
    snprintf(dev.name, UINPUT_MAX_NAME_SIZE, "Microsoft X-Box 360 pad");
    dev.id.bustype = BUS_USB;
    dev.id.vendor  = 0x045e;
    dev.id.product = 0x028e;
    dev.id.version = 0x0110;
    for (i = 0; i < ABS_CNT; i++) dev.absmin[i] = -32768, dev.absmax[i] = 32767;

    if (write(fd, &dev, sizeof(dev)) < 0) { perror("write dev"); return 1; }
    if (ioctl(fd, UI_DEV_CREATE) < 0) { perror("UI_DEV_CREATE"); return 1; }
    fprintf(stderr, "vpad created, sleeping %ds\n", delay);
    sleep(delay);

    for (i = 2; i < argc; i++) {
        char buf[64];
        snprintf(buf, sizeof(buf), "%s", argv[i]);

        if (strchr(buf, '+')) {
            /* 组合键：同时按下 */
            char *p, *save = NULL;
            int codes[8], n = 0;
            for (p = strtok_r(buf, "+", &save); p && n < 8; p = strtok_r(NULL, "+", &save)) {
                int c = btn_code(p);
                if (c > 0) codes[n++] = c;
            }
            for (int k = 0; k < n; k++) { emit(EV_KEY, codes[k], 1); emit(EV_SYN, SYN_REPORT, 0); usleep(30000); }
            usleep(350000);
            for (int k = 0; k < n; k++) { emit(EV_KEY, codes[k], 0); emit(EV_SYN, SYN_REPORT, 0); usleep(30000); }
            fprintf(stderr, "combo %s done\n", argv[i]);
        } else if (!strcmp(buf, "up") || !strcmp(buf, "down") ||
                   !strcmp(buf, "left") || !strcmp(buf, "right")) {
            int axis = (buf[0] == 'u' || buf[0] == 'd') ? ABS_HAT0Y : ABS_HAT0X;
            int val  = (buf[0] == 'u' || buf[0] == 'l') ? -1 : 1;
            emit(EV_ABS, axis, val); emit(EV_SYN, SYN_REPORT, 0);
            usleep(140000);
            emit(EV_ABS, axis, 0);   emit(EV_SYN, SYN_REPORT, 0);
            fprintf(stderr, "press %s done\n", buf);
        } else {
            int c = btn_code(buf);
            if (c < 0) { fprintf(stderr, "unknown btn %s\n", buf); continue; }
            emit(EV_KEY, c, 1); emit(EV_SYN, SYN_REPORT, 0);
            usleep(120000);
            emit(EV_KEY, c, 0); emit(EV_SYN, SYN_REPORT, 0);
            fprintf(stderr, "press %s done\n", buf);
        }
        usleep(250000);
    }

    sleep(1);
    ioctl(fd, UI_DEV_DESTROY);
    close(fd);
    return 0;
}
