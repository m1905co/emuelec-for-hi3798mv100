/*
 * a4-evinfo — 读取指定 input 设备的事件，打印按键/摇杆的原始 code。
 *
 * 用途：确认某个物理按键到底产生哪个编号，避免"配置看着对、按着不对"。
 *
 * 编译：arm-linux-gnueabihf-gcc -static -O2 -o a4-evinfo a4-evinfo.c
 * 用法：a4-evinfo /dev/input/event1        （Ctrl-C 或 timeout 结束）
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <linux/input.h>

static const char *btn_name(int code)
{
    switch (code) {
    case BTN_SOUTH: return "SOUTH/A";
    case BTN_EAST:  return "EAST/B";
    case BTN_NORTH: return "NORTH/Y";
    case BTN_WEST:  return "WEST/X";
    case BTN_TL:    return "TL/L1";
    case BTN_TR:    return "TR/R1";
    case BTN_TL2:   return "TL2/L2";
    case BTN_TR2:   return "TR2/R2";
    case BTN_SELECT:return "SELECT";
    case BTN_START: return "START";
    case BTN_MODE:  return "MODE";
    case BTN_THUMBL:return "THUMBL/L3";
    case BTN_THUMBR:return "THUMBR/R3";
    default:        return "-";
    }
}

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: %s /dev/input/eventN\n", argv[0]);
        return 2;
    }

    int fd = open(argv[1], O_RDONLY);
    if (fd < 0) {
        fprintf(stderr, "open %s: %s\n", argv[1], strerror(errno));
        return 1;
    }

    fprintf(stderr, "listening on %s (press keys now)\n", argv[1]);

    struct input_event ev;
    while (read(fd, &ev, sizeof(ev)) == (ssize_t)sizeof(ev)) {
        if (ev.type == EV_SYN)
            continue;

        if (ev.type == EV_KEY) {
            printf("KEY  code=%-3d %-10s value=%d\n",
                   ev.code, btn_name(ev.code), ev.value);
        } else if (ev.type == EV_ABS) {
            /* 摇杆轴/hat 只报变化 */
            printf("ABS  code=%-3d %-10s value=%d\n",
                   ev.code, ev.code == ABS_HAT0X ? "HAT0X" :
                            ev.code == ABS_HAT0Y ? "HAT0Y" : "axis",
                   ev.value);
        }
        fflush(stdout);
    }
    close(fd);
    return 0;
}
