/*
 * a4-keys —— 往 evdev 设备注入按键（root 可用，用于遥控/手柄组合键验证）
 *
 * 用法：a4-keys <dev> d<code> u<code> ... [w<ms>]
 *   例：a4-keys /dev/input/event0 d318 d315 w200 u315 u318
 *       （先按下 R3(318) 与 Start(315)，200ms 后松开）
 *
 * 只发 EV_KEY + EV_SYN，够测组合键。
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <linux/input.h>

static int emit(int fd, int type, int code, int val)
{
    struct input_event ev;
    memset(&ev, 0, sizeof(ev));
    ev.type = type;
    ev.code = code;
    ev.value = val;
    if (write(fd, &ev, sizeof(ev)) != (ssize_t)sizeof(ev)) return -1;
    memset(&ev, 0, sizeof(ev));
    ev.type = EV_SYN;
    ev.code = SYN_REPORT;
    ev.value = 0;
    return (write(fd, &ev, sizeof(ev)) == (ssize_t)sizeof(ev)) ? 0 : -1;
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: %s <dev> d<code> u<code> [w<ms>] ...\n", argv[0]);
        return 2;
    }
    int fd = open(argv[1], O_WRONLY);
    if (fd < 0) { perror("open"); return 1; }

    int i;
    for (i = 2; i < argc; i++) {
        char *a = argv[i];
        if (a[0] == 'w') {
            int ms = atoi(a + 1);
            usleep(ms * 1000);
            continue;
        }
        if (a[0] == 'A' && strchr(a, ':')) {
            /* A<code>:<value> —— 绝对值事件（十字键是 ABS_HAT0X/Y） */
            int code = 0, val = 0;
            sscanf(a + 1, "%d:%d", &code, &val);
            if (emit(fd, EV_ABS, code, val) != 0) { perror("write"); close(fd); return 1; }
            printf("abs %d %d\n", code, val);
            fflush(stdout);
            usleep(60 * 1000);
            continue;
        }
        if (a[0] == 'd' || a[0] == 'u') {
            int code = atoi(a + 1);
            int val = (a[0] == 'd') ? 1 : 0;
            if (emit(fd, EV_KEY, code, val) != 0) { perror("write"); close(fd); return 1; }
            printf("%s %d\n", (a[0] == 'd') ? "down" : "up", code);
            fflush(stdout);
            usleep(60 * 1000);
        }
    }
    close(fd);
    return 0;
}
