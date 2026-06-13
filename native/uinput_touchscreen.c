// Minimal virtual multi-touch touchscreen for Redroid workers.
//
// Runs inside the Android container and registers a direct multi-touch uinput
// device so native Android/WebView input capabilities look like a phone rather
// than a keyboard-only virtual display.
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <linux/uinput.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static volatile sig_atomic_t keep_running = 1;

static void on_signal(int sig) {
    (void)sig;
    keep_running = 0;
}

static int set_bit(int fd, unsigned long request, int value, const char *label) {
    if (ioctl(fd, request, value) < 0) {
        fprintf(stderr, "ioctl %s(%d) failed: %s\n", label, value, strerror(errno));
        return -1;
    }
    return 0;
}

static void configure_abs(struct uinput_user_dev *dev, int code, int min, int max) {
    dev->absmin[code] = min;
    dev->absmax[code] = max;
    dev->absfuzz[code] = 0;
    dev->absflat[code] = 0;
}

int main(int argc, char **argv) {
    int width = argc > 1 ? atoi(argv[1]) : 1080;
    int height = argc > 2 ? atoi(argv[2]) : 2400;
    int slots = argc > 3 ? atoi(argv[3]) : 10;
    if (width <= 0) width = 1080;
    if (height <= 0) height = 2400;
    if (slots < 2) slots = 5;
    if (slots > 10) slots = 10;

    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);

    int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
    if (fd < 0) {
        fprintf(stderr, "open /dev/uinput failed: %s\n", strerror(errno));
        return 1;
    }

    if (set_bit(fd, UI_SET_EVBIT, EV_KEY, "EV_KEY") < 0 ||
        set_bit(fd, UI_SET_KEYBIT, BTN_TOUCH, "BTN_TOUCH") < 0 ||
        set_bit(fd, UI_SET_KEYBIT, BTN_TOOL_FINGER, "BTN_TOOL_FINGER") < 0 ||
        set_bit(fd, UI_SET_EVBIT, EV_ABS, "EV_ABS") < 0 ||
        set_bit(fd, UI_SET_ABSBIT, ABS_X, "ABS_X") < 0 ||
        set_bit(fd, UI_SET_ABSBIT, ABS_Y, "ABS_Y") < 0 ||
        set_bit(fd, UI_SET_ABSBIT, ABS_MT_SLOT, "ABS_MT_SLOT") < 0 ||
        set_bit(fd, UI_SET_ABSBIT, ABS_MT_TRACKING_ID, "ABS_MT_TRACKING_ID") < 0 ||
        set_bit(fd, UI_SET_ABSBIT, ABS_MT_POSITION_X, "ABS_MT_POSITION_X") < 0 ||
        set_bit(fd, UI_SET_ABSBIT, ABS_MT_POSITION_Y, "ABS_MT_POSITION_Y") < 0 ||
        set_bit(fd, UI_SET_ABSBIT, ABS_MT_TOUCH_MAJOR, "ABS_MT_TOUCH_MAJOR") < 0 ||
        set_bit(fd, UI_SET_ABSBIT, ABS_MT_PRESSURE, "ABS_MT_PRESSURE") < 0) {
        close(fd);
        return 1;
    }

#ifdef UI_SET_PROPBIT
    if (ioctl(fd, UI_SET_PROPBIT, INPUT_PROP_DIRECT) < 0) {
        fprintf(stderr, "ioctl INPUT_PROP_DIRECT failed: %s\n", strerror(errno));
    }
#endif

    struct uinput_user_dev dev;
    memset(&dev, 0, sizeof(dev));
    snprintf(dev.name, sizeof(dev.name), "damru virtual touchscreen");
    dev.id.bustype = BUS_I2C;
    dev.id.vendor = 0x18d1;
    dev.id.product = 0x4ee1;
    dev.id.version = 1;

    configure_abs(&dev, ABS_X, 0, width - 1);
    configure_abs(&dev, ABS_Y, 0, height - 1);
    configure_abs(&dev, ABS_MT_SLOT, 0, slots - 1);
    configure_abs(&dev, ABS_MT_TRACKING_ID, 0, 65535);
    configure_abs(&dev, ABS_MT_POSITION_X, 0, width - 1);
    configure_abs(&dev, ABS_MT_POSITION_Y, 0, height - 1);
    configure_abs(&dev, ABS_MT_TOUCH_MAJOR, 0, 255);
    configure_abs(&dev, ABS_MT_PRESSURE, 0, 255);

    if (write(fd, &dev, sizeof(dev)) != sizeof(dev)) {
        fprintf(stderr, "write uinput_user_dev failed: %s\n", strerror(errno));
        close(fd);
        return 1;
    }
    if (ioctl(fd, UI_DEV_CREATE) < 0) {
        fprintf(stderr, "UI_DEV_CREATE failed: %s\n", strerror(errno));
        close(fd);
        return 1;
    }

    fprintf(stdout, "created damru virtual touchscreen %dx%d slots=%d\n", width, height, slots);
    fflush(stdout);
    while (keep_running) {
        sleep(60);
    }
    ioctl(fd, UI_DEV_DESTROY);
    close(fd);
    return 0;
}
