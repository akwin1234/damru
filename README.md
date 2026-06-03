<div align="center">
  <img src="logo.svg" alt="Damru" width="148" height="148">

  # Damru

  **Real Android browser automation. Native fingerprints. Redroid scale.**

  Damru runs Android Chrome/WebView inside Redroid containers and controls the browser from below the JavaScript layer: Android props, native hooks, Chrome assets, CDP, display density, network policy, and worker targets.

  <br>

  [![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
  [![Host](https://img.shields.io/badge/Host-Ubuntu%2024.04%20%7C%20WSL2-24292f.svg?style=for-the-badge&logo=ubuntu&logoColor=white)](#supported-hosts)
  [![License](https://img.shields.io/badge/License-PolyForm%20Noncommercial-red.svg?style=for-the-badge)](LICENSE)

  <a href="docs/PYTHON_API.md">Python API</a>
  &nbsp;|&nbsp;
  <a href="docs/PROOF.md">Proof</a>
  &nbsp;|&nbsp;
  <a href="docs/VIEWER.md">Viewer</a>
  &nbsp;|&nbsp;
  <a href="docs/WSL_KERNEL.md">WSL Kernel</a>
  &nbsp;|&nbsp;
  <a href="https://discord.gg/GsxFdjdrT">Discord</a>
</div>

---

## The Short Version

Desktop stealth browsers pretend to be mobile. Damru runs a real Android browser and changes the environment around it.

Instead of fragile `Object.defineProperty` patches, Damru works through Android system properties, native memory hooks, GPU string patching, Chrome/WebView asset control, CDP overrides, worker auto-attach, realistic device profiles, and Redroid container orchestration.

> Beta notice: Damru is verified on the supported Ubuntu paths below, but Android containers are kernel-sensitive. Use the documented environment for the smooth path.

## Supported Hosts

| Host | Status | Notes |
| --- | --- | --- |
| Ubuntu 24.04 LTS native/VPS | Supported | Best server path. Docker bridge/NAT validated. |
| Ubuntu 24.04 WSL2 | Supported | Requires Damru's bundled WSL kernel for Redroid + Docker NAT. |
| Debian 13 | Not supported yet | Stock VPS kernel tested without required binderfs support. |
| Ubuntu 25/26 | Not supported yet | New OS labels can break Playwright dependency paths. |
| Native Windows Docker | Not supported | Redroid is Linux-only. Use WSL2. |
| Physical Android phones | Not supported | Damru is designed for disposable Redroid containers. |
| MuMu Player | Experimental | Present in code, not recommended for real work. |

## Why It Exists

Modern detection looks past user agents. It checks workers, memory, GPU, display density, voices, TLS behavior, network leaks, timezone, language, Android build props, and browser internals.

Damru's goal is simple: make automation look like a coherent Android device from the OS up.

## Core Capabilities

| Layer | What Damru Controls |
| --- | --- |
| Android identity | Model, build fingerprint, SDK props, screen size, density, battery, network state. |
| Browser engine | Hardware concurrency, touch, locale, timezone, client hints, worker targets. |
| Native runtime | Memory spoofing through native preload, GPU/vendor string patching, Chrome flags. |
| Assets | Chrome/WebView versions, TTS engines, voices, fonts, resetprop support assets. |
| Networking | Proxy-aware locale/timezone, WebRTC leak controls, Android/Docker routing fixes. |
| Operations | Setup, health checks, WSL repair, screenshots, video, scrcpy viewer, pools. |

## Install

Use Ubuntu 24.04, either native Linux/VPS or Ubuntu inside WSL2.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install git+https://github.com/akwin1234/damru.git

python -m damru setup -y
python -m damru check-env --viewer
```

### WSL2 First Run

Use a fresh/dedicated Ubuntu WSL distro when possible. Damru's WSL kernel installer updates `%USERPROFILE%\.wslconfig`, which affects how WSL boots.

```powershell
python -m damru wsl-kernel install --yes --confirm-wsl-kernel-risk
wsl --shutdown
```

Then reopen Ubuntu:

```bash
python -m damru fix-wsl
python -m damru check-env --viewer
```

## Requirements

| Workload | CPU | RAM | Disk |
| --- | --- | --- | --- |
| 1 Redroid worker | 2 vCPU | 4 GB | 15 GB free |
| 2 Redroid workers | 4 vCPU | 8 GB | 25-30 GB free |
| Each extra worker | +2 vCPU | +2-3 GB | +5-8 GB |
| Comfortable WSL2 host | 4+ vCPU | 8-16 GB | 40+ GB WSL disk |

## Proof

Fresh Ubuntu and WSL verification notes live in [docs/PROOF.md](docs/PROOF.md). The proof set includes Android screen recording plus sanitized screenshots for Amazon, Foot Locker/DataDome, Fingerprint Pro, Sannysoft, and CreepJS.

| Fingerprint Pro | CreepJS |
| :---: | :---: |
| <img src="docs/assets/proof/sites/fingerprint-pro.png" alt="Fingerprint Pro proof" width="330"> | <img src="docs/assets/proof/sites/creepjs.png" alt="CreepJS proof" width="330"> |

| Sannysoft | DataDome Target |
| :---: | :---: |
| <img src="docs/assets/proof/sites/sannysoft.png" alt="Sannysoft proof" width="330"> | <img src="docs/assets/proof/sites/datadome-footlocker.png" alt="DataDome proof" width="330"> |

## Basic Usage

```python
import asyncio
from damru import AsyncDamru

async def main():
    async with AsyncDamru(device="pixel_8_pro") as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        print(await page.title())

asyncio.run(main())
```

## Pool Usage

```python
import asyncio
from damru import DamruPool

async def main():
    pool = DamruPool(size=2, mode="auto")
    async with pool:
        async def visit(worker):
            page = await worker.new_page()
            await page.goto("https://example.com")
            return await page.title()

        print(await asyncio.gather(*(visit(worker) for worker in pool.workers)))

asyncio.run(main())
```

Full API: [docs/PYTHON_API.md](docs/PYTHON_API.md)

## CLI Reference

| Command | Purpose |
| --- | --- |
| `python -m damru setup -y` | First-run config and dependency setup. |
| `python -m damru install-deps -y` | Install Docker, ADB, Linux/WSL deps, Playwright patch. |
| `python -m damru check-env --viewer` | Verify Docker, binderfs, image/assets, viewer tools. |
| `python -m damru fix-wsl` | Repair common WSL Docker, binderfs, netfilter, DNS state. |
| `python -m damru wsl-kernel status` | Show bundled WSL kernel install state. |
| `python -m damru wsl-kernel install --yes --confirm-wsl-kernel-risk` | Install Damru's WSL kernel. |
| `python -m damru install-apks --download` | Download Chrome/WebView/TTS APK assets. |
| `python -m damru install-image --download` | Download/load baked Redroid image when available. |
| `python -m damru devices` | List built-in Android profiles. |
| `python -m damru screenshot --serial <serial>` | Capture Android screen. |
| `python -m damru record --serial <serial>` | Record Android screen video. |
| `python -m damru view --serial <serial>` | Open scrcpy live viewer. |

## Viewer Mode

Damru can be used like a disposable Android emulator window when `scrcpy` is installed.

```bash
python -m damru install-viewer -y
python -m damru view --serial wsl:127.0.0.1:5600
```

Use `--no-control` for watch-only mode. See [docs/VIEWER.md](docs/VIEWER.md).

## Assets and Images

Damru can run from a baked `damru-redroid:latest` Docker image or prepare raw Redroid with the APK asset bundle.

| Asset | Link |
| --- | --- |
| Baked Redroid image | https://drive.google.com/file/d/1AzSTOlGpSfqHB-F-Yty2JqbOEMlgFT5F/view?usp=sharing |
| Manual APK bundle | https://drive.google.com/file/d/1xh5Z-LXqUIEjO08KKjhaB_89KS2pBWZq/view?usp=sharing |

Automatic APK setup stores assets under `/home/damru/chrome-apks` on Linux/WSL. The bundle contains Chrome, Trichrome WebView, TTS engines, and local resetprop support assets for raw/unbaked Redroid.

## WSL2 Kernel

Damru ships a verified WSL2 kernel artifact for Redroid plus Docker bridge/NAT support.

| Resource | Link |
| --- | --- |
| Source fork | https://github.com/akwin1234/damru-wsl2-kernel-redroid-natfix-source |
| Compiled release | https://github.com/akwin1234/damru-wsl2-kernel-redroid-natfix-source/releases/tag/v6.6.114.1-damru-redroid-natfix-20260602 |

Details: [docs/WSL_KERNEL.md](docs/WSL_KERNEL.md)

## Documentation Map

| Document | What it covers |
| --- | --- |
| [Python API](docs/PYTHON_API.md) | `AsyncDamru`, sync wrapper, pools, config, profiles. |
| [Proof](docs/PROOF.md) | Verification notes and proof assets. |
| [Device Profiles](docs/DEVICE_PROFILES.md) | Built-in Android device profile list. |
| [Viewer](docs/VIEWER.md) | Screenshot, video, and scrcpy workflows. |
| [WSL Kernel](docs/WSL_KERNEL.md) | WSL custom kernel, Docker NAT, binderfs notes. |
| [Automation Roadmap](docs/AUTOMATION_GAPS_PLAN.md) | Remaining infrastructure work. |

## Project Layout

```text
damru/
  async_core.py      async browser entry point
  core.py            sync wrapper
  pool.py            multi-container orchestration
  devices.py         Android profile database
  chrome.py          Chrome lifecycle and preferences
  root.py            Android/root/native patching
native/              C hooks and native spoofing source
docs/                user and developer docs
chrome-apks/         local APK bundle layout docs
scripts/             image/proof/helper scripts
```

## License and Copy Policy

Damru is distributed under the [PolyForm Noncommercial License 1.0.0](LICENSE). Commercial use, hosted services, paid automation, paid scraping, managed traffic operations, SaaS use, and customer work require a separate written commercial license.

This policy applies to the whole Damru project: source code, native code, Python modules, CLI code, docs, examples, tests, configs, package metadata, release artifacts, screenshots, videos, proof assets, and substantial derived work. Public forks, mirrors, source copies, README copies, package copies, release copies, asset copies, and substantial reposts must preserve the license, credits, and attribution.

Separate repositories must put clear top-level attribution (`Based on Damru by akwin1234`) and an `Unofficial fork/mirror` notice near the top of the README. See [LEGAL.md](LEGAL.md).

## Responsible Use

Damru is for educational research, authorized security testing, and defensive study. Users are solely responsible for complying with laws and target terms of service. Do not use Damru for credential stuffing, data theft, service disruption, unauthorized access, or malicious activity.

The software is provided as-is, without warranty. The maintainers are not liable for damage, account loss, blacklisting, legal claims, or misuse.
