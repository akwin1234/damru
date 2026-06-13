#  Damru Python API Reference

Welcome to the definitive API reference for the **Damru** library. This guide covers everything from basic automation to advanced multi-container orchestration and stealth tuning.

Damru is designed to be a transparent drop-in replacement for standard Playwright setups, adding deep-level Android OS and Chromium C++ spoofing.

---

## Table of Contents
- [Core Classes](#-core-classes)
    - [AsyncDamru (Recommended)](#asyncdamru-recommended)
    - [Damru (Synchronous)](#damru-synchronous)
- [Exception Handling](#-exception-handling)
- [Pool Management](#-pool-management)
    - [DamruPool (Async)](#damrupool)
    - [DamruPoolSync (Sync)](#damrupoolsync)
- [Device Management](#-device-management)
- [Advanced Configuration](#-advanced-configuration)
- [Advanced Modules](#-advanced-modules)
    - [Edge-Layer Bypass (CDN TLS)](#edge-layer-bypass-cdn)
- [Cookbook: Common Patterns](#-cookbook-common-patterns)

---

## Core Classes

### `AsyncDamru` (Recommended)
The primary asynchronous context manager. It orchestrates the 8 layers of stealth and returns a Playwright `BrowserContext`.

#### Usage
```python
from damru import AsyncDamru

async with AsyncDamru(device="pixel_8_pro", proxy="socks5://...") as context:
    page = await context.new_page()
    await page.goto("https://creepjs.com")
```

Damru expects Redroid to run inside Ubuntu Linux or Ubuntu WSL2. On Windows, Docker/Redroid is managed inside WSL2; native Windows Docker is not a supported Redroid backend. The tested production paths are native Ubuntu VPS/Linux and Ubuntu WSL2 with Damru's bundled WSL kernel. Debian 13 VPS kernels tested so far have `CONFIG_ANDROID_BINDERFS` disabled, so they are not supported for Redroid multi-container pools.

#### `__init__` Parameters
| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `device` | `str` | `"random"` | Target device string (e.g., `"samsung_galaxy_s24_ultra"`). |
| `profile_tier` | `str` | config `PROFILE_TIER` / `"premium"` | Random profile pool when `device` is unset or `"random"`: `premium`, `premium_verified`, `premium_new`, `medium`, `experimental`, `extended`, or `all`. Explicit named devices ignore this filter. |
| `serial` | `str` | `None` | ADB identifier. If `None`, Damru auto-detects virtual devices only: TCP Redroid endpoints first, then `emulator-*`. Physical-looking USB serials are refused by default. |
| `proxy` | `str` | `None` | Browser proxy URL used for GeoIP and Python-side proxy checks. SOCKS5 and HTTP URLs are accepted. |
| `http_proxy` | `str` | `None` | Android system HTTP proxy as `host:port` or `http://user:pass@host:port`. Use this when Android Chrome must route through an HTTP CONNECT proxy or local bridge. |
| `timezone` | `str` | `None` | Force a specific IANA timezone. Leave unset so Damru resolves it from the active proxy exit. |
| `locale` | `str` | `None` | Force a specific BCP-47 locale. Leave unset so Damru chooses a realistic locale for the proxy country. |
| `debug` | `bool` | `False` | Enables verbose console logging for debugging OS patches. |

Proxy timezone safety:

- If `http_proxy` is provided, Damru resolves GeoIP through that same Android system proxy path because it is the path Chrome actually uses.
- If only `proxy` is provided, Damru derives the Android proxy when possible.
- Rotating residential proxies are resolved at session start and rechecked through Chrome after CDP connects, so browser timezone and locale follow the actual exit IP instead of stale cached data.
- Explicit `timezone` or `locale` values always override auto detection. Only set them when you know they match your proxy exit.
- Auto locale selection covers standard ISO country codes plus CLDR exceptional territory codes. For countries with multiple common phone locales, Damru may choose a realistic variant, for example `en-PH` or `fil-PH` for the Philippines, and `en-IN` or `hi-IN` for India.

#### Methods & Properties
*   **`await new_page()`**: Creates a new stealth-hardened `Page`.
*   **`browser`**: Access the underlying Playwright `Browser` object.
*   **`pages`**: List of currently open `Page` objects.
*   **`profile`**: Returns the active `DamruProfile` (Device specs, UA, etc.).

---

### `Damru` (Synchronous)
The blocking version of `AsyncDamru`. Perfect for traditional scripts or multi-threaded environments.

#### Usage
```python
from damru import Damru

with Damru(device="pixel_7") as context:
    page = context.new_page()
    page.goto("https://bot.sannysoft.com")
```
*Note: Methods and parameters are identical to `AsyncDamru` but without `await`.*

---

## Exception Handling

### `DamruError`
All Damru-specific failures (ADB connection errors, rooting issues, binary patching failures) raise a `DamruError`.

```python
from damru import Damru, DamruError

try:
    with Damru() as browser:
        ...
except DamruError as e:
    print(f"Damru failed to initialize: {e}")
```

---

## Pool Management

### `DamruPool` (Async)
Designed for massive parallelization across dozens of Docker containers. It automatically manages container lifecycles and port forwarding.

#### Usage
```python
from damru import DamruPool

# mode="auto" automatically starts and manages Redroid Docker containers
async with DamruPool(mode="auto", max_devices=10) as pool:
    # pool.session() provides an AsyncDamru context from an available container
    async with pool.session() as browser:
        page = await browser.new_page()
        ...
```

#### `__init__` Parameters
| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `max_devices` | `int` | config `NUM_DEVICES` | Number of concurrent instances/containers to maintain. Use `0` only in manual mode to use every detected ADB device. |
| `mode` | `str` | config `MODE` | Deployment mode: `"auto"` manages Redroid via Docker, `"manual"` uses existing ADB devices, and `"mumu"` is experimental. Redroid auto mode is the supported production path. |
| `proxy` | `str` | config `PROXY` | One proxy shared by all sessions. |
| `proxies` | `list[str]` | config `PROXIES` | Per-worker proxy list. Pool rotates through these by slot index. |
| `http_proxy` / `http_proxies` | `str` / `list[str]` | config values | Android system HTTP proxy override when it differs from the browser proxy. GeoIP is resolved through this path when present. |
| `device` | `str` | config `DEVICE` | Fixed device profile, or `None`/`"random"` for per-session random profiles. |
| `profile_tier` | `str` | config `PROFILE_TIER` / `"premium"` | Random pool for sessions without a fixed `device`; medium/experimental/all are opt-in. |
| `timezone` / `locale` | `str` | config values | Force timezone and locale instead of deriving them from proxy/profile data. |
| `chrome_apk` | `str` | config `CHROME_APK` | Chrome APK file or split-APK directory for raw/unbaked auto mode. Leave unset to auto-search the validated APK bundle and allow Chrome rotation during random profile actions. |
| `wsl_distro` | `str` | config `WSL_DISTRO` | Windows only: WSL distro that owns Docker/Redroid. |

### `DamruPoolSync` (Sync)
The synchronous counterpart, ideal for distributed task workers and multi-threading frameworks like `concurrent.futures`.

#### Usage
```python
from damru import DamruPoolSync

# proxies enables per-container proxy rotation
with DamruPoolSync(mode="auto", max_devices=5, proxies=["socks5://..."]) as pool:
    with pool.session() as context:
        page = context.new_page()
        page.goto("https://example.com")
```

---

## Device Management

### `AndroidDevice` Database
Access the physical specifications of the 155 built-in device profiles. The full generated list is in [DEVICE_PROFILES.md](DEVICE_PROFILES.md). Profiles can be selected by exact marketing name, model, or slug. Default random selection uses the premium pool only: 51 original verified profiles plus 49 high-confidence new profiles. Medium and experimental profiles remain available by explicit name or opt-in tier.

```python
from damru import list_device_names, get_device, get_devices_by_tier, get_random_device

# Get hardware specs for a specific phone
pixel = get_device("pixel_8_pro")
print(f"Cores: {pixel.hardware_concurrency}, RAM: {pixel.device_memory}GB")

# Select a random Android 13 profile
random_phone = get_random_device(android_version="13")

# Opt into wider lower-confidence pools only when you want extra diversity
all_profiles = get_devices_by_tier("all")
medium_phone = get_random_device(profile_tier="medium")
```

Random tier names are `premium` (default), `premium_verified`, `premium_new`, `medium`, `experimental`, `extended`, and `all`. Explicit `device="Nokia C32"` or `get_device("Nokia C32")` is never blocked by the default premium filter.

To force a specific profile onto an already-running rooted worker without opening a full Damru Playwright session, use the CLI or the async helper:

```bash
python -m damru force-profile --serial 127.0.0.1:5600 --device pixel_8_pro
python -m damru force-profile --serial 127.0.0.1:5600 --device "Xiaomi POCO F5"
python -m damru force-profile --serial 127.0.0.1:5600 --device xiaomi_redmi_9a --no-chrome --clear-proxy
python -m damru force-profile --serial 127.0.0.1:5600 --device xiaomi_redmi_9a --browser-package org.chromium.webview_shell --locale pt-BR --timezone America/Sao_Paulo
```

```python
from damru import force_device_profile

result = await force_device_profile(
    "127.0.0.1:5600",
    "pixel_8_pro",
    timezone="America/New_York",
    locale="en-US",
)
print(result.description)
```

`force-profile` applies Android props, release string, timezone, locale, display size/density, CPU core spoofing, native Vulkan GPU spoofing, memory preload, and Chromium command-line/preferences by default. Locale writes include modern `persist.sys.locale`/`system_locales` plus legacy `persist.sys.language` and `persist.sys.country`, so Android Chrome/WebView-family processes do not keep a stale `en-US` language. Pass `--browser-package org.chromium.webview_shell` for WebView Shell harnesses; Damru will write `/data/local/tmp/webview-command-line` and `app_webview/pref_store` instead of Chrome's command-line/preferences. Pass `--no-chrome` or `configure_chrome=False` only for harnesses that cannot use Chromium preferences, `--no-gpu` / `--no-memory` for native-layer isolation tests, and `--clear-proxy` or `clear_proxy=True` when a debug run should not inherit the worker's current Android HTTP proxy. CDP overrides remain part of the runtime harness because they are active-page specific.

### WebView Shell and Custom WebView Apps

Use WebView Shell when you need to validate Android WebView behavior without Chrome UI:

```bash
python -m damru force-profile --serial 127.0.0.1:5600 --device pixel_8_pro --browser-package org.chromium.webview_shell --proxy socks5://user:pass@host:port
adb -s 127.0.0.1:5600 shell am start -n org.chromium.webview_shell/.WebViewBrowserActivity -a android.intent.action.VIEW -d https://example.com
```

That path writes `/data/local/tmp/webview-command-line`, patches `/data/data/org.chromium.webview_shell/app_webview/pref_store`, enables native memory preload for `org.chromium.webview_shell`, and applies WebRTC blocking when a proxy is active.

For your own Android app that embeds WebView, keep the system WebView provider aligned through the baked image or Chrome/WebView APK bundle, then apply Android-level profile hardening and launch your app separately:

```bash
python -m damru force-profile --serial 127.0.0.1:5600 --device pixel_8_pro --no-chrome --proxy socks5://user:pass@host:port
adb -s 127.0.0.1:5600 shell am start -n com.example.webview/.MainActivity -a android.intent.action.VIEW -d https://example.com
```

Do not pass arbitrary app package names to `--browser-package` unless that app has a Chromium-compatible profile layout. PR #8's package-specific command-line/preference hardening is intentionally wired for `org.chromium.webview_shell`; generic embedded WebView apps still benefit from the aligned system WebView, Android props, timezone/locale, display, CPU/GPU, memory, proxy, and DNS layers.

---

## Advanced Configuration

You can tune Damru's behavior globally via the `damru.config` module before initialization.

On Windows, installing Damru's bundled WSL kernel is intentionally high-friction: use a fresh/dedicated WSL distro when possible, and pass `--confirm-wsl-kernel-risk` for noninteractive setup. Native Linux/Ubuntu does not use the WSL kernel installer.

For first-run setup, prefer the CLI:

```bash
python -m damru setup
python -m damru install-image
python -m damru check-env
python -m damru check preflight
python -m damru fix-wsl
```

`setup` runs dependency setup by default. If no baked image is loaded and no local Chrome/WebView/TTS APK assets exist, Damru downloads and extracts the APK bundle automatically. `install-image` auto-detects and loads `damru-redroid-latest.tar`; use `python -m damru install-image --download` if the tarball is not local. The baked image already contains Chrome, WebView/TTS assets, fonts, and warm preferences, so users do not need separate APK assets unless they intentionally run an unbaked raw Redroid image.

For raw image baking, APK recovery, or Chrome rotation assets, run `python -m damru install-apks --download`. It downloads the [Chrome/WebView/TTS APK bundle](https://damru.dev/assets/chrome-apks.zip), extracts to `/home/damru/chrome-apks` on Linux/WSL, copies Damru's shipped `magisk.apk` there when needed, then sets `CHROME_APK` only when needed. Manual Linux/WSL extraction is also valid: `sudo mkdir -p /home/damru && sudo chown "$USER:$USER" /home/damru && unzip chrome-apks.zip -d /home/damru/chrome-apks`. Keep `webview.apk` or `TrichromeWebView.apk` inside each Chrome version folder that Damru should rotate. Top-level TTS APKs remain beside the Chrome version folders, and Damru also discovers `google_tts.apk`, `espeak.apk`, `rhvoice.apk`, and the copied `magisk.apk` from the same bundle root.

Random profile actions rotate only through Chrome version folders that include a matching WebView APK. This keeps Chrome and Android WebView aligned and skips stale/incomplete folders. Chrome 149 is not included yet because tested APKMirror bundles were missing the required English/x86/x86_64 split layout. If automatic detection fails, set `CHROME_APK` to a Chrome split-APK version directory such as `/home/damru/chrome-apks/148.0.7778.178`. On Windows, extract with File Explorer/7-Zip and use the WSL path such as `/mnt/c/Users/you/Downloads/damru/chrome-apks/148.0.7778.178`.

`check-env` verifies Linux/WSL tools, Docker, binderfs, baked image/Chrome asset discovery, and the Damru Playwright `crPage.js` patch. `check preflight` is the fast read-only variant for CI/fleet rollout: it reports Docker, ADB, binder/binderfs, Redroid image, APK bundle, disk/RAM/CPU, ports, config, WSL kernel status, and physical ADB warnings without installing, repairing, mounting, starting containers, or changing routes/iptables. On WSL, preflight reads kernel config to distinguish unsupported kernels from supported-but-unmounted binderfs; default mode warns for the latter, while `--strict` fails it. ADB auto-detection refuses physical-looking USB serials by default; set `DAMRU_ALLOW_PHYSICAL=1` only for a disposable test device. `fix-wsl` retries safe Docker, binderfs, routing, and netfilter repairs. `fix-internet` repairs WSL/Docker/Android DNS state for one worker or all online workers. On Windows, Docker/Redroid is always managed inside WSL2; native Windows Docker is not used. Redroid auto mode routes ADB through WSL and uses stable per-worker ADB ports (`wsl:127.0.0.1:5600`, `wsl:127.0.0.1:5601`, ...). Native Linux uses Docker bridge/NAT and Damru selects the nft iptables backend to match modern Docker daemons; WSL uses legacy iptables where available because several WSL kernels reject Docker's `addrtype` NAT rule through nft.

Damru normalizes new Android Chrome tabs before returning them from `context.new_page()`. User code can immediately navigate a new page in single sessions or concurrent pools without first fighting Chrome's Android startup/home-tab navigation.

```python
import damru.config

# Custom WSL2 settings
damru.config.WSL_DISTRO = "Ubuntu-22.04"
damru.config.WSL_USERNAME = "my-wsl-user"
damru.config.WSL_PASSWORD = ""  # compatibility only; setup asks for sudo when needed

# Path to local Chrome APKs if using raw/unbaked Redroid instead of the baked image
damru.config.CHROME_APK = "/custom/path/to/chrome.apk"
```

Existing WSL installs are supported. Set `WSL_DISTRO` and `WSL_USERNAME`, or pass them to `python -m damru setup`; Damru uses `wsl -u root` for Windows-launched privileged WSL commands when available, and the guided Linux/WSL flow asks for sudo only when it is actually running as a normal WSL user. On native Linux, `setup`/`install-deps` install `python3-venv`, Docker, ADB, binderfs tools, auto-download raw APK assets only when needed, and add the current user to the Docker group when possible; open a new login shell or reconnect SSH if Docker works with sudo but `check-env` still reports a socket permission failure. For noninteractive native Linux, use `printf '%s\n' 'your-sudo-password' | python -m damru setup -y --sudo-password-stdin`.

For optional visual debugging, use the CLI rather than changing the Python API surface:

```bash
python -m damru devices
python -m damru screenshot --serial wsl:127.0.0.1:5600 --output screen.png
python -m damru record --serial wsl:127.0.0.1:5600 --time-limit 30 --output clip.mp4
python -m damru stealth-open-url --serial wsl:127.0.0.1:5600 --url https://example.com
python -m damru view --serial wsl:127.0.0.1:5600 --no-control
```

These commands use ADB/scrcpy and are intentionally not started by `AsyncDamru`, `Damru`, or pool sessions.

`stealth-open-url` is for CLI/UI manual and debug sessions that still need Damru's full profile setup. The default `--mode reattach` path applies or reuses the profile, disconnects CDP for the actual protected navigation, opens the URL through Android Chrome's native `VIEW` intent, then reconnects CDP so the loaded page can be inspected or automated after load. It reuses existing Chrome/profile state by default for fast repeated opens; pass `--cold-start` when you need to clear Chrome and rebuild a fresh identity. Use `--mode cdp` when CDP-side overrides must stay live during the native open, `--mode native` to leave CDP detached after opening, and `--mode playwright` only when you specifically want raw Playwright `page.goto` behavior for debugging.

For a local browser dashboard, run:

```bash
python -m damru ui
```

The UI is experimental and localhost-only by default. It wraps the same allowlisted CLI/backend actions: setup health, workers, Work Lab URL navigation, quick checks, screenshots, gallery cleanup, internet repair, random profile actions, browser viewer streaming, native `scrcpy` command copy, and logs. Work Lab URL navigation uses `stealth-open-url` in default detached-navigation/CDP-reattach mode. It is meant for setup/debugging/manual inspection, not as the primary automation API.

---

## Advanced Modules

### Edge-Layer Bypass (CDN TLS)
Defeat CDN TLS and other TLS-fingerprinting WAFs by replaying requests through `curl_cffi` browser impersonation.

```python
from damru.bypass import arm_bypass_async

async with AsyncDamru() as browser:
    page = await browser.new_page()
    
    # Persistent interception for this domain
    await arm_bypass_async(page, domain="target-site.com")
    
    # All document navigations now use randomized browser TLS hashes
    await page.goto("https://target-site.com")
```

---

## Cookbook: Common Patterns

### 1. Multi-Page Scraping in One Session
```python
async with AsyncDamru(device="random") as browser:
    # All pages in this context share the same spoofed Device & IP identity
    page1 = await browser.new_page()
    page2 = await browser.new_page()
    
    await asyncio.gather(
        page1.goto("https://google.com"),
        page2.goto("https://bing.com")
    )
```

### 2. Monitoring Low-Level Spoofing Events
```python
# Enable debug mode to see exact root commands and CDP overrides
async with AsyncDamru(debug=True) as browser:
    ...
```

### 3. Handling Proxies with Authentication
```python
# Pass authenticated proxies directly to AsyncDamru
async with AsyncDamru(proxy="socks5://user:pass@host:port") as browser:
    ...
```

For Android system proxy compatibility, provide an HTTP CONNECT proxy separately:

```python
async with AsyncDamru(
    proxy="socks5://user:pass@host:port",
    http_proxy="127.0.0.1:18888",
) as browser:
    page = await browser.new_page()
    await page.goto("https://demo.fingerprint.com/playground")
```

Leave `timezone` and `locale` unset unless you intentionally need fixed values. Damru will set Android timezone, Chrome timezone, `Accept-Language`, and `Intl` locale from the proxy exit. CLI `stealth-open-url` also hints `pt-BR` for `.com.br` URLs when no explicit locale is provided.

---

## Requirements
*   **Host**: Windows (WSL2) or Linux.
*   **Android**: Rooted Redroid in Docker. MuMu Player code is experimental and not recommended for production.
*   **Python**: 3.10 or higher.
*   **Main Dependencies**: `playwright>=1.40,<1.60`, `requests`, `pysocks`.
*   **Playwright Patch**: Damru ships and verifies a patched `crPage.js` file used to reduce CDP/Runtime detection surface.
*   **Stealth Add-ons**: `curl_cffi` (highly recommended for TLS spoofing).
