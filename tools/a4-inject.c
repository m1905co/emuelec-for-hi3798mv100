/* a4-inject: create a virtual keyboard, wait, then press a key once.
 * usage: a4-inject [delay_secs] [keyname]
 *   keyname: enter (default) | down | up | left | right | esc
 */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <linux/uinput.h>
#include <sys/ioctl.h>

static void emit(int fd, int type, int code, int val)
{
    struct input_event ie;
    memset(&ie, 0, sizeof(ie));
    ie.type = type;
    ie.code = code;
    ie.value = val;
    write(fd, &ie, sizeof(ie));
}

static int keycode(const char *n)
{
    if (!n) return KEY_ENTER;
    if (!strcmp(n, "down"))  return KEY_DOWN;
    if (!strcmp(n, "up"))    return KEY_UP;
    if (!strcmp(n, "left"))  return KEY_LEFT;
    if (!strcmp(n, "right")) return KEY_RIGHT;
    if (!strcmp(n, "esc"))   return KEY_ESC;
    return KEY_ENTER;
}

int main(int argc, char **argv)
{
    int delay = argc > 1 ? atoi(argv[1]) : 20;
    int code  = keycode(argc > 2 ? argv[2] : NULL);

    int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
    if (fd < 0) { perror("open /dev/uinput"); return 1; }

    ioctl(fd, UI_SET_EVBIT, EV_KEY);
    ioctl(fd, UI_SET_KEYBIT, KEY_ENTER);
    ioctl(fd, UI_SET_KEYBIT, KEY_UP);
    ioctl(fd, UI_SET_KEYBIT, KEY_DOWN);
    ioctl(fd, UI_SET_KEYBIT, KEY_LEFT);
    ioctl(fd, UI_SET_KEYBIT, KEY_RIGHT);
    ioctl(fd, UI_SET_KEYBIT, KEY_ESC);

    struct uinput_user_dev dev;
    memset(&dev, 0, sizeof(dev));
    snprintf(dev.name, UINPUT_MAX_NAME_SIZE, "a4-inject-kbd");
    dev.id.bustype = BUS_USB;
    dev.id.vendor  = 0x1234;
    dev.id.product = 0x5678;
    dev.id.version = 1;
    write(fd, &dev, sizeof(dev));

    if (ioctl(fd, UI_DEV_CREATE) < 0) { perror("UI_DEV_CREATE"); return 1; }
    printf("a4-inject: device created, waiting %ds before key %d\n", delay, code);
    fflush(stdout);

    sleep(delay);

    emit(fd, EV_KEY, code, 1);
    emit(fd, EV_SYN, SYN_REPORT, 0);
    usleep(90000);
    emit(fd, EV_KEY, code, 0);
    emit(fd, EV_SYN, SYN_REPORT, 0);
    printf("a4-inject: key sent\n");
    fflush(stdout);

    sleep(3);
    ioctl(fd, UI_DEV_DESTROY);
    close(fd);
    return 0;
}
