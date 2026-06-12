/*
 * Minimal Redroid legacy sensors HAL.
 *
 * Purpose: give Android sensorservice a real native backend when Redroid has
 * no /vendor sensors HAL.  This is intentionally dependency-free so it can be
 * built like libfakemem with host gcc and loaded by Android's linker.
 *
 * Build:
 *   gcc -shared -fPIC -nostdlib -fno-stack-protector \
 *       -Wl,--hash-style=sysv -o sensors.redroid.so sensors_redroid.c
 */

typedef signed char int8_t;
typedef unsigned char uint8_t;
typedef unsigned short uint16_t;
typedef int int32_t;
typedef unsigned int uint32_t;
typedef long long int64_t;
typedef unsigned long size_t;

#define NULL ((void *)0)

#define HARDWARE_MODULE_TAG 0x48574d54U /* 'HWMT' */
#define HARDWARE_DEVICE_TAG 0x48574454U /* 'HWDT' */
#define SENSORS_HARDWARE_MODULE_ID "sensors"
#define SENSORS_HARDWARE_POLL "poll"

#define SENSOR_TYPE_ACCELEROMETER 1
#define SENSOR_TYPE_MAGNETIC_FIELD 2
#define SENSOR_TYPE_ORIENTATION 3
#define SENSOR_TYPE_GYROSCOPE 4
#define SENSOR_TYPE_LIGHT 5
#define SENSOR_TYPE_GRAVITY 9
#define SENSOR_TYPE_LINEAR_ACCELERATION 10
#define SENSOR_TYPE_ROTATION_VECTOR 11
#define SENSOR_TYPE_GAME_ROTATION_VECTOR 15

#define SENSOR_STATUS_ACCURACY_HIGH 3

#define SYS_nanosleep 35
#define SYS_clock_gettime 228
#define CLOCK_MONOTONIC 1

struct timespec {
    long tv_sec;
    long tv_nsec;
};

static inline long _sc2(long nr, long a1, long a2) {
    long ret;
    __asm__ volatile("syscall"
        : "=a"(ret) : "0"(nr), "D"(a1), "S"(a2)
        : "rcx", "r11", "memory");
    return ret;
}

static int64_t now_ns(void) {
    struct timespec ts;
    if (_sc2(SYS_clock_gettime, CLOCK_MONOTONIC, (long)&ts) == 0)
        return (int64_t)ts.tv_sec * 1000000000LL + (int64_t)ts.tv_nsec;
    return 0;
}

static void sleep_20ms(void) {
    struct timespec req;
    req.tv_sec = 0;
    req.tv_nsec = 20000000L;
    _sc2(SYS_nanosleep, (long)&req, 0);
}

struct hw_module_t;
struct hw_device_t;

struct hw_module_methods_t {
    int (*open)(const struct hw_module_t *module, const char *id, struct hw_device_t **device);
};

struct hw_module_t {
    uint32_t tag;
    uint16_t module_api_version;
    uint16_t hal_api_version;
    const char *id;
    const char *name;
    const char *author;
    struct hw_module_methods_t *methods;
    void *dso;
    uint32_t reserved[32 - 7];
};

struct hw_device_t {
    uint32_t tag;
    uint32_t version;
    struct hw_module_t *module;
    uint32_t reserved[12];
    int (*close)(struct hw_device_t *device);
};

struct sensor_t {
    const char *name;
    const char *vendor;
    int version;
    int handle;
    int type;
    float maxRange;
    float resolution;
    float power;
    int32_t minDelay;
    uint32_t fifoReservedEventCount;
    uint32_t fifoMaxEventCount;
    const char *stringType;
    const char *requiredPermission;
    int32_t maxDelay;
    uint32_t flags;
    void *reserved[2];
};

struct sensors_vec_t {
    union { float v[3]; struct { float x, y, z; }; struct { float azimuth, pitch, roll; }; };
    int8_t status;
    uint8_t reserved[3];
};

struct sensors_event_t {
    int32_t version;
    int32_t sensor;
    int32_t type;
    int32_t reserved0;
    int64_t timestamp;
    union {
        float data[16];
        struct sensors_vec_t acceleration;
        struct sensors_vec_t magnetic;
        struct sensors_vec_t orientation;
        struct sensors_vec_t gyro;
        float light;
    };
    uint32_t flags;
    int32_t reserved1[3];
};

struct sensors_poll_device_t {
    struct hw_device_t common;
    int (*activate)(struct sensors_poll_device_t *dev, int handle, int enabled);
    int (*setDelay)(struct sensors_poll_device_t *dev, int handle, int64_t ns);
    int (*poll)(struct sensors_poll_device_t *dev, struct sensors_event_t *data, int count);
};

struct sensors_poll_device_1_t {
    union { struct sensors_poll_device_t v0; struct { struct hw_device_t common; int (*activate)(struct sensors_poll_device_t *, int, int); int (*setDelay)(struct sensors_poll_device_t *, int, int64_t); int (*poll)(struct sensors_poll_device_t *, struct sensors_event_t *, int); }; };
    int (*batch)(struct sensors_poll_device_1_t *dev, int handle, int flags, int64_t period_ns, int64_t timeout);
    int (*flush)(struct sensors_poll_device_1_t *dev, int handle);
    int (*inject_sensor_data)(struct sensors_poll_device_1_t *dev, const struct sensors_event_t *data);
    int (*register_direct_channel)(struct sensors_poll_device_1_t *dev, const void *mem, int channel_handle);
    int (*config_direct_report)(struct sensors_poll_device_1_t *dev, int sensor_handle, int channel_handle, const void *rate);
};

struct sensors_module_t {
    struct hw_module_t common;
    int (*get_sensors_list)(struct sensors_module_t *module, struct sensor_t const **list);
    int (*set_operation_mode)(unsigned int mode);
};

static struct sensor_t sensor_list[] = {
    {"BMI270 Accelerometer", "Bosch", 1, 1, SENSOR_TYPE_ACCELEROMETER, 39.2f, 0.01f, 0.18f, 10000, 0, 256, "android.sensor.accelerometer", "", 200000, 0, {0, 0}},
    {"BMI270 Gyroscope", "Bosch", 1, 2, SENSOR_TYPE_GYROSCOPE, 34.9f, 0.001f, 0.80f, 10000, 0, 256, "android.sensor.gyroscope", "", 200000, 0, {0, 0}},
    {"AK09918 Magnetometer", "AKM", 1, 3, SENSOR_TYPE_MAGNETIC_FIELD, 4912.0f, 0.15f, 0.35f, 20000, 0, 256, "android.sensor.magnetic_field", "", 200000, 0, {0, 0}},
    {"Gravity Sensor", "Damru", 1, 4, SENSOR_TYPE_GRAVITY, 39.2f, 0.01f, 0.18f, 10000, 0, 256, "android.sensor.gravity", "", 200000, 0, {0, 0}},
    {"Linear Acceleration Sensor", "Damru", 1, 5, SENSOR_TYPE_LINEAR_ACCELERATION, 39.2f, 0.01f, 0.18f, 10000, 0, 256, "android.sensor.linear_acceleration", "", 200000, 0, {0, 0}},
    {"Rotation Vector Sensor", "Damru", 1, 6, SENSOR_TYPE_ROTATION_VECTOR, 1.0f, 0.0001f, 0.20f, 10000, 0, 256, "android.sensor.rotation_vector", "", 200000, 0, {0, 0}},
    {"Game Rotation Vector Sensor", "Damru", 1, 7, SENSOR_TYPE_GAME_ROTATION_VECTOR, 1.0f, 0.0001f, 0.20f, 10000, 0, 256, "android.sensor.game_rotation_vector", "", 200000, 0, {0, 0}},
    {"Orientation Sensor", "Damru", 1, 8, SENSOR_TYPE_ORIENTATION, 360.0f, 0.1f, 0.20f, 10000, 0, 256, "android.sensor.orientation", "", 200000, 0, {0, 0}},
    {"Ambient Light Sensor", "AMS", 1, 9, SENSOR_TYPE_LIGHT, 10000.0f, 1.0f, 0.10f, 0, 0, 32, "android.sensor.light", "", 0, 0, {0, 0}},
};

static int active[16] = {0};
static int seq = 0;

static int module_get_sensors_list(struct sensors_module_t *module, struct sensor_t const **list) {
    (void)module;
    *list = sensor_list;
    return (int)(sizeof(sensor_list) / sizeof(sensor_list[0]));
}

static int module_set_operation_mode(unsigned int mode) {
    (void)mode;
    return 0;
}

static int dev_close(struct hw_device_t *device) {
    (void)device;
    return 0;
}

static int dev_activate(struct sensors_poll_device_t *dev, int handle, int enabled) {
    (void)dev;
    if (handle >= 0 && handle < 16)
        active[handle] = enabled ? 1 : 0;
    return 0;
}

static int dev_set_delay(struct sensors_poll_device_t *dev, int handle, int64_t ns) {
    (void)dev; (void)handle; (void)ns;
    return 0;
}

static void fill_event(struct sensors_event_t *e, int handle) {
    int i;
    for (i = 0; i < (int)(sizeof(*e) / sizeof(int32_t)); i++)
        ((int32_t *)e)[i] = 0;
    e->version = (int32_t)sizeof(struct sensors_event_t);
    e->sensor = handle;
    e->type = sensor_list[handle - 1].type;
    e->timestamp = now_ns();
    e->acceleration.status = SENSOR_STATUS_ACCURACY_HIGH;

    switch (handle) {
    case 1: e->acceleration.x = -0.20f; e->acceleration.y = -0.45f; e->acceleration.z = 9.80f; break;
    case 2: e->gyro.x = 0.002f; e->gyro.y = -0.003f; e->gyro.z = 0.001f; e->gyro.status = SENSOR_STATUS_ACCURACY_HIGH; break;
    case 3: e->magnetic.x = 26.3f; e->magnetic.y = -4.2f; e->magnetic.z = -37.1f; e->magnetic.status = SENSOR_STATUS_ACCURACY_HIGH; break;
    case 4: e->acceleration.x = -0.21f; e->acceleration.y = -0.45f; e->acceleration.z = 9.80f; break;
    case 5: e->acceleration.x = 0.01f; e->acceleration.y = -0.01f; e->acceleration.z = 0.0f; break;
    case 6: e->data[0] = 0.02f; e->data[1] = -0.01f; e->data[2] = 0.16f; e->data[3] = 0.987f; break;
    case 7: e->data[0] = 0.02f; e->data[1] = -0.01f; e->data[2] = 0.16f; e->data[3] = 0.987f; break;
    case 8: e->orientation.azimuth = 18.0f; e->orientation.pitch = 2.4f; e->orientation.roll = -1.8f; e->orientation.status = SENSOR_STATUS_ACCURACY_HIGH; break;
    case 9: e->light = 320.0f; break;
    }
    seq++;
    if (seq > 1000000) seq = 0;
}

static int dev_poll(struct sensors_poll_device_t *dev, struct sensors_event_t *data, int count) {
    int handle;
    (void)dev;
    if (count <= 0) return 0;
    sleep_20ms();
    for (handle = 1; handle <= 9; handle++) {
        if (active[handle]) {
            fill_event(data, handle);
            return 1;
        }
    }
    fill_event(data, 1);
    return 1;
}

static int dev_batch(struct sensors_poll_device_1_t *dev, int handle, int flags, int64_t period_ns, int64_t timeout) {
    (void)dev; (void)handle; (void)flags; (void)period_ns; (void)timeout;
    return 0;
}

static int dev_flush(struct sensors_poll_device_1_t *dev, int handle) {
    (void)dev; (void)handle;
    return 0;
}

static int dev_inject(struct sensors_poll_device_1_t *dev, const struct sensors_event_t *data) {
    (void)dev; (void)data;
    return -22;
}

static int dev_register_direct(struct sensors_poll_device_1_t *dev, const void *mem, int channel_handle) {
    (void)dev; (void)mem; (void)channel_handle;
    return -22;
}

static int dev_config_direct(struct sensors_poll_device_1_t *dev, int sensor_handle, int channel_handle, const void *rate) {
    (void)dev; (void)sensor_handle; (void)channel_handle; (void)rate;
    return -22;
}

static struct sensors_poll_device_1_t poll_dev;

static int module_open(const struct hw_module_t *module, const char *id, struct hw_device_t **device) {
    (void)id;
    poll_dev.common.tag = HARDWARE_DEVICE_TAG;
    poll_dev.common.version = 0x0104;
    poll_dev.common.module = (struct hw_module_t *)module;
    poll_dev.common.close = dev_close;
    poll_dev.activate = dev_activate;
    poll_dev.setDelay = dev_set_delay;
    poll_dev.poll = dev_poll;
    poll_dev.batch = dev_batch;
    poll_dev.flush = dev_flush;
    poll_dev.inject_sensor_data = dev_inject;
    poll_dev.register_direct_channel = dev_register_direct;
    poll_dev.config_direct_report = dev_config_direct;
    *device = &poll_dev.common;
    return 0;
}

static struct hw_module_methods_t module_methods = { module_open };

__attribute__((visibility("default")))
struct sensors_module_t HAL_MODULE_INFO_SYM = {
    .common = {
        .tag = HARDWARE_MODULE_TAG,
        .module_api_version = 1,
        .hal_api_version = 0,
        .id = SENSORS_HARDWARE_MODULE_ID,
        .name = "Damru Redroid Virtual Sensors",
        .author = "Damru Framework",
        .methods = &module_methods,
        .dso = NULL,
    },
    .get_sensors_list = module_get_sensors_list,
    .set_operation_mode = module_set_operation_mode,
};
