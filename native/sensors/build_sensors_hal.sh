#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="${DAMRU_SENSORS_BUILD_DIR:-/tmp/damru-sensors-aidl}"
NDK="${ANDROID_NDK_HOME:-/usr/lib/android-sdk/ndk/27.2.12479018}"
AIDL="${ANDROID_AIDL:-/usr/lib/android-sdk/build-tools/35.0.1/aidl}"
OUT="${1:-$ROOT/native/sensors/android.hardware.sensors-service.damru}"
ADB_SERIAL="${DAMRU_SENSOR_ADB_SERIAL:-127.0.0.1:5600}"

if [ ! -x "$AIDL" ]; then
  echo "aidl not found at $AIDL" >&2
  exit 127
fi
if [ ! -x "$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/x86_64-linux-android34-clang++" ]; then
  echo "Android NDK clang not found under $NDK" >&2
  exit 127
fi

mkdir -p "$WORK/aidl" "$WORK/gen" "$WORK/syslib" "$WORK/aosp/system/libfmq/include/fmq" \
  "$WORK/aosp/system/core/libcutils/include/cutils" "$WORK/aosp/system/libbase/include/android-base" \
  "$WORK/aosp/system/core/libutils/include/utils"

fetch_b64() {
  local url="$1" dest="$2"
  [ -s "$dest" ] && return 0
  curl -fsSL "$url?format=TEXT" | base64 -d > "$dest"
}

base="https://android.googlesource.com/platform/hardware/interfaces/+/refs/heads/main"
for f in \
  sensors/aidl/android/hardware/sensors/AdditionalInfo.aidl \
  sensors/aidl/android/hardware/sensors/DynamicSensorInfo.aidl \
  sensors/aidl/android/hardware/sensors/Event.aidl \
  sensors/aidl/android/hardware/sensors/ISensors.aidl \
  sensors/aidl/android/hardware/sensors/ISensorsCallback.aidl \
  sensors/aidl/android/hardware/sensors/SensorInfo.aidl \
  sensors/aidl/android/hardware/sensors/SensorStatus.aidl \
  sensors/aidl/android/hardware/sensors/SensorType.aidl \
  common/aidl/android/hardware/common/NativeHandle.aidl \
  common/fmq/aidl/android/hardware/common/fmq/GrantorDescriptor.aidl \
  common/fmq/aidl/android/hardware/common/fmq/MQDescriptor.aidl \
  common/fmq/aidl/android/hardware/common/fmq/SynchronizedReadWrite.aidl \
  common/fmq/aidl/android/hardware/common/fmq/UnsynchronizedWrite.aidl; do
  dest="$WORK/aidl/${f#*/aidl/}"
  dest="${dest/common\/fmq\/aidl\//}"
  mkdir -p "$(dirname "$dest")"
  fetch_b64 "$base/$f" "$dest"
done

fmq_base="https://android.googlesource.com/platform/system/libfmq/+/refs/heads/main/include/fmq"
for f in AidlMessageQueue.h EventFlag.h MessageQueue.h AidlMQDescriptorShim.h AidlMessageQueueBase.h AidlMQDescriptorShimBase.h MessageQueueBase.h; do
  fetch_b64 "$fmq_base/$f" "$WORK/aosp/system/libfmq/include/fmq/$f"
done
fetch_b64 "https://android.googlesource.com/platform/system/libfmq/+/refs/heads/main/base/fmq/MQDescriptorBase.h" "$WORK/aosp/system/libfmq/include/fmq/MQDescriptorBase.h"
fetch_b64 "https://android.googlesource.com/platform/system/core/+/refs/heads/main/libcutils/include/cutils/native_handle.h" "$WORK/aosp/system/core/libcutils/include/cutils/native_handle.h"
fetch_b64 "https://android.googlesource.com/platform/system/core/+/refs/heads/main/libcutils/include/cutils/ashmem.h" "$WORK/aosp/system/core/libcutils/include/cutils/ashmem.h"
fetch_b64 "https://android.googlesource.com/platform/system/libbase/+/refs/heads/main/include/android-base/unique_fd.h" "$WORK/aosp/system/libbase/include/android-base/unique_fd.h"
cat > "$WORK/aosp/system/core/libutils/include/utils/Errors.h" <<'EOF'
#pragma once
#include <stdint.h>
namespace android {
typedef int32_t status_t;
static constexpr status_t OK = 0;
static constexpr status_t NO_ERROR = 0;
static constexpr status_t BAD_VALUE = -22;
static constexpr status_t TIMED_OUT = -110;
}
EOF
cat > "$WORK/aosp/system/core/libutils/include/utils/Log.h" <<'EOF'
#pragma once
#define ALOGE(...) ((void)0)
#define ALOGW(...) ((void)0)
#define ALOGI(...) ((void)0)
#define ALOGD(...) ((void)0)
#define LOG_ALWAYS_FATAL_IF(cond, ...) do { if (cond) abort(); } while (0)
EOF
cat > "$WORK/aosp/system/core/libutils/include/utils/SystemClock.h" <<'EOF'
#pragma once
#include <stdint.h>
#include <time.h>
namespace android {
inline int64_t elapsedRealtimeNano() {
  struct timespec ts{};
  clock_gettime(CLOCK_BOOTTIME, &ts);
  return static_cast<int64_t>(ts.tv_sec) * 1000000000LL + ts.tv_nsec;
}
}
EOF

if ! command -v adb >/dev/null 2>&1; then
  echo "adb is required to pull Android system libraries into $WORK/syslib" >&2
  exit 127
fi
adb -s "$ADB_SERIAL" wait-for-device
for lib in \
  android.hardware.sensors-V2-ndk.so \
  android.hardware.common.fmq-V1-ndk.so \
  libfmq.so \
  libbinder_ndk.so libbase.so libutils.so libcutils.so liblog.so; do
  if [ ! -s "$WORK/syslib/$lib" ]; then
    adb -s "$ADB_SERIAL" pull "/system/lib64/$lib" "$WORK/syslib/$lib" >/dev/null
  fi
done

mapfile -t aidls < <(find "$WORK/aidl" -name '*.aidl' | sort)
"$AIDL" --lang=ndk --structured --stability=vintf -I "$WORK/aidl" -o "$WORK/gen/cpp" -h "$WORK/gen/include" "${aidls[@]}"

mapfile -t gen_cpp < <(find "$WORK/gen/cpp" -name '*.cpp' | sort)
clang="$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/x86_64-linux-android34-clang++"
"$clang" -std=c++17 -O2 -Wall -Wextra -static-libstdc++ \
  -I"$WORK/gen/include" -I"$WORK/aosp/system/libfmq/include" \
  -I"$WORK/aosp/system/core/libcutils/include" -I"$WORK/aosp/system/libbase/include" \
  -I"$WORK/aosp/system/core/libutils/include" \
  "$ROOT/native/damru_sensors_service.cpp" "${gen_cpp[@]}" \
  "$WORK/syslib/android.hardware.sensors-V2-ndk.so" \
  "$WORK/syslib/android.hardware.common.fmq-V1-ndk.so" \
  "$WORK/syslib/libfmq.so" \
  "$WORK/syslib/libbinder_ndk.so" "$WORK/syslib/libbase.so" "$WORK/syslib/libutils.so" \
  "$WORK/syslib/libcutils.so" "$WORK/syslib/liblog.so" \
  -pthread -o "$OUT"
chmod 755 "$OUT"
echo "$OUT"
