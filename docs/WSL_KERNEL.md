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

Damru's current Windows/WSL runtime uses Docker bridge networking with published ADB ports. This keeps Android `netd` isolated from the WSL host namespace, which prevents Redroid from corrupting WSL routes, policy rules, iptables, or DNS. Workers appear at stable per-worker serials:

```text
worker 0 -> wsl:127.0.0.1:5600
worker 1 -> wsl:127.0.0.1:5601
worker N -> wsl:127.0.0.1:(5600 + N)
```

If an older Damru container was created with host networking, current Damru recreates it with bridge networking on the next start.

Bridge/NAT requirements:

- Docker bridge/NAT must work inside the selected WSL distro.
- The bundled Damru WSL kernel includes the binderfs and netfilter pieces needed by Docker bridge/NAT and Redroid.
- If Android inside Redroid also lacks the `iptables` filter table, Damru skips the kernel WebRTC UDP block and keeps Chrome's native `disable_non_proxied_udp` WebRTC policy plus CDP protections active. That is stable; kernel-level WebRTC blocking is defense in depth.

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

The UI requires typing `yes` before installing the bundled WSL kernel. Noninteractive CLI installs require both `--yes` and `--confirm-wsl-kernel-risk`; `--yes` alone is intentionally refused.

`python -m damru check preflight` is read-only. On WSL it checks the active kernel config for `CONFIG_ANDROID_BINDER_IPC` and `CONFIG_ANDROID_BINDERFS`, but it does not mount binderfs. If the kernel supports binderfs and `/dev/binderfs` is simply not mounted after a WSL restart, default preflight reports a warning; `python -m damru fix-wsl` or worker startup mounts binderfs before Redroid launch. Use `--strict` if your deployment pipeline wants that warning to fail.
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
- Start the Docker daemon inside Linux/WSL. It tries systemd, classic `service`, then direct `dockerd`.
- Repair Docker bridge container internet by enabling IPv4 forwarding and inserting targeted `docker0` FORWARD/MASQUERADE rules before stale Android-style chains such as `oem_fwd`, `fw_FORWARD`, `bw_FORWARD`, and `tetherctrl_FORWARD`.
- Report clearly when the active kernel blocks bridge/NAT mode.

## If Bridge/NAT Is Still Broken

Install or boot a WSL2 kernel that includes Docker bridge/NAT and binderfs support, then restart WSL:

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

Windows auto mode uses Docker bridge networking with published ADB ports. Use one dedicated Damru WSL distro at a time so old/stale containers from another distro do not confuse ADB or Docker state. For temporary side-by-side testing only, set a different base port such as `$env:DAMRU_REDROID_BASE_PORT = "5700"` before starting workers.

## Verified Commands

The current bundled kernel/setup path was validated again on June 4, 2026 with a disposable fresh WSL distro and a separate base ADB port:

```powershell
$env:DAMRU_REDROID_BASE_PORT = "5900"
python -m damru install-deps -y
python -m damru fix-wsl
python -m damru install-image --tar /mnt/c/path/to/damru-redroid-latest.tar
python -m damru check preflight --json --timeout 3
python -m damru ui-worker start --count 2
python -m damru quick-check --serial 127.0.0.1:5900 --output /tmp/damru-wsl-quick-5900.json
python -m damru quick-check --serial 127.0.0.1:5901 --output /tmp/damru-wsl-quick-5901.json
python -m damru open-url --serial 127.0.0.1:5900 --url https://example.com
```

The disposable WSL distro then passed a two-worker Redroid smoke. Both workers reported Android boot complete, Chrome installed, DNS present, locale present, timezone present, and Android Chrome opened `https://example.com` on the first worker.

Native Ubuntu/Linux does not use the WSL kernel installer. The native Ubuntu 24.04 path was reset by removing Docker packages/state in earlier loops, then validated again with a fresh Python venv, `python -m damru install-deps -y`, `python -m damru check preflight --json`, two Redroid workers, `quick-check` on both workers, and `open-url https://example.com`. Native Linux selected `iptables-nft` and Docker bridge/NAT passed.
