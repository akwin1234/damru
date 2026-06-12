#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERIAL="${DAMRU_SENSOR_ADB_SERIAL:-127.0.0.1:5600}"
WORK="${DAMRU_SENSORS_BUILD_DIR:-/tmp/damru-sensors-aidl}"
BIN="${1:-$ROOT/native/sensors/android.hardware.sensors-service.damru}"

if [ ! -x "$BIN" ]; then
  "$ROOT/native/sensors/build_sensors_hal.sh" "$BIN"
fi
mkdir -p "$WORK/syslib"

adb -s "$SERIAL" wait-for-device
adb -s "$SERIAL" push "$BIN" /data/local/tmp/android.hardware.sensors-service.damru >/dev/null
adb -s "$SERIAL" push "$ROOT/native/sensors/manifest/damru-sensors.xml" /data/local/tmp/damru-sensors.xml >/dev/null
adb -s "$SERIAL" push "$ROOT/native/sensors/init/android.hardware.sensors-service.damru.rc" /data/local/tmp/android.hardware.sensors-service.damru.rc >/dev/null
adb -s "$SERIAL" pull /vendor/etc/init/redroid.common.rc "$WORK/redroid.common.rc" >/dev/null
perl -0pi -e 's#\n?# Damru synthetic sensors HAL.*?(?=\nservice |\non |\z)##sg; s#\nservice vendor\.damru-sensors .*?(?=\nservice |\non |\z)##sg; s#\non early-boot\n\s*start vendor\.damru-sensors\n#\n#sg' "$WORK/redroid.common.rc"
cat >> "$WORK/redroid.common.rc" <<'EOF'

# Damru synthetic sensors HAL: start before framework SensorService initializes.
service vendor.damru-sensors /vendor/bin/hw/android.hardware.sensors-service.damru
    class hal
    user root
    group system

on early-boot
    start vendor.damru-sensors
EOF
adb -s "$SERIAL" push "$WORK/redroid.common.rc" /data/local/tmp/redroid.common.rc >/dev/null

for lib in android.hardware.sensors-V2-ndk.so android.hardware.common.fmq-V1-ndk.so; do
  if [ ! -s "$WORK/syslib/$lib" ]; then
    adb -s "$SERIAL" pull "/system/lib64/$lib" "$WORK/syslib/$lib" >/dev/null
  fi
  adb -s "$SERIAL" push "$WORK/syslib/$lib" "/data/local/tmp/$lib" >/dev/null
done

adb -s "$SERIAL" shell su 0 setprop ctl.stop vendor.damru-sensors >/dev/null 2>&1 || true
adb -s "$SERIAL" shell su 0 pkill -f android.hardware.sensors-service.damru >/dev/null 2>&1 || true
sleep 1
adb -s "$SERIAL" shell su 0 mkdir -p /vendor/bin/hw /vendor/etc/vintf/manifest /vendor/etc/init /vendor/lib64
adb -s "$SERIAL" shell su 0 cp /data/local/tmp/android.hardware.sensors-service.damru /vendor/bin/hw/android.hardware.sensors-service.damru
adb -s "$SERIAL" shell su 0 cp /data/local/tmp/damru-sensors.xml /vendor/etc/vintf/manifest/damru-sensors.xml
adb -s "$SERIAL" shell su 0 cp /data/local/tmp/android.hardware.sensors-service.damru.rc /vendor/etc/init/android.hardware.sensors-service.damru.rc
adb -s "$SERIAL" shell su 0 cp /data/local/tmp/redroid.common.rc /vendor/etc/init/redroid.common.rc
adb -s "$SERIAL" shell su 0 cp /data/local/tmp/android.hardware.sensors-V2-ndk.so /vendor/lib64/android.hardware.sensors-V2-ndk.so
adb -s "$SERIAL" shell su 0 cp /data/local/tmp/android.hardware.common.fmq-V1-ndk.so /vendor/lib64/android.hardware.common.fmq-V1-ndk.so
adb -s "$SERIAL" shell su 0 chmod 755 /vendor/bin/hw/android.hardware.sensors-service.damru
adb -s "$SERIAL" shell su 0 chmod 644 \
  /vendor/etc/vintf/manifest/damru-sensors.xml \
  /vendor/etc/init/android.hardware.sensors-service.damru.rc \
  /vendor/etc/init/redroid.common.rc \
  /vendor/lib64/android.hardware.sensors-V2-ndk.so \
  /vendor/lib64/android.hardware.common.fmq-V1-ndk.so
adb -s "$SERIAL" shell su 0 restorecon \
  /vendor/bin/hw/android.hardware.sensors-service.damru \
  /vendor/etc/vintf/manifest/damru-sensors.xml \
  /vendor/etc/init/android.hardware.sensors-service.damru.rc \
  /vendor/etc/init/redroid.common.rc \
  /vendor/lib64/android.hardware.sensors-V2-ndk.so \
  /vendor/lib64/android.hardware.common.fmq-V1-ndk.so >/dev/null 2>&1 || true

if command -v docker >/dev/null 2>&1 && [[ "$SERIAL" =~ :([0-9]+)$ ]]; then
  PORT="${BASH_REMATCH[1]}"
  CONTAINER="$(docker ps --format '{{.Names}} {{.Ports}}' | awk -v pat=":${PORT}->5555" 'index($0, pat) {print $1; exit}')"
  if [ -n "$CONTAINER" ]; then
    docker cp "$BIN" "$CONTAINER:/vendor/bin/hw/android.hardware.sensors-service.damru" >/dev/null
    docker cp "$ROOT/native/sensors/manifest/damru-sensors.xml" "$CONTAINER:/vendor/etc/vintf/manifest/damru-sensors.xml" >/dev/null
    docker cp "$ROOT/native/sensors/init/android.hardware.sensors-service.damru.rc" "$CONTAINER:/vendor/etc/init/android.hardware.sensors-service.damru.rc" >/dev/null
    docker cp "$WORK/redroid.common.rc" "$CONTAINER:/vendor/etc/init/redroid.common.rc" >/dev/null
    docker cp "$WORK/syslib/android.hardware.sensors-V2-ndk.so" "$CONTAINER:/vendor/lib64/android.hardware.sensors-V2-ndk.so" >/dev/null
    docker cp "$WORK/syslib/android.hardware.common.fmq-V1-ndk.so" "$CONTAINER:/vendor/lib64/android.hardware.common.fmq-V1-ndk.so" >/dev/null
    docker exec "$CONTAINER" chmod 755 /vendor/bin/hw/android.hardware.sensors-service.damru >/dev/null
    docker exec "$CONTAINER" chmod 644 \
      /vendor/etc/vintf/manifest/damru-sensors.xml \
      /vendor/etc/init/android.hardware.sensors-service.damru.rc \
      /vendor/etc/init/redroid.common.rc \
      /vendor/lib64/android.hardware.sensors-V2-ndk.so \
      /vendor/lib64/android.hardware.common.fmq-V1-ndk.so >/dev/null
  fi
fi

echo "Installed Damru sensor HAL fragment. Restart the Redroid container to activate it."