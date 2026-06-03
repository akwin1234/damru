<div align="center">
  <img src="logo.svg" alt="Damru Logo" width="200" height="200">
  <h1>Damru</h1>
  <p><strong>The Apex Predator of Android Browser Automation</strong></p>
  <p><em>The world's first open-source framework for natively modded Android browser automation.</em></p>
  <p>High-performance, ultra-stealth browser automation framework designed for web scraping and botting at scale.</p>

  [![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
  [![Playwright](https://img.shields.io/badge/playwright-1.40--1.59-green.svg?style=for-the-badge&logo=playwright&logoColor=white)](https://playwright.dev/python/)
  [![Platform](https://img.shields.io/badge/Platform-WSL2%20%7C%20Linux-lightgrey.svg?style=for-the-badge&logo=linux&logoColor=white)](#minimum-system-requirements)
  [![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/License-PolyForm%20Noncommercial%201.0.0-red.svg?style=for-the-badge)](https://polyformproject.org/licenses/noncommercial/1.0.0)

  <p>
    <strong>Community:</strong>
    <a href="https://discord.gg/GsxFdjdrT">Discord server</a> recommended
  </p>
  <p><strong>Official repository:</strong> <a href=https://github.com/akwin1234/damru>github.com/akwin1234/damru</a></p>
</div>

<br/>

> **Damru** leverages rooted Android emulators (like Redroid in Docker) via ADB to achieve undetectable automation. Whether you are bypassing modern WAFs (like Cloudflare Turnstile) or scoring 100% on CreepJS, Damru provides an impenetrable disguise.

> [!WARNING]
> **Project Status: Beta**
> This project is currently in a **Beta** state. While it has been verified as 100% stable and fully functional on the local systems of the developers who built it, it requires further testing across diverse environments and hardware configurations. We welcome feedback and issue reports!

---

## Table of Contents

- [Core Features](#core-features)
- [Why Damru is Better](#why-damru-is-better-than-the-rest)
- [Proof of Stealth: Benchmarks](#proof-of-stealth-benchmark-comparisons)
- [Verification Proof](docs/PROOF.md)
- [Architecture: The 8 Layers of Stealth](#architecture-the-8-layers-of-zero-js-stealth)
- [Project Structure](#project-structure)
- [Python API Documentation](docs/PYTHON_API.md)
- [Device Profiles](docs/DEVICE_PROFILES.md)
- [Viewer, Screenshots, and Video](docs/VIEWER.md)
- [WSL2 Kernel Requirements](docs/WSL_KERNEL.md)
- [Download Custom OS Image](#download-custom-os-image)
- [Quickstart Guide](#first-time-user-deployment-guide-wsl2--linux)
- [Usage & Examples](#usage--examples)
- [Redroid vs MuMu Player](#platform-recommendation-redroid-vs-mumu)
- [Testing](#testing-your-setup)
- [Roadmap](#the-big-plan-roadmap)
- [FAQ](#frequently-asked-questions)
- [License & Fork Policy](#license--fork-policy)
- [Legal Disclaimer](#mandatory-legal-disclaimer--ethical-use-notice)

---

## Platform Recommendation: Redroid vs MuMu

While Damru technically lists multiple environments, **Redroid (Docker)** is the only officially supported and functional path.

| Platform | Status | Stealth Level | Stability | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| **Redroid (Docker)** | **Production-Ready** | **Absolute** | **High** | **Highly Recommended** |
| **MuMu Player** | **Unfinished / Beta** | Moderate | Low | **Non-functional / Not Recommended** |
| **Physical Devices** | **NOT SUPPORTED** | N/A | N/A | **DO NOT USE** |

> [!CAUTION]
> **Physical Device Warning**
> Damru is designed strictly for containerized environments (Redroid). **It does not support physical Android devices.** Do not attempt to run Damru against your personal phone. If you choose to use a spare rooted device, you do so at your own risk. Damru's low-level OS patches and binary injections may brick or destabilize physical hardware.

**Why Redroid**
Damru's most advanced stealth layers - including native GPU binary patching and OS-level `iptables` hooks-are optimized for the Redroid kernel. It provides a more stable environment for multi-container pools and is significantly more undetectable by modern anti-bot heuristics. MuMu Player support is currently an experimental, unfinished, and non-functional beta feature.

---

## Core Features

*   **Zero JS Injection**: All spoofing is executed at the OS, Binary, and CDP levels. No brittle `Object.defineProperty` hacks.
*   **Massive Device Database**: Built-in profiles for 49 real Android devices (Samsung, Pixel, Xiaomi, OnePlus, Nothing, Honor, Vivo, POCO, etc.) with realistic hardware specifications.
*    **Display & Resolution Spoofing**: Natively overrides screen dimensions and DPI via Android's Window Manager (`wm size/density`) for physical accuracy.
*    **Browser Version & Client Hints Randomization**: Dynamically selects from a database of verified Chrome versions and generates perfectly accurate `sec-ch-ua` Client Hints, including Chromium GREASE brand permutations.
*    **TLS/JA3 Randomization**: Generates ~184 unique TLS fingerprints from a single binary by dynamically toggling cipher suites and experimental flags.

*   **Auto Image Management**: Automatically pulls and tags the required Redroid Docker images if the custom baked image is missing.
*   **Font & Voice Randomization**: Installs custom TTS engines and extra system fonts, randomizing them per session.
*   **Hardware Status Spoofing**: Fakes battery levels, charging status, and even audio sample rates (48kHz) to mirror real mobile hardware behavior.
*   **Hardware Overrides**: Spoofs CPU cores, RAM (via syscall hooks), and touch points (e.g., 5-point touch) directly via native OS patching and CDP.
*   **Network & DNS Stealth**: Faithfully fakes mobile network conditions and forces resolution through proxy-level ISP DNS to pass "DNS Leak" and "Targeted DNS" checks.
*   **CDN & Anti-Bot Bypass**: Out-of-the-box native bypass for modern WAFs (like Cloudflare Turnstile, CDN TLS) and advanced behavioral detection systems.

---

## Why Damru is Better Than the Rest

We spent significant time modifying and testing popular desktop-first solutions like **Camoufox**, **Fingerprinting Chromium**, and various Playwright stealth patches to work on mobile - but nothing reached the level of stability and undetectability achieved by this project. 

The botting landscape is littered with tools that *used* to work: `puppeteer-stealth`, `undetected-chromedriver`, and various anti-detect browsers. Here is why they fail today, and why Damru succeeds:

| Feature | Legacy Tools (`puppeteer-stealth`, etc.) | Damru |
| :--- | :--- | :--- |
| **Spoofing Method** | **JavaScript Injection** (`Object.defineProperty`). Leaves massive detectable traces. | **Native Overrides**. Modifies C++ engine via CDP, patches binaries, edits OS props. |
| **JS Leakage** | Anti-bots check `.toString()` on functions. Injected JS is caught instantly. | **Zero JS Injected**. Functions remain entirely native. |
| **Hardware Emulation** | Fakes `navigator.hardwareConcurrency` via JS. Fails worker tests. | **C++ CDP Override**. Changes the main-page value at the Chromium engine level; worker targets are handled best-effort through CDP auto-attach. |
| **GPU Fingerprint** | WebGL spoofing via JS wrapping. Leaks real GPU via extensions. | **Binary Patching**. Physically patches the `.so` Vulkan/GLES driver files on Android. |
| **Physical Memory** | Fakes `deviceMemory` via JS. Easily caught by timing or syscall checks. | **Syscall Hooks**. Uses `libfakemem.so` to intercept `sysinfo` calls via `LD_PRELOAD`. |
| **Worker Stealth** | Workers often leak the real hardware concurrency of the host. | **Worker Interception**. Uses CDP `Target.setAutoAttach` to force overrides on all Threads/Workers. |
| **TLS/JA3 Hash** | Fixed TLS fingerprint based on the Chrome binary version. | **TLS Randomization**. Produces ~184 unique JA3 hashes via dynamic cipher blacklisting. |
| **Screen Dimensions** | Viewing desktop Chrome as mobile via viewport scaling (leaks real screen size). | **OS-Level Display**. Modifies Android `wm size/density` natively. |
| **Network Identity** | Frequently leaks WebRTC private IPs and IPv6 fingerprints. | **OS-Level IP Tables**. Blocks WebRTC leaks and IPv6 at the Android kernel level. |
| **Mobile Emulation** | Desktop Chrome pretending to be mobile via viewport scaling. | **Real Android OS**. Runs inside Redroid (Android 14) or MuMu Player. It *is* mobile. |

### Proof of Stealth: Benchmark Comparisons

We regularly test Damru against the hardest anti-bot systems in the industry. These results are reproducible using the built-in benchmark suite (`python -m damru benchmark`) or the comprehensive functional test suite (`python example.py`).

Fresh Ubuntu/WSL verification proof is tracked in [docs/PROOF.md](docs/PROOF.md). The current sanitized Ubuntu VPS proof assets include:

- [Android screen recording](docs/assets/proof/ubuntu-redroid-proof.mp4)
- Individual site proof screenshots: [Amazon](docs/assets/proof/sites/amazon.png), [Foot Locker / DataDome target](docs/assets/proof/sites/datadome-footlocker.png), [Fingerprint Pro](docs/assets/proof/sites/fingerprint-pro.png), [Sannysoft](docs/assets/proof/sites/sannysoft.png), and [CreepJS](docs/assets/proof/sites/creepjs.png)
- [Sanitized site proof metadata](docs/assets/proof/sites/proof-sites.json)

#### Screenshot Proof Gallery

| Fingerprint Pro | CreepJS |
| :---: | :---: |
| <img src="docs/assets/proof/sites/fingerprint-pro.png" alt="Fingerprint Pro proof" width="360"> | <img src="docs/assets/proof/sites/creepjs.png" alt="CreepJS proof" width="360"> |

| Sannysoft | Foot Locker / DataDome target |
| :---: | :---: |
| <img src="docs/assets/proof/sites/sannysoft.png" alt="Sannysoft proof" width="360"> | <img src="docs/assets/proof/sites/datadome-footlocker.png" alt="Foot Locker DataDome proof" width="360"> |

| Amazon |
| :---: |
| <img src="docs/assets/proof/sites/amazon.png" alt="Amazon proof" width="520"> |

| Target Anti-Bot | Standard Playwright | Typical Stealth Plugins | Damru |
| :--- | :--- | :--- | :--- |
| **CreepJS (Trust)** | 0% (Trash) | ~45% (High Lies) | **85%+ (0% Lies, Top Stealth)** |
| **BrowserScan** | Fails Hardware/OS | Fails WebGL/Fonts | **Passes 100% OS/Hardware/WebRTC** |
| **Sannysoft** | Fails | Passes | **Passes 100%** |
| **Cloudflare Turnstile**| Blocked ("Just a moment")| Frequently Blocked | **Bypassed Natively** |
| **Other Enterprise WAFs**| Blocked | Frequently Blocked | **Bypassed Natively** |

*Note: Damru is capable of bypassing many other advanced detection systems not listed here. As an educational project, we focus on demonstrating these core industry-standard benchmarks.*

---

## Architecture: The 8 Layers of "Zero JS" Stealth

Damru's core philosophy is **Zero JavaScript Injection**. Instead of trying to outsmart anti-bot JavaScript *with* more JavaScript, Damru lies from the outside in.

1.  **Layer 1: Android System Props (Root `resetprop`)**
    Damru connects via ADB and uses root access to modify `build.prop` values dynamically. It changes `ro.product.model`, `ro.build.fingerprint`, and the Android SDK version at the OS level. The browser sees a genuine Pixel 8 Pro or Samsung S24.
2.  **Layer 2: GPU Binary Patching**
    Anti-bots actively check your GPU. Generic Docker containers show "SwiftShader" (an instant ban). Damru physically patches the Vulkan/GLES `.so` binaries on the filesystem *before* Chrome launches, reading as an `Adreno (TM) 640` or `Mali-G710`.
3.  **Layer 3: Syscall Interception (`LD_PRELOAD`)**
    Damru uses a custom C shared library (`libfakemem.so`) to intercept the `sysinfo` and `sysconf` system calls. This ensures that even low-level system checks see the spoofed RAM and CPU specifications of the targeted device.
4.  **Layer 4: Deep CDP Protocol Overrides**
    Damru uses low-level Chrome DevTools Protocol (CDP) commands (`Emulation.setHardwareConcurrencyOverride`, `Emulation.setTouchEmulationEnabled`) to spoof CPU cores and touch points directly inside Chromium's C++ engine.
5.  **Layer 5: Thread & Worker Interception**
    Using `Target.setAutoAttach`, Damru ensures that every Worker (Dedicated, Shared, and Service) created by the browser inherits the same hardware overrides as the main thread, closing a common leakage vector for advanced anti-bots.
6.  **Layer 6: Chrome Preferences & Flag Patching**
    Damru modifies Chrome's underlying `Preferences` JSON and launch flags to force specific Locales, randomize TLS cipher suites (~184 JA3 variants), and disable DNS-over-HTTPS to force resolution through proxy ISP DNS.
7.  **Layer 7: OS-Level Evasions**
    Using Android `iptables`, Damru blocks WebRTC private IP leaks and completely disables IPv6. It also neutralizes DevTools timing detection by bypassing `debugger` pauses natively via CDP.
8.  **Layer 8: Display & Density Spoofing (`wm size/density`)**
    To avoid "Resolution Mismatch" detections, Damru modifies the Android Window Manager natively. It uses `wm size` and `wm density` to force the OS to report physically accurate screen dimensions and pixel densities for the targeted device (e.g., Pixel 8's 1344x2992 @560dpi).

---

## Project Structure

Damru is organized into specialized modules to maintain the separation between high-level Python automation and low-level system spoofing.

```text
damru-project/
+-- damru/                 # Core Framework (Python)
|   +-- async_core.py      # Async entry points (AsyncDamru)
|   +-- core.py            # Sync entry points (Damru)
|   +-- root.py            # OS/Binary patching logic (resetprop/iptables/display)
|   +-- devices.py         # 49 Real Device Specifications Database
|   +-- chrome.py          # Browser lifecycle & Preferences patching
|   +-- bypass.py          # CDN TLS/WAF edge-layer TLS impersonation
|   +-- pool.py            # Multi-container orchestration (DamruPool)
+-- native/                # Native Binary Hooks (C source)
|   +-- vulkan_layer.c     # Vulkan C++ string spoofing binary
|   +-- libfakemem.c       # Physical RAM spoofing via sysconf hooks
+-- tests/                 # Stealth & Stability Benchmarks
|   +-- benchmark_auto.py  # Automated Anti-Bot probe
|   +-- test_stealth.py    # Unit tests for fingerprinting integrity
+-- chrome-apks/           # Pre-validated Mobile Assets
|   +-- espeak.apk         # TTS engines for Voice fingerprinting
|   +-- magisk.apk         # Local resetprop source for raw Redroid
|   +-- 145.x/             # Specific Chrome/WebView versions
+-- docs/                  # Roadmaps & Infrastructure Plans
+-- scripts/               # Maintenance & Image Baking Utils
+-- tools/                 # External Debugging Tools (Magisk.apk)
```

---

## Python API Documentation

For detailed information on how to use the Damru library programmatically, including class references, managed pooling, and advanced configuration, please see the:

**[Damru Python API Reference](docs/PYTHON_API.md)**

For the full list of available Android identities, see the:

**[Damru Device Profile Reference](docs/DEVICE_PROFILES.md)**

### Quick Summary:
*   **`AsyncDamru`**: The primary entry point for asynchronous automation.
*   **`Damru`**: Synchronous wrapper for standard blocking scripts.
*   **`DamruPool`**: Orchestration for high-throughput multi-container scraping.
*   **`damru.bypass`**: Advanced TLS/JA3 impersonation for edge-layer bypasses.

---

## Download Custom OS Image

> [!IMPORTANT]
> The pre-baked Damru Redroid image is a large Docker tarball and is not tracked in Git. Redroid is Linux-only: load or bake this image inside native Linux or WSL2, never native Windows Docker.

Download the current pre-baked image:

**[Download damru-redroid-latest.tar](https://drive.google.com/file/d/1AzSTOlGpSfqHB-F-Yty2JqbOEMlgFT5F/view?usp=sharing)**

Current local artifact prepared for release testing:

```bash
python -m damru install-deps -y
python -m damru install-image
```

`install-image` auto-detects `damru-redroid-latest.tar` in the current directory, parent directory, project root, home, or Downloads, verifies its SHA-256, and runs `docker load` inside Linux/WSL. If the tarball is not local, use:

```bash
python -m damru install-image --download
```

If the tarball is missing, rebuild it on Linux/WSL:

```bash
python -m damru bake-image --image damru-redroid:latest
docker save damru-redroid:latest -o damru-redroid-latest.tar
sha256sum damru-redroid-latest.tar > damru-redroid-latest.tar.sha256
```

Once downloaded, follow **Step 3** in the Deployment Guide below to load it into Docker.

### Optional Raw APK Asset Bundle

Normal users should prefer `python -m damru install-image`; the baked image already contains Chrome, WebView/TTS assets, fonts, and warm preferences. Use the raw APK bundle only when you want to bake your own image or run unbaked raw Redroid containers.

Google Drive bundle: [Chrome/WebView/TTS/resetprop APK assets](https://drive.google.com/file/d/1xh5Z-LXqUIEjO08KKjhaB_89KS2pBWZq/view?usp=sharing)

Automatic install:

```bash
python -m damru install-apks --download
```

`install-apks` downloads the APK asset bundle, extracts to `/home/damru/chrome-apks` on Linux/WSL by default, validates that APK files exist, and updates `CHROME_APK` only when needed. `install-deps` and `setup` also run this automatically when no baked image and no local APKs are available.

Extract/copy the bundle so one bundle root contains this layout. The bundle is not only Chrome; it also includes Trichrome WebView and TTS voice APKs. Damru ships `magisk.apk` and copies it into this bundle automatically when raw/unbaked Redroid needs a local `resetprop` source:

```text
chrome-apks/
  143.0.7499.52/*.apk
  144.0.7559.132/*.apk
  145.0.7632.75/*.apk
  espeak.apk
  google_tts.apk
  rhvoice.apk
  magisk.apk
```

Damru auto-selects only Chrome versions that pass the current raw Redroid voice/fingerprint smoke tests. Chrome `145.0.7632.75` can still be selected manually with `CHROME_APK` or `chrome_apk=`, but auto mode skips it until its Android TTS voice behavior is stable.

Manual Linux/WSL extraction, from the directory where you downloaded the bundle:

```bash
sudo mkdir -p /home/damru
sudo chown "$USER:$USER" /home/damru
unzip damru-chrome-apks-latest.zip -d /home/damru/chrome-apks
find /home/damru/chrome-apks -maxdepth 2 -name '*.apk' | head
```

On Windows, extract the archive with File Explorer or 7-Zip, then copy the resulting `chrome-apks` folder into your Damru project folder. If Damru runs inside WSL, the same folder is visible as a `/mnt/c/...` path.

Then either let Damru auto-detect it from the project root:

```bash
python -m damru check-env
python -m damru bake-image --image damru-redroid:latest
```

Damru auto-searches `/home/damru/chrome-apks`, package-local `chrome-apks/`, the current directory's `chrome-apks/`, and the parent directory's `chrome-apks/`. From that one bundle root it discovers Chrome split APKs, `TrichromeWebView.apk`, `google_tts.apk`, `espeak.apk`, `rhvoice.apk`, and `magisk.apk`. If automatic detection fails, keep the full `chrome-apks/` bundle together and point config/code at the specific Chrome split-APK version directory:

```python
CHROME_APK = "/home/damru/chrome-apks/145.0.7632.75"
```

For WSL paths, convert the Windows path to `/mnt/c/...`:

```python
CHROME_APK = "/mnt/c/Users/you/Downloads/damru/chrome-apks/145.0.7632.75"
```

Or pass it directly in Python:

```python
from damru import AsyncDamru

async with AsyncDamru(chrome_apk="/home/damru/chrome-apks/145.0.7632.75") as browser:
    page = await browser.new_page()
```

Damru ships `magisk.apk` as a package asset and uses it only when raw/unbaked Redroid needs a local source for extracting standalone `resetprop`. During `setup`, `install-apks`, or `check-env`, Damru copies that asset to `/home/damru/chrome-apks/magisk.apk` when needed. Damru does not download Magisk, eSpeak, Google TTS, or RHVoice from third-party APK sites at runtime.

---

## First-Time User Deployment Guide (WSL2 / Linux)

Ready to start Damru uses **Redroid** (Android in Docker) to spin up headless mobile devices instantly. Follow this step-by-step guide to deploy Damru from scratch on the tested Ubuntu paths: native Ubuntu VPS/Linux, or Ubuntu inside WSL2 with Damru's bundled WSL kernel.

> [!IMPORTANT]
> Redroid is Linux-only. On Windows, Docker and Redroid must run inside WSL2; native Windows Docker is not a supported Redroid target.
>
> Current supported/tested host paths are **Ubuntu native Linux** and **Ubuntu WSL2 with Damru's bundled custom WSL kernel**. We did not patch or replace the kernel on the native Ubuntu VPS; it worked with the provider's normal Ubuntu kernel. Debian 13 VPS kernels tested so far ship with `CONFIG_ANDROID_BINDERFS` disabled, so they are not supported for Redroid multi-container pools.

### Minimum System Requirements

> [!WARNING]
> **Supported Linux host today: Ubuntu 24.04 LTS only.** Damru Redroid auto mode is currently supported on native Ubuntu 24.04 VPS/Linux and Ubuntu 24.04 WSL2 with Damru's bundled WSL kernel. Other Linux distributions are not supported yet, even if Docker itself works, because Redroid multi-container reliability depends on kernel binderfs support. Ubuntu 25.xx/26.xx are not part of the supported public path yet; Playwright's browser installer may reject those newer OS labels even though Damru normally connects to Android Chrome inside Redroid.

Damru runs one full Android container per worker. The default Redroid worker limit is `2` CPU cores and `2g` memory per container (`REDROID_CPUS = 2.0`, `REDROID_MEMORY = "2g"`). Use these numbers for capacity planning:

| Workload | CPU | RAM | Disk | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Bare minimum, 1 worker** | 2 vCPU | 4 GB host RAM | 15 GB free | Enough for install, Docker, one Redroid worker, and basic smoke tests. |
| **Recommended, 1 worker** | 4 vCPU | 8 GB host RAM | 30 GB free | Better for high-resolution pages, proof captures, and fewer Chrome startup races. |
| **Each additional worker** | +2 vCPU | +2-3 GB RAM | +5-8 GB free | Matches the default Docker worker limit plus image/container overhead. |
| **Baking/exporting image** | 4 vCPU | 8 GB RAM | 20 GB temporary free | Needs room for base image, baked image layer, and exported `.tar`. |
| **WSL2 recommended host** | 4+ vCPU | 8-16 GB RAM | 40+ GB free in WSL disk | WSL stores Docker layers inside the distro virtual disk unless you move Docker data-root. |

For large pools, start with `max_devices=1`, run `python -m damru check-env`, then increase workers gradually. Redroid is CPU and disk-I/O heavy during boot; too many workers on a small VPS will look like browser instability.

`DamruPool(max_devices > 1, mode="auto")` requires real binderfs support, not only `/dev/binder`, `/dev/hwbinder`, and `/dev/vndbinder` device nodes. If the kernel has `CONFIG_ANDROID_BINDERFS` disabled, one Redroid container may boot while a second container appears in ADB but fails Android userspace (`zygote`, `system_server`, WebView/CDP). Current Damru checks this before starting a multi-worker pool and tells the user to run `max_devices=1` or boot a binderfs-enabled kernel.

### Step 1: System Preparation (Ubuntu Linux / Ubuntu WSL2)

You need a tested Ubuntu Linux environment. If you are on Windows, install Ubuntu in WSL2 and let Damru apply its bundled WSL kernel when setup asks for confirmation. Ensure your system is up to date and install `adb`:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install adb wget curl git jq -y
```

After Damru is installed, you can also let the CLI install the common Linux/WSL dependencies:

```bash
python -m damru install-deps
python -m damru install-image
python -m damru check-env
```

`install-deps` is idempotent: on a fresh Ubuntu WSL/Linux install it installs ADB, Docker, iptables, curl/wget/git/jq, mounts binderfs, and starts Docker. On later runs it reuses installed packages and rehydrates Docker/binderfs after WSL restarts.
`install-image` loads the baked `damru-redroid:latest` image, which already contains Chrome, WebView/TTS assets, fonts, and warm preferences. Users do not need to provide Chrome APKs unless they intentionally run an unbaked raw Redroid image.

On Windows/WSL2, Damru runs Docker and Redroid inside WSL and routes Redroid ADB through WSL. When Docker-published ADB ports are unreliable, Damru uses host networking and remaps each Redroid worker's `adbd` to a unique port (`5600`, `5601`, ...), so multi-worker pools can still run without native Windows Docker. Native Linux uses Docker bridge/NAT and Damru selects the nft iptables backend to match modern Docker daemons; WSL prefers legacy iptables where available because some WSL kernels reject Docker's `addrtype` NAT rule through nft. See [WSL kernel notes](docs/WSL_KERNEL.md) and the latest [WSL fallback test results](docs/WSL_FALLBACK_TEST_RESULTS.md).

Damru's WSL kernel installer also writes `dnsTunneling=true` and `networkingMode=NAT` into `%USERPROFILE%\.wslconfig`. This avoids a common WSL failure where the distro can ping public IPs but `apt`, `pip`, or Docker containers cannot resolve DNS names. Run `wsl --shutdown` after kernel/DNS changes, then reopen Ubuntu.

Current validation on June 2, 2026. Full sanitized notes are in [Verification Proof](docs/PROOF.md):

- WSL2 fresh-loop distro: `install-deps -y`, `fix-wsl`, `install-viewer -y`, `check-env --viewer`, single-worker browser smoke, and two-worker `DamruPool(mode="auto", max_devices=2)` passed.
- Native Ubuntu VPS reset loop: Docker packages/state removed, fresh venv created, `install-deps -y`, `check-env --viewer`, unit tests, single-worker browser smoke, and two-worker pool smoke passed.
- Both Ubuntu WSL2 and native Ubuntu verified `https://example.com` in two concurrent Redroid workers with `navigator.hardwareConcurrency == 8`.
- Debian 13 Trixie VPS was tested with kernel `6.12.86+deb13-amd64`; Docker worked, but Redroid multi-container support failed because the kernel reported `# CONFIG_ANDROID_BINDERFS is not set`.

### Step 2: Install Docker & Enable Binderfs (Crucial for Redroid)

Prefer `python -m damru install-deps`; it performs these package, Docker, binderfs, iptables, and Playwright-patch steps automatically. The manual commands below are only for debugging or custom Linux images.

Redroid requires Docker and Android's `binderfs` kernel modules. 

1.  **Install Docker**:
    ```bash
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    ```
    *(Log out and log back in, or run `newgrp docker` to apply permissions).*

2.  **Mount Binderfs** (Required for Android inside Docker):
    ```bash
    sudo mkdir -p /dev/binderfs
    sudo mount -t binder binder /dev/binderfs
    ```
    *(Note: To make this persistent across reboots, you will need to add it to `/etc/fstab`).*

### The Instant Custom OS Image

Compiling native C binaries, injecting them via ADB, applying `iptables` rules, and installing Chrome on every run is slow. The recommended path is a baked `damru-redroid:latest` Docker image exported as `damru-redroid-latest.tar`, where Chrome, native patches, fonts, TTS assets, and warm Chrome preferences are already installed. The tarball is intentionally ignored by Git because it is large; keep the checksum file with the release artifact.

### Step 3: Instant Boot with the Custom OS (Recommended)

1.  **Load the pre-baked image**:
    
    **For WSL2 Users:** copy or mount the tarball inside your WSL distro, then run Docker from WSL:
    ```bash
    sha256sum -c damru-redroid-latest.tar.sha256
    docker load -i damru-redroid-latest.tar
    ```
    
    **For Native Linux Users:**
    ```bash
    sha256sum -c damru-redroid-latest.tar.sha256
    docker load -i damru-redroid-latest.tar
    ```

2.  **Start the custom Damru container**:
    ```bash
    docker run -itd --rm --privileged \
        -v ~/data:/data \
        -p 5555:5555 \
        damru-redroid:latest \
        androidboot.redroid_width=1080 \
        androidboot.redroid_height=2400 \
        androidboot.redroid_dpi=480
    ```

3.  Wait 30 seconds for Android to boot, then connect via ADB:
    ```bash
    adb connect localhost:5555
    adb devices
    # You should see: localhost:5555 device
    ```

#### Troubleshooting Common WSL2 Errors

If your Redroid container fails to boot or Docker won't start in WSL, run these mandatory "Fix-it" commands:

*   **Binderfs Error** (`docker: Error... no such device`):
    ```bash
    sudo mkdir -p /dev/binderfs
    sudo mount -t binder binder /dev/binderfs
    ```
*   **Docker Network Error** (`iptables` failure):
    ```bash
    python -m damru fix-wsl
    ```
    Damru selects a Docker-compatible iptables backend automatically. On some WSL kernels, Docker's `addrtype` NAT rule works with `iptables-legacy` but fails with `iptables-nft`.
*   **Missing WSL Kernel Module** (`xt_addrtype not found`):
    ```bash
    python -m damru fix-wsl
    ```
    If the module is still missing, Damru tries its no-iptables/no-bridge Docker fallback. Windows auto mode uses WSL host networking with per-worker ADB port remapping for Redroid workers. For classic Docker bridge/NAT mode, boot a WSL2 kernel with Docker bridge/NAT and binderfs support.
*   **Permission Denied**:
    ```bash
    sudo usermod -aG docker $USER
    # Restart WSL after running this
    ```

> [!TIP]
> **What is an ADB Serial**

> An ADB serial is a unique identifier for your Android device. 
> - For **Redroid/Docker**, it is usually the network address: `localhost:5555` or an internal IP.
> - Physical-device serials may appear in `adb devices`, but Damru does not support physical phones as automation targets.

### Step 4: Install Damru

**Option A: Pip Install in a Virtual Environment (Fastest)**
```bash
sudo apt install -y python3-venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip setuptools wheel
pip install git+https://github.com/akwin1234/damru.git
```

Do not install Damru into the system Python on modern Ubuntu. Ubuntu uses PEP 668 externally-managed Python environments, so use a virtual environment. Damru connects to Chrome inside Android/Redroid through CDP, so `playwright install chromium` is not required for normal Damru sessions and may fail on brand-new Ubuntu releases before Playwright officially supports that OS label.

Verify the local environment:

```bash
python -m damru setup
python -m damru install-image
python -m damru check-env
```

`setup` runs dependency setup by default. If no baked image is loaded and no local Chrome/WebView/TTS APK assets exist, Damru downloads and extracts the APK bundle automatically. Users should not need to run `install-apks` manually unless they are baking/customizing raw Redroid images or recovering from an APK asset error.

If Docker still fails inside WSL, run the safe repair/diagnostic pass:

```bash
python -m damru fix-wsl
```

If it reports a missing kernel module such as `xt_addrtype`, the active WSL2 kernel lacks Docker bridge/NAT support. See [WSL2 Kernel Requirements](docs/WSL_KERNEL.md).

For scripted setup with a custom WSL distro/user, pass them explicitly:

```bash
python -m damru setup -y --wsl-distro Ubuntu --wsl-username your-wsl-user
```

#### Windows Installation Fix (Important)

If you are using an older Windows Python/setuptools combination and encounter an `AssertionError: ...distutils\core.py` during `pip install`, upgrade packaging tools first:

```powershell
python -m pip install -U pip setuptools wheel
pip install git+https://github.com/akwin1234/damru.git
```

Do not set `SETUPTOOLS_USE_DISTUTILS=stdlib` globally on modern Python. It can break editable builds on Python 3.14 and newer.

**Option B: Clone & Install (For Developers)**
```bash
git clone https://github.com/akwin1234/damru.git
cd damru
python3 -m venv venv
source venv/bin/activate
python -m pip install -U pip setuptools wheel
pip install -e .
python -m damru setup --skip-deps
```

When you import Damru, it verifies and applies the bundled Playwright `crPage.js` patch used to reduce CDP target discovery leaks.

### CLI Commands

```bash
python -m damru setup           # guided first-run setup and config writer
python -m damru check-env       # validate Linux/WSL dependencies and assets
python -m damru install-deps    # install common Linux/WSL dependencies
python -m damru fix-wsl         # retry safe WSL Docker/binderfs/netfilter fixes
python -m damru wsl-kernel status # inspect bundled/active WSL kernel state
python -m damru benchmark       # run the benchmark command
python -m damru bake-image      # bake a warm Redroid image
python -m damru devices         # list ADB devices from Linux/WSL
python -m damru screenshot      # capture Android display PNG through ADB
python -m damru record          # capture Android display MP4 through ADB
python -m damru view            # open optional scrcpy live viewer
python -m damru install-viewer  # check/install optional scrcpy tooling
```

For testing a separate WSL distro without changing `config.py`, set `DAMRU_WSL_DISTRO`, for example: `$env:DAMRU_WSL_DISTRO="DamruFreshKernelTest"`. Do not run host-network Redroid workers in multiple WSL distros at the same time; `check-env` reports this conflict.

> **WSL custom kernel safety:** On Windows, Damru recommends using a fresh/dedicated WSL distro for Redroid. The bundled kernel installer edits `%USERPROFILE%\.wslconfig`, which changes how WSL boots. Damru backs up `.wslconfig`, but a custom WSL kernel can still break Docker/networking/modules or other WSL workloads. Interactive installs require typing the full warning phrase; scripted installs require `--confirm-wsl-kernel-risk` in addition to `--yes`. Native Linux/Ubuntu does not use this WSL kernel installer.

On Windows, `setup`/`install-deps` run inside WSL as root and do not use native Windows Docker. On native Linux scripted setup where sudo cannot prompt interactively, pass one password line on stdin:

```bash
printf '%s\n' 'your-sudo-password' | python -m damru setup -y --sudo-password-stdin
printf '%s\n' 'your-sudo-password' | python -m damru install-deps -y --sudo-password-stdin
```

For visual inspection or manual browser operation, see [Viewer, Screenshots, and Video](docs/VIEWER.md). Viewer support is optional and never starts automatically during `AsyncDamru`, `Damru`, or pool sessions.

### Use Redroid Like an Emulator Window

Damru normally runs headless, but you can open a live Android window with `scrcpy` when you want to inspect or manually operate the browser like an emulator.

Install and verify the optional viewer tooling:

```bash
python -m damru install-viewer
python -m damru check-env --viewer
```

Start or reuse a Redroid worker, then list ADB devices:

```bash
python -m damru devices
```

Open a live viewer for one worker:

```bash
python -m damru view --serial wsl:127.0.0.1:5600
```

If `--serial` is omitted, Damru uses the first online ADB device. On Windows/WSL, Redroid workers usually appear as `wsl:127.0.0.1:5600`, `wsl:127.0.0.1:5601`, and so on. On native Linux they usually appear as `127.0.0.1:5600`, `127.0.0.1:5601`, and so on.

Use watch-only mode when you do not want keyboard/mouse/touch input to change the Android session:

```bash
python -m damru view --serial wsl:127.0.0.1:5600 --no-control
```

Capture the full Android display for debugging or proof assets:

```bash
python -m damru screenshot --serial wsl:127.0.0.1:5600 --output screen.png
python -m damru record --serial wsl:127.0.0.1:5600 --time-limit 30 --output clip.mp4
```

Manual viewer control can click pages, type text, change Android settings, or alter browser state. Keep manual viewer sessions separate from benchmark/proof runs when you need clean automation results.

---

## Global Configuration

Damru uses a centralized configuration file located at `damru/config.py`. If you clone the repository or install it locally, you should modify these settings before running large pools or automated scripts.

> [!TIP]
> **Pre-made Configurations Available!**
> We have provided OS-specific configuration templates in the `damru/` directory to get you started faster:
> - **Windows / WSL2**: Copy `damru/config.py.windows` and rename it to `config.py`.
> - **Native Linux**: Copy `damru/config.py.linux` and rename it to `config.py`.

### Essential Configurations

1. **WSL2 Settings (Windows Auto-Mode)**:
   If you are running Python on Windows, Docker and Redroid still run inside WSL2. Damru uses `wsl -u root` for Linux setup and Docker preparation, so a WSL sudo password is not required for the CLI setup path.
   ```python
   # damru/config.py
   WSL_DISTRO = "Ubuntu"
   WSL_USERNAME = "your-wsl-user"
   WSL_PASSWORD = ""  # Kept for compatibility; current WSL setup uses wsl -u root
   ```

   Existing WSL installs are covered by `damru setup`: set `WSL_DISTRO` and `WSL_USERNAME`, then run `python -m damru check-env`. Damru's current Windows setup/runtime path uses `wsl -u root` for privileged WSL commands, so it does not need to store a sudo password in `config.py`.

2. **Chrome APK Path**:
   When not using the pre-baked `.tar` image, Damru will dynamically install Chrome onto raw Redroid instances. Use the automatic APK installer:

   ```bash
   python -m damru install-apks --download
   ```

   It downloads the Chrome/WebView/TTS/resetprop APK bundle automatically, extracts to `/home/damru/chrome-apks` on Linux/WSL, and configures `CHROME_APK` only when needed. The [Google Drive APK bundle](https://drive.google.com/file/d/1xh5Z-LXqUIEjO08KKjhaB_89KS2pBWZq/view?usp=sharing) is for manual recovery if automatic download is unavailable.

   If you still see an APK asset error, download the same Google Drive bundle manually, extract it as `/home/damru/chrome-apks`, keep the WebView/TTS/Magisk APKs beside the Chrome version folders, then set `CHROME_APK` to a Chrome split-APK version directory, for example:

   ```python
   CHROME_APK = "/home/damru/chrome-apks/145.0.7632.75"
   ```

   Manual Linux/WSL extraction example:
   ```bash
   sudo mkdir -p /home/damru
   sudo chown "$USER:$USER" /home/damru
   unzip damru-chrome-apks-latest.zip -d /home/damru/chrome-apks
   find /home/damru/chrome-apks -maxdepth 2 -name '*.apk' | head
   ```

   ```python
   # None = auto-searches the 'chrome-apks/' directory in the project root
   CHROME_APK = None  
   # Or specify an absolute path:
   # CHROME_APK = "/mnt/c/path/to/damru/chrome-apks/145.0.7632.75"
   ```

3. **Pool Settings (`NUM_DEVICES` & `MODE`)**:
   ```python
   MODE = "auto"          # "auto" = manages Docker containers; "mumu" = local VMs; "manual" = ADB
   NUM_DEVICES = 10       # How many concurrent containers to spin up/maintain
   REDROID_IMAGE = "damru-redroid:latest"  # The Docker image to use
   ```

4. **Proxy, Timezone, and Locale**:
Leave `TIMEZONE` and `LOCALE` as `None` unless you intentionally need fixed values. Damru resolves the active proxy exit at session start, then applies matching Android timezone, Chrome timezone, `Accept-Language`, and `Intl` locale. Rotating residential proxies are rechecked through Chrome after CDP connects so the browser does not keep a stale timezone from a previous exit.

Auto locale selection covers standard ISO country codes plus CLDR exceptional territory codes. Countries with more than one realistic phone/browser language can rotate between valid local variants, for example `en-PH` / `fil-PH` or `en-IN` / `hi-IN`.
   ```python
   PROXY = None        # Optional: SOCKS5/HTTP proxy URL for Python-side checks
   HTTP_PROXY = None   # Optional: Android system HTTP proxy as host:port
   TIMEZONE = None     # Auto from proxy exit when unset
   LOCALE = None       # Auto from proxy country when unset
   ```

   If your upstream proxy is SOCKS5 but Android needs an HTTP CONNECT proxy, run or provide a local HTTP bridge and pass it as `http_proxy` in code or `HTTP_PROXY` in config.

### Docker Storage Location (Crucial for Windows Users)
Redroid containers consume significant disk space. If you are using WSL2 Docker, it saves data to your `ext4.vhdx` virtual drive on the `C:` drive by default, which can quickly fill up your primary SSD.

**To save Docker images to a secondary HDD:**
You must configure the Docker daemon inside WSL to use a different data-root.
1. Open WSL (`wsl -d Ubuntu`).
2. Stop docker: `sudo service docker stop`.
3. Move existing data to your HDD: `sudo mv /var/lib/docker /mnt/d/docker-data`.
4. Symlink it back: `sudo ln -s /mnt/d/docker-data /var/lib/docker`.
5. Start docker: `sudo service docker start`.

*(Note: Native `DOCKER_STORAGE_PATH` configuration via Python is on the upcoming roadmap).*

---

## Usage & Examples

Damru handles the heavy lifting: it connects to ADB, gains root, applies system patches, spoofs the GPU, launches Chrome, and attaches via CDP-all automatically.

### Example 1: Basic Async Usage (The Standard Way)

```python
import asyncio
from damru import AsyncDamru

async def main():
    print("Launching Damru...")
    
    # device="random" picks from 49 real Android device profiles.
    # Leave timezone/locale unset so Damru follows the active proxy exit.
    async with AsyncDamru(
        device="random", 
        proxy="socks5://your.proxy.ip:1080",
        debug=True
    ) as browser:
        
        # 'browser' is a standard Playwright BrowserContext!
        page = await browser.new_page()
        
        print("Navigating to CreepJS to test stealth...")
        await page.goto("https://abrahamjuliot.github.io/creepjs/")
        await page.wait_for_timeout(10000)
        await page.screenshot(path="creepjs_score.png")
        print("Done! Check creepjs_score.png")

asyncio.run(main())
```

### Example 1b: Authenticated Proxy with Android HTTP Bridge

Android system proxy supports HTTP CONNECT. If your provider gives SOCKS5 for Python-side checks but Android Chrome must use a local HTTP bridge, pass both values:

```python
from damru import AsyncDamru

async with AsyncDamru(
    device="pixel_8_pro",
    proxy="socks5://user:pass@proxy.example:824",
    http_proxy="172.17.0.1:18888",
) as browser:
    page = await browser.new_page()
    await page.goto("https://demo.fingerprint.com/playground")
```

Damru resolves timezone and locale through `http_proxy` because that is the route Chrome actually uses. Do not set `timezone` or `locale` manually unless they match the current proxy exit.

### Example 2: Synchronous Usage

If you prefer synchronous code, Damru provides a blocking wrapper:

```python
from damru import Damru

def run_sync():
    with Damru(device="pixel_8_pro") as browser:
        page = browser.new_page()
        page.goto("https://bot.sannysoft.com/")
        page.wait_for_timeout(5000)
        page.screenshot(path="sannysoft.png")
        print("Passed Sannysoft!")

if __name__ == "__main__":
    run_sync()
```

### Example 3: Scaling Up with Connection Pooling

Scraping thousands of pages Damru provides a native Pool manager to run operations concurrently across multiple Docker containers.

```python
from damru import DamruPoolSync

proxies = [
    "socks5://proxy1:1080",
    "socks5://proxy2:1080",
    "socks5://proxy3:1080"
]

with DamruPoolSync(mode="auto", max_devices=3, proxies=proxies) as pool:
    for i in range(3):
        with pool.session() as context:
            page = context.new_page()
            page.goto("https://example.com/api/scrape_target")
            print(f"Worker {i} finished scraping: {page.title()}")
```

---

## Testing Your Setup

Damru ships with a comprehensive benchmark suite. Run it to ensure your setup is truly undetectable.

```bash
# Run all benchmark tests on a random device
python -m damru benchmark --device random

# Run specific tests with a proxy
python -m damru benchmark --device samsung_galaxy_s24_ultra --proxy socks5://ip:port --tests creepjs cloudflare
```

---

## The "Big Plan" (Roadmap)

We are aggressively building Damru into a fully autonomous infrastructure tool. Check `docs/AUTOMATION_GAPS_PLAN.md` for details.

*   [x] **`damru setup` CLI**: Single-command configuration plus Linux/WSL dependency setup.
*   [x] **Automated Health Checks**: Verification of ADB, Docker, binderfs, Chrome APKs, and Playwright patches.
*   [x] **Manual Viewer Tools**: Optional screenshots, video recording, and scrcpy live viewer.
*   [ ] **Auto Image Management**: Damru will dynamically bake "Damru-Ready" Docker images natively.
*   [ ] **Mass Orchestration**: Expanding `DamruPool` for Kubernetes/Swarm deployment.

---

## Frequently Asked Questions

### 1. Does Damru support physical Android devices
**No.** Damru is designed strictly for containerized environments (Redroid). Its low-level OS patches, `resetprop` logic, and binary driver injections are optimized for Redroid's kernel and filesystem. **Do not attempt to use Damru on your personal phone.** If you use a spare rooted device, you do so entirely at your own risk.

### 2. Can I use MuMu Player instead of Docker
MuMu Player support is currently an **experimental, unfinished, and non-functional beta feature**. While the code structure for it exists, we highly recommend using **Redroid (Docker)** for any production or serious research work.

### 3. Why is the .tar image so large
The `damru-redroid-latest.tar` image is a full Android 14 operating system export. The current test artifact is about 915 MB as a Docker tarball and expands to a larger Docker image after `docker load`. It includes pre-installed Chrome, TTS assets, custom fonts, and pre-patched binary drivers for faster deployment.

### 4. Does Damru work on native Linux
**Ubuntu 24.04 LTS is the only officially supported native Linux target today.** Other distributions may run Docker, but Damru Redroid reliability depends on kernel binderfs and container networking behavior. Debian 13 was tested and is not supported yet because its stock kernel did not provide the binderfs support needed for reliable multi-container Redroid.

### 5. Why "Zero JS Injection"
Standard stealth tools are caught by anti-bots because their JavaScript injections leave traces (timing, prototype pollution). Damru lies from the outside-in (OS, Binary, and Protocol levels), making it mathematically invisible to scripts.

---

## Acknowledgments & Credits

Damru is built on the shoulders of giants. We would like to credit the following projects and technologies that make this framework possible:

*   **[redroid](https://github.com/remote-android/redroid-doc)**: The core GPU-accelerated Android-in-Container solution that provides our high-performance mobile environment.
*   **[Playwright](https://playwright.dev/)**: The incredible browser automation library that serves as our high-level API.
*   **[Chromium](https://www.chromium.org/Home)**: The world-class browser engine we patch and automate.
*   **[Android Open Source Project (AOSP)](https://source.android.com/)**: For the robust operating system foundation.
*   **[Chrome DevTools Protocol (CDP)](https://chromedevtools.github.io/devtools-protocol/)**: The low-level protocol that allows us to bypass JavaScript-based fingerprinting.
*   **[Magisk](https://github.com/topjohnwu/Magisk)**: For the inspiration behind the `resetprop` logic used in our system property spoofing.
*   **[curl_cffi](https://github.com/yifeikong/curl_cffi)**: For providing the TLS impersonation capabilities used in our edge-layer bypasses.
*   **[Docker](https://www.docker.com/)**: For the containerization infrastructure that enables scalable automation pools.

---

## License & Fork Policy

Damru is distributed under the **PolyForm Noncommercial License 1.0.0**. Personal, educational, and noncommercial research use is allowed. Commercial use, hosted services, paid automation, paid scraping, paid botting, managed traffic operations, and SaaS use require a separate written commercial license.

This policy applies to the whole Damru project: source code, native code, Python modules, CLI code, docs, examples, tests, configs, package metadata, release artifacts, screenshots, videos, and substantial derived work. Public forks, mirrors, source copies, README copies, package copies, release copies, asset copies, and substantial reposts must preserve the license, credits, and attribution. GitHub copies should use GitHub's fork feature where possible. Separate repositories must put clear top-level attribution (`Based on Damru by akwin1234`) and an `Unofficial fork/mirror` notice near the top of the README. Rebranding Damru source, hiding Damru origin, removing attribution, or using the `damru` name in a confusing official-looking copy is not allowed by the project policy. See [LEGAL.md](LEGAL.md) for the full fork, copy, attribution, and commercial-use policy.

Damru is public source code, not public domain. Copied or modified code, documentation, examples, tests, package metadata, proof assets, or releases remain subject to Damru's license and attribution requirements.

---

## Mandatory Legal Disclaimer & Ethical Use Notice

**IMPORTANT: READ CAREFULLY BEFORE PROCEEDING**

Damru (the "Software") is developed and distributed strictly for **educational purposes, ethical security research, and authorized academic study**. By using this Software, you acknowledge and agree to the following terms:

### 1. Educational and Research Intent
Any examples provided within this repository-including but not limited to the bypassing of **Cloudflare, CreepJS, or BrowserScan**-are presented solely as theoretical demonstrations of browser fingerprinting vulnerabilities. These "bypasses" are intended for use against systems you own or have explicit, written permission to test. They are designed to help security professionals and developers understand how to improve their own defensive measures.

### 2. No Warranty and Limitation of Liability
The Software is provided **"AS IS"**, without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and non-infringement. In no event shall the authors, contributors, or copyright holders be liable for any claim, damages, or other liability, whether in an action of contract, tort, or otherwise, arising from, out of, or in connection with the Software or the use or other dealings in the Software.

### 3. Compliance with Laws and Terms of Service (ToS)
The user assumes **full and sole responsibility** for ensuring that their use of Damru complies with all applicable local, state, national, and international laws, including but not limited to the **Computer Fraud and Abuse Act (CFAA)**. 
*   **Terms of Service:** Bypassing security measures or anti-bot protections often violates the target website's Terms of Service. 
*   **Unauthorized Access:** Unauthorized scraping or automated interaction with third-party systems may result in civil or criminal penalties.
*   **Ethics:** Users must not use this tool to facilitate malicious activity, data theft, credential stuffing, or any form of service disruption.

### 4. Risk Acknowledgment
Using automation frameworks against high-security systems carries inherent risks, including IP blacklisting, account termination, and potential legal action from service providers. **The authors do not condone, support, or encourage the illegal or unethical use of this Software.**

### 5. Commercial and Business Use Restriction
In accordance with the **PolyForm Noncommercial License 1.0.0**, all commercial and business use of this Software is strictly prohibited. This includes, but is not limited to, use by for-profit entities, use in support of commercial services, or any activity directed toward monetary compensation. The Software is licensed exclusively for personal, educational, and non-commercial research purposes.
