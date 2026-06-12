with open("damru/docker.py", "r") as f:
    content = f.read()

old = '            logger.info("Cleaning up temp files in container before commit...")\n            for clean_cmd in [\n                "rm -rf /data/local/tmp/*.apk /data/local/tmp/*.zip /data/local/tmp/*.tar* 2>/dev/null; true",\n                "rm -rf /data/dalvik-cache/arm64/* 2>/dev/null; true",\n                "rm -rf /data/resource-cache/* 2>/dev/null; true",\n                "rm -rf /data/system/package_cache/* 2>/dev/null; true",\n                "rm -rf /data/anr/* 2>/dev/null; true",\n                "rm -rf /data/backup/* 2>/dev/null; true",\n                "rm -rf /data/cache/* 2>/dev/null; true",\n                "rm -rf /data/tombstones/* 2>/dev/null; true",\n                "rm -rf /data/vendor/wifi/* 2>/dev/null; true",\n                "logcat -c 2>/dev/null; true",\n                "pm trim-caches 999999999 2>/dev/null; true",\n            ]:\n                await adb.shell_root(clean_cmd, timeout=10, allow_failure=True)'

new = '            logger.info("Cleaning up temp files in container before commit...")\n            for clean_cmd in [\n                "rm -rf /data/local/tmp/*.apk /data/local/tmp/*.zip /data/local/tmp/*.tar* 2>/dev/null; true",\n                "rm -rf /data/dalvik-cache/arm64/* 2>/dev/null; true",\n                "rm -rf /data/resource-cache/* 2>/dev/null; true",\n                "rm -rf /data/system/package_cache/* 2>/dev/null; true",\n                "rm -rf /data/anr/* 2>/dev/null; true",\n                "rm -rf /data/backup/* 2>/dev/null; true",\n                "rm -rf /data/cache/* 2>/dev/null; true",\n                "rm -rf /data/tombstones/* 2>/dev/null; true",\n                "rm -rf /data/vendor/wifi/* 2>/dev/null; true",\n                "logcat -c 2>/dev/null; true",\n                "pm trim-caches 999999999 2>/dev/null; true",\n            ]:\n                try:\n                    await adb.shell_root(clean_cmd, timeout=10)\n                except Exception:\n                    pass'

if old in content:
    content = content.replace(old, new)
    with open("damru/docker.py", "w") as f:
        f.write(content)
    print("Fixed cleanup to use try/except")
else:
    print("ERROR: old text not found")
    idx = content.find("Cleaning up temp files")
    if idx >= 0:
        print(content[idx:idx+500])