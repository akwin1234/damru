# 🐍 Damru Python API Reference

Welcome to the definitive API reference for the **Damru** library. This guide covers everything from basic automation to advanced multi-container orchestration and stealth tuning.

Damru is designed to be a transparent drop-in replacement for standard Playwright setups, adding deep-level Android OS and Chromium C++ spoofing.

---

## 📑 Table of Contents
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

## 🏛️ Core Classes

### `AsyncDamru` (Recommended)
The primary asynchronous context manager. It orchestrates the 8 layers of stealth and returns a Playwright `BrowserContext`.

#### Usage
```python
from damru import AsyncDamru

async with AsyncDamru(device="pixel_8_pro", proxy="socks5://...") as browser:
    page = await browser.new_page()
    await page.goto("https://creepjs.com")
```

#### `__init__` Parameters
| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `device` | `str` | `"random"` | Target device string (e.g., `"samsung_s24_ultra"`). |
| `serial` | `str` | `None` | ADB identifier. If `None`, Damru auto-detects connected devices. |
| `proxy` | `str` | `None` | SOCKS5/HTTP proxy. Damru uses this to match Geo-Identity (TZ, Locale). |
| `timezone` | `str` | `None` | Force a specific IANA Timezone (e.g., `"Europe/London"`). |
| `locale` | `str` | `None` | Force a specific BCP-47 Locale (e.g., `"fr-FR"`). |
| `debug` | `bool` | `False` | Enables verbose console logging for debugging OS patches. |

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

with Damru(device="pixel_7") as browser:
    page = browser.new_page()
    page.goto("https://bot.sannysoft.com")
```
*Note: Methods and parameters are identical to `AsyncDamru` but without `await`.*

---

## 🚨 Exception Handling

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

## 🏊 Pool Management

### `DamruPool` (Async)
Designed for massive parallelization across dozens of Docker containers. It automatically manages container lifecycles and port forwarding.

#### Usage
```python
from damru import DamruPool

# mode="auto" automatically starts and manages Redroid Docker containers
async with DamruPool(size=10, mode="auto") as pool:
    # pool.session() provides an AsyncDamru context from an available container
    async with pool.session() as browser:
        page = await browser.new_page()
        ...
```

#### `__init__` Parameters
| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `size` | `int` | `1` | Number of concurrent instances/containers to maintain. |
| `mode` | `str` | `"auto"` | Deployment mode: `"auto"` (manages Redroid via Docker), `"mumu"` (local MuMu Player instances), or `"remote"` (connects to existing ADB instances). |
| `proxy_list` | `list[str]` | `None` | List of proxies. Pool rotates through these when assigning contexts. |

### `DamruPoolSync` (Sync)
The synchronous counterpart, ideal for distributed task workers and multi-threading frameworks like `concurrent.futures`.

#### Usage
```python
from damru import DamruPoolSync

# proxy_list enables per-container proxy rotation
with DamruPoolSync(size=5, proxy_list=["socks5://..."]) as pool:
    # Yields fully prepared browser contexts as they become ready
    for context in pool.get_contexts():
        page = context.new_page()
        ...
```

---

## 📱 Device Management

### `AndroidDevice` Database
Access the physical specifications of our 32+ device profiles.

```python
from damru import list_device_names, get_device, get_random_device

# Get hardware specs for a specific phone
pixel = get_device("pixel_8_pro")
print(f"Cores: {pixel.cores}, RAM: {pixel.ram_gb}GB")

# Select a random Android 13 profile
random_phone = get_random_device(android_version="13")
```

---

## ⚙️ Advanced Configuration

You can tune Damru's behavior globally via the `damru.config` module before initialization.

```python
import damru.config

# Custom WSL2 settings
damru.config.WSL_DISTRO = "Ubuntu-22.04"
damru.config.WS_PASSWORD = "my-secure-password"

# Path to local Chrome APKs if not in the default folder
damru.config.CHROME_APK = "/custom/path/to/chrome.apk"
```

---

## 🛠️ Advanced Modules

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

## 📖 Cookbook: Common Patterns

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

---

## ⚠️ Requirements
*   **Host**: Windows (WSL2) or Linux.
*   **Android**: Rooted Redroid (Docker) or MuMu Player.
*   **Python**: 3.10 or higher.
*   **Main Dependencies**: `playwright`, `requests`, `pysocks`.
*   **Stealth Add-ons**: `curl_cffi` (highly recommended for TLS spoofing).
