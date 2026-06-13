#!/system/bin/sh
#
# Materialize Linux input event nodes early during Redroid boot.
#
# Some Redroid boots expose touch devices in /sys/class/input and
# /proc/bus/input/devices, but /dev/input is absent when Android InputReader
# starts. Creating the directory and nodes before framework startup lets
# InputReader see a normal direct touchscreen device.

timeout="${1:-25}"
case "$timeout" in
    ''|*[!0-9]*) timeout=25 ;;
esac

mkdir -p /dev/input
chmod 0755 /dev/input 2>/dev/null || true

end=$(( $(date +%s) + timeout ))
while [ "$(date +%s)" -le "$end" ]; do
    touch_ready=0
    for event_path in /sys/class/input/event*; do
        [ -r "$event_path/dev" ] || continue
        event_name="${event_path##*/}"
        node="/dev/input/$event_name"
        major_minor="$(cat "$event_path/dev" 2>/dev/null || true)"
        [ -n "$major_minor" ] || continue
        major="${major_minor%:*}"
        minor="${major_minor#*:}"
        device_name="$(cat "$event_path/device/name" 2>/dev/null || true)"

        if [ ! -e "$node" ]; then
            mknod "$node" c "$major" "$minor" 2>/dev/null || true
        fi
        # This Redroid image runs system_server without the Android input group.
        # root:system keeps the node private to Android system services while
        # still allowing EventHub/InputReader to open it.
        chown 0:1000 "$node" 2>/dev/null || true
        chmod 0660 "$node" 2>/dev/null || true
        chcon u:object_r:input_device:s0 "$node" 2>/dev/null || true

        case "$device_name" in
            *touch*|*Touch*|*TOUCH*|redroid\ vinput|damru-virtual-multitouch|damru\ virtual\ touchscreen)
                touch_ready=1
                ;;
        esac
    done
    [ "$touch_ready" = "1" ] && exit 0
    sleep 0.25
done

exit 0
