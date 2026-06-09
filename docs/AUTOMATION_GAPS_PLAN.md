# Damru Automation Status and Roadmap

Last reviewed: 2026-06-05

This file is the current automation checklist. Older notes in this repo may mention missing image setup, missing preflight, or missing WSL repair; those items are now implemented in the CLI and UI.

## Implemented Now

| Area | Current behavior |
| --- | --- |
| First-run setup | `python -m damru setup` guides config and can run dependency setup. |
| Dependencies | `install-deps` installs Linux/WSL packages, Docker, ADB, binderfs tools, and applies Damru's Playwright patch. |
| Baked image | `install-image` loads or downloads `damru-redroid:latest` when available. |
| Raw APK assets | `install-apks --download` downloads/extracts Chrome/WebView/TTS/resetprop assets to `/home/damru/chrome-apks`. |
| Chrome rotation | Random profile actions rotate through Chrome APK folders only when that folder also includes a matching WebView APK. |
| Preflight | `check preflight` is fast, read-only, JSON-capable, and suitable for deployment scripts. |
| Deep environment check | `check-env` performs slower setup validation and optional viewer checks. |
| WSL repair | `fix-wsl` repairs safe Docker, binderfs, iptables, DNS, and WSL networking cases. |
| Worker internet repair | `fix-internet` repairs WSL/Docker/Android DNS/internet state for one worker or all workers. |
| Worker lifecycle | CLI/UI worker helpers can start, stop, delete, quick-check, open URL, screenshot, and view workers. |
| Viewer | `view`, `install-viewer`, browser viewer, and native `scrcpy` command copy are documented. |
| Safety | Physical USB ADB devices are refused by default; `DAMRU_ALLOW_PHYSICAL=1` is explicit override only. |

## Supported Public Host Path

Damru Redroid auto mode is supported on:

- native Ubuntu 24.04 LTS
- Ubuntu 24.04 in WSL2 with Damru's bundled WSL kernel

Other Linux distributions are not public-supported yet. Docker may run there, but Redroid multi-container reliability depends on kernel binderfs support and Docker networking behavior.

## Remaining Gaps

| Gap | Why it matters | Current workaround |
| --- | --- | --- |
| Docker data-root management | WSL Docker layers can fill the default WSL virtual disk. | Manually move Docker data-root or keep enough WSL disk space. |
| Better fleet orchestration | `check preflight --json` is usable by external orchestrators, but Damru does not yet manage thousands of hosts itself. | Run Damru per host and collect JSON centrally. |
| UI maturity | `python -m damru ui` is useful but still marked experimental. | Prefer Python API/CLI for production automation. |
| Custom kernel coverage outside WSL | Debian/custom VPS kernels may lack `CONFIG_ANDROID_BINDERFS`. | Use Ubuntu 24.04, or provide a binderfs-enabled kernel yourself. |
| Release asset hosting | Large Docker image and APK zips are intentionally outside Git. | Use the documented release/download links and checksums. |

## Useful Commands

```bash
python -m damru setup
python -m damru install-deps -y
python -m damru install-image
python -m damru install-apks --download
python -m damru check preflight --json --timeout 3
python -m damru check-env --viewer
python -m damru fix-wsl
python -m damru fix-internet --all
python -m damru quick-check --serial 127.0.0.1:5600
python -m damru open-url --serial 127.0.0.1:5600 --url https://example.com
python -m damru ui
```

## Next Good Improvements

1. Add Docker data-root helper with a clear backup/restore path.
2. Add a read-only `damru doctor report` that bundles sanitized preflight, check-env, Docker, ADB, and UI job history.
3. Add optional signed/checksummed release manifest for the baked image and APK bundle.
4. Improve UI setup wizard wording and disabled-state explanations.
5. Keep expanding Chrome APK versions only after full install/launch/spoof validation.
