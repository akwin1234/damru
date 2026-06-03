# Damru Documentation

This directory is the long-form knowledge base for Damru. The main README stays quick; these pages hold the operational details, references, and verification notes.

## Start Here

| Document | Use it for |
| --- | --- |
| [Python API](PYTHON_API.md) | `AsyncDamru`, `Damru`, pools, profiles, proxy options, and examples. |
| [Proof](PROOF.md) | Sanitized verification results, screenshots, and video proof. |
| [Device Profiles](DEVICE_PROFILES.md) | Full list of 49 built-in Android identities. |
| [Viewer](VIEWER.md) | Screenshots, screen recording, and scrcpy live viewer. |
| [WSL Kernel](WSL_KERNEL.md) | WSL2 custom kernel, Docker NAT, binderfs, and repair behavior. |
| [WSL Fallback Results](WSL_FALLBACK_TEST_RESULTS.md) | Known degraded WSL behavior and fallback validation. |
| [Automation Roadmap](AUTOMATION_GAPS_PLAN.md) | Remaining infrastructure and automation work. |

## Supported Path

The public supported host path is Ubuntu 24.04 LTS:

- Native Ubuntu 24.04 VPS/Linux.
- Ubuntu 24.04 inside WSL2 with Damru's bundled WSL kernel.

Debian 13 was tested, but its stock VPS kernel did not expose the binderfs support required for reliable multi-container Redroid. Other Linux variants are future targets, not current support promises.

## Setup Commands

```bash
python -m damru setup -y
python -m damru check-env --viewer
```

Useful recovery commands:

```bash
python -m damru install-deps -y
python -m damru fix-wsl
python -m damru install-apks --download
python -m damru install-image --download
```

WSL kernel install:

```powershell
python -m damru wsl-kernel install --yes --confirm-wsl-kernel-risk
wsl --shutdown
```

## Proof Assets

Proof assets live under `docs/assets/proof/` and are sanitized before publication. Do not commit proxy credentials, private IP addresses, account data, local usernames, or private screenshots.
