# Legacy WSL Fallback Test Results

Test date: 2026-06-01

> **Historical note:** This file records the old no-custom-kernel host-network fallback experiment. It is not the recommended public setup path anymore. Current Damru WSL users should use Ubuntu WSL2 with the bundled Damru WSL kernel, Docker bridge/NAT, published per-worker ADB ports, `python -m damru check preflight`, and `python -m damru fix-wsl`. See [WSL_KERNEL.md](WSL_KERNEL.md) and [PROOF.md](PROOF.md) for the current June 4, 2026 validation.

## Environment

- Windows host with Ubuntu WSL2.
- Python installed in a fresh virtual environment outside the project tree.
- Docker/Redroid running inside WSL/Linux only.
- No custom WSL kernel.
- Docker daemon started with Damru's older no-iptables/no-bridge fallback because the WSL kernel was missing bridge/NAT netfilter modules.

## Results

- `python -m damru check-env`: passed.
- Focused unit tests from that historical run: `8 passed`.
- Redroid boot: passed with `damru-redroid:latest`.
- ADB connection: passed at the WSL host-network ADB endpoint.
- Multi-worker Redroid manager check: passed with `wsl:127.0.0.1:5600` and `wsl:127.0.0.1:5601` online.
- CLI screenshot: passed, PNG validated at `1080x2400`.
- CLI recording: passed, MP4/H.264 at `1080x2400`.
- Live `AsyncDamru`: passed Chrome launch, CDP attach, navigation, locator reads, UA spoof, `navigator.webdriver === false`, direct CDP screenshot, Playwright `page.screenshot()`, and secure-context `navigator.deviceMemory` spoofing.
- Fresh host-network Redroid smoke: passed no-proxy HTTPS navigation to `https://example.com/` after automatic WSL route repair and Redroid DNS boot parameters.
- Worker fingerprint smoke: passed with main page and dedicated worker reporting `navigator.hardwareConcurrency == 8` and `navigator.deviceMemory == 8` on a secure context.
- GPU binary spoof smoke: passed with WebGL reporting a target mobile GPU string and no SwiftShader renderer leak.
- `example.py`: final full run passed, `8 passed`, `0 failed`. A later run after the memory fix also passed `8 passed`, `0 failed`, with Sannysoft reachable and passing.

## Known Degraded Behavior In This Legacy Fallback

- Docker bridge/NAT was unavailable; Damru used Docker host networking.
- Windows host-network Redroid used per-worker ADB port remapping after boot. Each worker briefly used Android's default `5555` port while starting, so workers were started/remapped sequentially.
- Android kernel `iptables` filter table was unavailable in this environment, so Damru logged a warning and skipped the kernel WebRTC UDP block. Chrome's native `disable_non_proxied_udp` WebRTC policy and CDP protections remained active; kernel-level blocking was defense in depth only.
- Public benchmark sites can time out independently of Damru. The example smoke test treats external benchmark outages as unavailable instead of a Damru failure.

Local artifacts from this run were written to:

```text
<local-artifacts-dir>
```

Important files:

- `example-final.log`
- `playwright-page-screenshot.png`
- `redroid-screen-fixed.png`
- `redroid-record.mp4`
