/*
 * a4-exitd —— 手柄"退出游戏"守护
 *
 * 为什么需要它：这台机器上的 RetroArch 1.9 里 `input_exit_emulator_btn`
 * 怎么配都不触发（把 8 个候选热键 × Start 全试过，一次都没退出去；
 * 详见 report/28 §17）。但热键本身是活的（能开菜单），所以不是手柄问题，
 * 是这个 RA 构建的退出动作失灵。
 *
 * 做法：直接在 evdev 层看按键，命中组合就 kill 掉 retroarch，
 * 由 histb-emuelec-supervisor 把 ES 拉起来 —— 不依赖 RetroArch 的任何配置。
 *
 * 支持的组合（任一）：
 *   LB(BTN_TL 310)      + Start(BTN_START 315)
 *   R3(BTN_THUMBR 318)  + Start(BTN_START 315)
 *
 * 只读 /dev/input/event0，不 grab，不影响 RetroArch 自己收键。
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <signal.h>
#include <dirent.h>
#include <stdarg.h>
#include <linux/input.h>

#define DEV_DEFAULT "/dev/input/event0"
#define LOG_FILE    "/storage/ee/logs/exit.log"

#define BTN_TL_CODE      310
#define BTN_THUMBR_CODE  318
#define BTN_START_CODE   315

static long now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000L + ts.tv_nsec / 1000000L;
}

static void alog(const char *fmt, ...)
{
    FILE *f = fopen(LOG_FILE, "a");
    va_list ap;
    if (!f) return;
    va_start(ap, fmt);
    vfprintf(f, fmt, ap);
    va_end(ap);
    fputc('\n', f);
    fclose(f);
}

/* 找 retroarch 的主进程（cmdline 里带 bin/retroarch） */
static pid_t find_retroarch(void)
{
    DIR *d = opendir("/proc");
    struct dirent *e;
    pid_t found = -1;
    if (!d) return -1;
    while ((e = readdir(d))) {
        char path[64], buf[512];
        int fd, n;
        if (e->d_name[0] < '0' || e->d_name[0] > '9') continue;
        snprintf(path, sizeof(path), "/proc/%s/cmdline", e->d_name);
        fd = open(path, O_RDONLY);
        if (fd < 0) continue;
        n = read(fd, buf, sizeof(buf) - 1);
        close(fd);
        if (n <= 0) continue;
        buf[n] = 0;
        /* cmdline 是 NUL 分隔的，strstr 会在第一个 NUL 停下 —— 先把 NUL 换成空格 */
        {
            int k;
            for (k = 0; k < n - 1; k++)
                if (buf[k] == '\0') buf[k] = ' ';
        }
        if (strstr(buf, "retroarch") && !strstr(buf, "run-retroarch")) {
            found = atoi(e->d_name);
            break;
        }
    }
    closedir(d);
    return found;
}

int main(int argc, char **argv)
{
    const char *dev = (argc > 1) ? argv[1] : DEV_DEFAULT;
    int fd = open(dev, O_RDONLY);
    if (fd < 0) { perror("open"); return 1; }

    alog("a4-exitd started (dev=%s)", dev);

    int lb = 0, r3 = 0, st = 0;
    long lb_t = 0, r3_t = 0, st_t = 0;
    long blocked_until = 0;

    while (1) {
        struct input_event ev;
        ssize_t n = read(fd, &ev, sizeof(ev));
        if (n != (ssize_t)sizeof(ev)) continue;
        if (ev.type != EV_KEY) continue;

        if (ev.code == BTN_TL_CODE)      { lb = ev.value; lb_t = now_ms(); }
        else if (ev.code == BTN_THUMBR_CODE) { r3 = ev.value; r3_t = now_ms(); }
        else if (ev.code == BTN_START_CODE)  { st = ev.value; st_t = now_ms(); }
        else continue;

        long t = now_ms();
        if (t < blocked_until) continue;
        if (!st) continue;

        int hit = 0;
        const char *who = "";
        if (lb && labs(st_t - lb_t) < 400) { hit = 1; who = "LB+Start"; }
        else if (r3 && labs(st_t - r3_t) < 400) { hit = 1; who = "R3+Start"; }
        if (!hit) continue;

        pid_t pid = find_retroarch();
        if (pid > 0) {
            alog("%ld %s -> kill retroarch pid=%d", t, who, (int)pid);
            kill(pid, SIGTERM);
            blocked_until = t + 2500;
        } else {
            alog("%ld %s (no retroarch running)", t, who);
            blocked_until = t + 1000;
        }
        lb = r3 = st = 0;
    }
    close(fd);
    return 0;
}
