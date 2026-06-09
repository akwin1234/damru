"""Runtime manager selection for Redroid-backed Damru workers."""
from __future__ import annotations

from typing import Optional

from . import config


def redroid_runtime_name() -> str:
    runtime = str(getattr(config, "REDROID_RUNTIME", "docker") or "docker").strip().lower()
    if runtime in {"ctr", "containerd"}:
        return "containerd"
    return "docker"


def create_redroid_manager(wsl_distro: Optional[str] = None):
    if redroid_runtime_name() == "containerd":
        from .containerd import ContainerdRedroidManager

        return ContainerdRedroidManager(wsl_distro=wsl_distro)
    from .docker import RedroidManager

    return RedroidManager(wsl_distro=wsl_distro)
