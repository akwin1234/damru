// Damru AIDL sensors HAL prototype for Redroid Android 14+.
//
// Registers android.hardware.sensors.ISensors/default and writes natural
// low-motion phone sensor events into the AIDL FMQ. Intended for baking into
// Redroid /vendor with a VINTF manifest and init rc. No browser JS injection.

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <map>
#include <memory>
#include <mutex>
#include <random>
#include <set>
#include <string>
#include <thread>
#include <vector>

#include <errno.h>
#include <stdio.h>
#include <linux/futex.h>
#include <sys/syscall.h>
#include <unistd.h>

#include <android/binder_interface_utils.h>
#include <android/binder_status.h>
#include <sys/system_properties.h>
#include <aidl/android/hardware/sensors/BnSensors.h>
#include <aidl/android/hardware/sensors/Event.h>
#include <aidl/android/hardware/sensors/ISensors.h>
#include <aidl/android/hardware/sensors/ISensorsCallback.h>
#include <aidl/android/hardware/sensors/SensorInfo.h>
#include <aidl/android/hardware/sensors/SensorStatus.h>
#include <aidl/android/hardware/sensors/SensorType.h>
#define private public
#include <fmq/AidlMessageQueue.h>
#undef private

using aidl::android::hardware::common::fmq::MQDescriptor;
using aidl::android::hardware::common::fmq::SynchronizedReadWrite;
using aidl::android::hardware::sensors::BnSensors;
using aidl::android::hardware::sensors::Event;
using aidl::android::hardware::sensors::ISensors;
using aidl::android::hardware::sensors::ISensorsCallback;
using aidl::android::hardware::sensors::SensorInfo;
using aidl::android::hardware::sensors::SensorStatus;
using aidl::android::hardware::sensors::SensorType;
using ndk::ScopedAStatus;

extern "C" {
int32_t AServiceManager_addService(AIBinder* binder, const char* instance);
bool AServiceManager_isDeclared(const char* instance);
void AIBinder_markVintfStability(AIBinder* binder);
void ABinderProcess_setThreadPoolMaxThreadCount(int32_t numThreads);
void ABinderProcess_startThreadPool();
void ABinderProcess_joinThreadPool();
}

namespace android::hardware::details {
void logError(const std::string&) {}
void errorWriteLog(int, const char*) {}
void check(bool exp, const char*) {
    if (!exp) std::abort();
}
}

namespace android::hardware {
EventFlag::EventFlag(std::atomic<uint32_t>* efWordPtr, status_t* status) : mEfWordPtr(efWordPtr) {
    if (status) *status = efWordPtr ? NO_ERROR : BAD_VALUE;
}
EventFlag::~EventFlag() {}
status_t EventFlag::createEventFlag(std::atomic<uint32_t>* efWordPtr, EventFlag** ef) {
    if (!ef || !efWordPtr) return BAD_VALUE;
    status_t status = NO_ERROR;
    *ef = new EventFlag(efWordPtr, &status);
    if (status != NO_ERROR) {
        delete *ef;
        *ef = nullptr;
    }
    return status;
}
status_t EventFlag::deleteEventFlag(EventFlag** ef) {
    if (!ef || !*ef) return BAD_VALUE;
    delete *ef;
    *ef = nullptr;
    return NO_ERROR;
}
status_t EventFlag::wake(uint32_t bitmask) {
    if (!mEfWordPtr || bitmask == 0) return BAD_VALUE;
    mEfWordPtr->fetch_or(bitmask, std::memory_order_release);
    syscall(SYS_futex, reinterpret_cast<int*>(mEfWordPtr), FUTEX_WAKE, INT32_MAX, nullptr, nullptr, 0);
    return NO_ERROR;
}
status_t EventFlag::wait(uint32_t bitmask, uint32_t* efState, int64_t timeOutNanoSeconds, bool retry) {
    if (!mEfWordPtr || !efState || bitmask == 0) return BAD_VALUE;
    for (;;) {
        uint32_t old = mEfWordPtr->load(std::memory_order_acquire);
        uint32_t bits = old & bitmask;
        if (bits) {
            mEfWordPtr->fetch_and(~bits, std::memory_order_acq_rel);
            *efState = bits;
            return NO_ERROR;
        }
        timespec ts{};
        timespec* tsp = nullptr;
        if (timeOutNanoSeconds > 0) {
            ts.tv_sec = timeOutNanoSeconds / 1000000000LL;
            ts.tv_nsec = timeOutNanoSeconds % 1000000000LL;
            tsp = &ts;
        }
        int rc = syscall(SYS_futex, reinterpret_cast<int*>(mEfWordPtr), FUTEX_WAIT, old, tsp, nullptr, 0);
        if (rc == -1 && errno == ETIMEDOUT) return TIMED_OUT;
        if (rc == -1 && errno != EINTR && errno != EAGAIN) return -errno;
        if (!retry) return -errno;
    }
}
status_t EventFlag::waitHelper(uint32_t bitmask, uint32_t* efState, int64_t timeOutNanoSeconds) {
    return wait(bitmask, efState, timeOutNanoSeconds, true);
}
status_t EventFlag::unmapEventFlagWord(std::atomic<uint32_t>*, bool*) { return NO_ERROR; }
void EventFlag::addNanosecondsToCurrentTime(int64_t nanoseconds, struct timespec* timeAbs) {
    clock_gettime(CLOCK_MONOTONIC, timeAbs);
    timeAbs->tv_sec += nanoseconds / 1000000000LL;
    timeAbs->tv_nsec += nanoseconds % 1000000000LL;
    if (timeAbs->tv_nsec >= 1000000000L) {
        timeAbs->tv_sec += 1;
        timeAbs->tv_nsec -= 1000000000L;
    }
}
}

namespace {
using EventQueue = android::AidlMessageQueue<Event, SynchronizedReadWrite>;

constexpr int kAccel = 1;
constexpr int kGyro = 2;
constexpr int kMag = 3;
constexpr int kGravity = 4;
constexpr int kLinear = 5;
constexpr int kRotation = 6;
constexpr int kGameRotation = 7;
constexpr int kLight = 8;
constexpr uint32_t kReadAndProcess = 1;
constexpr uint32_t kEventsRead = 2;

int64_t now_ns() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
                   std::chrono::steady_clock::now().time_since_epoch())
            .count();
}

float clampf(float v, float lo, float hi) { return std::max(lo, std::min(hi, v)); }

SensorInfo make_sensor(int handle, SensorType type, const char* name, const char* vendor,
                       const char* type_str, float max_range, float resolution, float power,
                       int min_delay_us, int flags = SensorInfo::SENSOR_FLAG_BITS_CONTINUOUS_MODE) {
    SensorInfo s;
    s.sensorHandle = handle;
    s.name = name;
    s.vendor = vendor;
    s.version = 1;
    s.type = type;
    s.typeAsString = type_str;
    s.maxRange = max_range;
    s.resolution = resolution;
    s.power = power;
    s.minDelayUs = min_delay_us;
    s.fifoReservedEventCount = 0;
    s.fifoMaxEventCount = 512;
    s.requiredPermission = "";
    s.maxDelayUs = std::max(min_delay_us, 200000);
    s.flags = flags;
    return s;
}

Event::EventPayload::Vec3 vec3(float x, float y, float z) {
    Event::EventPayload::Vec3 v;
    v.x = x;
    v.y = y;
    v.z = z;
    v.status = SensorStatus::ACCURACY_HIGH;
    return v;
}

Event::EventPayload::Vec4 vec4(float x, float y, float z, float w) {
    Event::EventPayload::Vec4 v;
    v.x = x;
    v.y = y;
    v.z = z;
    v.w = w;
    return v;
}

Event::EventPayload::Data data4(float x, float y, float z, float w) {
    Event::EventPayload::Data d;
    d.values[0] = x;
    d.values[1] = y;
    d.values[2] = z;
    d.values[3] = w;
    d.values[4] = -1.0f;
    return d;
}

Event::EventPayload::MetaData flush_meta() {
    Event::EventPayload::MetaData m;
    m.what = Event::EventPayload::MetaData::MetaDataEventType::META_DATA_FLUSH_COMPLETE;
    return m;
}

struct Motion {
    float alpha0;
    float beta0;
    float gamma0;
    float alpha_drift;
    float beta_drift;
    float gamma_drift;
    float tremor;
    float linear;
    float phases[12];
    float freqs[12];
    float mag_x;
    float mag_y;
    float mag_z;
};

Motion new_motion() {
    char seed_prop[PROP_VALUE_MAX] = {0};
    uint32_t seed = static_cast<uint32_t>(now_ns());
    if (__system_property_get("persist.damru.sensor.seed", seed_prop) > 0) {
        for (const char* c = seed_prop; *c; ++c) seed = seed * 131u + static_cast<uint8_t>(*c);
    } else {
        std::random_device rd;
        seed ^= rd();
    }
    std::mt19937 rng(seed);
    auto uf = [&](float a, float b) { return std::uniform_real_distribution<float>(a, b)(rng); };
    Motion m{};
    m.alpha0 = uf(0.0f, 360.0f);
    m.beta0 = uf(-9.0f, 13.0f);
    m.gamma0 = uf(-7.0f, 7.0f);
    m.alpha_drift = uf(-0.018f, 0.018f);
    m.beta_drift = uf(-0.010f, 0.010f);
    m.gamma_drift = uf(-0.010f, 0.010f);
    float stillness = uf(0.65f, 1.35f);
    m.tremor = uf(0.10f, 0.32f) * stillness;
    m.linear = uf(0.010f, 0.045f) * stillness;
    for (float& p : m.phases) p = uf(0.0f, static_cast<float>(2.0 * M_PI));
    for (int i = 0; i < 6; ++i) m.freqs[i] = uf(0.06f, 0.32f);
    for (int i = 6; i < 12; ++i) m.freqs[i] = uf(1.7f, 4.1f);
    float heading = uf(0.0f, static_cast<float>(2.0 * M_PI));
    float strength = uf(28.0f, 52.0f);
    m.mag_x = std::cos(heading) * strength;
    m.mag_y = std::sin(heading) * strength * 0.35f;
    m.mag_z = -uf(31.0f, 43.0f);
    return m;
}

Event make_event(int handle, SensorType type, Event::EventPayload payload) {
    Event e;
    e.timestamp = now_ns();
    e.sensorHandle = handle;
    e.sensorType = type;
    e.payload = std::move(payload);
    return e;
}

void euler_to_quat(float alpha_deg, float beta_deg, float gamma_deg, float* x, float* y, float* z, float* w) {
    float az = alpha_deg * static_cast<float>(M_PI / 180.0) * 0.5f;
    float bx = beta_deg * static_cast<float>(M_PI / 180.0) * 0.5f;
    float gy = gamma_deg * static_cast<float>(M_PI / 180.0) * 0.5f;
    float cz = std::cos(az), sz = std::sin(az);
    float cx = std::cos(bx), sx = std::sin(bx);
    float cy = std::cos(gy), sy = std::sin(gy);
    *x = sx * cy * cz - cx * sy * sz;
    *y = cx * sy * cz + sx * cy * sz;
    *z = cx * cy * sz - sx * sy * cz;
    *w = cx * cy * cz + sx * sy * sz;
}

std::vector<Event> sample_events(const Motion& m, double t, const std::set<int>& active) {
    if (active.empty()) return {};
    float phase = static_cast<float>(t);
    const float* f = m.freqs;
    const float* p = m.phases;
    float slow_a = std::sin(t * f[0] + p[0]) * 1.4f + std::sin(t * f[1] + p[1]) * 0.7f;
    float slow_b = std::sin(t * f[2] + p[2]) * 1.0f + std::cos(t * f[3] + p[3]) * 0.55f;
    float slow_g = std::cos(t * f[4] + p[4]) * 0.9f + std::sin(t * f[5] + p[5]) * 0.45f;
    float fast_b = std::sin(t * f[6] + p[6]) * m.tremor + std::sin(t * f[7] + p[7]) * m.tremor * 0.33f;
    float fast_g = std::cos(t * f[8] + p[8]) * m.tremor + std::sin(t * f[9] + p[9]) * m.tremor * 0.33f;
    float fast_a = std::sin(t * f[10] + p[10]) * m.tremor * 0.7f;
    float alpha = std::fmod(m.alpha0 + phase * m.alpha_drift + slow_a + fast_a + 360.0f, 360.0f);
    float beta = clampf(m.beta0 + phase * m.beta_drift + slow_b + fast_b, -35.0f, 35.0f);
    float gamma = clampf(m.gamma0 + phase * m.gamma_drift + slow_g + fast_g, -28.0f, 28.0f);
    float gx = std::sin(gamma * static_cast<float>(M_PI / 180.0)) * 9.80665f;
    float gy = -std::sin(beta * static_cast<float>(M_PI / 180.0)) * 9.80665f;
    float gz = std::cos(beta * static_cast<float>(M_PI / 180.0)) * std::cos(gamma * static_cast<float>(M_PI / 180.0)) * 9.80665f;
    float lx = std::sin(phase * 1.7f + p[6]) * m.linear;
    float ly = std::cos(phase * 1.3f + p[7]) * m.linear * 0.8f;
    float lz = std::sin(phase * 1.1f + p[8]) * m.linear * 0.55f;
    float db = m.beta_drift + std::cos(t * f[2] + p[2]) * f[2] - std::sin(t * f[3] + p[3]) * f[3] * 0.55f + std::cos(t * f[6] + p[6]) * f[6] * m.tremor;
    float dg = m.gamma_drift - std::sin(t * f[4] + p[4]) * f[4] * 0.9f + std::cos(t * f[5] + p[5]) * f[5] * 0.45f - std::sin(t * f[8] + p[8]) * f[8] * m.tremor;
    float da = m.alpha_drift + std::cos(t * f[0] + p[0]) * f[0] * 1.4f + std::cos(t * f[1] + p[1]) * f[1] * 0.7f;
    float qx, qy, qz, qw;
    euler_to_quat(alpha, beta, gamma, &qx, &qy, &qz, &qw);
    std::vector<Event> out;
    auto has = [&](int h) { return active.count(h) != 0; };
    if (has(kAccel)) out.push_back(make_event(kAccel, SensorType::ACCELEROMETER, Event::EventPayload::make<Event::EventPayload::vec3>(vec3(gx + lx, gy + ly, gz + lz))));
    if (has(kGravity)) out.push_back(make_event(kGravity, SensorType::GRAVITY, Event::EventPayload::make<Event::EventPayload::vec3>(vec3(gx, gy, gz))));
    if (has(kLinear)) out.push_back(make_event(kLinear, SensorType::LINEAR_ACCELERATION, Event::EventPayload::make<Event::EventPayload::vec3>(vec3(lx, ly, lz))));
    if (has(kGyro)) out.push_back(make_event(kGyro, SensorType::GYROSCOPE, Event::EventPayload::make<Event::EventPayload::vec3>(vec3(db * static_cast<float>(M_PI / 180.0), dg * static_cast<float>(M_PI / 180.0), da * static_cast<float>(M_PI / 180.0)))));
    if (has(kMag)) out.push_back(make_event(kMag, SensorType::MAGNETIC_FIELD, Event::EventPayload::make<Event::EventPayload::vec3>(vec3(m.mag_x + std::sin(phase * 0.09f + p[9]) * 0.45f, m.mag_y + std::cos(phase * 0.08f + p[10]) * 0.35f, m.mag_z + std::sin(phase * 0.07f + p[11]) * 0.40f))));
    if (has(kRotation)) out.push_back(make_event(kRotation, SensorType::ROTATION_VECTOR, Event::EventPayload::make<Event::EventPayload::data>(data4(qx, qy, qz, qw))));
    if (has(kGameRotation)) out.push_back(make_event(kGameRotation, SensorType::GAME_ROTATION_VECTOR, Event::EventPayload::make<Event::EventPayload::vec4>(vec4(qx, qy, qz, qw))));
    if (has(kLight)) out.push_back(make_event(kLight, SensorType::LIGHT, Event::EventPayload::make<Event::EventPayload::scalar>(320.0f + std::sin(phase * 0.11f) * 24.0f)));
    return out;
}

void log_line(const std::string& msg) {
    std::ofstream log("/data/local/tmp/damru-sensors.log", std::ios::app);
    if (log) log << now_ns() << " " << msg << "\n";
    fprintf(stderr, "damru-sensors: %s\n", msg.c_str());
}
}  // namespace

class DamruSensors : public BnSensors {
  public:
    DamruSensors() : motion_(new_motion()) {}

    ScopedAStatus activate(int32_t handle, bool enabled) override {
        std::lock_guard<std::mutex> lock(mu_);
        if (enabled) active_.insert(handle);
        else active_.erase(handle);
        return ScopedAStatus::ok();
    }

    ScopedAStatus batch(int32_t handle, int64_t sampling_period_ns, int64_t) override {
        std::lock_guard<std::mutex> lock(mu_);
        if (sampling_period_ns > 0) periods_[handle] = sampling_period_ns;
        return ScopedAStatus::ok();
    }

    ScopedAStatus configDirectReport(int32_t, int32_t, ISensors::RateLevel, int32_t* ret) override {
        *ret = 0;
        return ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
    }

    ScopedAStatus flush(int32_t handle) override {
        std::lock_guard<std::mutex> lock(mu_);
        if (queue_ && queue_->isValid()) {
            Event e = make_event(handle, SensorType::META_DATA, Event::EventPayload::make<Event::EventPayload::meta>(flush_meta()));
            if (queue_->write(&e, 1) && queue_->mEventFlag) {
                queue_->mEventFlag->wake(kReadAndProcess);
            }
        }
        return ScopedAStatus::ok();
    }

    ScopedAStatus getSensorsList(std::vector<SensorInfo>* ret) override {
        *ret = {
                make_sensor(kAccel, SensorType::ACCELEROMETER, "BMI270 Accelerometer", "Bosch", "android.sensor.accelerometer", 39.2f, 0.01f, 0.18f, 10000),
                make_sensor(kGyro, SensorType::GYROSCOPE, "BMI270 Gyroscope", "Bosch", "android.sensor.gyroscope", 34.9f, 0.001f, 0.80f, 10000),
                make_sensor(kMag, SensorType::MAGNETIC_FIELD, "AK09918 Magnetometer", "AKM", "android.sensor.magnetic_field", 4912.0f, 0.15f, 0.35f, 20000),
                make_sensor(kGravity, SensorType::GRAVITY, "Gravity Sensor", "Damru", "android.sensor.gravity", 39.2f, 0.01f, 0.18f, 10000),
                make_sensor(kLinear, SensorType::LINEAR_ACCELERATION, "Linear Acceleration Sensor", "Damru", "android.sensor.linear_acceleration", 39.2f, 0.01f, 0.18f, 10000),
                make_sensor(kRotation, SensorType::ROTATION_VECTOR, "Rotation Vector Sensor", "Damru", "android.sensor.rotation_vector", 1.0f, 0.0001f, 0.20f, 10000),
                make_sensor(kGameRotation, SensorType::GAME_ROTATION_VECTOR, "Game Rotation Vector Sensor", "Damru", "android.sensor.game_rotation_vector", 1.0f, 0.0001f, 0.20f, 10000),
                make_sensor(kLight, SensorType::LIGHT, "TCS3701 Ambient Light", "AMS", "android.sensor.light", 10000.0f, 1.0f, 0.10f, 0, SensorInfo::SENSOR_FLAG_BITS_ON_CHANGE_MODE),
        };
        return ScopedAStatus::ok();
    }

    ScopedAStatus initialize(const MQDescriptor<Event, SynchronizedReadWrite>& event_desc,
                             const MQDescriptor<int32_t, SynchronizedReadWrite>&,
                             const std::shared_ptr<ISensorsCallback>&) override {
        {
            std::lock_guard<std::mutex> lock(mu_);
            queue_.reset(new EventQueue(event_desc, true));
        }
        running_.store(true);
        if (!pump_.joinable()) pump_ = std::thread([this] { pump_loop(); });
        return ScopedAStatus::ok();
    }

    ScopedAStatus injectSensorData(const Event&) override {
        return ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
    }

    ScopedAStatus registerDirectChannel(const ISensors::SharedMemInfo&, int32_t* ret) override {
        *ret = 0;
        return ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
    }

    ScopedAStatus setOperationMode(ISensors::OperationMode) override { return ScopedAStatus::ok(); }
    ScopedAStatus unregisterDirectChannel(int32_t) override { return ScopedAStatus::ok(); }

  private:
    void pump_loop() {
        auto start = std::chrono::steady_clock::now();
        while (running_.load()) {
            EventQueue* q = nullptr;
            std::set<int> active;
            {
                std::lock_guard<std::mutex> lock(mu_);
                q = queue_.get();
                active = active_;
            }
            if (q && q->isValid()) {
                double t = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
                auto events = sample_events(motion_, t, active);
                if (!events.empty()) {
                    if (q->write(events.data(), events.size()) && q->mEventFlag) {
                        q->mEventFlag->wake(kReadAndProcess);
                    }
                }
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
    }

    std::mutex mu_;
    std::unique_ptr<EventQueue> queue_;
    std::set<int> active_;
    std::map<int, int64_t> periods_;
    Motion motion_;
    std::atomic<bool> running_{false};
    std::thread pump_;
};

int main() {
    log_line("starting damru sensors hal");
    ABinderProcess_setThreadPoolMaxThreadCount(4);
    auto service = ndk::SharedRefBase::make<DamruSensors>();
    std::string name = std::string(ISensors::descriptor) + "/default";
    auto binder = service->asBinder();
    log_line("binder created");
    log_line(std::string("isDeclared=") + (AServiceManager_isDeclared(name.c_str()) ? "true" : "false"));
    log_line(std::string("declared power=") + (AServiceManager_isDeclared("android.hardware.power.IPower/default") ? "true" : "false"));
    log_line(std::string("declared health=") + (AServiceManager_isDeclared("android.hardware.health.IHealth/default") ? "true" : "false"));
    log_line(std::string("declared cas=") + (AServiceManager_isDeclared("android.hardware.cas.IMediaCasService/default") ? "true" : "false"));
    // Redroid's service manager does not report this synthetic HAL as VINTF-declared.
    // Register as a normal binder service when VINTF declaration probing fails.
    if (AServiceManager_isDeclared(name.c_str())) {
        AIBinder_markVintfStability(binder.get());
        log_line("marked vintf stability");
    } else {
        log_line("skipping vintf stability mark for undeclared synthetic service");
    }
    binder_status_t status = AServiceManager_addService(binder.get(), name.c_str());
    log_line("addService " + name + " status=" + std::to_string(status));
    if (status != STATUS_OK) return 1;
    ABinderProcess_startThreadPool();
    log_line("joining binder thread pool");
    ABinderProcess_joinThreadPool();
    log_line("binder thread pool returned");
    return 0;
}
