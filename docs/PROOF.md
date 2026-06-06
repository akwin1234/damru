# Damru Verification Proof

Date: 2026-06-04

This file records sanitized local verification results. It intentionally does not include private proxy credentials, local usernames, local IP addresses, SSH details, or machine-specific secrets.

## WSL2 Redroid

Validated on a disposable fresh-loop WSL2 distro using the bundled Damru WSL kernel path. The long-lived WSL distro that stores kernel source/build trees was not touched.

Commands verified:

```powershell
python -m damru install-deps -y
python -m damru fix-wsl
python -m damru install-viewer -y
python -m damru check-env --viewer
python -m damru check preflight --json --timeout 3
python -m damru ui-worker start --count 2
python -m damru quick-check --serial 127.0.0.1:5900 --output /tmp/damru-wsl-quick-5900.json
python -m damru quick-check --serial 127.0.0.1:5901 --output /tmp/damru-wsl-quick-5901.json
python -m damru open-url --serial 127.0.0.1:5900 --url https://example.com
```

Result:

- Docker daemon inside WSL: OK
- Docker bridge/NAT networking: OK
- Docker bridge container internet: OK
- binderfs mounted at `/dev/binderfs`: OK
- Chrome APK discovery: OK
- Redroid image available: OK
- scrcpy viewer command: OK
- Cross-distro WSL Redroid conflict: none detected
- Preflight after worker start: `ok=true`, `fail=0`
- Fresh two-worker quick checks: OK on both workers

Browser smoke:

- Two Redroid workers booted, reported Chrome installed, DNS present, locale present, timezone present, and Android boot complete.
- `open-url` loaded `https://example.com` in Android Chrome on the first worker.

## Native Ubuntu/Linux

Validated on an Ubuntu 24.04 VPS after removing Docker packages/state in earlier loops and recreating temporary Python virtual environments for current-tree smoke checks.

Reset/install flow verified:

```bash
python3 -m venv /tmp/damru-linux-proof/venv
/tmp/damru-linux-proof/venv/bin/python -m pip install -U pip setuptools wheel
/tmp/damru-linux-proof/venv/bin/python -m pip install -e .[dev]
/tmp/damru-linux-proof/venv/bin/python -m damru install-deps -y
/tmp/damru-linux-proof/venv/bin/python -m damru check-env --viewer
/tmp/damru-linux-proof/venv/bin/python -m pytest -q
python -m damru check preflight --json --timeout 3
python -m damru ui-worker start --count 2
python -m damru quick-check --serial 127.0.0.1:5600 --output /tmp/damru-vps-quick-5600.json
python -m damru quick-check --serial 127.0.0.1:5601 --output /tmp/damru-vps-quick-5601.json
python -m damru open-url --serial 127.0.0.1:5600 --url https://example.com
```

Result:

- Docker package reinstall from `install-deps`: OK
- Native Linux iptables backend: nft selected
- Docker bridge/NAT networking: OK
- binderfs mounted at `/dev/binderfs`: OK
- Damru Playwright `crPage.js` patch: OK
- Unit test suite: `29 passed, 13 skipped`
- `scrcpy`: optional warning only when not installed
- Preflight: `ok=true`, `fail=0`

Browser smoke:

- Single-worker `AsyncDamru` session loaded `https://example.com` and reported Android UA plus `navigator.hardwareConcurrency == 8`.
- Two-worker `DamruPool(mode="auto", max_devices=2)` loaded `https://example.com` in both workers.
- Both native Linux workers reported `navigator.hardwareConcurrency == 8`.
- Latest two-worker `quick-check` reported ADB online, boot completed, Chrome installed, DNS present, fingerprint present, locale present, model present, and timezone present for both workers.

## External Stealth Benchmark

On 2026-06-06, Damru Redroid was also run against the external `techinz/browsers-benchmark` project. The sanitized report records a 10/10 proxy-mode bypass run across Google Search, Cloudflare, DataDome, Amazon, Ticketmaster/Imperva, Akamai, PerimeterX/HUMAN, Kasada, and Reddit.

Report: [BROWSERS_BENCHMARK_REPORT.md](BROWSERS_BENCHMARK_REPORT.md)

Machine-readable sanitized result: [assets/benchmark/browsers-benchmark-final-clean.json](assets/benchmark/browsers-benchmark-final-clean.json)

Proof assets from the native Ubuntu VPS run with a US proxy are stored in [`docs/assets/proof/`](assets/proof/):

- [Example.com screenshot](assets/proof/ubuntu-example-page.png)
- [Android screen recording](assets/proof/ubuntu-redroid-proof.mp4)
- [Sanitized proof metadata](assets/proof/ubuntu-proof.json)

Individual viewport proof captures are stored in [`docs/assets/proof/sites/`](assets/proof/sites/):

- [Example.com](assets/proof/sites/example.png)
- [Amazon](assets/proof/sites/amazon.png)
- [Foot Locker / DataDome target](assets/proof/sites/datadome-footlocker.png)
- [Fingerprint Pro Playground](assets/proof/sites/fingerprint-pro.png)
- [Sannysoft](assets/proof/sites/sannysoft.png)
- [CreepJS](assets/proof/sites/creepjs.png)
- [Sanitized site metadata](assets/proof/sites/proof-sites.json)

Recorded proof values:

```json
{
  "example_title": "Example Domain",
  "android_user_agent": true,
  "hardwareConcurrency": 8,
  "maxTouchPoints": 5,
  "browser_timezone": "America/New_York",
  "proxy_country": "US",
  "proxy_timezone": "America/New_York"
}
```

The individual site proof pass used a fixed Pixel 8 Pro Android 14 profile for repeatability. Targets loaded successfully through a runtime-only proxy bridge. The metadata records Android Chrome UA, `navigator.hardwareConcurrency == 8`, `navigator.deviceMemory == 8`, and `navigator.maxTouchPoints == 5`. Timezone and locale are resolved from the active proxy exit at session start; the latest Fingerprint Pro proof used a Philippine exit with `Asia/Manila` and `en-PH`, returned `Bot: Not detected`, `VPN: Not detected`, and showed confidence score `1`. CreepJS reported `0% headless`, `0% stealth`, and WebRTC host/STUN connections blocked.

## APK Rotation Validation

The local APK matrix validated 19 Chrome split-APK folders from `143.0.7499.52` through `148.0.7778.217`. Each folder was tested for Trichrome/Chrome split installation, exact `versionName`, `quick-check`, explicit Chrome launch, PID alive, DNS ping, and a CDP JavaScript probe covering UA, memory, cores, timezone, languages, and WebGL API availability.

Representative full spoof probes passed for Chrome `146.0.7680.177`, `147.0.7727.138`, and `148.0.7778.217`, including Android UA version matching, `navigator.webdriver == false`, `navigator.deviceMemory == 8`, `navigator.hardwareConcurrency == 8`, proxy timezone/language application, GPU spoofing, TTS warm-up, and normal page load.

Chrome 149 APKs are not included yet because tested public bundles were missing the required English/x86/x86_64 split layout.

## Fixed During Verification

- Added `python -m damru check preflight`, a fast read-only readiness check with JSON, strict, no-ADB, timeout, resource, port, WSL kernel, image, APK, Docker, ADB, binderfs, and config checks.
- Fixed WSL `wsl:` ADB serial handling when the CLI is already running inside Linux/WSL.
- Changed WSL preflight to detect actual binderfs kernel support from `/proc/config.gz` or `/boot/config-*` instead of relying on kernel filename guesses.
- Treated supported-but-unmounted WSL binderfs as a warning in default preflight because `fix-wsl` or worker startup can mount it; strict mode still fails the warning.
- Added a fresh Redroid fallback locale (`en-US`) only when Android has no locale yet, preventing false `locale_present=false` quick-check failures on raw fresh workers.

- Native Linux no longer forces `iptables-legacy`; it selects `iptables-nft` so Docker's NAT chain exists in the backend Docker uses.
- Docker is restarted after backend selection during setup/repair.
- Python 3.14 editable installs no longer use `SETUPTOOLS_USE_DISTUTILS=stdlib`.
- `context.new_page()` now normalizes Android Chrome tabs to `about:blank` before user navigation.
- Page-level CDP auto-attach no longer pauses new page targets; worker overrides remain handled by raw browser CDP auto-attach.
- `context.new_page()` applies touch emulation after creating each page, so `navigator.maxTouchPoints` remains `5` on new pages.
- Authenticated SOCKS proof runs use a runtime-only local HTTP CONNECT bridge for Android system proxy compatibility; credentials are not stored in source or proof files.
- Proxy timezone/locale now resolves through the same Android HTTP proxy path Chrome uses. This prevents rotating residential proxies from using one IP/timezone for Python GeoIP and a different IP/timezone inside Chrome.

## Asset Hygiene

The proof run used a private proxy only at runtime. The committed screenshots, video, and JSON do not contain proxy credentials, SSH credentials, local usernames, local IP addresses, or VPS connection details.
