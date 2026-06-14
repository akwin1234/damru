# Changelog
## Unreleased

- Fixed stealth-open-url default mode: changed from --mode reattach (ADB intent, triggered anti-bot on Shopee, Cloudflare etc.) to --mode playwright (CDP page.goto, works with all tested sites). All four modes preserved; user can --mode reattach/
ative/cdp explicitly.

- Precomputed mobile User-Agent during _chrome_prep() — UA + Client Hints metadata are now written to Chrome's native command line via --user-agent= flag, so the first native HTTP request carries the correct profile UA. CDP setUserAgentOverride reuses the same payload, eliminating version/UA mismatches between page and Worker targets.

- Replaced WebRTC kernel UDP blocking with emove_webrtc_block(): iptables DROP rules are removed and Chrome flag changed from default_public_interface_only to default_public_and_private_interfaces. WebRTC now discovers the real proxy exit IP instead of appearing disabled — matches real device behavior.

- Updated 
avigator.credentials, 
avigator.serviceWorker, 
avigator.mediaDevices, 
avigator.bluetooth, 
avigator.usb, 
avigator.storage, 
avigator.keyboard verified working on HTTPS pages (previously undefined on about:blank before CDP overrides attach).

- Verified external techinz/browsers-benchmark against 10 bypass targets (Google Search, Cloudflare, DataDome x2, Amazon, Ticketmaster/Imperva, Akamai, PerimeterX/HUMAN, Kasada, Reddit): 10/10 PASS, 100% bypass rate.

## Unreleased

- Made experimental features default-on: DAMRU_EXPERIMENTAL_CDP_SENSORS, DAMRU_EXPERIMENTAL_BATTERY_DUMPSYS, DAMRU_EXPERIMENTAL_SENSOR_HAL, DAMRU_ENABLE_NATIVE_SENSOR_HAL, DAMRU_EXPERIMENTAL_HIDL_SENSOR_HAL are now =1 by default. Set to =0 to disable.
- Documented all experimental env vars (DAMRU_EXPERIMENTAL_SENSOR_HAL, HIDL_SENSOR_HAL, BATTERY_DUMPSYS, CDP_SENSORS, WORKER_CORE_CDP, RAW_WORKER_CDP, ENABLE_NATIVE_SENSOR_HAL, PROFILE_TIER) in README.md Experimental Features section.


- Added WebView Shell-aware profile hardening: `force-profile --browser-package org.chromium.webview_shell` now writes WebView command-line/preferences, applies native memory preload for WebView Shell, and keeps Android props/timezone/locale/GPU/CPU profile behavior consistent with Chrome harnesses.
- Tightened Chrome/WebView version alignment: Chrome rotation and explicit `--chrome-version` selection require matching WebView APK assets, install/bake replaces the system WebView provider with safe `root:root 0644` permissions, and stale WebView oat/dalvik cache is cleared to avoid Android writable-dex rejection.
- Made `stealth-open-url` default to `--mode reattach`: apply full Damru stealth, detach CDP for the protected native Chrome navigation, then reconnect CDP so the loaded page can be inspected or automated. `--mode cdp`, `--mode native`, and `--mode playwright` remain available for specific debugging needs.
- Added profile tiers: default random selection now uses only the 100-profile premium pool (51 original verified + 49 high-confidence new profiles), while medium and experimental profiles remain available by explicit name or opt-in `profile_tier` / `--profile-tier`.
- Expanded the built-in Android profile database from 51 to 155 profiles by importing 104 additional regional devices from the `r.txt` research set. Malformed entries, existing duplicate devices, `UNKNOWN` fingerprints, obvious placeholder fingerprints, and incomplete critical records were skipped; all imported profiles passed Sannysoft on WSL Redroid with a runtime-only DataImpulse proxy after retrying transient proxy/network timeouts, and representative Adreno/Mali/PowerVR profiles passed the full CreepJS, BrowserScan, Sannysoft, and Cloudflare benchmark sample.
- Rebuilt the baked Redroid image from the clean Redroid base instead of stacking on an older `damru-redroid:latest`; the current export is about 1.2 GB and includes the validated Chrome/WebView/TTS/resetprop assets.
- Fixed `quick-check` DNS readiness so it accepts Android DNS from the active resolver state instead of requiring only `net.dns1`, which prevented false DNS failures on freshly imported images.
- Updated UI Workers and Logs pages with compact pagination and clearer ADB-empty wording when Docker workers exist but ADB is still reconnecting.
- Added release metadata tests so the hardcoded image checksum must match `damru-redroid-latest.tar.sha256` and Chrome auto-selection cannot silently re-skip known-good versions.
- Added UI documentation and screenshots for Dashboard, Setup, Workers, Work Lab, Settings, and Logs.
- Expanded the raw Chrome APK bundle to 19 validated Chrome split-APK versions from `143.0.7499.52` through `148.0.7778.217`; Chrome 149 is intentionally excluded until a compatible English/x86/x86_64 bundle is available.
- Made random profile actions rotate Chrome APK versions when the validated APK bundle is present, while keeping Chrome first-run prompts suppressed and stale tabs cleared.
- Verified the APK matrix across install, exact Chrome `versionName`, `quick-check`, Chrome launch/PID, DNS, CDP probes, and representative full spoof sessions for Chrome 146/147/148 builds.
- Fixed authenticated HTTP/SOCKS proxy handling across UI Open URL, `open-url`, `random-profile`, and full Damru/benchmark sessions by adding an automatic local no-auth proxy bridge for Android's `host:port`-only system proxy setting.
- Changed UI Open URL to use a full Damru stealth session instead of raw Android Chrome launch, so Android OS, UA/client hints, timezone, locale, proxy, WebRTC, GPU, hardware, and TLS setup are applied before navigation.
- Made random profile changes proxy-aware: timezone/locale follow the current proxy exit, Chrome data is reset, stale tabs are cleared, and Chrome first-run prompts remain suppressed for the next launch.
- Hardened BrowserScan benchmark extraction against page self-navigation and verified the full benchmark set passes with bridged authenticated proxy routing.
- Merged physical ADB safety behavior: auto-detection now prefers TCP Redroid endpoints, then `emulator-*`, and refuses physical-looking USB serials by default unless `DAMRU_ALLOW_PHYSICAL=1` is explicitly set for a disposable test device.
- Added focused ADB unit tests for TCP preference, emulator fallback, physical USB refusal, and explicit physical override.
- Updated README/docs for the current Ubuntu 24.04 and Ubuntu WSL2 beta path, minimum capacity planning, preflight, local UI, viewer workflows, image/APK handling, WSL kernel behavior, proof results, and legal/fork policy.
- Verified the current tree on a disposable Ubuntu WSL2 distro and a native Ubuntu 24.04 VPS: preflight, two Redroid workers, `quick-check`, and `open-url https://example.com` passed on both.
- Fixed WSL `wsl:` ADB serial handling when Damru is already running inside Linux/WSL, so commands such as `quick-check --serial wsl:127.0.0.1:5600` do not try to launch `wsl.exe` from inside WSL.
- Fixed fresh Redroid quick checks by setting a fallback Android locale only when `persist.sys.locale` is empty.
- Made preflight detect WSL kernel binderfs support from the active kernel config on both Windows-launched and WSL-launched paths.
- Made supported-but-unmounted WSL binderfs a default preflight warning instead of a false hard failure; `--strict` still fails it for CI/fleet policies.
- Removed exact private-provider gateway wording from proxy test fixtures while keeping sticky-session behavior covered.
- Added `python -m damru check preflight`, a fast read-only readiness check for Docker, ADB, binder/binderfs, Redroid image, APK bundle, ports, resources, WSL kernel status, JSON fleet output, and strict warning handling.
- Added `python -m damru ui`, an experimental localhost dashboard for setup checks, worker lifecycle actions, Work Lab browser actions, browser-based live viewing, native viewer command copy, gallery cleanup, and inline job logs.
- Added `python -m damru quick-check`, a fast local Android/Chrome sanity checker for ADB, boot, Chrome, DNS, timezone, locale, Android props, and core fingerprint fields.
- Added `python -m damru fix-internet` and UI worker actions for repairing WSL/Docker/Android DNS and internet state across one worker or all running Damru workers.
- Changed Windows/WSL Redroid worker startup to use Docker bridge networking with published ADB ports, avoiding host-network Redroid mutations of WSL routes, policy rules, iptables, and DNS.
- Made native `scrcpy` viewer commands strip the internal `wsl:` serial prefix on Windows while keeping WSL-routed ADB support for Damru CLI actions.
- Packaged `damru.ui` static assets in both `pyproject.toml` and legacy `setup.py` so pip installs can run the UI without a source checkout.
- Added `DAMRU_REDROID_BASE_PORT` for temporary side-by-side WSL testing when another local Damru runtime already owns the default `5600+` ADB ports.
- Added copyright, official-repository, no-false-authorship, no-relicensing, no-confusing-copy, and public-source-not-public-domain notices to the legal policy.
- Broadened the legal policy so attribution and unofficial-copy requirements apply to the full Damru codebase, docs, native code, examples, tests, configs, package metadata, release artifacts, and proof assets.
- Tightened fork/mirror attribution policy so public copies must preserve the license, credit Damru visibly, and identify themselves as unofficial unless maintained by the Damru maintainers.
- Published the Damru WSL2 Redroid/NAT kernel source fork and compiled kernel release, and linked them from WSL kernel documentation.
- Added `LEGAL.md` with fork, mirror, attribution, and commercial-use policy, plus README/license links to the policy.
- Rewrote `CONTRIBUTING.md` to remove corrupted encoding and add privacy/licensing contribution rules.
- Fixed README shields.io badge URLs that lost the `?style=` query separator.
- Removed the old `ubuntu-proof-summary.png` proof asset and all references to it.
- Fixed Google Drive manual-download links that lost `?usp=sharing` during text cleanup.
- Made setup choose from the validated Chrome APK bundle instead of pinning one Chrome version by default.
- Shipped `damru/assets/magisk.apk` and `damru/assets/libfakemem.c` in the Python package so pip installs no longer need third-party runtime APK downloads or a source checkout for memory spoofing.
- Removed runtime APK downloads from Magisk, F-Droid eSpeak, NikGapps GoogleTTS, and RHVoice paths; runtime APK use now comes from Damru's bundle/package assets.
- Fixed the Playwright `crPage.js` Runtime patch syntax and added regression tests for corrupted patch repair.
- Restored ternary operators in JS/C snippets that were damaged by mojibake cleanup.
- Verified fresh Ubuntu 24 VPS reset flow from GitHub `main`: setup, check-env, single Redroid smoke, and two-worker pool smoke all pass with Android UA, `hardwareConcurrency == 8`, `deviceMemory == 8`, `speechSynthesis` voices, and `webdriver == false`.
- Added pytest markers for unit, ADB, Docker, network, end-to-end, and GPU tests.
- Added automatic test marker assignment in `tests/conftest.py`.
- Made default `pytest` skip environment-heavy probes unless `--run-damru-probes` is passed.
- Removed an unsupported pytest-asyncio config option that caused collection warnings.
- Added the `python -m damru` CLI with `benchmark`, `check-env`, `install-deps`, `bake-image`, and `devices` commands.
- Added `python -m damru setup` for guided first-run config writing and dependency setup.
- Added `python -m damru fix-wsl` for safe Docker, binderfs, and netfilter repair attempts plus clear missing-kernel-module guidance.
- Added optional visual tooling commands: `screenshot`, `record`, `view`, and `install-viewer`.
- Added `docs/VIEWER.md` for scrcpy, screenshot, and video workflows.
- Added `docs/WSL_KERNEL.md` for WSL2 Docker/Redroid kernel requirements.
- Added Linux/WSL environment validation via `check-env`.
- Made `check-env` verify the Damru Playwright `crPage.js` patch is present in the installed Playwright package.
- Added Linux/WSL dependency installation via `install-deps`; Docker/Redroid setup is kept inside Linux or WSL only.
- Made `install-deps` install Damru's Python runtime dependencies into the active interpreter and apply the bundled Playwright `crPage.js` patch.
- Made `install-deps` continue to Python setup when WSL apt fails but required Linux commands are already present.
- Made `install-deps` run setup inside WSL as root on Windows, avoiding native Windows Docker and noninteractive sudo issues.
- Made Windows Docker commands run through WSL root so existing WSL users are not blocked by Docker group membership state.
- Made Linux/WSL Docker startup try systemd, classic service startup, and direct `dockerd` fallback for fresh/minimal WSL installs.
- Added WSL-routed ADB serials (`wsl:host:port`) for Redroid workers managed from Windows.
- Made Windows Redroid auto mode use host networking with per-worker `adbd` port remapping (`5600`, `5601`, ...) when Docker-published ADB ports are unreliable.
- Added a WSL no-custom-kernel fallback that starts Docker with `--iptables=false --bridge=none` and runs Redroid with host-network ADB remapping when Docker bridge/NAT modules are missing.
- Made Redroid startup recreate stale bridge-network containers as host-network containers on Windows when needed.
- Fixed WSL ADB file transfer by translating Windows paths to `/mnt/<drive>/...` for `push`, `pull`, and APK install commands.
- Fixed WSL rooted shell execution by sending complex `su` commands as base64-decoded scripts, avoiding nested shell quote expansion.
- Fixed WSL Linux command execution by base64-wrapping WSL `bash` scripts, preventing `wsl.exe` from stripping shell `$variables` in repair/setup flows.
- Hardened WSL host-network repair to restore both the `lookup main` policy rule and a missing default route after Redroid host-network operations mutate the shared WSL network namespace.
- Added Redroid DNS boot parameters so fresh host-network containers expose DNS servers to Android `LinkProperties` and Chrome can resolve domains without a proxy.
- Added `websockets` as an explicit runtime dependency for the raw CDP worker auto-attach path.
- Made Linux `install-deps` install `python3-venv`, add the current user to the Docker group when possible, and avoid dumping pip editable-install tracebacks when the runtime dependency fallback succeeds.
- Fixed worker `navigator.hardwareConcurrency` leakage by adding a raw CDP worker auto-attach path that applies the core override to dedicated workers created after navigation.
- Verified secure-context `navigator.deviceMemory` spoofing in both main page and worker scopes with the native memory preload path.
- Made `damru devices`, `screenshot`, `record`, and `view` understand WSL-routed Redroid serials.
- Made Android WebRTC iptables blocking degrade cleanly when Redroid's kernel lacks the `filter` table, instead of aborting the browser session.
- Fixed native memory spoofing by moving from a global `app_process64` wrapper to Android's per-Chrome wrap property and correcting `libfakemem` Android `sysconf` handling.
- Added a Windows LLVM fallback for building `libfakemem_x86_64.so` when WSL `gcc` is unavailable.
- Added `gcc` to `install-deps` because native memory spoofing needs a compiler when the prebuilt `.so` is absent.
- Changed the Playwright `crPage.js` patcher to patch the installed Playwright file in place, preserving current Playwright video/screencast internals while adding Damru's Runtime toggle.
- Hardened `example.py` against public benchmark-site flakiness and proxy-optional runs.
- Added `docs/WSL_FALLBACK_TEST_RESULTS.md` with the WSL fallback verification results and known degraded behavior.
- Made noninteractive setup auto-detect the WSL default user when config still contains a username placeholder.
- Made `fix-wsl` avoid long Docker waits when kernel modules are missing and report the kernel blocker without a traceback.
- Updated `example.py` for the current device/profile API and made live browser sections skip cleanly when no ADB device is available.
- Made `install-deps` and `fix-wsl` prefer `iptables-legacy` when available because some WSL kernels reject Docker's `addrtype` NAT rule through the nft backend.
- Made native Linux setup prefer `iptables-nft`, while WSL continues to prefer `iptables-legacy`, so Docker's NAT chain matches the daemon backend on both platforms.
- Made setup/repair restart Docker after iptables backend changes so stale Docker NAT chains do not survive from the previous backend.
- Fixed `install-deps` editable install on Python 3.14 by removing the `SETUPTOOLS_USE_DISTUTILS=stdlib` override that made pip unable to import `setuptools.build_meta`.
- Made `install-deps` skip editable reinstall attempts when Damru is running from an installed package without a nearby `pyproject.toml`.
- Made `fix-wsl`, `check-env`, and Windows auto sessions verify and repair Docker bridge container internet with targeted `docker0` FORWARD and MASQUERADE rules, without flushing unrelated firewall chains.
- Added a short post-CDP page-context settle step to reduce first-navigation `Execution context was destroyed` races after Redroid warm starts.
- Made the post-CDP settle step return a fresh single tab so `context.pages[0]` is stable for immediate user navigation/evaluation.
- Wrapped returned Playwright `context.new_page()` calls to normalize Android Chrome tabs to `about:blank` before user navigation, fixing pooled warm-reuse tab races on WSL and native Linux.
- Made page-level CDP target auto-attach non-pausing; worker targets are still handled by the raw browser CDP auto-attach path, but new tabs no longer stall during concurrent pool sessions.
- Suppressed a known Windows asyncio Proactor closed-pipe destructor noise path after successful WSL subprocess use.
- Made `install-deps` verify Docker and binderfs after setup and fail clearly when WSL kernel netfilter modules are missing.
- Made `check-env` report the missing `xt_addrtype` WSL kernel module when Docker cannot start.
- Made Chrome APK discovery check the current working directory so pip-installed users can keep `chrome-apks/` beside their project.
- Added `docs/DEVICE_PROFILES.md` with the generated built-in Android profile list; the current regenerated list now contains 155 profiles.
- Removed the WSL sudo-password requirement from the Windows Docker/Redroid setup path.
- Updated README, API docs, docs index, and automation notes for the new CLI/setup/check behavior.
- Added `install-deps --sudo-password-stdin` for noninteractive setup runs that need sudo authentication.
- Included the bundled Playwright `crPage.js` patch file in built packages.
- Constrained Playwright to `<1.60` because 1.60 removed the patched `crPage.js` path Damru currently depends on.
- Updated the build backend requirement so `pip install -e .` works in fresh developer clones.
- Cleaned README encoding to avoid corrupted Unicode rendering.
- Documented the Linux-only Redroid requirement and new CLI commands.
