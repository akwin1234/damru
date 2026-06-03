"""Root-level system property spoofing for damru.

Uses resetprop to change Android ro.* properties at runtime.
resetprop sources (in priority order):
  1. Magisk's built-in resetprop (if Magisk installed)
  2. Standalone resetprop pushed from bundled Magisk binary
  3. setprop fallback (only works for non-ro.* props)
"""
from __future__ import annotations

import asyncio
import base64
from importlib import resources
import os
import random
import subprocess
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from typing import Dict, Optional

from .adb import ADB
from .apk_assets import bundled_magisk_apk, find_any_bundle_apk
from .devices import AndroidDevice
from .utils import logger, sleep


def _detect_gpu_family(gles_string: str) -> str:
    """Determine GPU family from a GLES renderer string.

    Works with SurfaceFlinger output like 'Qualcomm, Adreno (TM) 640, OpenGL ES 3.2'.
    """
    low = gles_string.lower()
    if "adreno" in low:
        return "adreno"
    if "mali" in low:
        return "mali"
    if "xclipse" in low:
        return "xclipse"
    return "unknown"

# Path where we push the standalone resetprop binary on device.
# MUST be named "resetprop" because Magisk's binary is multi-call (like busybox)
# and uses argv[0] to determine which applet to run.
_DEVICE_RESETPROP = "/data/local/tmp/resetprop"

# Memory spoof paths on device
_FAKEMEM_SO = "/data/local/tmp/libfakemem.so"
_FAKEMEM_TARGET = "/data/local/tmp/damru_fakemem_gb"
_FAKEMEM_WRAP = "/data/local/tmp/damru_chrome_wrap.sh"
_APP_PROCESS_REAL = "/system/bin/app_process64.real"

# Font paths
_FONTS_XML = "/system/etc/fonts.xml"
_FONTS_XML_ORIG = "/data/local/tmp/damru_fonts_orig.xml"
_FONT_MARKER = "/data/local/tmp/damru_fonts_installed"

# Extra fonts to install for font fingerprint diversity.
# Each: (css_family_name, ttf_filename, download_urls, [creepjs_alias_names])
# Aliases map common fingerprinting test names to distinct typefaces,
# increasing the font detection count from 7 to ~15.
_EXTRA_FONTS: list[tuple[str, str, list[str], list[str]]] = [
    ("open-sans", "OpenSans-Regular.ttf", [
        "https://raw.githubusercontent.com/googlefonts/opensans/main/fonts/ttf/OpenSans-Regular.ttf",
    ], ["Open Sans", "Segoe UI"]),
    ("lato", "Lato-Regular.ttf", [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/lato/Lato-Regular.ttf",
    ], ["Trebuchet MS"]),
    ("montserrat", "Montserrat-Regular.ttf", [
        "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-Regular.ttf",
    ], ["Century Gothic"]),
    ("oswald", "Oswald-Regular.ttf", [
        "https://raw.githubusercontent.com/googlefonts/OswaldFont/main/fonts/ttf/Oswald-Regular.ttf",
    ], ["Impact"]),
    ("fira-mono", "FiraMono-Regular.ttf", [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/firamono/FiraMono-Regular.ttf",
    ], ["Fira Mono", "Consolas", "Lucida Console"]),
    ("merriweather", "Merriweather-Regular.ttf", [
        "https://raw.githubusercontent.com/SorkinType/Merriweather/master/fonts/ttf/Merriweather-Regular.ttf",
    ], ["Cambria"]),
    ("pt-sans", "PTSans-Regular.ttf", [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/ptsans/PT_Sans-Web-Regular.ttf",
    ], ["PT Sans", "Calibri", "Book Antiqua"]),
    ("poppins", "Poppins-Regular.ttf", [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Regular.ttf",
    ], ["Century Schoolbook"]),
    ("inconsolata", "Inconsolata-Regular.ttf", [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/inconsolata/static/Inconsolata-Regular.ttf",
    ], ["Lucida Sans Typewriter"]),
]


class RootError(Exception):
    """Root operation failed."""


class RootOps:
    """Root-level operations on an Android device."""

    def __init__(self, adb: ADB):
        self.adb = adb
        self._resetprop_cmd: Optional[str] = None
        self._original_props: Dict[str, str] = {}

    async def check_root(self) -> bool:
        """Verify root access is available."""
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                rooted = await self.adb.is_rooted()
                if rooted:
                    return True
            except Exception as exc:
                last_error = exc

            if attempt < 2:
                # MuMu can expose ADB before su/adbd is fully ready.
                await asyncio.sleep(1.0)

        if last_error is not None:
            raise RootError(
                "Root access check failed. Ensure the device/emulator has root "
                f"(Magisk, SuperSU, or adbd running as root). Last error: {last_error}"
            )
        raise RootError(
            "Root access required. Ensure the device/emulator has root "
            "(Magisk, SuperSU, or adbd running as root)."
        )

    async def _ensure_resetprop(self) -> str:
        """Ensure resetprop is available and return the command to invoke it.

        Checks (in order):
          1. Magisk resetprop in PATH
          2. Already-pushed standalone at /data/local/tmp/resetprop
          3. Extract from bundled Magisk APK and push to device
        """
        if self._resetprop_cmd is not None:
            return self._resetprop_cmd

        # 1. Check Magisk resetprop
        out = await self.adb.shell("which resetprop", timeout=5, allow_failure=True)
        if "resetprop" in out:
            self._resetprop_cmd = "resetprop"
            logger.info("Using Magisk resetprop")
            return self._resetprop_cmd

        # 2. Check if already pushed
        out = await self.adb.shell(
            f"test -x {_DEVICE_RESETPROP} && echo OK",
            timeout=5, allow_failure=True,
        )
        if "OK" in out:
            self._resetprop_cmd = _DEVICE_RESETPROP
            logger.info("Using previously pushed resetprop")
            return self._resetprop_cmd

        # 3. Push standalone resetprop from Magisk APK
        logger.info("No Magisk detected. Pushing standalone resetprop...")
        await self._push_resetprop()
        self._resetprop_cmd = _DEVICE_RESETPROP
        return self._resetprop_cmd

    async def _push_resetprop(self) -> None:
        """Extract resetprop from Magisk APK and push to device."""
        # Determine device ABI
        abi = await self.adb.get_prop("ro.product.cpu.abi")
        if not abi:
            abi = "x86_64"  # fallback for emulators

        # Map ABI to Magisk lib path
        abi_map = {
            "x86_64": "lib/x86_64/libmagisk.so",
            "x86": "lib/x86/libmagisk.so",
            "arm64-v8a": "lib/arm64-v8a/libmagisk.so",
            "armeabi-v7a": "lib/armeabi-v7a/libmagisk.so",
        }
        lib_path = abi_map.get(abi)
        if not lib_path:
            raise RootError(f"Unsupported ABI: {abi}. Cannot push resetprop.")

        # Find local Magisk APK used as a resetprop binary source.
        magisk_apk = self._find_magisk_apk()
        if not magisk_apk:
            raise RootError(
                "Missing Damru magisk.apk asset. Raw Redroid needs it only to "
                "extract standalone resetprop. Reinstall Damru or run "
                "`python -m damru setup`."
            )

        # Extract libmagisk.so from APK
        tmp_path = os.path.join(tempfile.gettempdir(), "damru_resetprop.so")
        try:
            with zipfile.ZipFile(magisk_apk, "r") as zf:
                if lib_path not in zf.namelist():
                    # Try fallback ABIs
                    for fallback in abi_map.values():
                        if fallback in zf.namelist():
                            lib_path = fallback
                            break
                    else:
                        raise RootError(
                            f"Magisk APK does not contain {lib_path}. "
                            f"Available: {[n for n in zf.namelist() if n.startswith('lib/')]}"
                        )
                with open(tmp_path, "wb") as f:
                    f.write(zf.read(lib_path))

            # Push to device
            await self.adb.push(tmp_path, _DEVICE_RESETPROP)
            await self.adb.shell_root(f"chmod 755 {_DEVICE_RESETPROP}")

            # Verify it works (--help may return non-zero exit code)
            out = await self.adb.shell(
                f"{_DEVICE_RESETPROP} --help 2>&1",
                timeout=5, allow_failure=True,
            )
            if "resetprop" not in out.lower() and "property" not in out.lower():
                logger.warning("resetprop verification failed: %s", out[:200])

            logger.info("Pushed standalone resetprop (%s) to device", abi)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _find_magisk_apk(self) -> Optional[str]:
        """Find Magisk APK in the local Damru APK bundle or package tools."""
        bundled = find_any_bundle_apk(["magisk.apk", "Magisk.apk", "Magisk-v28.1.apk"])
        if bundled is not None:
            return str(bundled)

        shipped = bundled_magisk_apk()
        if shipped is not None:
            return str(shipped)

        # Check package directory
        pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            "/home/damru/tools/magisk.apk",
            "/home/damru/tools/Magisk.apk",
            os.path.join(pkg_dir, "tools", "magisk.apk"),
            os.path.join(pkg_dir, "tools", "Magisk.apk"),
            os.path.join(pkg_dir, "magisk.apk"),
            os.path.join(pkg_dir, "magisk_tmp", "lib"),  # already extracted
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c

        # Check if there's a magisk*.apk in package dir
        for f in os.listdir(pkg_dir):
            if f.lower().startswith("magisk") and f.endswith(".apk"):
                return os.path.join(pkg_dir, f)

        return None
    async def set_prop(self, key: str, value: str) -> None:
        """Set a single system property.

        Uses resetprop for ro.* props, setprop for others.
        Handles values with spaces (e.g. 'Pixel 8 Pro') via proper quoting.
        """
        # Use double quotes to handle values with spaces
        escaped_value = value.replace('"', '\\"')
        if key.startswith("ro."):
            resetprop = await self._ensure_resetprop()
            await self.adb.shell_root(f'{resetprop} {key} "{escaped_value}"')
        else:
            await self.adb.shell_root(f'setprop {key} "{escaped_value}"')

    async def get_prop(self, key: str) -> str:
        """Get current value of a system property."""
        return await self.adb.get_prop(key)

    async def apply_device_props(
        self, device: AndroidDevice, safe_only: bool = True, parallel: bool = False,
    ) -> None:
        """Apply all system properties for the target device identity.

        Args:
            device: Target device profile.
            safe_only: If True, skip version props (ro.build.version.release/sdk).
                Set to False when the device profile's Android version matches
                the emulator's real version.
            parallel: If True, fire all resetprop calls concurrently (faster
                for warm reuse where we don't need to save originals).
        """
        props = device.system_props(safe_only=safe_only)
        logger.info("Applying %d system props for %s (safe_only=%s, parallel=%s)",
                     len(props), device.name, safe_only, parallel)

        if parallel:
            # All props are independent — run concurrently for speed.
            # Skip saving originals (not restored on exit anyway).
            await asyncio.gather(*(self.set_prop(k, v) for k, v in props.items()))
        else:
            for key, value in props.items():
                if key not in self._original_props:
                    self._original_props[key] = await self.get_prop(key)
                await self.set_prop(key, value)

        # Verify critical props
        actual_model = await self.get_prop("ro.product.model")
        if actual_model == device.model:
            logger.info("Device identity: %s %s (verified)", device.brand, device.model)
        else:
            logger.warning(
                "Device model mismatch: expected %s, got %s "
                "(resetprop may not be available)", device.model, actual_model
            )

    async def apply_version_release(self, device: "AndroidDevice") -> None:
        """Override ro.build.version.release and security_patch for Android version spoofing.

        Safe to call regardless of whether the real Android version matches the
        target device — only sets the display release string and security_patch,
        NOT the SDK integer (which can crash native code if mismatched).

        Chrome reads ro.build.version.release at startup to build its UA string,
        so Workers (which CDP cannot override) also get the spoofed version.
        """
        props = device.version_release_props()
        for key, value in props.items():
            await self.set_prop(key, value)
        logger.info(
            "Android version spoofed: %s (security_patch=%s)",
            device.android_version, device.security_patch,
        )

    async def apply_timezone(self, timezone: str) -> None:
        """Set the device timezone and sync device clock.

        Also syncs the device clock to the host's current time to prevent
        clock mismatch detection (todetect.net compares IP time vs local time).
        """
        await self.adb.shell("settings put global auto_time_zone 0", allow_failure=True)
        await self.adb.shell("settings put global auto_time 0", allow_failure=True)
        await self.set_prop("persist.sys.timezone", timezone)

        # Sync device clock to host time (prevents IP-time vs local-time mismatch)
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        # Android date format: MMDDhhmmYYYY.ss (month, day, hour, min, year, sec)
        date_str = now.strftime("%m%d%H%M%Y.%S")
        try:
            await self.adb.shell_root(f"date -u {date_str}")
        except Exception:
            logger.debug("Could not sync device clock (non-fatal)")
        logger.info("Timezone set to %s, clock synced to UTC %s", timezone, now.strftime("%H:%M:%S"))

    async def apply_locale(self, locale: str) -> None:
        """Set the device locale.

        Sets both the system property and the Android settings value
        so Chrome picks up the new locale immediately without reboot.
        """
        await self.set_prop("persist.sys.locale", locale)
        # Android settings locale takes effect immediately for apps
        await self.adb.shell(
            f"settings put system system_locales {locale}",
            allow_failure=True,
        )
        logger.info("Locale set to %s", locale)

    async def apply_ipv6_block(self) -> None:
        """Disable IPv6 completely to prevent IPv6 address leak.

        Real phones behind mobile carriers often have IPv6, but emulators
        leak the host's IPv6 address which reveals the real ISP.
        Disabling IPv6 via sysctl + ip6tables is invisible to fingerprinting
        (many real networks disable IPv6).

        Idempotent: checks sysctl before applying.
        """
        check = await self.adb.shell(
            "sysctl -n net.ipv6.conf.all.disable_ipv6 2>/dev/null",
            allow_failure=True,
        )
        if check.strip() == "1":
            logger.debug("IPv6 already disabled — skipping")
            return

        cmds = [
            "sysctl -w net.ipv6.conf.all.disable_ipv6=1",
            "sysctl -w net.ipv6.conf.default.disable_ipv6=1",
            "sysctl -w net.ipv6.conf.lo.disable_ipv6=1",
            "sysctl -w net.ipv6.conf.eth0.disable_ipv6=1",
            "ip -6 addr flush dev eth0 2>/dev/null || true",
            "ip6tables -P INPUT DROP 2>/dev/null || true",
            "ip6tables -P OUTPUT DROP 2>/dev/null || true",
            "ip6tables -P FORWARD DROP 2>/dev/null || true",
        ]
        for cmd in cmds:
            await self.adb.shell_root(cmd)
        logger.info("IPv6 disabled (sysctl + ip6tables DROP)")

    async def apply_webrtc_block(self, chrome_package: str = "com.android.chrome") -> None:
        """Block ALL outgoing UDP from Chrome to prevent WebRTC IP leak.

        Uses iptables owner match (xt_owner module) to drop all UDP packets
        from Chrome's UID. This blocks STUN on ANY port, not just standard
        ports (3478, 5349, 19302-19309). Sites like todetect.net use custom
        STUN servers on non-standard ports which port-based rules miss.

        Chrome only needs TCP (HTTP proxy handles all TCP traffic). DNS goes
        through DoH (HTTPS/TCP). No UDP is needed for Chrome operation.

        WebRTC API stays "enabled" in Chrome — STUN simply fails silently,
        so no public IP candidate is generated. This looks like being behind
        a restrictive firewall, not like WebRTC being "disabled" (which is a
        fingerprint tell).

        Falls back to port-based blocking if xt_owner module is unavailable.

        Idempotent: checks if rule already exists before applying.
        """
        # Some WSL fallback kernels can boot Redroid but do not expose the
        # Android iptables filter table. In that case Chrome prefs/CDP still
        # constrain WebRTC, but kernel-level UDP blocking is unavailable.
        iptables_check = await self.adb.shell(
            "su 0 iptables -L OUTPUT -n 2>&1",
            timeout=5,
            allow_failure=True,
        )
        if self._iptables_unavailable(iptables_check):
            logger.warning(
                "Android iptables unavailable; skipping kernel WebRTC UDP block. "
                "Chrome WebRTC policy remains active, but kernel-level leak "
                "protection is degraded on this kernel."
            )
            return

        # Resolve Chrome's UID (u0_aNN = 10000 + NN)
        owner_info = await self.adb.shell(
            f"stat -c '%U' /data/data/{chrome_package} 2>/dev/null",
            allow_failure=True,
        )
        chrome_uid = None
        if owner_info and owner_info.strip().startswith("u0_a"):
            try:
                chrome_uid = 10000 + int(owner_info.strip().split("u0_a")[1])
            except (ValueError, IndexError):
                pass

        if chrome_uid:
            # Check if UID-based rule already exists
            check = await self.adb.shell(
                f"su 0 iptables -C OUTPUT -p udp -m owner --uid-owner {chrome_uid} -j DROP 2>&1",
                allow_failure=True,
            )
            if check.strip() == "":
                logger.debug("WebRTC UID-based UDP block already applied — skipping")
                return

            # Try UID-based block (requires xt_owner kernel module)
            try:
                result = await self.adb.shell_root(
                    f"iptables -I OUTPUT -p udp -m owner --uid-owner {chrome_uid} -j DROP 2>&1",
                )
                if result.strip() == "" or "owner" not in result.lower():
                    logger.info("WebRTC blocked: ALL UDP from Chrome UID %d (iptables owner match)", chrome_uid)
                    return
                logger.debug("xt_owner unavailable (%s), falling back to port-based block", result.strip())
            except Exception as exc:
                logger.debug("xt_owner unavailable (%s), falling back to port-based block", exc)

        # Fallback: block all high-port UDP (covers custom STUN ports, not just well-known ones)
        check = await self.adb.shell(
            "su 0 iptables -C OUTPUT -p udp --dport 1024:65535 -j DROP 2>&1",
            allow_failure=True,
        )
        if check.strip() == "":
            logger.debug("WebRTC port-based rules already applied — skipping")
            return

        rules = [
            "iptables -I OUTPUT -p udp --dport 1024:65535 -j DROP",  # all high-port UDP (STUN on any port)
            "iptables -I OUTPUT -p tcp --dport 3478 -j DROP",
            "iptables -I OUTPUT -p tcp --dport 5349 -j DROP",
        ]
        for rule in rules:
            try:
                result = await self.adb.shell_root(f"{rule} 2>&1")
            except Exception as exc:
                logger.warning(
                    "Android iptables rule failed; continuing without full "
                    "kernel WebRTC UDP block: %s",
                    exc,
                )
                return
            if self._iptables_unavailable(result):
                logger.warning(
                    "Android iptables unavailable; continuing without full "
                    "kernel WebRTC UDP block: %s",
                    result.strip(),
                )
                return
        logger.info("WebRTC blocked via port-based iptables (high-port UDP range + TCP STUN)")

    @staticmethod
    def _iptables_unavailable(output: str) -> bool:
        """Return True when Android iptables cannot use kernel filter tables."""
        text = (output or "").lower()
        return any(
            marker in text
            for marker in (
                "can't initialize iptables table",
                "table does not exist",
                "no chain/target/match by that name",
                "protocol not supported",
                "operation not supported",
            )
        )

    async def remove_webrtc_block(self, chrome_package: str = "com.android.chrome") -> None:
        """Remove iptables WebRTC blocking rules (best-effort cleanup)."""
        # Try removing UID-based rule
        owner_info = await self.adb.shell(
            f"stat -c '%U' /data/data/{chrome_package} 2>/dev/null",
            allow_failure=True,
        )
        if owner_info and owner_info.strip().startswith("u0_a"):
            try:
                chrome_uid = 10000 + int(owner_info.strip().split("u0_a")[1])
                await self.adb.shell_root(
                    f"iptables -D OUTPUT -p udp -m owner --uid-owner {chrome_uid} -j DROP 2>/dev/null || true",
                )
            except (ValueError, IndexError):
                pass

        # Also remove port-based rules (in case fallback was used)
        rules = [
            "iptables -D OUTPUT -p udp --dport 1024:65535 -j DROP",
            "iptables -D OUTPUT -p tcp --dport 3478 -j DROP",
            "iptables -D OUTPUT -p tcp --dport 5349 -j DROP",
        ]
        for rule in rules:
            await self.adb.shell_root(f"{rule} 2>/dev/null || true")
        logger.info("WebRTC iptables rules removed")

    async def apply_cpu_cores_spoof(self, target_cores: int, restart_zygote: bool = False) -> None:
        """Override visible CPU count via bind-mounts on /sys and /proc/stat.

        Chrome can read CPU topology from multiple kernel views. Spoof both:
          - /sys/devices/system/cpu/online (sysconf/getconf path)
          - /proc/stat (worker/process-level enumeration path)

        Args:
            target_cores: Number of cores to report.
            restart_zygote: Restart zygote to flush stale cached CPU count.
        """
        if target_cores < 1:
            logger.warning("Invalid target cores: %d", target_cores)
            return

        for path in ("/sys/devices/system/cpu/online", "/proc/stat"):
            try:
                await self.adb.shell_root(f"umount {path} 2>/dev/null || true")
            except Exception:
                pass

        current = await self.adb.shell(
            "cat /sys/devices/system/cpu/online",
            timeout=5, allow_failure=True,
        )
        current_count = current.strip()

        real_cores = 0
        try:
            for part in current_count.split(","):
                part = part.strip()
                if not part:
                    continue
                if "-" in part:
                    lo, hi = part.split("-", 1)
                    real_cores += int(hi) - int(lo) + 1
                else:
                    real_cores += 1
        except (ValueError, IndexError):
            real_cores = 0

        if real_cores > 0 and target_cores > real_cores:
            logger.warning(
                "Target cores (%d) > real cores (%d) - capping to %d",
                target_cores, real_cores, real_cores,
            )
            target_cores = real_cores

        cpu_range = "0" if target_cores == 1 else f"0-{target_cores - 1}"
        await self.adb.shell_root(
            f'printf "%s" "{cpu_range}" > /data/local/tmp/cpu_online',
        )
        await self.adb.shell_root(
            "mount --bind /data/local/tmp/cpu_online /sys/devices/system/cpu/online",
        )

        await self.adb.shell_root(
            "out=/data/local/tmp/proc_stat_spoof; "
            "head -n 1 /proc/stat > \"$out\"; "
            f"i=0; while [ $i -lt {target_cores} ]; do "
            "grep \"^cpu${i} \" /proc/stat >> \"$out\"; "
            "i=$((i+1)); "
            "done; "
            "grep -v '^cpu' /proc/stat >> \"$out\"",
        )
        await self.adb.shell_root(
            "mount --bind /data/local/tmp/proc_stat_spoof /proc/stat",
        )

        if restart_zygote:
            try:
                await self.adb.shell_root("setprop ctl.restart zygote", timeout=8)
                await sleep(4.0)
                for _ in range(20):
                    zygote = await self.adb.shell(
                        "getprop init.svc.zygote", timeout=3, allow_failure=True,
                    )
                    boot = await self.adb.shell(
                        "getprop sys.boot_completed", timeout=3, allow_failure=True,
                    )
                    if zygote.strip() == "running" and boot.strip() == "1":
                        break
                    await sleep(1.0)
                logger.info("Zygote restarted after CPU spoof")
            except Exception as exc:
                logger.warning("Zygote restart failed after CPU spoof: %s", exc)

        verify = await self.adb.shell(
            "getconf _NPROCESSORS_ONLN",
            timeout=5, allow_failure=True,
        )
        verify_count = verify.strip()

        proc_verify = await self.adb.shell(
            "grep '^cpu[0-9]' /proc/stat | wc -l",
            timeout=5, allow_failure=True,
        )
        proc_count = proc_verify.strip()

        if verify_count == str(target_cores) and proc_count == str(target_cores):
            logger.info(
                "CPU cores spoofed: %d -> %d (/sys + /proc/stat bind-mounts)",
                real_cores, target_cores,
            )
        else:
            logger.warning(
                "CPU spoof partial: getconf=%s, /proc/stat cpu lines=%s (expected %d)",
                verify_count, proc_count, target_cores,
            )

    async def apply_battery_spoof(self) -> None:
        """Spoof battery state to look like a real phone, not an emulator.

        Emulator defaults (AC=true, level=100, status=5/full, temp=0) are
        instant detection flags. Uses `dumpsys battery set` which overrides
        the BatteryService - Chrome's navigator.getBattery() reads from this.

        Randomizes: level (23-89%), temperature (25-33C), charging source.
        """
        import random

        level = random.randint(23, 89)
        temp = random.randint(250, 330)  # tenths of C (25.0-33.0C)

        # Reset battery stats first to clear stale history that can produce
        # negative dischargingTime values after manual dumpsys overrides.
        await self.adb.shell("dumpsys batterystats --reset", allow_failure=True)

        source = random.choice(["ac", "usb", "wireless"])
        cmds = [
            f"dumpsys battery set level {level}",
            "dumpsys battery set status 2",      # charging
            f"dumpsys battery set ac {1 if source == 'ac' else 0}",
            f"dumpsys battery set usb {1 if source == 'usb' else 0}",
            f"dumpsys battery set wireless {1 if source == 'wireless' else 0}",
            f"dumpsys battery set temp {temp}",
        ]
        for cmd in cmds:
            await self.adb.shell(cmd, allow_failure=True)

        logger.info(
            "Battery spoofed: %d%%, charging via %s, %.1fC",
            level, source, temp / 10.0,
        )

    @staticmethod
    def _parse_bounds_center(bounds: str) -> Optional[tuple[int, int]]:
        """Parse Android bounds format '[x1,y1][x2,y2]' and return center."""
        try:
            clean = bounds.strip().replace("][", ",").replace("[", "").replace("]", "")
            x1s, y1s, x2s, y2s = clean.split(",")
            x1, y1, x2, y2 = int(x1s), int(y1s), int(x2s), int(y2s)
            return ((x1 + x2) // 2, (y1 + y2) // 2)
        except Exception:
            return None

    async def _dump_uiautomator_xml(self, path: str = "/data/local/tmp/damru_ui.xml") -> str:
        """Dump current UI hierarchy and return XML text."""
        await self.adb.shell(
            f"uiautomator dump {path} >/dev/null 2>&1",
            timeout=10, allow_failure=True,
        )
        return await self.adb.shell(f"cat {path}", timeout=5, allow_failure=True)

    @staticmethod
    def _prepare_google_tts_apks() -> list[str]:
        """Return bundled GoogleTTS APKs in installation order."""
        bundled = find_any_bundle_apk(["google_tts.apk", "GoogleTTS.apk"])
        if bundled is not None:
            return [str(bundled)]
        return []

    async def _ensure_local_tts_apk_installed(
        self,
        package: str,
        names: list[str],
        installed_pkgs: set[str],
    ) -> set[str]:
        """Install a TTS APK from the local Damru APK bundle when present."""
        if package in installed_pkgs:
            return installed_pkgs

        apk = find_any_bundle_apk(names)
        if apk is None:
            return installed_pkgs

        out = await self.adb._run(
            ["install", "-r", str(apk)],
            timeout=240, allow_failure=True,
        )
        if "success" not in out.lower():
            logger.debug("Local TTS APK install output for %s: %s", apk.name, out)
            return installed_pkgs

        refreshed = await self.adb.shell(
            "pm list packages",
            timeout=10, allow_failure=True,
        )
        refreshed_pkgs = {
            line.replace("package:", "").strip()
            for line in refreshed.splitlines()
            if line.strip().startswith("package:")
        }
        if package in refreshed_pkgs:
            logger.info("Installed local TTS APK: %s", apk.name)
            return refreshed_pkgs
        return installed_pkgs

    async def _ensure_google_tts_installed(self, installed_pkgs: set[str]) -> set[str]:
        """Install Google Speech Services from the local Damru APK bundle."""
        pkg = "com.google.android.tts"
        if pkg in installed_pkgs:
            return installed_pkgs

        try:
            apk_paths = await asyncio.to_thread(self._prepare_google_tts_apks)
            for apk in apk_paths:
                out = await self.adb._run(
                    ["install", "-r", apk],
                    timeout=240, allow_failure=True,
                )
                if "success" not in out.lower():
                    logger.debug("GoogleTTS install output for %s: %s", os.path.basename(apk), out)

            refreshed = await self.adb.shell(
                "pm list packages",
                timeout=10, allow_failure=True,
            )
            refreshed_pkgs = {
                line.replace("package:", "").strip()
                for line in refreshed.splitlines()
                if line.strip().startswith("package:")
            }
            if pkg in refreshed_pkgs:
                logger.info("Installed Google Speech Services from APK bundle")
                return refreshed_pkgs
        except Exception as exc:
            logger.debug("Google Speech Services bundle install failed: %s", exc)

        return installed_pkgs

    async def ensure_speech_voices(self) -> None:
        """Ensure Android TTS has at least one local voice for speechSynthesis.

        Preference order:
          1) eSpeak-NG (bundled 100+ voices, always works, no Play Services needed)
          2) Google Speech Services (if present AND has voice data)
          3) RHVoice (with voice auto-install flow)
          4) Current configured engine (if installed)

        eSpeak is preferred because it bundles voices in the APK. Google TTS
        needs Play Services to download voice data. On containers (redroid)
        without Play Services it installs but has 0 voices.

        When both eSpeak AND Google TTS are enabled, Chrome's
        speechSynthesis.getVoices() lists voices from ALL engines,
        giving 100+ (eSpeak) + whatever Google TTS provides.

        No JS spoofing involved.
        """
        rhvoice_pkg = "com.github.olga_yakovleva.rhvoice.android"
        google_tts_pkg = "com.google.android.tts"
        espeak_pkg = "com.reecedunn.espeak"

        installed_raw = await self.adb.shell(
            "pm list packages",
            timeout=8, allow_failure=True,
        )
        installed_pkgs = {
            line.replace("package:", "").strip()
            for line in installed_raw.splitlines()
            if line.strip().startswith("package:")
        }

        # Try to install eSpeak-NG (best option for containers)
        if espeak_pkg not in installed_pkgs:
            espeak_ok = await self.ensure_espeak_tts()
            if espeak_ok:
                installed_pkgs.add(espeak_pkg)

        installed_pkgs = await self._ensure_google_tts_installed(installed_pkgs)
        installed_pkgs = await self._ensure_local_tts_apk_installed(
            rhvoice_pkg,
            ["rhvoice.apk", "RHVoice.apk"],
            installed_pkgs,
        )

        current_engine = (
            await self.adb.shell(
                "settings get secure tts_default_synth",
                timeout=5, allow_failure=True,
            )
        ).strip()

        # Google TTS needs Play Services to download voice data.
        # On containers (redroid) without Play Services it installs but has 0 voices.
        # Check for actual voice data before selecting it.
        google_has_voices = False
        if google_tts_pkg in installed_pkgs:
            voice_check = await self.adb.shell_root(
                f"find /data/data/{google_tts_pkg}/files -type f 2>/dev/null | head -1",
                timeout=5,
            )
            google_has_voices = bool(voice_check.strip())

        # Prefer eSpeak (bundled voices, always works on containers)
        if espeak_pkg in installed_pkgs:
            selected_pkg = espeak_pkg
        elif google_tts_pkg in installed_pkgs and google_has_voices:
            selected_pkg = google_tts_pkg
        elif rhvoice_pkg in installed_pkgs:
            selected_pkg = rhvoice_pkg
        elif current_engine in installed_pkgs and current_engine:
            selected_pkg = current_engine
        elif google_tts_pkg in installed_pkgs:
            selected_pkg = google_tts_pkg  # last resort even without voice data
        else:
            logger.warning("Speech voices unavailable: no TTS engine package installed")
            return

        await self.adb.shell(f"settings put secure tts_default_synth {selected_pkg}", allow_failure=True)
        await self.adb.shell("settings put secure tts_default_locale en-US", allow_failure=True)
        await self.adb.shell("settings put secure tts_default_rate 100", allow_failure=True)
        await self.adb.shell("settings put secure tts_default_pitch 100", allow_failure=True)

        # Enable ALL installed TTS engines so Chrome lists voices from all of them.
        # This maximizes speechSynthesis.getVoices() count.
        enabled_engines = []
        for pkg in [espeak_pkg, google_tts_pkg, rhvoice_pkg]:
            if pkg in installed_pkgs:
                enabled_engines.append(pkg)
        if enabled_engines:
            # Value must be quoted — otherwise Android `settings put` only
            # keeps the first space-separated word.
            plugins_val = " ".join(enabled_engines)
            await self.adb.shell(
                f"settings put secure tts_enabled_plugins '{plugins_val}'",
                allow_failure=True,
            )

        if selected_pkg == espeak_pkg:
            # Initialize eSpeak TTS service so voices are available when
            # Chrome queries speechSynthesis.getVoices().
            await self.adb.shell(
                f"am startservice -a android.intent.action.TTS_SERVICE "
                f"-n {espeak_pkg}/.TtsService",
                allow_failure=True,
            )
            await self.adb.shell(
                f"am start -a android.speech.tts.engine.CHECK_TTS_DATA "
                f"-n {espeak_pkg}/.CheckVoiceData",
                allow_failure=True,
            )
            # Also warm-start the engine via Android TTS manager intent
            # so the service is fully bound before Chrome needs it.
            await self.adb.shell(
                f"am startservice --user 0 "
                f"-n {espeak_pkg}/.TtsService",
                allow_failure=True,
            )
            await sleep(2.0)
            logger.info("Speech TTS engine: eSpeak-NG (100+ bundled voices)")
            return
        if selected_pkg == google_tts_pkg:
            logger.info("Speech TTS engine: Google Speech Services (%s)",
                        "with voices" if google_has_voices else "no voice data")
            return
        if selected_pkg != rhvoice_pkg:
            logger.info("Speech TTS engine: %s", selected_pkg)
            return

        pkg = rhvoice_pkg
        app_data = f"/data/data/{pkg}/app_data"
        voice_glob = f"{pkg}.voice.*"

        voice_count_raw = await self.adb.shell_root(
            f"find {app_data} -maxdepth 1 -type d -name '{voice_glob}' 2>/dev/null | wc -l",
            timeout=8,
        )
        try:
            voice_count = int(voice_count_raw.strip() or "0")
        except ValueError:
            voice_count = 0

        if voice_count > 0:
            logger.info("Speech voices ready: %d local voice package(s)", voice_count)
            return

        if pkg not in installed_pkgs:
            logger.warning("Speech voices unavailable: RHVoice package not installed")
            return

        # Open RHVoice installer flow.
        await self.adb.shell(
            f"am start -a android.speech.tts.engine.INSTALL_TTS_DATA -n {pkg}/.MainActivity",
            timeout=10, allow_failure=True,
        )
        await sleep(2.0)
        # Multi-pass installer: tap all visible "Install" buttons across
        # multiple scroll pages to maximize available local voices.
        installs_done = 0
        tapped_bounds: set[str] = set()
        action_id = f"{pkg}:id/action"
        for _ in range(5):
            xml = await self._dump_uiautomator_xml()
            try:
                root = ET.fromstring(xml)
            except ET.ParseError:
                root = None

            install_centers: list[tuple[int, int, str]] = []
            if root is not None:
                for node in root.iter("node"):
                    rid = node.attrib.get("resource-id", "")
                    desc = (node.attrib.get("content-desc", "") or "").strip().lower()
                    text = (node.attrib.get("text", "") or "").strip().lower()
                    bounds = node.attrib.get("bounds", "")
                    if rid != action_id:
                        continue
                    if bounds in tapped_bounds:
                        continue
                    if ("install" not in desc and "instalar" not in desc and
                            "install" not in text and "instalar" not in text):
                        continue
                    center = self._parse_bounds_center(bounds)
                    if center is not None:
                        install_centers.append((center[0], center[1], bounds))

            install_centers.sort(key=lambda p: (p[1], p[0]))
            for cx, cy, bounds in install_centers:
                await self.adb.shell(f"input tap {cx} {cy}", allow_failure=True)
                tapped_bounds.add(bounds)
                installs_done += 1
                await sleep(0.6)

            # Scroll to discover additional language/voice rows.
            await self.adb.shell("input swipe 540 1850 540 550 280", allow_failure=True)
            await sleep(1.0)

        if installs_done == 0:
            logger.warning("Speech voice install UI found no tappable Install buttons")
            return

        # Downloads are performed by WorkManager in background.
        await sleep(55.0)
        voice_count_raw = await self.adb.shell_root(
            f"find {app_data} -maxdepth 1 -type d -name '{voice_glob}' 2>/dev/null | wc -l",
            timeout=8,
        )
        try:
            voice_count = int(voice_count_raw.strip() or "0")
        except ValueError:
            voice_count = 0

        if voice_count > 0:
            logger.info("Speech voices installed: %d local voice package(s)", voice_count)
        else:
            logger.warning("Speech voices still missing after install attempt")

    async def apply_dns_leak_prevention(self) -> None:
        """Block direct DNS queries via iptables to prevent DNS leaks.

        When using system HTTP proxy, Chrome sends HTTP requests through
        the proxy (which resolves DNS). But DNS prefetch, speculative
        connections, and system services can still query DNS directly,
        leaking the real location.

        This blocks ALL direct DNS (port 53) traffic. Since the proxy
        is configured by IP address (not hostname), no DNS is needed
        to reach it. Chrome resolves domains through the HTTP proxy.

        Also sets Android DNS servers to reduce leak surface.
        """
        rules = [
            # Block all direct DNS (Chrome uses proxy for resolution)
            "iptables -I OUTPUT -p udp --dport 53 -j DROP",
            "iptables -I OUTPUT -p tcp --dport 53 -j DROP",
        ]
        for rule in rules:
            await self.adb.shell_root(rule)

        # Set Android DNS to localhost (unusable) to prevent system DNS leaks
        # This doesn't break anything because Chrome resolves through proxy
        await self.adb.shell_root("setprop net.dns1 127.0.0.1")
        await self.adb.shell_root("setprop net.dns2 127.0.0.1")

        logger.info("DNS leak prevention: direct DNS blocked via iptables")

    async def remove_dns_leak_prevention(self) -> None:
        """Remove DNS blocking iptables rules (best-effort cleanup)."""
        rules = [
            "iptables -D OUTPUT -p udp --dport 53 -j DROP",
            "iptables -D OUTPUT -p tcp --dport 53 -j DROP",
        ]
        for rule in rules:
            await self.adb.shell_root(rule)

        # Restore DNS to Google DNS
        await self.adb.shell_root("setprop net.dns1 8.8.8.8")
        await self.adb.shell_root("setprop net.dns2 8.8.4.4")

        logger.info("DNS leak prevention removed")

    async def apply_gpu_spoof(
        self, device: AndroidDevice, chrome_package: str, native_gpu: str = ""
    ) -> None:
        """Spoof GPU renderer + GL extensions for Chrome via renderer.config.

        renderer.config supports per-app overrides:
          CustomizedRendererString  -> changes WEBGL_debug_renderer_info
          CustomizedGLESExtension   -> changes raw GL extension list

        When the target device's GPU family differs from the emulator's native
        GPU, we ALSO override extensions so the WebGL extension set matches
        the spoofed renderer (e.g. no BPTC/RGTC for Mali targets).

        Approach: direct write to /system + restart opengl-gc ONCE (in apply only,
        not in remove_gpu_spoof, to avoid double-restart grey screen).
        Silently skipped if renderer.config doesn't exist.
        """
        src = "/system/etc/mumu-configs/renderer.config"
        backup = "/data/local/tmp/damru_renderer_orig.config"
        entry_file = "/data/local/tmp/damru_gpu_entry.txt"

        # Check if renderer config exists
        out = await self.adb.shell(
            f"test -f {src} && echo OK", timeout=5, allow_failure=True
        )
        if "OK" not in out:
            logger.warning("No renderer.config found - GPU spoof not available on this emulator")
            return

        # Backup original config ONLY if no backup exists yet.
        # This prevents the accumulation bug: if a previous run left damru
        # entries in renderer.config and cleanup failed, re-backing up would
        # save the corrupted config as "original". By only saving once, the
        # backup always contains the truly original config.
        out = await self.adb.shell(
            f"test -f {backup} && echo EXISTS", timeout=5, allow_failure=True
        )
        if "EXISTS" not in out:
            await self.adb.shell_root(f"cp {src} {backup}")
            logger.debug("Backed up original renderer.config")
        else:
            logger.debug("Using existing backup of original renderer.config")

        # Build Chrome entry with escaped package name (dots -> \.)
        pkg_escaped = chrome_package.replace(".", "\\.")
        renderer = device.webgl_renderer

        # NOTE: We only override the renderer STRING, not the GL extension list.
        # CustomizedGLESExtension was tested but breaks WebGL1 because Chrome
        # tries to USE extensions that don't exist on the actual GPU hardware
        # (e.g. GL_ARM_* on Adreno). The renderer string override alone is
        # sufficient - BrowserScan doesn't cross-reference extensions vs renderer.
        target_family = device.gpu_family
        native_family = _detect_gpu_family(native_gpu)
        if target_family != native_family:
            logger.info("GPU family mismatch: native=%s, target=%s (renderer spoofed, extensions kept native)",
                        native_family, target_family)

        # Always restart opengl-gc to clear any stale GPU process connection state
        # from a previous killed or incomplete session. Without this, Chrome's GPU
        # process may fail to connect to opengl-gc (grey screen) even when no
        # renderer.config change is needed.
        # We do NOT restart in remove_gpu_spoof() — only one restart per session
        # to avoid the double-restart grey screen (cleanup + next apply = broken).
        await self.adb.shell_root("stop opengl-gc")
        await sleep(0.5)
        await self.adb.shell_root("start opengl-gc")
        await sleep(5.0)  # wait for opengl-gc to be fully ready before Chrome connects

        # Skip renderer.config write if native GPU already reports the target string.
        # Writing an entry causes opengl-gc to intercept Chrome GPU connections which
        # is unnecessary overhead when native renderer already matches.
        if renderer in native_gpu:
            logger.info(
                "GPU renderer matches native '%s' — skipping renderer.config write (opengl-gc reset done)",
                renderer,
            )
            self._gpu_spoofed = True
            return

        entry_lines = [
            f"Name {pkg_escaped}",
            f"CustomizedRendererString {renderer}",
        ]

        entry = "\n".join(entry_lines) + "\n\n"

        # Write entry to temp file via base64 (avoids shell escaping issues)
        import base64
        b64 = base64.b64encode(entry.encode()).decode()
        await self.adb.shell_root(f"echo '{b64}' | base64 -d > {entry_file}")

        # Make system writable, write config, restore read-only
        await self.adb.shell(
            f"su 0 mount -o remount,rw /system 2>/dev/null || true",
            allow_failure=True,
        )
        # Prepend Chrome entry to config file
        await self.adb.shell_root(f"cat {entry_file} {backup} > {src}")
        await self.adb.shell_root(f"rm -f {entry_file}")
        await self.adb.shell(
            f"su 0 mount -o remount,ro /system 2>/dev/null || true",
            allow_failure=True,
        )

        self._gpu_spoofed = True
        logger.info("GPU spoofed: %s for %s (renderer.config written, opengl-gc restarted)", renderer, chrome_package)

    # Vulkan vendor IDs used by ANGLE to construct GL_VENDOR string.
    # SwiftShader reports 0x1AE0 (Google). Changing this makes ANGLE
    # automatically map to the correct vendor name.
    _VULKAN_VENDOR_IDS = {
        "qualcomm": 0x5143,
        "arm": 0x13B5,
        "samsung": 0x144D,
        "google": 0x1AE0,
        "nvidia": 0x10DE,
        "intel": 0x8086,
        "amd": 0x1002,
    }
    _VULKAN_DEVICE_IDS = {
        # Real IDs vary by SKU/driver; these are plausible family-level values
        # to avoid SwiftShader sentinel 0xC0DE leakage.
        "adreno": 0x043A,
        "mali": 0x7093,
        "xclipse": 0x0920,
    }

    async def is_gpu_already_patched(self, target_renderer: str) -> bool:
        """Check if vulkan.pastel.so already contains the target renderer.

        Used by warm-reuse path to skip GPU re-patch + SurfaceFlinger
        restart when the same device (or same GPU model) is used again.
        """
        vulkan_so = "/vendor/lib64/hw/vulkan.pastel.so"
        result = await self.adb.shell(
            f"su 0 strings {vulkan_so} 2>/dev/null | grep -qF '{target_renderer}' && echo YES",
            timeout=10, allow_failure=True,
        )
        return "YES" in result

    @staticmethod
    def effective_renderer(device: AndroidDevice) -> str:
        """Compute the actual renderer string that would be patched into the .so.

        Replicates the truncation/mapping logic from apply_gpu_binary_spoof
        so callers can check is_gpu_already_patched() without duplicating code.
        """
        renderer = device.webgl_renderer.strip()
        if device.gpu_family == "xclipse":
            renderer = "Xclipse 920"
        max_len = 24
        if len(renderer.encode("utf-8")) > max_len:
            short = {
                "adreno": "Adreno (TM) 740",
                "mali": "Mali-G715",
                "xclipse": "Xclipse 920",
            }.get(device.gpu_family, renderer)
            renderer = short[:max_len]
        return renderer

    async def apply_gpu_binary_spoof(self, device: AndroidDevice) -> None:
        """Spoof GPU by binary-patching vulkan.pastel.so (redroid 14).

        Redroid 14 uses ANGLE (OpenGL ES over Vulkan) with SwiftShader as
        the Vulkan backend via vulkan.pastel.so. Chrome's WebGL strings
        are composed by ANGLE from the Vulkan device properties:
          Renderer: ANGLE (<vendor>, Vulkan 1.3.0 (<deviceName> ...), <driverName>-5.0.0)
          Vendor:   Google Inc. (<vendor>)

        We patch vulkan.pastel.so with THREE types of changes:
          1. String: "SwiftShader Device" -> target GPU (e.g. "Adreno (TM) 750")
          2. String: "SwiftShader driver" -> target driver name
          3. Binary: vendorID 0x1AE0 -> target vendor ID (e.g. 0x5143 for Qualcomm)
             Found by locating vendorID near deviceID 0xC0DE in the binary.

        The vendorID patch is critical: ANGLE maps it to the vendor name that
        appears in both GL_VENDOR "Google Inc. (Google)" -> "Google Inc. (Qualcomm)"
        and GL_RENDERER "ANGLE (Google, ...)" -> "ANGLE (Qualcomm, ...)".

        Note: "Google Inc." prefix in GL_VENDOR is ANGLE's own constant (normal
        for any device using ANGLE). Only the parenthesized vendor name leaks.

        After patching, SurfaceFlinger is restarted to reload the .so.
        Without SF restart, Chrome can't render (empty UI, no devtools socket).

        Args:
            device: Target device profile with webgl_renderer and webgl_vendor.
        """
        vulkan_so = "/vendor/lib64/hw/vulkan.pastel.so"

        vk_exists = "OK" in await self.adb.shell(
            f"test -f {vulkan_so} && echo OK", timeout=5, allow_failure=True
        )
        if not vk_exists:
            logger.warning("vulkan.pastel.so not found - GPU binary spoof unavailable")
            return

        # Keep renderer names reasonable; binary patcher will still enforce
        # in-slot writes and truncate safely if the storage slot is smaller.
        target_renderer = device.webgl_renderer.strip()
        if device.gpu_family == "xclipse":
            # Fits the SwiftShader slot while retaining the exact model family.
            target_renderer = "Xclipse 920"
        max_renderer_len = 24
        if len(target_renderer.encode("utf-8")) > max_renderer_len:
            short_renderer = {
                "adreno": "Adreno (TM) 740",
                "mali": "Mali-G715",
                "xclipse": "Xclipse 920",
            }.get(device.gpu_family, target_renderer)
            target_renderer = short_renderer[:max_renderer_len]

        target_vendor = device.webgl_vendor       # e.g. "Qualcomm"

        # Determine target Vulkan vendor ID
        vendor_key = target_vendor.lower()
        target_vendor_id = self._VULKAN_VENDOR_IDS.get(vendor_key)
        if target_vendor_id is None:
            # Try matching by gpu_family
            family = device.gpu_family
            family_vendor_map = {"adreno": "qualcomm", "mali": "arm", "xclipse": "samsung"}
            vendor_key = family_vendor_map.get(family, "")
            target_vendor_id = self._VULKAN_VENDOR_IDS.get(vendor_key)

        await self.adb.shell("su 0 mount -o remount,rw /vendor 2>/dev/null", allow_failure=True)

        # NOTE: No backup integrity check here. _binary_patch_so() handles
        # backup creation correctly: backs up ONCE from the original .so,
        # then always patches from the backup. Android's toybox `strings`
        # unreliably finds literal strings in ELF binaries, so any check
        # using `strings | grep` causes false positives that corrupt the
        # backup by overwriting it with an already-patched .so.

        # Build string replacements
        # Driver name: use GPU family for a clean, short driver name
        _DRIVER_NAMES = {
            "adreno": "Adreno",
            "mali": "ARM",
            "xclipse": "Xclipse",
        }
        driver_name = _DRIVER_NAMES.get(device.gpu_family, target_renderer.split()[0])
        target_device_id = self._VULKAN_DEVICE_IDS.get(device.gpu_family)

        # ANGLE builds GL_RENDERER from Vulkan device properties:
        #   ANGLE (<vendor>, Vulkan X.X.X (<deviceName> (0x<ID>)), <driverName>-X.X.X)
        # SwiftShader constructs deviceName via snprintf("%s (%s)", base, llvm_ver)
        # producing "SwiftShader Device (LLVM 10.0.0)". Patching the "%s (%s)"
        # format string to "%s" strips the LLVM version tell completely.
        # DeviceID (0x0000C0DE) is a uint32, not a text string — patched
        # via the separate device_id_patch parameter below.
        replacements = [
            (b"SwiftShader Device", target_renderer),
            (b"SwiftShader driver", driver_name),
            # Kill the "%s (%s)" format that appends "(LLVM 10.0.0)" to deviceName
            (b"%s (%s)", "%s"),
        ]

        patched = await self._binary_patch_so(
            vulkan_so,
            "/data/local/tmp/damru_vk_pastel_orig.so",
            replacements,
            vendor_id_patch=(0x1AE0, target_vendor_id) if target_vendor_id else None,
            device_id_patch=(0xC0DE, target_device_id) if target_device_id else None,
        )

        await self.adb.shell("su 0 mount -o remount,ro /vendor 2>/dev/null", allow_failure=True)
        await self.adb.shell("su 0 sync", allow_failure=True)

        if patched:
            self._gpu_binary_spoofed = True
            vid_str = f", vendorID=0x{target_vendor_id:04X}" if target_vendor_id else ""
            logger.info("GPU binary spoofed: %s (%s%s) via vulkan.pastel.so patch",
                        target_renderer, target_vendor, vid_str)

            # SurfaceFlinger must restart to reload the patched .so.
            # Without this, Chrome can't render (empty UI, no devtools socket).
            await self.adb.shell_root("setprop ctl.restart surfaceflinger")
            logger.info("SurfaceFlinger restarted (GPU .so reload)")

            # SF restart kills Zygote + all apps and can drop ADB connection.
            # On redroid containers, ADB goes offline for 5-10 seconds.
            # Wait longer, then aggressively reconnect ADB before proceeding.
            await sleep(5.0)

            # Force ADB reconnect — disconnect + connect cycle
            serial = self.adb.serial
            for _reconn in range(5):
                await self.adb._run(["disconnect", serial], timeout=3, allow_failure=True)
                await sleep(1.0)
                await self.adb._run(["connect", serial], timeout=5, allow_failure=True)
                await sleep(1.0)
                await self.adb._run(["root"], timeout=5, allow_failure=True)
                await sleep(1.0)
                # Verify we can actually talk to the device
                out = await self.adb.shell("id", timeout=5, allow_failure=True)
                if "uid=0" in out:
                    logger.info("ADB reconnected after SF restart (attempt %d)", _reconn + 1)
                    break
                logger.warning("ADB reconnect attempt %d/5: device not ready yet", _reconn + 1)
                await sleep(2.0)
            else:
                logger.warning("ADB reconnect failed after 5 attempts, continuing anyway")

            # Poll PackageManager readiness — system needs time to respawn
            # Zygote and re-register package activities.
            for _poll in range(20):
                out = await self.adb.shell(
                    "pm path com.android.chrome 2>&1 | head -1",
                    timeout=5, allow_failure=True,
                )
                if "base.apk" in out:
                    break
                await sleep(1.0)
            else:
                logger.warning("PackageManager not ready after 20s, continuing anyway")
            await sleep(3.0)  # Extra buffer for Activity Manager to re-register
        else:
            logger.warning("GPU binary spoof: no patches applied")

    async def _binary_patch_so(
        self,
        so_path: str,
        backup_path: str,
        replacements: list,
        vendor_id_patch: tuple | None = None,
        device_id_patch: tuple | None = None,
    ) -> bool:
        """Pull a .so, binary-patch string literals and vendorID, push it back.

        Each replacement is (original_bytes, target_string). Target is
        truncated/null-padded to match original length exactly.

        vendor_id_patch: optional (old_id, new_id) tuple of uint32 values.
        Finds old_id (as little-endian 4 bytes) near deviceID 0xC0DE and
        replaces with new_id.
        device_id_patch: optional (old_id, new_id) tuple of uint32 values.
        Replaces sentinel 0xC0DE with a plausible vendor-specific device ID.

        Returns True if any replacements were made.
        """
        import os
        import struct
        import tempfile

        # Backup original ONLY ONCE
        out = await self.adb.shell(
            f"test -f {backup_path} && echo EXISTS", timeout=5, allow_failure=True
        )
        if "EXISTS" not in out:
            await self.adb.shell_root(f"cp {so_path} {backup_path}")
            logger.debug("Backed up %s", so_path)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".so") as tmp:
            local_path = tmp.name

        try:
            await self.adb._run(
                ["pull", backup_path, local_path], timeout=60, allow_failure=False
            )

            with open(local_path, "rb") as f:
                data = bytearray(f.read())

            total_patches = 0

            # --- String replacements ---
            for orig_bytes, target_str in replacements:
                target_full = target_str.encode("utf-8")

                count = 0
                available = 0
                idx = 0
                while True:
                    idx = data.find(orig_bytes, idx)
                    if idx == -1:
                        break

                    # Determine available space: original string + trailing nulls.
                    # In .rodata, strings are packed contiguously:
                    #   "SwiftShader Device\0next_string\0..."
                    # So available = len(orig) + trailing_nulls (typically just 1).
                    end = idx + len(orig_bytes)
                    end_limit = min(end + 238, len(data))  # cap scan at 256 total
                    while end < end_limit and data[end] == 0:
                        end += 1
                    available = end - idx

                    # Safe write: never extend beyond contiguous null-padded
                    # string storage. Overwriting adjacent rodata can crash
                    # SurfaceFlinger/ANGLE.
                    if available <= 0:
                        idx += len(orig_bytes)
                        continue

                    # If there is explicit null padding after the original
                    # token, preserve null-terminated semantics. Otherwise,
                    # do a fixed-width overwrite only.
                    if available > len(orig_bytes):
                        payload = target_full[:available - 1]
                        target_encoded = payload + b"\x00"
                        if len(target_encoded) < available:
                            target_encoded += b"\x00" * (available - len(target_encoded))
                    else:
                        target_encoded = target_full[:available]
                        if len(target_encoded) < available:
                            target_encoded += b"\x00" * (available - len(target_encoded))

                    data[idx:idx + available] = target_encoded
                    count += 1
                    idx += available

                if count:
                    logger.debug(
                        "Patched %r -> %r (%d occurrences, %d bytes each) in %s",
                        orig_bytes.decode(), target_str, count, available, so_path.split("/")[-1],
                    )
                    total_patches += count
                else:
                    logger.debug("String %r not found in %s", orig_bytes.decode(), so_path.split("/")[-1])

            # --- VendorID binary patch ---
            if vendor_id_patch:
                old_vid, new_vid = vendor_id_patch
                old_vid_bytes = struct.pack("<I", old_vid)
                new_vid_bytes = struct.pack("<I", new_vid)
                device_id_bytes = struct.pack("<I", 0xC0DE)
                window = 64  # search vendorID within 64 bytes of deviceID

                # Find all deviceID 0xC0DE positions
                device_positions = []
                idx = 0
                while True:
                    idx = data.find(device_id_bytes, idx)
                    if idx == -1:
                        break
                    device_positions.append(idx)
                    idx += 4

                vid_count = 0
                for dpos in device_positions:
                    search_start = max(0, dpos - window)
                    search_end = min(len(data), dpos + window)
                    vidx = search_start
                    while True:
                        vidx = data.find(old_vid_bytes, vidx, search_end)
                        if vidx == -1:
                            break
                        data[vidx:vidx + 4] = new_vid_bytes
                        vid_count += 1
                        vidx += 4

                if vid_count:
                    logger.debug(
                        "Patched vendorID 0x%04X -> 0x%04X (%d occurrences) in %s",
                        old_vid, new_vid, vid_count, so_path.split("/")[-1],
                    )
                    total_patches += vid_count
                else:
                    logger.debug(
                        "VendorID 0x%04X not found near deviceID 0xC0DE in %s",
                        old_vid, so_path.split("/")[-1],
                    )

            # --- DeviceID binary patch ---
            if device_id_patch:
                old_did, new_did = device_id_patch
                old_did_bytes = struct.pack("<I", old_did)
                new_did_bytes = struct.pack("<I", new_did)

                did_count = 0
                idx = 0
                while True:
                    idx = data.find(old_did_bytes, idx)
                    if idx == -1:
                        break
                    data[idx:idx + 4] = new_did_bytes
                    did_count += 1
                    idx += 4

                if did_count:
                    logger.debug(
                        "Patched deviceID 0x%04X -> 0x%04X (%d occurrences) in %s",
                        old_did, new_did, did_count, so_path.split("/")[-1],
                    )
                    total_patches += did_count

            if total_patches == 0:
                return False

            with open(local_path, "wb") as f:
                f.write(data)

            patched_tmp = "/data/local/tmp/damru_patched_tmp.so"
            await self.adb._run(
                ["push", local_path, patched_tmp], timeout=60, allow_failure=False
            )
            await self.adb.shell_root(f"cp {patched_tmp} {so_path}")
            await self.adb.shell_root(f"chmod 644 {so_path}")
            await self.adb.shell_root(f"rm -f {patched_tmp}")
            return True

        finally:
            try:
                os.unlink(local_path)
            except OSError:
                pass

    async def remove_gpu_spoof(self) -> None:
        """Restore original renderer.config and restart opengl-gc."""
        if not getattr(self, "_gpu_spoofed", False):
            return
        src = "/system/etc/mumu-configs/renderer.config"
        backup = "/data/local/tmp/damru_renderer_orig.config"

        # Restore original config
        out = await self.adb.shell(
            f"test -f {backup} && echo OK", timeout=5, allow_failure=True
        )
        if "OK" in out:
            await self.adb.shell_root(f"cp {backup} {src}")
            await self.adb.shell_root(f"rm -f {backup}")

        # Do NOT restart opengl-gc here — restarting on cleanup then again
        # on the next session causes double-restart which breaks Chrome
        # rendering (grey screen). The restored config takes effect naturally
        # when opengl-gc next handles a new Chrome GPU process connection.
        self._gpu_spoofed = False
        logger.info("GPU spoof removed (original config restored, opengl-gc not restarted)")

    async def hide_emulator_identity(self) -> None:
        """Hide emulator-specific system properties.

        MuMu and other emulators expose identity props like ro.nemu=1,
        ro.build.version.nemux=true that fingerprinting sites can detect.
        """
        emulator_props = {
            "ro.nemu": "",
            "ro.build.version.nemux": "",
            "ro.kernel.qemu": "",
            "ro.kernel.qemu.gles": "",
        }
        for key, value in emulator_props.items():
            current = await self.adb.get_prop(key)
            if current:
                if key not in self._original_props:
                    self._original_props[key] = current
                try:
                    resetprop = await self._ensure_resetprop()
                    # Use --delete to remove the prop entirely
                    await self.adb.shell_root(f"{resetprop} --delete {key}")
                except Exception:
                    # Fallback: set to empty
                    try:
                        await self.set_prop(key, "")
                    except Exception:
                        pass
        logger.info("Emulator identity hidden")

    async def restore_original_props(self) -> None:
        """Restore original system props (best-effort)."""
        if not self._original_props:
            return
        logger.info("Restoring %d original system props", len(self._original_props))
        for key, value in self._original_props.items():
            try:
                await self.set_prop(key, value)
            except Exception as e:
                logger.debug("Failed to restore %s: %s", key, e)
        self._original_props.clear()

    # -- Memory spoof (LD_PRELOAD sysinfo interceptor) --

    @staticmethod
    def _compile_fakemem() -> str:
        """Compile libfakemem.so for x86_64. Returns local path to .so.

        Uses gcc in WSL2 (Windows) or native gcc (Linux).
        Result is cached - only compiles once.
        """
        repo_native_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "native"
        )
        c_path = os.path.join(repo_native_dir, "libfakemem.c")
        build_dir = repo_native_dir

        if not os.path.isfile(c_path):
            try:
                asset = resources.files("damru.assets").joinpath("libfakemem.c")
                data = asset.read_bytes()
                build_dir = os.path.join(tempfile.gettempdir(), "damru-native")
                os.makedirs(build_dir, exist_ok=True)
                c_path = os.path.join(build_dir, "libfakemem.c")
                with open(c_path, "wb") as f:
                    f.write(data)
            except Exception:
                pass

        os.makedirs(build_dir, exist_ok=True)
        so_path = os.path.join(build_dir, "libfakemem_x86_64.so")

        if os.path.isfile(so_path):
            return so_path

        if not os.path.isfile(c_path):
            raise RootError(f"libfakemem.c not found at {c_path}")

        if sys.platform == "win32":
            # Convert Windows path to WSL mount path
            def _to_wsl(p: str) -> str:
                p = p.replace("\\", "/")
                if len(p) >= 2 and p[1] == ":":
                    return f"/mnt/{p[0].lower()}{p[2:]}"
                return p

            result = subprocess.run(
                [
                    "wsl", "-d", "Ubuntu", "--", "bash", "-c",
                    f'gcc -shared -fPIC -nostdlib -fno-stack-protector '
                    f'-o "{_to_wsl(so_path)}" "{_to_wsl(c_path)}"',
                ],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                clang_candidates = [
                    r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\Llvm\x64\bin\clang.exe",
                    r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\Llvm\bin\clang.exe",
                    r"C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Tools\Llvm\x64\bin\clang.exe",
                    r"C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Tools\Llvm\bin\clang.exe",
                ]
                clang = next((p for p in clang_candidates if os.path.isfile(p)), None)
                if clang:
                    result = subprocess.run(
                        [
                            clang,
                            "--target=x86_64-linux-android",
                            "-shared",
                            "-fPIC",
                            "-nostdlib",
                            "-fno-stack-protector",
                            "-Wl,-soname,libfakemem.so",
                            "-o", so_path,
                            c_path,
                        ],
                        capture_output=True, text=True, timeout=30,
                    )
        else:
            result = subprocess.run(
                [
                    "gcc", "-shared", "-fPIC", "-nostdlib", "-fno-stack-protector",
                    "-o", so_path, c_path,
                ],
                capture_output=True, text=True, timeout=30,
            )

        if result.returncode != 0:
            raise RootError(f"Failed to compile libfakemem.so:\n{result.stderr}")

        if not os.path.isfile(so_path):
            raise RootError("Compilation succeeded but .so file not found")

        logger.info("Compiled libfakemem.so (%s)", so_path)
        return so_path

    async def apply_memory_spoof(self, target_gb: float) -> None:
        """Push libfakemem.so and write target GB file to device.

        The .so intercepts sysinfo() at syscall level to return fake RAM.
        Target is read from a file so it can be updated per-session
        without restarting Zygote.

        Must call setup_memory_preload() once per container boot to activate.
        """
        # Push .so if not already on device
        out = await self.adb.shell(
            f"test -f {_FAKEMEM_SO} && echo OK",
            timeout=5, allow_failure=True,
        )
        if "OK" not in out:
            so_local = self._compile_fakemem()
            await self.adb.push(so_local, _FAKEMEM_SO)
            await self.adb.shell_root(f"chmod 755 {_FAKEMEM_SO}")
            logger.info("Pushed libfakemem.so to device")

        # Write target GB (Chrome reads this on startup via the .so)
        target_int = int(target_gb)
        await self.adb.shell_root(f"echo {target_int} > {_FAKEMEM_TARGET}")
        logger.debug("Memory spoof target: %d GB", target_int)

    async def setup_memory_preload(self, chrome_package: str = "com.android.chrome") -> None:
        """Enable per-Chrome LD_PRELOAD memory spoofing.

        Prefer Android's ``wrap.<package>`` property over replacing
        ``app_process64`` globally. The older global wrapper affects zygote and
        system processes and can destabilize ADB/Android after a live restart.
        """
        await self._restore_global_memory_preload_if_needed()
        if await self.is_memory_preload_active(chrome_package):
            logger.debug("Memory preload already active")
            return

        # Ensure .so is on device
        out = await self.adb.shell(
            f"test -f {_FAKEMEM_SO} && echo OK",
            timeout=5, allow_failure=True,
        )
        if "OK" not in out:
            so_local = self._compile_fakemem()
            await self.adb.push(so_local, _FAKEMEM_SO)
            await self.adb.shell_root(f"chmod 755 {_FAKEMEM_SO}")

        wrapper = (
            "#!/system/bin/sh\n"
            f"export LD_PRELOAD={_FAKEMEM_SO}\n"
            "exec \"$@\"\n"
        )
        b64 = base64.b64encode(wrapper.encode()).decode()
        await self.adb.shell_root(f"echo '{b64}' | base64 -d > {_FAKEMEM_WRAP}")
        await self.adb.shell_root(f"chmod 755 {_FAKEMEM_WRAP}")
        await self.adb.shell_root(f"setprop wrap.{chrome_package} {_FAKEMEM_WRAP}")
        value = await self.adb.shell(
            f"getprop wrap.{chrome_package}", timeout=5, allow_failure=True,
        )
        if _FAKEMEM_WRAP not in value:
            raise RootError(f"Failed to set wrap.{chrome_package} for memory preload")
        logger.info("Memory preload active for %s via Android wrap property", chrome_package)

    async def remove_memory_preload(self, chrome_package: str = "com.android.chrome") -> None:
        """Restore original app_process64 (best-effort cleanup)."""
        await self.adb.shell_root(f"setprop wrap.{chrome_package} ''")
        await self._restore_global_memory_preload_if_needed()

    async def _restore_global_memory_preload_if_needed(self) -> None:
        """Undo older app_process64 wrapper installs if present."""
        out = await self.adb.shell(
            f"test -f {_APP_PROCESS_REAL} && echo OK",
            timeout=5,
            allow_failure=True,
        )
        if "OK" not in out:
            return

        await self.adb.shell(
            "su 0 sh -c 'mount -o remount,rw /system 2>/dev/null || true; "
            "mount -o remount,rw / 2>/dev/null || true'",
            timeout=10,
            allow_failure=True,
        )
        await self.adb.shell_root(f"cp {_APP_PROCESS_REAL} /system/bin/app_process64")
        await self.adb.shell_root(f"rm -f {_APP_PROCESS_REAL}")
        logger.info("Removed legacy global app_process64 memory preload wrapper")

    async def is_memory_preload_active(self, chrome_package: str = "com.android.chrome") -> bool:
        """Check if Chrome's wrap property points at libfakemem."""
        value = await self.adb.shell(
            f"getprop wrap.{chrome_package}", timeout=5, allow_failure=True,
        )
        if _FAKEMEM_SO in value:
            return True
        if _FAKEMEM_WRAP in value:
            return True
        out = await self.adb.shell(
            f"test -f {_APP_PROCESS_REAL} && echo OK",
            timeout=5, allow_failure=True,
        )
        return "OK" in out

    async def _wait_for_system(self, timeout: float = 30) -> None:
        """Wait for SystemServer to be ready after Zygote restart."""
        elapsed = 0.0
        while elapsed < timeout:
            out = await self.adb.shell(
                "pm list packages 2>/dev/null | head -1",
                timeout=5, allow_failure=True,
            )
            if "package:" in out:
                return
            await sleep(2.0)
            elapsed += 2.0
        logger.warning("System not fully ready after %.0fs", timeout)

    # -- Audio sample rate fix --

    async def apply_audio_48khz(self) -> None:
        """Patch audio HAL config to use 48000Hz (real phone default).

        Redroid's default primary audio output uses 44100Hz which is
        detectable by AudioContext.sampleRate. Real phones use 48000Hz.
        Idempotent: checks current config before patching.
        """
        cfg = "/vendor/etc/primary_audio_policy_configuration.xml"
        check = await self.adb.shell(
            f"cat {cfg} 2>/dev/null",
            timeout=5, allow_failure=True,
        )
        if not check or cfg.split("/")[-1] not in check and "samplingRates" not in check:
            logger.debug("Audio config not found at %s", cfg)
            return
        if 'samplingRates="48000"' in check:
            logger.debug("Audio already at 48000Hz")
            return
        if 'samplingRates="44100"' not in check:
            logger.debug("Audio config has unexpected sample rate, skipping")
            return

        await self.adb.shell(
            "su 0 mount -o remount,rw /vendor 2>/dev/null", allow_failure=True,
        )
        await self.adb.shell_root(
            f'sed -i \'s/samplingRates="44100"/samplingRates="48000"/g\' {cfg}',
        )
        await self.adb.shell(
            "su 0 mount -o remount,ro /vendor 2>/dev/null", allow_failure=True,
        )
        # Restart audioserver to pick up new config
        await self.adb.shell_root("setprop ctl.restart audioserver")
        await sleep(2.0)
        logger.info("Audio sample rate: 44100 -> 48000 Hz")

    # -- Font fingerprint expansion --

    @staticmethod
    def _download_fonts() -> list[tuple[str, str]]:
        """Download extra font .ttf files to host cache. Returns [(local_path, filename)]."""
        cache_dir = os.path.join(tempfile.gettempdir(), "damru_fonts")
        os.makedirs(cache_dir, exist_ok=True)

        results = []
        for _family, filename, urls, _aliases in _EXTRA_FONTS:
            local = os.path.join(cache_dir, filename)
            if os.path.isfile(local) and os.path.getsize(local) > 10_000:
                results.append((local, filename))
                continue

            downloaded = False
            for url in urls:
                try:
                    urllib.request.urlretrieve(url, local)
                    if os.path.getsize(local) > 10_000:
                        results.append((local, filename))
                        downloaded = True
                        break
                except Exception:
                    continue
            if not downloaded:
                logger.debug("Failed to download font: %s", filename)

        return results

    async def install_extra_fonts(self) -> None:
        """One-time: Download and push extra font .ttf files to /system/fonts/.

        Idempotent via marker file — only pushes files once per container.
        Does NOT modify fonts.xml (that's done per-session by randomize_fonts).
        """
        out = await self.adb.shell(
            f"test -f {_FONT_MARKER} && echo OK",
            timeout=5, allow_failure=True,
        )
        if "OK" in out:
            logger.debug("Extra font files already installed")
            return

        font_files = await asyncio.to_thread(self._download_fonts)
        if not font_files:
            logger.warning("No extra fonts available for install")
            return

        # Backup original fonts.xml (needed by randomize_fonts)
        backup_exists = await self.adb.shell(
            f"test -f {_FONTS_XML_ORIG} && echo EXISTS",
            timeout=5, allow_failure=True,
        )
        await self.adb.shell(
            "su 0 mount -o remount,rw /system 2>/dev/null", allow_failure=True,
        )
        if "EXISTS" not in backup_exists:
            await self.adb.shell_root(f"cp {_FONTS_XML} {_FONTS_XML_ORIG}")

        # Push font files to /system/fonts/ via tmp
        for local_path, filename in font_files:
            tmp_path = f"/data/local/tmp/{filename}"
            await self.adb.push(local_path, tmp_path)
            await self.adb.shell_root(f"cp {tmp_path} /system/fonts/{filename}")
            await self.adb.shell_root(f"chmod 644 /system/fonts/{filename}")
            await self.adb.shell_root(f"rm -f {tmp_path}")

        await self.adb.shell(
            "su 0 mount -o remount,ro /system 2>/dev/null", allow_failure=True,
        )
        await self.adb.shell_root(f"touch {_FONT_MARKER}")
        logger.info("Installed %d extra font files", len(font_files))

    async def randomize_fonts(self) -> int:
        """Per-session: Pick a random subset of extra fonts and rebuild fonts.xml.

        Each launch gets a different combination of fonts + aliases so the
        font fingerprint is unique per session. Always includes the 7 AOSP
        base fonts; the extra 9 Google Fonts are randomly sampled (6-9 of them).

        Returns the number of extra font families enabled this session.
        """
        # Ensure backup exists (install_extra_fonts creates it)
        backup_exists = await self.adb.shell(
            f"test -f {_FONTS_XML_ORIG} && echo EXISTS",
            timeout=5, allow_failure=True,
        )
        if "EXISTS" not in backup_exists:
            logger.debug("No fonts.xml backup — skipping font randomization")
            return 0

        original = await self.adb.shell(
            f"cat {_FONTS_XML_ORIG}",
            timeout=10, allow_failure=True,
        )
        if not original or "</familyset>" not in original:
            logger.debug("Cannot parse fonts.xml backup")
            return 0

        # Pick random subset: 6-9 out of 9 fonts (always different combo)
        n_fonts = random.randint(6, len(_EXTRA_FONTS))
        chosen = random.sample(_EXTRA_FONTS, n_fonts)
        # Shuffle alias order too (fingerprint scanners may check order)
        random.shuffle(chosen)

        # Check which font files actually exist on device
        xml_additions = "\n"
        enabled_count = 0
        for family_name, filename, _urls, aliases in chosen:
            xml_additions += (
                f'    <family name="{family_name}">\n'
                f'        <font weight="400" style="normal">{filename}</font>\n'
                f'    </family>\n'
            )
            # Shuffle aliases too
            shuffled_aliases = list(aliases)
            random.shuffle(shuffled_aliases)
            for alias in shuffled_aliases:
                xml_additions += (
                    f'    <alias name="{alias}" to="{family_name}" />\n'
                )
            enabled_count += 1

        # CarroisGothicSC (already on AOSP) — randomly include or not
        if random.random() > 0.3:
            xml_additions += (
                '    <family name="carrois-gothic-sc">\n'
                '        <font weight="400" style="normal">'
                'CarroisGothicSC-Regular.ttf</font>\n'
                '    </family>\n'
                '    <alias name="Lucida Sans" to="carrois-gothic-sc" />\n'
            )
            enabled_count += 1

        modified = original.replace("</familyset>", f"{xml_additions}</familyset>")

        fd, tmp_local = tempfile.mkstemp(prefix="damru_fonts_", suffix=".xml")
        os.close(fd)
        tmp_remote = f"/data/local/tmp/damru_fonts_{os.path.basename(tmp_local)}"
        try:
            with open(tmp_local, "w", encoding="utf-8") as f:
                f.write(modified)
            await self.adb.shell(
                "su 0 mount -o remount,rw /system 2>/dev/null", allow_failure=True,
            )
            await self.adb.push(tmp_local, tmp_remote)
            await self.adb.shell_root(f"cp {tmp_remote} {_FONTS_XML}")
            await self.adb.shell_root(f"chmod 644 {_FONTS_XML}")
        finally:
            await self.adb.shell_root(f"rm -f {tmp_remote}")
            try:
                os.remove(tmp_local)
            except OSError:
                pass
        await self.adb.shell(
            "su 0 mount -o remount,ro /system 2>/dev/null", allow_failure=True,
        )

        logger.info(
            "Font fingerprint randomized: %d/%d extra families enabled",
            enabled_count, len(_EXTRA_FONTS),
        )
        return enabled_count

    # -- eSpeak-NG TTS installation --

    @staticmethod
    def _find_espeak_apk() -> Optional[str]:
        """Find eSpeak-NG APK in the local Damru APK bundle."""
        bundled = find_any_bundle_apk(["espeak.apk", "espeak-ng.apk"])
        if bundled is not None:
            return str(bundled)
        return None

    async def ensure_espeak_tts(self) -> bool:
        """Install eSpeak-NG TTS if not present. Returns True if available."""
        espeak_pkg = "com.reecedunn.espeak"

        installed = await self.adb.shell(
            "pm list packages", timeout=8, allow_failure=True,
        )
        if espeak_pkg in installed:
            return True

        apk = await asyncio.to_thread(self._find_espeak_apk)
        if not apk:
            logger.debug("eSpeak-NG APK not available in Damru APK bundle")
            return False

        out = await self.adb._run(
            ["install", "-r", apk],
            timeout=120, allow_failure=True,
        )
        if "success" in out.lower():
            logger.info("eSpeak-NG TTS installed")
            return True

        logger.debug("eSpeak-NG install output: %s", out)
        return False
