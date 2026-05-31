"""Chrome management on Android for damru.

Handles Chrome launch/stop, command-line flag writing, FRE dismissal,
devtools socket detection, and root-level Chrome preferences patching.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from typing import List, Optional

from .adb import ADB
from .utils import logger, sleep

CHROME_PACKAGES = [
    "com.android.chrome",
    "com.chrome.beta",
    "com.chrome.dev",
    "com.chrome.canary",
    "org.chromium.chrome",
]


class ChromeError(Exception):
    """Chrome operation failed."""


class ChromeManager:
    """Manage Chrome on an Android device via ADB."""

    def __init__(self, adb: ADB, package: Optional[str] = None):
        self.adb = adb
        self.package = package or "com.android.chrome"

    async def detect_package(self, retries: int = 5, delay: float = 3.0) -> str:
        """Find which Chrome variant is installed.

        Retries because package manager may not be fully initialised immediately
        after a fresh Android boot (pm list packages returns empty too early).
        """
        for attempt in range(max(1, retries)):
            out = await self.adb.shell("pm list packages", allow_failure=True)
            installed = set(line.replace("package:", "").strip() for line in out.splitlines())
            for pkg in CHROME_PACKAGES:
                if pkg in installed:
                    self.package = pkg
                    return pkg
            if attempt < retries - 1 and not installed:
                # Package manager not ready yet — wait and retry
                logger.debug("Package manager not ready (attempt %d/%d), waiting %.0fs…", attempt + 1, retries, delay)
                await sleep(delay)
        raise ChromeError("No Chrome browser found on device. Install Chrome first.")

    async def get_version(self) -> str:
        """Get installed Chrome version string."""
        out = await self.adb.shell(
            f"dumpsys package {self.package} | grep versionName",
            allow_failure=True,
        )
        m = re.search(r"versionName=(\S+)", out)
        return m.group(1) if m else "unknown"

    async def force_stop(self) -> None:
        """Force-stop Chrome process."""
        await self.adb.shell(f"am force-stop {self.package}", allow_failure=True)
        await sleep(0.3)

    async def write_command_line(self, flags: List[str]) -> None:
        """Write Chrome command-line flags to /data/local/tmp/chrome-command-line.

        Chrome reads this file on startup. Format: first token is ignored (argv[0]),
        rest are flags. Must force-stop and relaunch for flags to take effect.

        CRITICAL: All --disable-features values are merged into ONE flag,
        because Chrome only uses the LAST --disable-features flag.
        """
        # Separate disable-features from other flags
        disable_features: List[str] = []
        other_flags: List[str] = []

        for flag in flags:
            flag = flag.strip()
            if not flag:
                continue
            if flag.startswith("--disable-features="):
                features = flag.split("=", 1)[1]
                disable_features.extend(f.strip() for f in features.split(",") if f.strip())
            else:
                other_flags.append(flag)

        # Build final flag list with merged disable-features
        final_flags = other_flags[:]
        if disable_features:
            final_flags.append(f"--disable-features={','.join(disable_features)}")

        # Write to command-line file (first token ignored by Chrome)
        cmd_line = "_ " + " ".join(final_flags)

        # Write via printf to avoid shell quoting issues with echo
        # Escape special chars for shell
        safe_line = cmd_line.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
        await self.adb.shell_root(
            f'printf "%s" "{safe_line}" > /data/local/tmp/chrome-command-line'
        )
        await self.adb.shell_root("chmod 644 /data/local/tmp/chrome-command-line")
        logger.debug("Chrome command-line: %s", cmd_line[:200])

    async def launch(self, url: str = "about:blank", startup_delay: float = 4.0) -> None:
        """Launch Chrome via am start.

        After pm clear, Chrome needs extra startup time to initialize
        fresh profile data and render the FRE screen (~4s).
        On warm reuse (no pm clear), Chrome starts faster (~2s).
        """
        activity = f"{self.package}/com.google.android.apps.chrome.Main"
        await self.adb.shell(
            f"am start -n {activity} -a android.intent.action.VIEW -d {url}",
            allow_failure=True,
        )
        await sleep(startup_delay)

    async def dismiss_fre(self, max_attempts: int = 8) -> bool:
        """Dismiss Chrome First Run Experience using uiautomator.

        Chrome 145 FRE flow on redroid/Android 14:
          Screen 1: "Welcome to Chrome" → signin_fre_continue_button ("Continue")
          Screen 2: "Chrome notifications" → negative_button ("No thanks")
          Then devtools socket appears.

        After pm clear, Chrome may take several seconds to render FRE,
        so we retry with delays if no dialog is found initially.
        """
        # Button IDs to look for, in priority order (dismiss > negative > continue)
        _FRE_BUTTONS = [
            "signin_fre_dismiss_button",
            "negative_button",
            "no_button",
            "signin_fre_continue_button",
            "positive_button",
        ]

        for attempt in range(max_attempts):
            await self.adb.shell(
                "uiautomator dump /data/local/tmp/damru_ui.xml",
                timeout=10, allow_failure=True,
            )
            xml = await self.adb.shell(
                "cat /data/local/tmp/damru_ui.xml",
                timeout=5, allow_failure=True,
            )
            if not xml:
                await sleep(2.0)
                continue

            # Check if we're past FRE (main browser UI visible)
            if "compositor_view_holder" in xml and "fre_pager" not in xml:
                logger.info("FRE complete — main browser UI detected (attempt %d)", attempt + 1)
                return True

            # Try each FRE button in priority order
            tapped = False
            for btn_id in _FRE_BUTTONS:
                if btn_id not in xml:
                    continue
                # Match button with bounds — handle both attribute orders
                m = re.search(
                    rf'{btn_id}[^/]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                    xml,
                )
                if not m:
                    m = re.search(
                        rf'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^/]*{btn_id}',
                        xml,
                    )
                if m:
                    cx = (int(m.group(1)) + int(m.group(3))) // 2
                    cy = (int(m.group(2)) + int(m.group(4))) // 2
                    await self.adb.shell(f"input tap {cx} {cy}", allow_failure=True)
                    logger.info("FRE: tapped %s at (%d,%d) (attempt %d)",
                                btn_id, cx, cy, attempt + 1)
                    tapped = True
                    await sleep(2.0)
                    break

            if tapped:
                continue

            # Look for "Accept & continue" or similar text buttons
            if "terms" in xml.lower() or "accept" in xml.lower():
                m = re.search(
                    r'text="Accept[^"]*"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                    xml,
                )
                if m:
                    cx = (int(m.group(1)) + int(m.group(3))) // 2
                    cy = (int(m.group(2)) + int(m.group(4))) // 2
                    await self.adb.shell(f"input tap {cx} {cy}", allow_failure=True)
                    logger.info("FRE: tapped Accept button (attempt %d)", attempt + 1)
                    await sleep(1.5)
                    continue

            # Look for "Use without an account" sign-in promo button
            # This screen appears before devtools socket is available.
            # It is NOT dismissed by --disable-fre; needs explicit tap.
            if "without an account" in xml.lower() or "Make Chrome your own" in xml:
                for text_pat in ["Use without an account", "without an account"]:
                    m = re.search(
                        rf'text="{re.escape(text_pat)}"[^/]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                        xml,
                    )
                    if not m:
                        m = re.search(
                            rf'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^/]*text="{re.escape(text_pat)}"',
                            xml,
                        )
                    if m:
                        cx = (int(m.group(1)) + int(m.group(3))) // 2
                        cy = (int(m.group(2)) + int(m.group(4))) // 2
                        await self.adb.shell(f"input tap {cx} {cy}", allow_failure=True)
                        logger.info("FRE: tapped 'Use without an account' at (%d,%d) (attempt %d)",
                                    cx, cy, attempt + 1)
                        await sleep(2.0)
                        tapped = True
                        break
                if tapped:
                    continue

            # FRE pager visible but buttons not rendered yet (spinner loading)
            if "fre_pager" in xml or "fre_native_and_policy_load_progress_spinner" in xml:
                logger.debug("FRE loading (spinner/no buttons yet), waiting... (attempt %d)", attempt + 1)
                await sleep(3.0)
                continue

            # No FRE dialogs detected — Chrome may still be loading
            if attempt < 4:
                logger.debug("No FRE dialog found (attempt %d), retrying...", attempt + 1)
                await sleep(2.0)
                continue

            # After enough retries, assume FRE is done
            return True

        return True

    async def wait_for_devtools_socket(self, timeout: float = 15.0) -> bool:
        """Poll for chrome_devtools_remote socket to become available."""
        import time
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            out = await self.adb.shell(
                "cat /proc/net/unix 2>/dev/null | grep chrome_devtools_remote",
                allow_failure=True,
            )
            if "chrome_devtools_remote" in out:
                return True
            await sleep(1.0)
        logger.warning("Chrome devtools socket not found after %.1fs", timeout)
        return False

    async def clear_all_data(self) -> None:
        """Wipe ALL Chrome data for a truly fresh instance.

        Uses `pm clear` which removes everything: cookies, sessions,
        localStorage, IndexedDB, cache, permissions, preferences.
        Chrome will behave as if freshly installed.

        Must be called AFTER force_stop() and BEFORE patch_preferences()/launch().
        """
        await self.adb.shell(f"pm clear {self.package}", allow_failure=True)
        await sleep(0.5)
        logger.info("Chrome data wiped (pm clear %s)", self.package)

    async def targeted_cleanup(self) -> None:
        """Clean session data but preserve Preferences, TTS state, and FRE flag.

        Unlike clear_all_data() (pm clear), this keeps:
          - Chrome Preferences (locale, DoH, WebRTC policy)
          - TTS service binding state (voices stay loaded)
          - FRE completion state (no re-dismiss needed)

        Deletes cookies, sessions, localStorage, IndexedDB, cache, etc.
        """
        pkg = self.package
        await self.adb.shell_root(
            f"cd /data/data/{pkg}/app_chrome/Default 2>/dev/null && "
            "rm -rf Cookies* 'Login Data'* History* Bookmarks* "
            "'Web Data'* 'Visited Links' 'Top Sites'* "
            "Sessions 'Current Session' 'Current Tabs' "
            "'Last Session' 'Last Tabs' "
            "IndexedDB 'Local Storage' 'Service Worker' "
            "'File System' blob_storage databases "
            "shared_proto_db Cache 'Code Cache' GPUCache "
            "optimization_guide_hint_cache_store"
            f"; rm -rf /data/data/{pkg}/cache 2>/dev/null; true"
        )
        logger.info("Chrome session data cleaned (Preferences preserved)")

    async def has_preferences(self) -> bool:
        """Check if Chrome Preferences file exists (warm start indicator).

        After pm clear (cold start), Preferences doesn't exist.
        After targeted_cleanup (warm start), it persists.
        Uses su 0 because /data/data/<pkg>/ is not accessible to shell user.
        """
        prefs_path = f"/data/data/{self.package}/app_chrome/Default/Preferences"
        out = await self.adb.shell(
            f"su 0 test -f {prefs_path} && echo OK",
            timeout=5, allow_failure=True,
        )
        return "OK" in out

    async def clear_command_line(self) -> None:
        """Remove the Chrome command-line flags file."""
        await self.adb.shell_root("rm -f /data/local/tmp/chrome-command-line")

    async def patch_preferences(self, locale: str, accept_lang: str) -> None:
        """Patch Chrome's Preferences file for stealth operation.

        ROOT-LEVEL approach - modifies Chrome's stored preferences on disk
        before launch. No JS injection needed.

        Patches applied:
          - Language/locale for Accept-Language header
          - WebRTC IP handling policy (suppress private IPs)
          - DNS prefetch disabled (prevents DNS leak outside proxy)
          - Network prediction disabled (prevents speculative connections)
          - Safe browsing disabled (prevents Google DNS pings)
          - Alternate error pages disabled (prevents DNS suggestions)

        Args:
            locale: BCP-47 locale (e.g. "en-PH")
            accept_lang: Accept-Language value (e.g. "en-PH,en-US;q=0.9,en;q=0.8")
        """
        prefs_path = f"/data/data/{self.package}/app_chrome/Default/Preferences"

        # Read current preferences (or create minimal if not yet existing)
        # Must use root — /data/data/<pkg>/ is mode 700 owned by Chrome's UID,
        # not accessible to the 'shell' user.
        raw = await self.adb.shell(
            f"su 0 cat {prefs_path}", timeout=10, allow_failure=True,
        )
        if not raw or raw.startswith("cat:") or "No such file" in raw or "Permission denied" in raw:
            # Preferences file doesn't exist yet (fresh install / cleared data).
            # Create the directory structure and a minimal prefs file.
            logger.info("Chrome Preferences not found - creating fresh")
            prefs_dir = prefs_path.rsplit("/", 1)[0]
            await self.adb.shell_root(f"mkdir -p {prefs_dir}")
            prefs = {}
        else:
            try:
                prefs = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Chrome Preferences is not valid JSON, starting fresh")
                prefs = {}

        # Build selected_languages from accept_lang
        # e.g. "en-PH,en-US;q=0.9,en;q=0.8" → "en-PH,en-US,en"
        langs = [part.split(";")[0].strip() for part in accept_lang.split(",")]
        selected = ",".join(langs)

        # --- Language ---
        if "intl" not in prefs:
            prefs["intl"] = {}
        prefs["intl"]["selected_languages"] = selected

        # --- WebRTC IP handling policy ---
        # "default_public_interface_only" hides private/local IPs (10.x, 172.x)
        # but allows STUN to discover the public exit IP (proxy IP).
        # DO NOT use "disable_non_proxied_udp" — it shows WebRTC as "disabled"
        # which is a fingerprint tell (no real device has WebRTC disabled).
        if "webrtc" not in prefs:
            prefs["webrtc"] = {}
        prefs["webrtc"]["ip_handling_policy"] = "default_public_interface_only"

        # --- DNS leak prevention ---
        # Disable DNS prefetching - Chrome prefetches DNS for links on page,
        # which bypasses the HTTP proxy and leaks DNS to local resolver.
        if "dns_prefetching" not in prefs:
            prefs["dns_prefetching"] = {}
        prefs["dns_prefetching"]["enabled"] = False

        # Disable network prediction (speculative pre-connections)
        # 0=default, 1=wifi-only, 2=never
        if "net" not in prefs:
            prefs["net"] = {}
        prefs["net"]["network_prediction_options"] = 2

        # Disable Safe Browsing (prevents DNS queries to Google's SB servers)
        if "safebrowsing" not in prefs:
            prefs["safebrowsing"] = {}
        prefs["safebrowsing"]["enabled"] = False

        # Disable alternate error pages (DNS suggestions from Google)
        if "alternate_error_pages" not in prefs:
            prefs["alternate_error_pages"] = {}
        prefs["alternate_error_pages"]["enabled"] = False

        # Disable background sync and push messaging (potential DNS leaks)
        if "background_sync" not in prefs:
            prefs["background_sync"] = {}
        prefs["background_sync"]["enabled"] = False

        # --- Sign-in promo suppression ("Make Chrome your own") ---
        # Without this, Chrome shows a sign-in promo screen on first launch
        # that blocks the devtools socket from appearing (no chrome_devtools_remote).
        # Must be set BEFORE Chrome launches.
        prefs["signin"] = {
            "allowed": False,
            "allowed_on_next_startup": False,
        }
        if "sync" not in prefs:
            prefs["sync"] = {}
        prefs["sync"]["suppress_start"] = True
        prefs["sync"]["requested"] = False

        # --- DNS-over-HTTPS (DoH) DISABLED for todetect.net ---
        # todetect.net requires DNS to match the proxy's ISP DNS servers.
        # Cloudflare DoH (1.1.1.1) causes -8% score for "DNS leak".
        # With DoH disabled, DNS goes through the proxy's DNS resolvers,
        # matching the ISP and getting 100% score on todetect.net.
        # Note: This may cause BrowserScan to detect DNS leak, but todetect
        # is stricter and more important for fingerprint quality.
        if "dns_over_https" not in prefs:
            prefs["dns_over_https"] = {}
        prefs["dns_over_https"]["mode"] = "off"  # Disabled - use proxy DNS

        # Write back
        patched_json = json.dumps(prefs, separators=(",", ":"))

        # Write to temp file then move. Using adb push avoids very long shell
        # command payloads that can fail on some MuMu/ADB transports.
        tmp = "/data/local/tmp/damru_chrome_prefs.json"
        local_tmp = None
        fd, local_tmp = tempfile.mkstemp(prefix="damru_prefs_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(patched_json)
            await self.adb.push(local_tmp, tmp)
        finally:
            if local_tmp and os.path.exists(local_tmp):
                try:
                    os.remove(local_tmp)
                except OSError:
                    pass

        # Get Chrome's UID for correct ownership (needs root for /data/data/<pkg>/)
        owner = await self.adb.shell(
            f"su 0 stat -c '%U:%G' {prefs_path}", timeout=5, allow_failure=True
        )
        if not owner or "No such file" in owner or "stat:" in owner:
            # Try to get ownership from Chrome's data directory instead
            chrome_dir = f"/data/data/{self.package}"
            owner = await self.adb.shell(
                f"su 0 stat -c '%U:%G' {chrome_dir}", timeout=5, allow_failure=True
            )
            if not owner or "stat:" in owner:
                owner = ""

        # Copy with correct permissions
        await self.adb.shell_root(f"cp {tmp} {prefs_path}")
        if owner and ":" in owner:
            await self.adb.shell_root(f"chown {owner.strip()} {prefs_path}")
        await self.adb.shell_root(f"chmod 600 {prefs_path}")
        await self.adb.shell_root(f"rm -f {tmp}")

        logger.info("Chrome language patched: %s → %s", locale, selected)
