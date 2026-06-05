#  Documentation (`docs/`)

Welcome to the Damru knowledge base. This directory holds project documentation, architecture plans, roadmaps, and research notes.

---

## Contents

*   **CLI setup**: Run `python -m damru setup` for guided first-run configuration, `python -m damru install-deps` for Linux/WSL dependencies, `python -m damru install-image` to load the baked Redroid image, `python -m damru install-apks --download` for raw Chrome/WebView/TTS APK assets plus Damru's shipped resetprop source when baking or using unbaked Redroid, `python -m damru fix-wsl`/`fix-internet` for safe Docker/binderfs/netfilter/DNS repair, `python -m damru check-env` to verify setup details, and `python -m damru check preflight --json` for fast read-only readiness checks across VPS/VM fleets. Preflight checks Docker, ADB, binder/binderfs, image/assets, resources, ports, config, and WSL kernel state without installing, mounting, starting containers, or editing networking.
*   **APK assets**: The raw APK bundle now contains 19 validated Chrome split-APK folders from `143.0.7499.52` through `148.0.7778.217`, plus WebView/TTS/resetprop support APKs. Random profile actions can rotate Chrome when the bundle is present.
*   **Local UI**: `python -m damru ui` starts the experimental localhost dashboard for setup health, worker actions, Work Lab URL/screenshot/quick-check flows, browser viewer, native viewer command copy, gallery cleanup, and inline logs. The backend is allowlisted and local-only by default; use it for setup/debugging/manual inspection, not as the stable automation API.
*   **Current validation**: On June 4, 2026, disposable Ubuntu WSL2 with Damru's bundled WSL kernel and native Ubuntu 24.04 VPS were both tested with fresh/reset setup flows, preflight, unit tests, two Redroid workers, `quick-check`, and `open-url https://example.com`. Debian 13 VPS was tested separately; Docker worked, but Redroid multi-container support failed because the stock Debian VPS kernel had `CONFIG_ANDROID_BINDERFS` disabled.
*   **[`PROOF.md`](PROOF.md)**: Sanitized WSL/native Linux verification notes plus proof assets: [Android screen recording](assets/proof/ubuntu-redroid-proof.mp4), Example.com proof, and individual site screenshots for Amazon, Foot Locker/DataDome, Fingerprint Pro, Sannysoft, and CreepJS.
*   **[`DEVICE_PROFILES.md`](DEVICE_PROFILES.md)**: Full generated reference for the 49 Android device profiles available in `damru/devices.py`.
*   **[`VIEWER.md`](VIEWER.md)**: Optional screenshot, video recording, and scrcpy live-view workflows.
*   **[`UI.md`](UI.md)**: Local dashboard guide with screenshots for Dashboard, Setup, Workers, Work Lab, Settings, and Logs.
*   **[`WSL_KERNEL.md`](WSL_KERNEL.md)**: WSL2 kernel requirements for Docker bridge/NAT networking and Redroid binderfs.
*   **Image baking**: Use `python -m damru install-apks --download`, then `python -m damru bake-image --image damru-redroid:latest` inside Linux/WSL2, then `docker save damru-redroid:latest -o damru-redroid-latest.tar`. The tarball is ignored by Git; keep `damru-redroid-latest.tar.sha256` with the release artifact. The APK installer downloads the Chrome/WebView/TTS bundle to `/home/damru/chrome-apks` on Linux/WSL and copies Damru's shipped `magisk.apk` there when raw Redroid needs standalone `resetprop`. Keep the full bundle root together; do not deduplicate version-matched Trichrome library splits across Chrome folders.
*   **[`AUTOMATION_GAPS_PLAN.md`](AUTOMATION_GAPS_PLAN.md)**: Current automation status and roadmap, including what setup/check/repair flows already exist and what remains for later fleet or storage work.
*   **Architecture notes**: The README and Python API document the current CDP, Android prop, GPU, memory, proxy, WSL, and Redroid layers. Deeper internals should be added as focused docs when the implementation stabilizes.
*   **`CONTRIBUTING.md`**: Guidelines for contributing to the Damru ecosystem.

Keep this index focused on current user-facing docs. Historical notes should clearly say when they are no longer the recommended setup path.
