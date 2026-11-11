/*
 * a4-evtest —— 极简 evdev 抓包（给手柄标定用）
 *
 * 只打印 EV_KEY / EV_ABS 事件，带相对毫秒时间戳，方便对"谁按了哪个键"。
 *
 * 用法：a4-evtest [/dev/input/event0] [秒数]
 * 输出：每行  <ms> K <code> <value>   或   <ms> A <code> <value>
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <linux/input.h>

int main(int argc, char **argv)
{
    const char *dev = (argc > 1) ? argv[1] : "/dev/input/event0";
    int secs = (argc > 2) ? atoi(argv[2]) : 60;
    int fd = open(dev, O_RDONLY);
    if (fd < 0) { perror("open"); return 1; }

    struct timespec t0, tn;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    printf("# dev=%s secs=%d\n", dev, secs);
    fflush(stdout);

    while (1) {
        struct input_event ev;
        ssize_t n = read(fd, &ev, sizeof(ev));
        if (n != (ssize_t)sizeof(ev)) continue;

        clock_gettime(CLOCK_MONOTONIC, &tn);
        long ms = (tn.tv_sec - t0.tv_sec) * 1000L + (tn.tv_nsec - t0.tv_nsec) / 1000000L;

        if (ev.type == EV_KEY) {
            printf("%ld K %u %d\n", ms, ev.code, ev.value);
            fflush(stdout);
        } else if (ev.type == EV_ABS) {
            printf("%ld A %u %d\n", ms, ev.code, ev.value);
            fflush(stdout);
        } else if (ev.type == EV_SYN && ev.code == SYN_REPORT) {
            /* 心跳：每 5 秒打一个点，确认还在跑 */
            static long last = -99999;
            if (ms - last > 5000) { last = ms; printf("%ld .\n", ms); fflush(stdout); }
        }
        if (ms > (long)secs * 1000) break;
    }
    close(fd);
    printf("# done\n");
    return 0;
}
