# Bundled WSL Kernel

Damru includes a locally verified WSL2 kernel artifact for Ubuntu WSL2 Redroid use.

## Public Source and Release

| Resource | Link |
| --- | --- |
| Source repo | https://github.com/akwin1234/damru-wsl2-kernel-redroid-natfix-source |
| Compiled release | https://github.com/akwin1234/damru-wsl2-kernel-redroid-natfix-source/releases/tag/v6.6.114.1-damru-redroid-natfix-20260602 |
| Binary asset | https://github.com/akwin1234/damru-wsl2-kernel-redroid-natfix-source/releases/download/v6.6.114.1-damru-redroid-natfix-20260602/wsl2-kernel-redroid-natfix-20260602 |

## Bundled Files

| File | Purpose |
| --- | --- |
| `wsl2-kernel-redroid-natfix-20260602` | WSL2 kernel binary with Android binderfs and Docker bridge/NAT options enabled. |
| `wsl2-kernel-redroid-natfix-20260602.config` | Exact kernel config captured from the build. |
| `SHA256SUMS` | Integrity checksums for bundled artifacts. |
| `source_metadata/` | Build config, old config, embedded kernel config data, and source/build notes. |

## Installer Behavior

Damru copies the kernel to `%USERPROFILE%\.damru\wsl-kernels\`, backs up an existing `%USERPROFILE%\.wslconfig`, preserves unrelated `.wslconfig` settings, and writes the `[wsl2] kernel=...` entry.

The user must restart WSL after installing or changing the kernel:

```powershell
wsl --shutdown
```

Then run:

```bash
python -m damru fix-wsl
python -m damru check-env --viewer
```

## Source Notes

The full local WSL kernel build tree was about 15 GB, so the Damru Python package stores the compiled artifact, checksums, and reproducibility metadata. The public kernel source fork above contains the modified source/config for users who want to audit or rebuild the kernel.
