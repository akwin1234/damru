#!/bin/bash
# Full setup: load modules, start container, install Chrome, test GPU
set -e

echo "=== Loading kernel modules ==="
modprobe ip_tables iptable_nat iptable_filter iptable_raw iptable_mangle
modprobe nf_nat nf_conntrack xt_nat xt_addrtype xt_conntrack

echo "=== Removing old container ==="
docker rm -f damru-test-0 2>/dev/null || true

echo "=== Starting Docker ==="
systemctl restart docker
sleep 5

echo "=== Loading xt_nat after Docker start ==="
modprobe xt_nat xt_addrtype iptable_raw

echo "=== Creating container ==="
docker run -d --privileged --name damru-test-0 \
  -v /dev/binderfs:/dev/binderfs \
  -p 5600:5555 \
  redroid/redroid:14.0.0_64only-latest \
  androidboot.use_memfd=true
sleep 8

echo "=== Container status ==="
docker ps

echo "=== Copying APKs ==="
APK_DIR="./chrome-apks/145.0.7632.75"
docker cp "$APK_DIR/google_trichrome_library.apk" damru-test-0:/data/local/tmp/trichrome.apk
docker cp "$APK_DIR/base.apk" damru-test-0:/data/local/tmp/base.apk
docker cp "$APK_DIR/split_chrome.apk" damru-test-0:/data/local/tmp/split_chrome.apk
docker cp "$APK_DIR/split_config.en.apk" damru-test-0:/data/local/tmp/split_config.en.apk
docker cp "$APK_DIR/split_on_demand.apk" damru-test-0:/data/local/tmp/split_on_demand.apk
echo "APKs copied"

echo "=== Installing TrichromeLibrary ==="
docker exec damru-test-0 pm install -r /data/local/tmp/trichrome.apk

echo "=== Installing Chrome split APKs ==="
docker exec damru-test-0 sh -c '
TOTAL=$(stat -c%s /data/local/tmp/base.apk)
TOTAL=$((TOTAL + $(stat -c%s /data/local/tmp/split_chrome.apk)))
TOTAL=$((TOTAL + $(stat -c%s /data/local/tmp/split_config.en.apk)))
TOTAL=$((TOTAL + $(stat -c%s /data/local/tmp/split_on_demand.apk)))
SID=$(pm install-create -S $TOTAL 2>&1 | grep -oE "[0-9]+")
echo "Session: $SID, Total: $TOTAL"
pm install-write -S $(stat -c%s /data/local/tmp/base.apk) $SID base /data/local/tmp/base.apk
pm install-write -S $(stat -c%s /data/local/tmp/split_chrome.apk) $SID split_chrome /data/local/tmp/split_chrome.apk
pm install-write -S $(stat -c%s /data/local/tmp/split_config.en.apk) $SID split_config /data/local/tmp/split_config.en.apk
pm install-write -S $(stat -c%s /data/local/tmp/split_on_demand.apk) $SID split_on_demand /data/local/tmp/split_on_demand.apk
pm install-commit $SID
'

echo "=== Verifying Chrome ==="
docker exec damru-test-0 pm path com.android.chrome

echo "=== Done ==="
