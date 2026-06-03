# Damru Verification Proof

Date: 2026-06-02

This file records sanitized local verification results. It intentionally does not include private proxy credentials, local usernames, local IP addresses, SSH details, or machine-specific secrets.

## WSL2 Redroid

Validated on a fresh-loop WSL2 distro using the bundled Damru WSL kernel path.

Commands verified:

```powershell
python -m damru install-deps -y
python -m damru fix-wsl
python -m damru install-viewer -y
python -m damru check-env --viewer
```

Result:

- Docker daemon inside WSL: OK
- Docker bridge/NAT networking: OK
- Docker bridge container internet: OK
- binderfs mounted at `/dev/binderfs`: OK
- Chrome APK discovery: OK
- Redroid image available: OK
- scrcpy viewer command: OK
- Cross-distro host-network Redroid conflict: none detected

Browser smoke:

- `AsyncDamru` single-worker session loaded `https://example.com`.
- `DamruPool(mode="auto", max_devices=2)` loaded `https://example.com` in two concurrent Redroid workers.
- Both WSL workers reported `navigator.hardwareConcurrency == 8`.

## Native Ubuntu/Linux

Validated on an Ubuntu VPS after removing Docker packages/state and recreating the Python virtual environment.

Reset/install flow verified:

```bash
python3 -m venv /tmp/damru-linux-proof/venv
/tmp/damru-linux-proof/venv/bin/python -m pip install -U pip setuptools wheel
/tmp/damru-linux-proof/venv/bin/python -m pip install -e .[dev]
/tmp/damru-linux-proof/venv/bin/python -m damru install-deps -y
/tmp/damru-linux-proof/venv/bin/python -m damru check-env --viewer
/tmp/damru-linux-proof/venv/bin/python -m pytest -q
```

Result:

- Docker package reinstall from `install-deps`: OK
- Native Linux iptables backend: nft selected
- Docker bridge/NAT networking: OK
- binderfs mounted at `/dev/binderfs`: OK
- Damru Playwright `crPage.js` patch: OK
- Unit test suite: `8 passed, 13 skipped`
- `scrcpy`: optional warning only when not installed

Browser smoke:

- Single-worker `AsyncDamru` session loaded `https://example.com` and reported Android UA plus `navigator.hardwareConcurrency == 8`.
- Two-worker `DamruPool(mode="auto", max_devices=2)` loaded `https://example.com` in both workers.
- Both native Linux workers reported `navigator.hardwareConcurrency == 8`.

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

## Fixed During Verification

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
