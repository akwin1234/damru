<div align="center">
  <img src="logo.svg" alt="Damru Logo" width="200" height="200">
  <h1>Damru</h1>
  <p><strong>The Apex Predator of Android Browser Automation</strong></p>
  <p>High-performance, ultra-stealth browser automation framework designed for web scraping and botting at scale.</p>

  [![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
  [![Playwright](https://img.shields.io/badge/playwright-1.40%2B-green.svg?style=for-the-badge&logo=playwright&logoColor=white)](https://playwright.dev/python/)
  [![Platform](https://img.shields.io/badge/Platform-WSL2%20%7C%20Linux-lightgrey.svg?style=for-the-badge&logo=linux&logoColor=white)]()
  [![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/License-PolyForm%20Noncommercial%201.0.0-red.svg?style=for-the-badge)](https://polyformproject.org/licenses/noncommercial/1.0.0)
</div>

<br/>

> **Damru** leverages rooted Android emulators (like Redroid in Docker) via ADB to achieve undetectable automation. Whether you are bypassing modern WAFs (like Cloudflare Turnstile) or scoring 100% on CreepJS, Damru provides an impenetrable disguise.

> [!WARNING]
> **Project Status: Alpha**
> This project is currently in an **Alpha** state. While it has been verified as 100% stable and fully functional on the local systems of the developers who built it, it requires further testing across diverse environments and hardware configurations. We welcome feedback and issue reports!

---

## 📑 Table of Contents

- [✨ Core Features](#-core-features)
- [🥊 Why Damru is Better](#-why-damru-is-better-than-the-rest)
- [📊 Proof of Stealth: Benchmarks](#-proof-of-stealth-benchmark-comparisons)
- [🧠 Architecture: The 8 Layers of Stealth](#-architecture-the-8-layers-of-zero-js-stealth)
- [📂 Project Structure](#-project-structure)
- [🐍 Python API Documentation](docs/PYTHON_API.md)
- [💾 Download Custom OS Image](#-download-custom-os-image)
- [🚀 Quickstart Guide](#-first-time-user-deployment-guide-wsl2--linux)
- [💻 Usage & Examples](#-usage--examples)
- [📡 Redroid vs MuMu Player](#-platform-recommendation-redroid-vs-mumu)
- [🧪 Testing](#-testing-your-setup)
- [🗺️ Roadmap](#️-the-big-plan-roadmap)
- [❓ FAQ](#-frequently-asked-questions)
- [⚖️ Legal Disclaimer](#️-mandatory-legal-disclaimer--ethical-use-notice)

---

## 📡 Platform Recommendation: Redroid vs MuMu

While Damru technically lists multiple environments, **Redroid (Docker)** is the only officially supported and functional path.

| Platform | Status | Stealth Level | Stability | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| **Redroid (Docker)** | **Production-Ready** | **Absolute** | **High** | **Highly Recommended** |
| **MuMu Player** | **Unfinished / Beta** | Moderate | Low | **Non-functional / Not Recommended** |
| **Physical Devices** | **NOT SUPPORTED** | N/A | N/A | **DO NOT USE** |

> [!CAUTION]
> **Physical Device Warning**
> Damru is designed strictly for containerized environments (Redroid). **It does not support physical Android devices.** Do not attempt to run Damru against your personal phone. If you choose to use a spare rooted device, you do so at your own risk. Damru's low-level OS patches and binary injections may brick or destabilize physical hardware.

**Why Redroid?**
Damru's most advanced stealth layers—including native GPU binary patching and OS-level `iptables` hooks—are optimized for the Redroid kernel. It provides a more stable environment for multi-container pools and is significantly more undetectable by modern anti-bot heuristics. MuMu Player support is currently an experimental, unfinished, and non-functional beta feature.

---

## ✨ Core Features

*   🚫 **Zero JS Injection**: All spoofing is executed at the OS, Binary, and CDP levels. No brittle `Object.defineProperty` hacks.
*   📱 **Massive Device Database**: Built-in profiles for 32+ real Android devices (Samsung, Pixel, Xiaomi, etc.) with perfect hardware specifications.
*   📐 **Display & Resolution Spoofing**: Natively overrides screen dimensions and DPI via Android's Window Manager (`wm size/density`) for physical accuracy.
*   🧪 **TLS/JA3 Randomization**: Generates ~184 unique TLS fingerprints from a single binary by dynamically toggling cipher suites and experimental flags (e.g., PostQuantumKyber).
*   🎭 **Font & Voice Randomization**: Installs custom TTS engines and extra system fonts, randomizing them per session to defeat advanced font/voice fingerprinting.
*   🔋 **Hardware Status Spoofing**: Fakes battery levels, charging status, and even audio sample rates (48kHz) to mirror real mobile hardware behavior.
*   ⚙️ **Hardware Overrides**: Spoofs CPU cores, RAM (via syscall hooks), and touch points (e.g., 5-point touch) directly via native OS patching and CDP.
*   📶 **Network & DNS Stealth**: Faithfully fakes mobile network conditions and forces resolution through proxy-level ISP DNS to pass "DNS Leak" and "Targeted DNS" checks.
*   🎯 **CDN & Anti-Bot Bypass**: Out-of-the-box native bypass for modern WAFs (like Cloudflare Turnstile, CDN TLS) and advanced behavioral detection systems.

---

## 🥊 Why Damru is Better Than the Rest

We spent significant time modifying and testing popular desktop-first solutions like **Camoufox**, **Fingerprinting Chromium**, and various Playwright stealth patches to work on mobile—but nothing reached the level of stability and undetectability achieved by this project. 

The botting landscape is littered with tools that *used* to work: `puppeteer-stealth`, `undetected-chromedriver`, and various anti-detect browsers. Here is why they fail today, and why Damru succeeds:

| Feature | Legacy Tools (`puppeteer-stealth`, etc.) | Damru |
| :--- | :--- | :--- |
| **Spoofing Method** | **JavaScript Injection** (`Object.defineProperty`). Leaves massive detectable traces. | **Native Overrides**. Modifies C++ engine via CDP, patches binaries, edits OS props. |
| **JS Leakage** | Anti-bots check `.toString()` on functions. Injected JS is caught instantly. | **Zero JS Injected**. Functions remain entirely native. |
| **Hardware Emulation** | Fakes `navigator.hardwareConcurrency` via JS. Fails worker tests. | **C++ CDP Override**. Changes the value at the Chromium engine level. Passes all tests. |
| **GPU Fingerprint** | WebGL spoofing via JS wrapping. Leaks real GPU via extensions. | **Binary Patching**. Physically patches the `.so` Vulkan/GLES driver files on Android. |
| **Physical Memory** | Fakes `deviceMemory` via JS. Easily caught by timing or syscall checks. | **Syscall Hooks**. Uses `libfakemem.so` to intercept `sysinfo` calls via `LD_PRELOAD`. |
| **Worker Stealth** | Workers often leak the real hardware concurrency of the host. | **Worker Interception**. Uses CDP `Target.setAutoAttach` to force overrides on all Threads/Workers. |
| **TLS/JA3 Hash** | Fixed TLS fingerprint based on the Chrome binary version. | **TLS Randomization**. Produces ~184 unique JA3 hashes via dynamic cipher blacklisting. |
| **Screen Dimensions** | Viewing desktop Chrome as mobile via viewport scaling (leaks real screen size). | **OS-Level Display**. Modifies Android `wm size/density` natively. |
| **Network Identity** | Frequently leaks WebRTC private IPs and IPv6 fingerprints. | **OS-Level IP Tables**. Blocks WebRTC leaks and IPv6 at the Android kernel level. |
| **Mobile Emulation** | Desktop Chrome pretending to be mobile via viewport scaling. | **Real Android OS**. Runs inside Redroid (Android 14) or MuMu Player. It *is* mobile. |

### 📊 Proof of Stealth: Benchmark Comparisons

We regularly test Damru against the hardest anti-bot systems in the industry. These results are reproducible using the built-in benchmark suite (`python -m damru.benchmark`) or the comprehensive functional test suite (`python example.py`).

| Target Anti-Bot | Standard Playwright | Typical Stealth Plugins | Damru |
| :--- | :--- | :--- | :--- |
| **CreepJS (Trust)** | 0% (Trash) | ~45% (High Lies) | **85%+ (0% Lies, Top Stealth)** |
| **BrowserScan** | Fails Hardware/OS | Fails WebGL/Fonts | **Passes 100% OS/Hardware/WebRTC** |
| **Sannysoft** | Fails | Passes | **Passes 100%** |
| **Cloudflare Turnstile**| Blocked ("Just a moment")| Frequently Blocked | **Bypassed Natively** |
| **Other Enterprise WAFs**| Blocked | Frequently Blocked | **Bypassed Natively** |

*Note: Damru is capable of bypassing many other advanced detection systems not listed here. As an educational project, we focus on demonstrating these core industry-standard benchmarks.*

---

## 🧠 Architecture: The 8 Layers of "Zero JS" Stealth

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

## 📂 Project Structure

Damru is organized into specialized modules to maintain the separation between high-level Python automation and low-level system spoofing.

```text
damru-project/
├── damru/                 # 🐍 Core Framework (Python)
│   ├── async_core.py      # Async entry points (AsyncDamru)
│   ├── core.py            # Sync entry points (Damru)
│   ├── root.py            # OS/Binary patching logic (resetprop/iptables/display)
│   ├── devices.py         # 32+ Real Device Specifications Database
│   ├── chrome.py          # Browser lifecycle & Preferences patching
│   ├── bypass.py          # CDN TLS/WAF edge-layer TLS impersonation
│   └── pool.py            # Multi-container orchestration (DamruPool)
├── native/                # ⚙️ Native Binary Hooks (C source)
│   ├── vulkan_layer.c     # Vulkan C++ string spoofing binary
│   └── libfakemem.c       # Physical RAM spoofing via sysconf hooks
├── tests/                 # 🧪 Stealth & Stability Benchmarks
│   ├── benchmark_auto.py  # Automated Anti-Bot probe
│   └── test_stealth.py    # Unit tests for fingerprinting integrity
├── chrome-apks/           # 📦 Pre-validated Mobile Assets
│   ├── espeak.apk         # TTS engines for Voice fingerprinting
│   └── 145.x/             # Specific Chrome/WebView versions
├── docs/                  # 📄 Roadmaps & Infrastructure Plans
├── scripts/               # 🛠️ Maintenance & Image Baking Utils
└── tools/                 # 🧰 External Debugging Tools (Magisk.apk)
```

---

## 🐍 Python API Documentation

For detailed information on how to use the Damru library programmatically, including class references, managed pooling, and advanced configuration, please see the:

👉 **[Damru Python API Reference](docs/PYTHON_API.md)**

### Quick Summary:
*   **`AsyncDamru`**: The primary entry point for asynchronous automation.
*   **`Damru`**: Synchronous wrapper for standard blocking scripts.
*   **`DamruPool`**: Orchestration for high-throughput multi-container scraping.
*   **`damru.bypass`**: Advanced TLS/JA3 impersonation for edge-layer bypasses.

---

## 💾 Download Custom OS Image

> [!IMPORTANT]
> The pre-baked Damru OS image is **2.3 GB**. Due to its size, it is hosted externally on Google Drive.

**Download the latest image here:**
👉 **[Download damru-redroid-latest.tar](https://drive.google.com/file/d/1na6YYHbpvDlaXhicg_nAKiaMFaYRN99U/view?usp=sharing)**

Once downloaded, follow **Step 3** in the Deployment Guide below to load it into Docker.

---

## 🚀 First-Time User Deployment Guide (WSL2 / Linux)

Ready to start? Damru uses **Redroid** (Android in Docker) to spin up headless mobile devices instantly. Follow this step-by-step guide to deploy Damru from scratch on Ubuntu/Debian or WSL2 (Windows Subsystem for Linux).

### Step 1: System Preparation (Linux / WSL2)

You need a Linux environment. If you are on Windows, install WSL2 (Ubuntu). Ensure your system is up to date and install `adb`:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install adb wget curl git jq -y
```

### Step 2: Install Docker & Enable Binderfs (Crucial for Redroid)

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

### 🪄 The Instant Custom OS Image

Compiling native C binaries, injecting them via ADB, applying `iptables` rules, and installing Chrome on every run is a long process. **The Instant Solution:** We provide a pre-baked OS image ([damru-redroid-latest.tar](https://drive.google.com/file/d/1na6YYHbpvDlaXhicg_nAKiaMFaYRN99U/view?usp=sharing)) where all native patches, TTS engines, and specific Chrome APKs are **already baked in**. This turns a complex 5-minute setup into an instant plug-and-play boot!

### Step 3: Instant Boot with the Custom OS (Recommended)

1.  **Load the pre-baked image**:
    
    **For WSL2 Users:** (Assuming `.tar` is in your Windows Downloads folder)
    ```bash
    docker load -i /mnt/c/Users/YourUsername/Downloads/damru-redroid-latest.tar
    ```
    
    **For Native Linux Users:**
    ```bash
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

Wait 30 seconds for Android to boot, then connect via ADB:
```bash
adb connect localhost:5555
adb devices
# You should see: localhost:5555 device
```

> [!TIP]
> **What is an ADB Serial?**
> An ADB serial is a unique identifier for your Android device. 
> - For **Redroid/Docker**, it is usually the network address: `localhost:5555` or an internal IP.
> - For **Physical Devices**, it is a hardware string like `9889d6444b49` (visible via `adb devices`).

### Step 4: Install Damru

**Option A: Direct Pip Install (Fastest)**
```bash
pip install git+https://github.com/akwin1234/damru.git
playwright install
```

#### 🛠️ Windows Installation Fix (Important)

If you are using Windows (especially Python 3.10) and encounter an `AssertionError: ...distutils\core.py` during `pip install`, you must force standard distutils. Run this in your terminal *before* installing:

```powershell
# PowerShell (Run this first!)
$env:SETUPTOOLS_USE_DISTUTILS="stdlib"

# Then run:
pip install git+https://github.com/akwin1234/damru.git
```

**Option B: Clone & Install (For Developers)**
```bash
git clone https://github.com/akwin1234/damru.git
cd damru
python3 -m venv venv
source venv/bin/activate
pip install -e .
playwright install
```

*(Magic Note: When you import Damru, it automatically patches Playwright's source code (`crPage.js`) on your system to prevent CDP target discovery leaks!)*

---

## ⚙️ Global Configuration

Damru uses a centralized configuration file located at `damru/config.py`. If you clone the repository or install it locally, you should modify these settings before running large pools or automated scripts.

> [!TIP]
> **Pre-made Configurations Available!**
> We have provided OS-specific configuration templates in the `damru/` directory to get you started faster:
> - **Windows / WSL2**: Copy `damru/config.py.windows` and rename it to `config.py`.
> - **Native Linux**: Copy `damru/config.py.linux` and rename it to `config.py`.

### 🔑 Essential Configurations

1. **WSL2 Sudo Authentication (Windows Auto-Mode)**:
   If you are running Python on Windows and orchestrating Docker containers inside WSL2, Damru needs to execute `sudo docker` commands automatically.
   ```python
   # damru/config.py
   WSL_DISTRO = "Ubuntu"
   WSL_USERNAME = "YOUR_WSL_USERNAME_HERE"
   WS_PASSWORD = "YOUR_WSL_PASSWORD_HERE"  # Required to bypass sudo prompts
   ```

2. **Chrome APK Path**:
   When not using the pre-baked `.tar` image, Damru will dynamically install Chrome onto raw Redroid instances. Point it to your APK directory.
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

### 🐋 Docker Storage Location (Crucial for Windows Users)
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

## 💻 Usage & Examples

Damru handles the heavy lifting: it connects to ADB, gains root, applies system patches, spoofs the GPU, launches Chrome, and attaches via CDP—all automatically.

### Example 1: Basic Async Usage (The Standard Way)

```python
import asyncio
from damru import AsyncDamru

async def main():
    print("Launching Damru...")
    
    # device="random" picks from our database of 32+ real Android devices.
    # proxy is used to auto-resolve Timezone and Locale!
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

Scraping thousands of pages? Damru provides a native Pool manager to run operations concurrently across multiple Docker containers.

```python
from damru import DamruPoolSync

proxies = [
    "socks5://proxy1:1080",
    "socks5://proxy2:1080",
    "socks5://proxy3:1080"
]

with DamruPoolSync(size=3, proxy_list=proxies) as pool:
    for i, context in enumerate(pool.get_contexts()):
        page = context.new_page()
        page.goto("https://example.com/api/scrape_target")
        print(f"Worker {i} finished scraping: {page.title()}")
```

---

## 🧪 Testing Your Setup

Damru ships with a comprehensive benchmark suite. Run it to ensure your setup is truly undetectable.

```bash
# Run all benchmark tests on a random device
python -m damru.benchmark --device random

# Run specific tests with a proxy
python -m damru.benchmark --device samsung_galaxy_s24_ultra --proxy socks5://ip:port --tests creepjs cloudflare
```

---

## 🗺️ The "Big Plan" (Roadmap)

We are aggressively building Damru into a fully autonomous infrastructure tool. Check `docs/AUTOMATION_GAPS_PLAN.md` for details.

*   [ ] **`damru setup` CLI**: Single-command installation for Docker and `binderfs`.
*   [ ] **Auto Image Management**: Damru will dynamically bake "Damru-Ready" Docker images natively.
*   [ ] **Automated Health Checks**: One-click verification of ADB, kernel config, and Playwright patches.
*   [ ] **Mass Orchestration**: Expanding `DamruPool` for Kubernetes/Swarm deployment.

---

## ❓ Frequently Asked Questions

### 1. Does Damru support physical Android devices?
**No.** Damru is designed strictly for containerized environments (Redroid). Its low-level OS patches, `resetprop` logic, and binary driver injections are optimized for Redroid's kernel and filesystem. **Do not attempt to use Damru on your personal phone.** If you use a spare rooted device, you do so entirely at your own risk.

### 2. Can I use MuMu Player instead of Docker?
MuMu Player support is currently an **experimental, unfinished, and non-functional beta feature**. While the code structure for it exists, we highly recommend using **Redroid (Docker)** for any production or serious research work.

### 3. Why is the .tar image so large?
The `damru-redroid-latest.tar` image (2.3 GB) is a full Android 14 operating system. It includes pre-installed Chrome, 30+ TTS voices, custom fonts, and pre-patched binary drivers to ensure instant deployment and maximum stealth.

### 4. Does Damru work on native Linux?
**Yes.** Any Docker image built in WSL2 is a standard Linux image. Damru works perfectly on native Linux (Ubuntu, Debian, etc.), provided the `binder` kernel modules are loaded.

### 5. Why "Zero JS Injection"?
Standard stealth tools are caught by anti-bots because their JavaScript injections leave traces (timing, prototype pollution). Damru lies from the outside-in (OS, Binary, and Protocol levels), making it mathematically invisible to scripts.

---

## 🙏 Acknowledgments & Credits

Damru is a **vibe-coded** project, built with a focus on rapid experimentation and deep technical intuition. We would like to credit the following projects, technologies, and AI co-pilots that made this framework possible:

*   **AI Co-Pilots**: Massive thanks to **OpenAI Codex**, **Claude Code**, and **Kimi CLI** for their instrumental assistance in research, C++ binary patching, and complex architectural orchestration.
*   **[redroid](https://github.com/remote-android/redroid-doc)**: The core GPU-accelerated Android-in-Container solution that provides our high-performance mobile environment.
*   **[Playwright](https://playwright.dev/)**: The incredible browser automation library that serves as our high-level API.
*   **[Chromium](https://www.chromium.org/Home)**: The world-class browser engine we patch and automate.
*   **[Android Open Source Project (AOSP)](https://source.android.com/)**: For the robust operating system foundation.
*   **[Chrome DevTools Protocol (CDP)](https://chromedevtools.github.io/devtools-protocol/)**: The low-level protocol that allows us to bypass JavaScript-based fingerprinting.
*   **[Magisk](https://github.com/topjohnwu/Magisk)**: For the inspiration behind the `resetprop` logic used in our system property spoofing.
*   **[curl_cffi](https://github.com/yifeikong/curl_cffi)**: For providing the TLS impersonation capabilities used in our edge-layer bypasses.
*   **[Docker](https://www.docker.com/)**: For the containerization infrastructure that enables scalable automation pools.

---

## ⚖️ Mandatory Legal Disclaimer & Ethical Use Notice

**IMPORTANT: READ CAREFULLY BEFORE PROCEEDING**

Damru (the "Software") is developed and distributed strictly for **educational purposes, ethical security research, and authorized academic study**. By using this Software, you acknowledge and agree to the following terms:

### 1. Educational and Research Intent
Any examples provided within this repository—including but not limited to the bypassing of **Cloudflare, CreepJS, or BrowserScan**—are presented solely as theoretical demonstrations of browser fingerprinting vulnerabilities. These "bypasses" are intended for use against systems you own or have explicit, written permission to test. They are designed to help security professionals and developers understand how to improve their own defensive measures.

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
