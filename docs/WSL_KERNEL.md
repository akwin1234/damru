# WSL2 Kernel Notes for Docker and Redroid

Damru can install Linux packages and apply common WSL fixes, but Redroid depends on kernel features that Python cannot create at runtime.

## Required Environment

On Windows, Damru requires this split:

- Python may run on Windows or inside WSL.
- Docker and Redroid must run inside Linux/WSL2.
- Native Windows Docker is not a supported Redroid target.

## Preferred Kernel Support

Docker bridge/NAT networking and Redroid need a WSL2 kernel with these pieces available built-in or as modules:

- `xt_addrtype`
- `ip_tables`, `iptable_nat`, `iptable_filter`
- `nf_nat`, `nf_conntrack`
- `bridge`, `br_netfilter`, `veth`
- Android binder and binderfs support

The common Docker bridge/NAT failure looks like this:

```text
modprobe: FATAL: Module xt_addrtype not found in directory /lib/modules/...
```

That means the current WSL kernel does not provide a module Docker normally uses for bridge/NAT rules, or it cannot load modules matching the active kernel. `apt install`, `service docker start`, and `modprobe` retries cannot create a kernel feature that was built out.

## Stock Module VHD Caveat

Recent WSL versions can mount Microsoft's module disk with `.wslconfig` settings such as:

```ini
[wsl2]
kernelModules=C:\\Program Files\\WSL\\tools\\modules.vhd
loadDefaultKernelModules=true
```

This can help the stock Microsoft WSL2 kernel load Docker netfilter modules. It does **not** make arbitrary custom kernels load stock Microsoft modules. Kernel modules must match the exact active `uname -r`. If `modprobe` reports `Exec format error`, the module VHD is for a different kernel and Docker bridge/NAT still cannot work on that custom kernel.

Local validation on this machine found:

- Stock Microsoft WSL2 kernel plus Microsoft `modules.vhd`: Docker bridge/NAT works, but Android `binderfs` is missing, so Redroid cannot boot correctly.
- The original Redroid custom WSL2 kernel: Android `binderfs` works, but Docker bridge/NAT fails when matching netfilter modules are missing or when nft rejects Docker's `addrtype` NAT rule.
- A rebuilt Redroid WSL2 kernel with Docker bridge/NAT options enabled plus `iptables-legacy` passed Docker default bridge validation and multi-worker Damru pool validation.
- Starting Docker with `--iptables=false --ip-masq=false` while keeping bridge enabled can still fail on limited kernels at `Failed to create bridge docker0 via netlink: operation not supported`.

## Host-Network ADB Fallback

Damru also supports a WSL fallback for kernels that can run binderfs/Redroid but cannot run Docker bridge/NAT cleanly. In the most limited mode Damru can start Docker like this:

```bash
dockerd --iptables=false --ip6tables=false --bridge=none --host=unix:///var/run/docker.sock
```

Redroid then runs with Docker host networking. On Windows/WSL, Damru remaps each worker's Android `adbd` after boot to a stable per-worker port:

```text
worker 0 -> wsl:127.0.0.1:5600
worker 1 -> wsl:127.0.0.1:5601
worker N -> wsl:127.0.0.1:(5600 + N)
```

This avoids the common WSL failure where Docker-published TCP ports accept connections but ADB stays `offline`. Damru starts/remaps host-network workers sequentially so only one container temporarily uses Redroid's default `5555` port during boot.

Fallback limits:

- Docker bridge/NAT features are unavailable until the WSL kernel supports the missing netfilter pieces, but Damru auto mode can still use host-network ADB remapping for Redroid workers.
- If Android inside Redroid also lacks the `iptables` filter table, Damru skips the kernel WebRTC UDP block and keeps the Chrome WebRTC policy/CDP protections active. That is stable, but kernel-level WebRTC leak protection is degraded on that kernel.

## Bundled Damru Kernel Installer

Damru ships the locally verified WSL2 Redroid/NAT kernel artifact in `damru/wsl_kernel/`:

- `wsl2-kernel-redroid-natfix-20260602`
- `wsl2-kernel-redroid-natfix-20260602.config`
- `SHA256SUMS`
- `source_metadata/` with the WSL build `.config`, `.config.old`, embedded `kernel/config_data`, and source tree info

The public source repository and compiled release are available here:

- Source repo: https://github.com/akwin1234/damru-wsl2-kernel-redroid-natfix-source
- Compiled kernel release: https://github.com/akwin1234/damru-wsl2-kernel-redroid-natfix-source/releases/tag/v6.6.114.1-damru-redroid-natfix-20260602
- Kernel binary: https://github.com/akwin1234/damru-wsl2-kernel-redroid-natfix-source/releases/download/v6.6.114.1-damru-redroid-natfix-20260602/wsl2-kernel-redroid-natfix-20260602
- SHA256: `1c2a5c2c4737a02b8f81dcd82162727cb5644d194bb9cfb2f9162a9862b03c6e`

The installer is backup-first. It verifies the bundled checksums, copies the kernel and config to `%USERPROFILE%\.damru\wsl-kernels\`, backs up any existing `%USERPROFILE%\.wslconfig`, preserves unrelated `.wslconfig` settings, and writes the `[wsl2] kernel=...` entry. It also writes `dnsTunneling=true` and `networkingMode=NAT`; this fixes the common WSL state where the distro can ping public IPs but `apt`, `pip`, or Docker containers cannot resolve DNS names.


### Fresh WSL Recommendation

For Windows users, Damru recommends a fresh/dedicated WSL distro for Redroid. Installing the bundled kernel changes `%USERPROFILE%\.wslconfig`, so it affects how WSL boots. Damru backs up `.wslconfig` before editing it, but a custom kernel can still break Docker, networking, modules, or other WSL workloads. Native Linux/Ubuntu does not use this WSL kernel installer.

Interactive installs require typing the full confirmation phrase shown by the CLI. Noninteractive installs require both `--yes` and `--confirm-wsl-kernel-risk`; `--yes` alone is intentionally refused.
Status only:

```powershell
python -m damru wsl-kernel status
```

Install the bundled kernel:

```powershell
python -m damru wsl-kernel install --yes --confirm-wsl-kernel-risk
wsl --shutdown
python -m damru fix-wsl
python -m damru check-env --viewer
```

`fix-wsl` can also install it after normal repair fails:

```powershell
python -m damru fix-wsl --install-kernel --yes --confirm-wsl-kernel-risk
wsl --shutdown
```

`setup` can opt into the same path on fresh Windows/WSL machines:

```powershell
python -m damru setup --install-wsl-kernel -y --confirm-wsl-kernel-risk
```

Damru does not overwrite the original kernel in-place. Existing target artifacts with different checksums are backed up with a timestamp before being replaced.
## What Damru Can Fix

Run:

```bash
python -m damru fix-wsl
python -m damru check-env
```

`fix-wsl` safely retries the pieces Damru can control:

- Select a Docker-compatible iptables backend. Damru prefers `iptables-legacy` in WSL because some WSL kernels reject Docker's `addrtype` NAT rule through `iptables-nft`. Native Linux prefers `iptables-nft`, which is what modern Docker daemons generally use for their NAT chains.
- Load common Docker/Redroid modules with `modprobe`.
- Mount binderfs at `/dev/binderfs`.
- Start the Docker daemon inside Linux/WSL. It tries systemd, classic `service`, direct `dockerd`, then the no-iptables/no-bridge fallback for limited WSL kernels.
- Repair Docker bridge container internet by enabling IPv4 forwarding and inserting targeted `docker0` FORWARD/MASQUERADE rules before stale Android-style chains such as `oem_fwd`, `fw_FORWARD`, `bw_FORWARD`, and `tetherctrl_FORWARD`.
- Report clearly when the active kernel blocks full bridge/NAT mode.

## If Full Bridge/NAT Is Still Required

For classic Docker bridge networking, install or boot a WSL2 kernel that includes Docker bridge/NAT and binderfs support, then restart WSL:

```powershell
wsl --shutdown
```

After WSL starts again, run:

```bash
python -m damru fix-wsl
python -m damru check-env
```

## Multiple WSL Distros

Damru can target a non-default WSL distro without rewriting `damru/config.py`:

```powershell
$env:DAMRU_WSL_DISTRO = "DamruFreshKernelTest"
python -m damru check-env --viewer
python -m damru fix-wsl
```

Windows auto mode uses host-network Redroid for reliable ADB. Host-network Redroid containers share WSL kernel-level sockets across distros. Do not run host-network Redroid workers in two WSL distros at the same time. `check-env` now reports a cross-distro conflict before pool startup if another distro already has running host-network Redroid containers.

## Verified Commands

The current bundled kernel/setup path was validated on June 2, 2026 with:

```powershell
$env:DAMRU_WSL_DISTRO = "DamruLoopTest10"
python -m damru install-deps -y
python -m damru fix-wsl
python -m damru install-viewer -y
python -m damru check-env --viewer
```

The same WSL distro then passed a single-worker `AsyncDamru` smoke and a two-worker `DamruPool(mode="auto", max_devices=2)` smoke. Both workers loaded `https://example.com` and reported `navigator.hardwareConcurrency == 8`.

Native Ubuntu/Linux does not use the WSL kernel installer. The native Linux path was reset by removing Docker packages/state, creating a fresh Python venv, running `python -m damru install-deps -y`, then validating `check-env --viewer`, unit tests, single-worker smoke, and two-worker pool smoke. Native Linux selected `iptables-nft` and Docker bridge/NAT passed.
