#!/system/bin/sh
am force-stop com.android.chrome
sleep 1
am start -n com.android.chrome/com.google.android.apps.chrome.Main
sleep 3
CPID=$(ps -A | grep 'com.android.chrome$' | head -1 | awk '{print $2}')
echo "Chrome PID=$CPID"
if [ -n "$CPID" ]; then
    timeout 5 strace -p $CPID -e trace=openat,sysinfo -f 2>&1 | grep -iE 'meminfo|sysinfo' | head -30
fi
echo DONE
