"""RedroidManager — container lifecycle for damru auto mode.

Redroid needs Linux kernel modules (binder via binderfs) so:
  - Windows: all docker commands run via WSL2 (auto-installs Docker if missing)
  - Linux: docker commands run directly (auto-installs if missing)

Requirements for WSL2:
  - Custom WSL2 kernel with CONFIG_ANDROID_BINDER_IPC=y, CONFIG_ANDROID_BINDERFS=y
  - Kernel modules: ip_tables, iptable_nat, nft_compat, xt_addrtype, bridge, veth
  - Binderfs mounted at /dev/binderfs
  - Docker-compatible iptables backend (legacy is preferred on WSL when nft rejects xt addrtype)

Containers are started once at pool init and stay alive.
Only Chrome is recycled per session (stop -> clear -> new fingerprint -> restart).
Containers are cleaned up on pool exit.

All credentials/settings come from config.py (single source of truth).
"""
from __future__ import annotations

import asyncio
import base64
from contextlib import suppress
import os
import re
import shlex
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from pathlib import PureWindowsPath
from typing import List, Optional

from .async_core import DamruError
from .apk_assets import candidate_apk_bundle_roots, find_matching_webview_apk
from .config import (
    CONTAINER_BOOT_TIMEOUT,
    DOCKER_CMD_TIMEOUT,
    APK_INSTALL_TIMEOUT,
    REDROID_BASE_IMAGE,
    REDROID_BASE_PORT,
    REDROID_CONTAINER_PREFIX,
    REDROID_CPUS,
    REDROID_GPU_MODE,
    REDROID_IMAGE,
    REDROID_MEMORY,
    REDROID_SETUPWIZARD_DISABLED,
    WSL_DISTRO,
    WSL_USERNAME,
)
from .netfix import android_dns_repair_command, wsl_runtime_network_repair_lines
from .utils import logger
from .webview_native_patch import (
    WebViewNativePatchError,
    is_webview_native_library_entry,
    patch_linux_armv8l_platform_string,
    patch_linux_armv8l_platform_string_in_apk,
    patch_x_requested_with_header_block,
)

_CHROME_APK_AUTO_SKIP_VERSIONS: set[str] = set()
_REDROID_SENSOR_SOURCE_IMAGE = "redroid/redroid:11.0.0-latest"
_SENSOR_MOCK_BIN = "android.hardware.sensors@2.1-service.mock"
_REDROID_STREAM_BOOT_ARG = "androidboot.use_redroid_stream=1"
_INPUT_NODE_FIX_SCRIPT = "/system/bin/damru-input-node-fix.sh"
_INPUT_NODE_FIX_RC = "/system/etc/init/damru-input-node-fix.rc"


def _kernel_config_enabled(config_text: str, option: str) -> Optional[bool]:
    """Return kernel config state for an option when it is visible."""
    enabled = f"{option}=y"
    module = f"{option}=m"
    disabled = f"# {option} is not set"
    for line in config_text.splitlines():
        value = line.strip()
        if value in {enabled, module}:
            return True
        if value == disabled:
            return False
    return None


class RedroidManager:
    """Manage redroid Docker containers for damru auto mode.

    Auto-installs Docker + dependencies if missing.
    All config from damru/config.py.
    """

    def __init__(self, wsl_distro: Optional[str] = None):
        self._is_windows = sys.platform == "win32"
        self._wsl_distro = wsl_distro or os.environ.get("DAMRU_WSL_DISTRO") or WSL_DISTRO
        self._wsl_user = WSL_USERNAME
        self._started_indices: List[int] = []
        self._adb_host: Optional[str] = None  # cached WSL2 IP for ADB

    async def _get_adb_host(self) -> str:
        """Get the host IP for ADB connections to Docker containers.

        On Windows with WSL2, 127.0.0.1 port forwarding is unreliable for
        ADB (shows 'offline'). Instead, we use WSL2's actual vEthernet IP
        which works reliably.
        """
        if self._adb_host:
            return self._adb_host

        if not self._is_windows:
            self._adb_host = "127.0.0.1"
            return self._adb_host

        # Get WSL2 IP from hostname -I (first IP is the vEthernet address)
        try:
            out = await self._run_cmd(
                ["wsl", "-d", self._wsl_distro, "--", "hostname", "-I"],
                timeout=5, allow_failure=True,
            )
            if out:
                ip = out.strip().split()[0]
                if ip and ip.count(".") == 3:
                    self._adb_host = ip
                    logger.info("WSL2 ADB host: %s", ip)
                    return self._adb_host
        except Exception:
            pass

        # Fallback to 127.0.0.1
        self._adb_host = "127.0.0.1"
        return self._adb_host

    def _make_serial(self, port: int) -> str:
        """Build ADB serial from cached host IP. Call _get_adb_host() first."""
        host = self._adb_host or "127.0.0.1"
        return f"{host}:{port}"

    def _make_wsl_serial(self, host: str, port: int = 5555) -> str:
        return f"wsl:{host}:{port}"

    def _plain_serial(self, serial: str) -> str:
        return serial[4:] if serial.startswith("wsl:") else serial

    @staticmethod
    def _to_wsl_path(value: str) -> str:
        if re.match(r"^[A-Za-z]:[\\/]", value):
            p = PureWindowsPath(value)
            drive = p.drive.rstrip(":").lower()
            rest = "/".join(p.parts[1:])
            return f"/mnt/{drive}/{rest}"
        return value

    @classmethod
    def _translate_wsl_file_args(cls, args: tuple[str, ...]) -> list[str]:
        translated = list(args)
        if not translated:
            return translated
        if translated[0] == "push" and len(translated) >= 3:
            translated[1] = cls._to_wsl_path(translated[1])
        elif translated[0] in {"install", "install-multiple", "install-multi-package"}:
            translated = [cls._to_wsl_path(part) for part in translated]
        return translated

    def _adb_cmd(self, *args: str, serial: Optional[str] = None) -> List[str]:
        """Build an adb command, routing Windows Redroid traffic through WSL."""
        routed_args = self._translate_wsl_file_args(args) if self._is_windows else list(args)
        parts = ["adb"]
        if serial:
            parts.extend(["-s", self._plain_serial(serial)])
        parts.extend(routed_args)
        if self._is_windows and serial and serial.startswith("wsl:"):
            return ["wsl", "-d", self._wsl_distro, "--", *parts]
        if self._is_windows and routed_args and routed_args[0] in {"connect", "disconnect"}:
            target = routed_args[1] if len(routed_args) > 1 else ""
            if target.startswith("wsl:"):
                routed = ["adb", args[0], self._plain_serial(target)]
                return ["wsl", "-d", self._wsl_distro, "--", *routed]
        return parts

    async def _get_container_ip(self, name: str) -> str:
        out = await self._run_cmd(
            self._docker_cmd(
                "inspect", "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                name,
            ),
            timeout=10,
            allow_failure=True,
        )
        return out.strip()

    async def _serial_for_container(self, name: str, port: int, use_host_network: bool = False) -> str:
        """Return the most reliable ADB serial for a Redroid container."""
        if self._is_windows:
            if use_host_network:
                return self._make_wsl_serial("127.0.0.1", port)
            return self._make_wsl_serial("127.0.0.1", port)
        await self._get_adb_host()
        return self._make_serial(port)

    # ── Command helpers ──

    def _docker_cmd(self, *args: str) -> List[str]:
        """Build docker command. On Windows, run via WSL2 distro."""
        if self._is_windows:
            return ["wsl", "-d", self._wsl_distro, "-u", "root", "--", "docker", *args]
        return ["docker", *args]

    def _wsl_sudo_cmd(self, cmd: str) -> List[str]:
        """Build a privileged Linux command.

        On Windows, Docker/Redroid must run inside WSL. Use WSL's root user
        directly instead of piping a sudo password through the shell.
        """
        if self._is_windows:
            encoded = base64.b64encode(cmd.encode("utf-8")).decode("ascii")
            wrapped = f"printf %s {encoded} | base64 -d | bash"
            return [
                "wsl", "-d", self._wsl_distro, "-u", "root", "--",
                "bash", "-lc", wrapped,
            ]
        return ["bash", "-lc", f"sudo {cmd}"]

    def _start_docker_cmd(self) -> List[str]:
        """Build a privileged Docker daemon startup command.

        Some fresh WSL Ubuntu images ship only systemd units for Docker, while
        systemd is not PID 1. In that case, fall back to launching dockerd
        directly so a first-run setup can still work.
        """
        script = "\n".join([
            "set +e",
            "if ! docker info >/dev/null 2>/dev/null && command -v systemctl >/dev/null 2>&1 && [ \"$(ps -p 1 -o comm= 2>/dev/null)\" = systemd ]; then",
            "  systemctl reset-failed docker docker.socket containerd 2>/dev/null || true",
            "  systemctl start docker.socket 2>/dev/null || true",
            "  systemctl start containerd 2>/dev/null || true",
            "  systemctl start docker 2>/dev/null || true",
            "fi",
            "if ! docker info >/dev/null 2>/dev/null; then service docker start 2>/dev/null || true; fi",
            "if ! docker info >/dev/null 2>/dev/null; then",
            "  pkill dockerd 2>/dev/null || true",
            "  pkill containerd 2>/dev/null || true",
            "  rm -f /var/run/docker.pid /var/run/docker.sock",
            "  nohup dockerd --host=unix:///var/run/docker.sock >/tmp/damru-dockerd.log 2>/tmp/damru-dockerd.err &",
            "  for i in {1..15}; do",
            "    docker info >/dev/null 2>/dev/null && break",
            "    sleep 2",
            "  done",
            "fi",
            "if ! docker info >/dev/null 2>/dev/null; then",
            "  pkill dockerd 2>/dev/null || true",
            "  pkill containerd 2>/dev/null || true",
            "  rm -f /var/run/docker.sock",
            "  nohup dockerd --iptables=false --ip6tables=false --bridge=none --host=unix:///var/run/docker.sock >/tmp/damru-dockerd-noiptables.log 2>/tmp/damru-dockerd-noiptables.err &",
            "  for i in {1..60}; do",
            "    docker info >/dev/null 2>/dev/null && break",
            "    sleep 2",
            "  done",
            "fi",
            *self._docker_bridge_nat_repair_script_lines(),
        ])
        return self._wsl_sudo_cmd(script)

    def _docker_bridge_nat_repair_script_lines(self) -> List[str]:
        """Targeted WSL Docker bridge repair after host-network Android rules."""
        return wsl_runtime_network_repair_lines()

    async def _repair_docker_bridge_nat(self) -> None:
        if not self._is_windows:
            return
        await self._run_cmd(
            self._wsl_sudo_cmd("\n".join(["set +e", *self._docker_bridge_nat_repair_script_lines()])),
            timeout=20,
            allow_failure=True,
        )

    async def _docker_bridge_available(self) -> bool:
        """Return True when Docker's default bridge network exists."""
        out = await self._run_cmd(
            self._docker_cmd("network", "ls", "--format", "{{.Name}}"),
            timeout=10,
            allow_failure=True,
        )
        return "bridge" in {line.strip() for line in out.splitlines()}

    async def _kernel_config_text(self) -> str:
        script = "\n".join([
            "set +e",
            "if [ -r /proc/config.gz ]; then zcat /proc/config.gz; fi",
            "if [ -r /boot/config-$(uname -r) ]; then cat /boot/config-$(uname -r); fi",
        ])
        return await self._run_cmd(
            self._wsl_sudo_cmd(script),
            timeout=10,
            allow_failure=True,
        )

    async def _binderfs_mount_status(self) -> tuple[bool, bool]:
        script = "\n".join([
            "set +e",
            "mounted=0",
            "populated=0",
            "mount | grep -q ' /dev/binderfs ' && mounted=1",
            "if [ -e /dev/binderfs/binder-control ] && [ -e /dev/binderfs/binder ] && [ -e /dev/binderfs/hwbinder ] && [ -e /dev/binderfs/vndbinder ]; then populated=1; fi",
            "printf '%s %s' \"$mounted\" \"$populated\"",
        ])
        out = await self._run_cmd(
            self._wsl_sudo_cmd(script),
            timeout=10,
            allow_failure=True,
        )
        parts = out.strip().split()
        return len(parts) >= 2 and parts[0] == "1", len(parts) >= 2 and parts[1] == "1"

    async def validate_redroid_multi_container_support(self, count: int) -> None:
        """Fail early when host binder support is unsafe for multiple Redroid workers."""
        if count <= 1:
            return

        await self._ensure_binderfs()
        mounted, populated = await self._binderfs_mount_status()
        config = await self._kernel_config_text()
        binderfs = _kernel_config_enabled(config, "CONFIG_ANDROID_BINDERFS")
        binder_ipc = _kernel_config_enabled(config, "CONFIG_ANDROID_BINDER_IPC")

        problems: list[str] = []
        if binder_ipc is False:
            problems.append("CONFIG_ANDROID_BINDER_IPC is disabled")
        if binderfs is False:
            problems.append("CONFIG_ANDROID_BINDERFS is disabled")
        if not mounted:
            problems.append("/dev/binderfs is not mounted as binderfs")
        if mounted and not populated:
            problems.append("/dev/binderfs is mounted but has no binder-control/binder entries")

        if problems:
            raise DamruError(
                "This host is not safe for multiple Redroid containers. "
                "Docker may start several containers and ADB may list them, but Android "
                "userspace can fail later with zygote/system_server/WebView/CDP errors.\n"
                "Detected problem(s):\n  - " + "\n  - ".join(problems) + "\n"
                "Use max_devices=1 on this host, or boot a Linux/WSL2 kernel with "
                "CONFIG_ANDROID_BINDER_IPC and CONFIG_ANDROID_BINDERFS enabled and mount "
                "binderfs at /dev/binderfs."
            )

    async def _ensure_wsl_main_route_rule(self) -> None:
        """Repair WSL policy routing after privileged host-network Redroid.

        Redroid in host-network mode can leave Android policy rules in the WSL
        host namespace, including an `unreachable` rule before Linux's normal
        `lookup main` rule. That makes apt/curl fail with "Network is
        unreachable" even though eth0 and the default route still exist.
        """
        if not self._is_windows:
            return
        script = "\n".join([
            "set +e",
            "if ip rule show | grep -q '32000:.*unreachable' && ! ip rule show | grep -q '31999:.*lookup main'; then",
            "  ip rule add pref 31999 lookup main 2>/dev/null || true",
            "fi",
            "if ! ip route show default | grep -q .; then",
            "  set -- $(ip -4 -o addr show eth0)",
            "  ip=${4%/*}",
            "  o1=${ip%%.*}; rest=${ip#*.}",
            "  o2=${rest%%.*}; rest=${rest#*.}",
            "  o3=${rest%%.*}",
            "  gw=$o1.$o2.$((o3 / 16 * 16)).1",
            "  [ -n \"$gw\" ] && ip route replace default via \"$gw\" dev eth0 2>/dev/null || true",
            "fi",
        ])
        await self._run_cmd(
            self._wsl_sudo_cmd(script),
            timeout=10,
            allow_failure=True,
        )

    async def _detect_cross_distro_host_redroid_conflict(self) -> list[str]:
        """Find running host-network Redroid containers in other WSL distros."""
        if not self._is_windows:
            return []
        try:
            proc = await asyncio.create_subprocess_exec(
                "wsl", "-l", "-q",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            if stdout.startswith(b"\xff\xfe") or stdout.count(b"\x00") > max(0, len(stdout) // 4):
                raw = stdout.decode("utf-16le", errors="ignore")
            else:
                raw = stdout.decode(errors="ignore").replace("\x00", "")
            distros = [line.strip(" \r") for line in raw.splitlines() if line.strip(" \r")]
        except Exception:
            return []

        conflicts: list[str] = []
        for distro in distros:
            if distro == self._wsl_distro:
                continue
            try:
                proc = await asyncio.create_subprocess_exec(
                    "wsl", "-d", distro, "-u", "root", "--", "bash", "-lc",
                    "docker ps --filter network=host --format '{{.Names}} {{.Image}}' 2>/dev/null | grep -E '(^| )damru-|redroid' || true",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                text = stdout.decode(errors="replace").strip()
                if text:
                    for line in text.splitlines():
                        conflicts.append(f"{distro}: {line}")
            except Exception:
                continue
        return conflicts

    def _should_use_host_network(self) -> bool:
        """Return True when Redroid should share the WSL host network.

        WSL host networking lets Android netd mutate the WSL namespace
        directly, which repeatedly breaks eth0/default route/DNS. Docker bridge
        keeps Android networking isolated while published ADB ports remain
        reachable from the WSL-side adb client.
        """
        return False

    async def _container_network_mode(self, name: str) -> str:
        out = await self._run_cmd(
            self._docker_cmd("inspect", "-f", "{{.HostConfig.NetworkMode}}", name),
            timeout=10,
            allow_failure=True,
        )
        return out.strip()

    async def _container_entrypoint_path(self, name: str) -> str:
        out = await self._run_cmd(
            self._docker_cmd("inspect", "-f", "{{.Path}}", name),
            timeout=10,
            allow_failure=True,
        )
        return out.strip()

    async def _run_cmd(
        self,
        cmd: List[str],
        timeout: float = DOCKER_CMD_TIMEOUT,
        allow_failure: bool = False,
    ) -> str:
        """Run a shell command and return stdout."""
        logger.debug("cmd: %s", " ".join(cmd))
        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            if proc is not None and proc.returncode is None:
                with suppress(ProcessLookupError):
                    proc.kill()
                with suppress(Exception):
                    await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if isinstance(exc, asyncio.CancelledError):
                raise
            if allow_failure:
                return ""
            raise DamruError(f"Command timed out: {' '.join(cmd)}")

        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0 and not allow_failure:
            detail = "\n".join(part for part in (out, err) if part)
            suffix = f"\n{detail}" if detail else ""
            raise DamruError(f"Command failed: {' '.join(cmd)}{suffix}")

        return out

    # ── Docker check + auto-install ──

    async def check_docker(self) -> None:
        """Verify Docker is available. Auto-installs if missing.

        Windows: checks WSL2 distro, loads kernel modules, mounts binderfs,
                 installs docker.io if needed, starts daemon.
        Linux: installs docker.io if needed, starts daemon.
        """
        if self._is_windows:
            await self._ensure_wsl_distro()
            await self._ensure_wsl_main_route_rule()

        # Load kernel modules needed for Docker + redroid
        await self._load_kernel_modules()

        # Mount binderfs if not already mounted
        await self._ensure_binderfs()

        # Check if docker is already working
        try:
            out = await self._run_cmd(
                self._docker_cmd("info", "--format", "{{.OSType}}"),
                timeout=15,
            )
            if "linux" in out.lower():
                await self._repair_docker_bridge_nat()
                logger.info(
                    "Docker OK (%s)",
                    f"WSL2: {self._wsl_distro}" if self._is_windows else "native Linux",
                )
                return
        except DamruError:
            pass

        # Docker not working — try to start daemon first
        logger.info("Docker not responding, attempting to start daemon...")
        await self._run_cmd(
            self._start_docker_cmd(),
            timeout=30, allow_failure=True,
        )

        # Re-check
        try:
            out = await self._run_cmd(
                self._docker_cmd("info", "--format", "{{.OSType}}"),
                timeout=15,
            )
            if "linux" in out.lower():
                await self._repair_docker_bridge_nat()
                logger.info("Docker started successfully")
                return
        except DamruError:
            pass

        # Still not working — auto-install
        logger.info("Docker not installed, auto-installing...")
        await self._auto_install_docker()

    async def _load_kernel_modules(self) -> None:
        """Load kernel modules needed for Docker networking and redroid."""
        modules = [
            "nf_tables", "nft_compat", "nft_nat", "nft_masq",
            "ip_tables", "iptable_nat", "iptable_filter", "iptable_raw",
            "iptable_mangle", "nf_nat", "nf_conntrack",
            "xt_nat", "xt_addrtype", "xt_conntrack", "xt_owner",
            "xt_MASQUERADE", "ipt_MASQUERADE", "bridge", "br_netfilter", "veth",
            "tun",  # for tun2socks (future WebRTC proxy spoofing)
        ]
        # depmod -a first to ensure module dependencies are resolved
        await self._run_cmd(
            self._wsl_sudo_cmd("depmod -a"),
            timeout=10, allow_failure=True,
        )
        for mod in modules:
            await self._run_cmd(
                self._wsl_sudo_cmd(f"modprobe {mod}"),
                timeout=5, allow_failure=True,
            )
        logger.debug("Kernel modules loaded")

    async def _ensure_binderfs(self) -> None:
        """Mount binderfs at /dev/binderfs if not already mounted."""
        script = "\n".join([
            "set +e",
            "modprobe binder_linux devices=binder,hwbinder,vndbinder 2>/dev/null || true",
            "mkdir -p /dev/binderfs",
            "if mount | grep -q ' /dev/binderfs ' && [ -e /dev/binderfs/binder-control ] && [ -e /dev/binderfs/binder ] && [ -e /dev/binderfs/hwbinder ] && [ -e /dev/binderfs/vndbinder ]; then exit 0; fi",
            "if mount | grep -q ' /dev/binderfs ' && [ ! -e /dev/binderfs/binder-control ]; then umount /dev/binderfs >/dev/null 2>&1 || true; fi",
            "mount | grep -q ' /dev/binderfs ' || mount -t binder binder /dev/binderfs >/dev/null 2>&1 || true",
            "test -e /dev/binderfs/binder-control && test -e /dev/binderfs/binder && test -e /dev/binderfs/hwbinder && test -e /dev/binderfs/vndbinder",
        ])
        await self._run_cmd(
            self._wsl_sudo_cmd(script),
            timeout=10, allow_failure=True,
        )
        mounted, populated = await self._binderfs_mount_status()
        if mounted and populated:
            logger.info("Binderfs mounted at /dev/binderfs")
        else:
            logger.warning(
                "Binderfs mount failed — redroid may not work. "
                "Ensure kernel has CONFIG_ANDROID_BINDERFS=y"
            )

    async def _ensure_wsl_distro(self) -> None:
        """Verify WSL2 distro exists on Windows."""
        try:
            out = await self._run_cmd(
                ["wsl", "--list", "--quiet"], timeout=10,
            )
        except Exception:
            raise DamruError(
                "WSL2 not available. Install:\n  wsl --install -d Ubuntu"
            )

        distros = [
            line.strip()
            for line in out.replace("\x00", "").splitlines()
            if line.strip() and "docker-desktop" not in line.strip().lower()
        ]

        if self._wsl_distro not in distros and distros:
            logger.warning(
                "Configured distro '%s' not found, available: %s",
                self._wsl_distro, distros,
            )
            self._wsl_distro = distros[0]
            logger.info("Using WSL2 distro: %s", self._wsl_distro)
        elif not distros:
            raise DamruError(
                f"No WSL2 distro found (need '{self._wsl_distro}').\n"
                f"Install: wsl --install -d {self._wsl_distro}"
            )

    async def _auto_install_docker(self) -> None:
        """Auto-install Docker inside WSL2 (or native Linux)."""
        steps = [
            ("apt-get update -y", 120),
            ("apt-get install -y docker.io cpio", 300),
            # Docker's addrtype NAT rule can fail on WSL's nft backend even when
            # the kernel supports it. Prefer legacy when available, otherwise nft.
            ("if command -v iptables-legacy >/dev/null 2>&1; then update-alternatives --set iptables /usr/sbin/iptables-legacy; elif command -v iptables-nft >/dev/null 2>&1; then update-alternatives --set iptables /usr/sbin/iptables-nft; fi", 10),
            ("if command -v ip6tables-legacy >/dev/null 2>&1; then update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy; elif command -v ip6tables-nft >/dev/null 2>&1; then update-alternatives --set ip6tables /usr/sbin/ip6tables-nft; fi", 10),
            (f"usermod -aG docker {self._wsl_user}", 10),
        ]

        for cmd, timeout in steps:
            logger.info("  -> %s", cmd)
            try:
                await self._run_cmd(
                    self._wsl_sudo_cmd(cmd),
                    timeout=timeout,
                )
            except DamruError as e:
                # usermod failure is non-fatal
                if "usermod" in cmd:
                    logger.warning("usermod failed (non-fatal): %s", e)
                else:
                    raise DamruError(f"Docker auto-install failed at: {cmd}\n{e}")

        logger.info("  -> start docker daemon")
        await self._run_cmd(
            self._start_docker_cmd(),
            timeout=30,
            allow_failure=True,
        )

        # Verify it works now
        try:
            out = await self._run_cmd(
                self._docker_cmd("info", "--format", "{{.OSType}}"),
                timeout=15,
            )
            if "linux" not in out.lower():
                raise DamruError("Docker installed but not returning Linux OS type")
        except DamruError:
            raise DamruError(
                "Docker auto-install completed but daemon won't start.\n"
                "Try manually: wsl -d {self._wsl_distro} sudo service docker start"
            )

        await self._repair_docker_bridge_nat()
        logger.info("Docker auto-installed and running!")

    # ── Image management ──

    async def _image_exists(self, image: str) -> bool:
        """Return True if a Docker image is present locally."""
        out = await self._run_cmd(
            self._docker_cmd("images", "-q", image),
            timeout=10, allow_failure=True,
        )
        return bool(out.strip())

    async def ensure_image(self, image: str) -> None:
        """Ensure a Docker image is available locally, pulling if missing.

        The launch image (REDROID_IMAGE) is normally baked by
        scripts/bake_image.py. When it is missing, fall back to pulling
        REDROID_BASE_IMAGE and tagging it as the launch image — unbaked but
        functional (cold starts stay slow until baked). For any other image,
        pull it and raise DamruError on failure rather than letting the later
        `docker run` crash with an opaque "No such image".
        """
        if await self._image_exists(image):
            logger.debug("Image %s present", image)
            return

        if image == REDROID_IMAGE:
            local_tar = Path(__file__).resolve().parent.parent / "damru-redroid-latest.tar"
            if local_tar.exists():
                logger.info("Loading baked image %s from %s", image, local_tar)
                tar_arg = self._to_wsl_path(str(local_tar)) if self._is_windows else str(local_tar)
                await self._run_cmd(
                    self._docker_cmd("load", "-i", tar_arg),
                    timeout=1200,
                )
                if await self._image_exists(image):
                    return
            logger.warning(
                "Baked image %s missing; pulling base %s as unbaked fallback",
                image, REDROID_BASE_IMAGE,
            )
            await self._run_cmd(
                self._docker_cmd("pull", REDROID_BASE_IMAGE),
                timeout=600,
            )
            await self._run_cmd(
                self._docker_cmd("tag", REDROID_BASE_IMAGE, image),
                timeout=10,
            )
            logger.warning(
                "Using unbaked %s. For faster cold starts: python scripts/bake_image.py",
                image,
            )
            return

        logger.info("Pulling image %s...", image)
        try:
            await self._run_cmd(
                self._docker_cmd("pull", image),
                timeout=600,
            )
        except DamruError as e:
            raise DamruError(
                f"Image {image} is missing and could not be pulled.\n{e}"
            )

    async def _sensor_hal_present(self, serial: str) -> bool:
        name_port = self._container_name_port_for_serial(serial)
        if name_port is not None:
            name, _ = name_port
            aidl = await self._run_cmd(
                self._docker_cmd(
                    "exec", name, "sh", "-lc",
                    "test -x /vendor/bin/hw/android.hardware.sensors-service.damru && "
                    "test -f /vendor/etc/vintf/manifest/damru-sensors.xml && "
                    "ps -A | grep -q android.hardware.sensors-service.damru && echo ready",
                ),
                timeout=10,
                allow_failure=True,
            )
            if aidl.strip() == "ready":
                return True
            files = await self._run_cmd(
                self._docker_cmd(
                    "exec", name, "sh", "-lc",
                    f"test -x /vendor/bin/hw/{_SENSOR_MOCK_BIN} && "
                    "test -f /vendor/etc/vintf/manifest/android.hardware.sensors@2.1.xml && echo ready",
                ),
                timeout=10,
                allow_failure=True,
            )
            if files.strip() == "ready":
                return True
            lshal = await self._run_cmd(
                self._docker_cmd("exec", name, "sh", "-lc", "lshal 2>/dev/null | grep -i 'android.hardware.sensors@2.1::ISensors/default'"),
                timeout=10,
                allow_failure=True,
            )
            if lshal.strip():
                return True
        out = await self._run_cmd(
            self._adb_cmd("shell", "dumpsys", "sensorservice", serial=serial),
            timeout=10,
            allow_failure=True,
        )
        return "BMI270 Accelerometer" in out
    async def _ensure_sensor_mock_assets(self) -> str:
        """Return a WSL/Linux path containing Redroid's HIDL mock sensor HAL."""
        asset_dir = "/tmp/damru-redroid11-sensors"
        marker = f"{asset_dir}/vendor/bin/hw/{_SENSOR_MOCK_BIN}"
        check = await self._run_cmd(
            self._wsl_sudo_cmd(f"test -s {shlex.quote(marker)} && echo ready"),
            timeout=10,
            allow_failure=True,
        )
        if check.strip() == "ready":
            return asset_dir

        logger.info("Preparing Redroid HIDL sensor mock assets from %s", _REDROID_SENSOR_SOURCE_IMAGE)
        await self._run_cmd(self._docker_cmd("pull", _REDROID_SENSOR_SOURCE_IMAGE), timeout=900)
        cid = (await self._run_cmd(self._docker_cmd("create", _REDROID_SENSOR_SOURCE_IMAGE), timeout=30)).strip()
        if not cid:
            raise DamruError(f"Could not create temporary container from {_REDROID_SENSOR_SOURCE_IMAGE}")
        try:
            await self._run_cmd(self._wsl_sudo_cmd(f"rm -rf {asset_dir}; mkdir -p {asset_dir}/vendor/bin/hw {asset_dir}/vendor/etc/init {asset_dir}/vendor/etc/vintf/manifest"), timeout=20)
            for src, dst in (
                (f"/vendor/bin/hw/{_SENSOR_MOCK_BIN}", f"{asset_dir}/vendor/bin/hw/{_SENSOR_MOCK_BIN}"),
                ("/vendor/etc/init/android.hardware.sensors@2.1-service-mock.rc", f"{asset_dir}/vendor/etc/init/android.hardware.sensors@2.1-service-mock.rc"),
                ("/vendor/etc/vintf/manifest/android.hardware.sensors@2.1.xml", f"{asset_dir}/vendor/etc/vintf/manifest/android.hardware.sensors@2.1.xml"),
            ):
                await self._run_cmd(self._docker_cmd("cp", f"{cid}:{src}", dst), timeout=60)
        finally:
            await self._run_cmd(self._docker_cmd("rm", "-f", cid), timeout=20, allow_failure=True)
        return asset_dir

    async def _install_hidl_sensor_hal(self, name: str, serial: Optional[str] = None) -> None:
        """Install HIDL sensor HAL files into a Redroid container rootfs."""
        asset_dir = await self._ensure_sensor_mock_assets()
        init_dir = Path(__file__).resolve().parent.parent / "native" / "sensors" / "init"
        sensorservice_rc = self._to_wsl_path(str(init_dir / "sensorservice.rc")) if self._is_windows else str(init_dir / "sensorservice.rc")

        await self._run_cmd(self._docker_cmd("exec", name, "mkdir", "-p", "/vendor/bin/hw", "/vendor/etc/init", "/vendor/etc/vintf/manifest", "/system/etc/init"), timeout=20)
        await self._run_cmd(self._docker_cmd("cp", f"{asset_dir}/vendor/bin/hw/{_SENSOR_MOCK_BIN}", f"{name}:/vendor/bin/hw/{_SENSOR_MOCK_BIN}"), timeout=60)
        await self._run_cmd(self._docker_cmd("cp", f"{asset_dir}/vendor/etc/init/android.hardware.sensors@2.1-service-mock.rc", f"{name}:/vendor/etc/init/android.hardware.sensors@2.1-service-mock.rc"), timeout=60)
        await self._run_cmd(self._docker_cmd("cp", f"{asset_dir}/vendor/etc/vintf/manifest/android.hardware.sensors@2.1.xml", f"{name}:/vendor/etc/vintf/manifest/android.hardware.sensors@2.1.xml"), timeout=60)
        await self._run_cmd(self._docker_cmd("cp", sensorservice_rc, f"{name}:/system/etc/init/sensorservice.rc"), timeout=60)

        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        manifest_tmp = f"/tmp/damru-{safe_name}-manifest.xml"
        if await self._run_cmd(self._docker_cmd("cp", f"{name}:/vendor/etc/vintf/manifest.xml", manifest_tmp), timeout=20, allow_failure=True) is not None:
            await self._run_cmd(
                self._wsl_sudo_cmd(
                    "perl -0pi -e "
                    + shlex.quote(r's#\s*<hal format="aidl">\s*<name>android\.hardware\.sensors</name>.*?</hal>\s*#\n#sg')
                    + f" {shlex.quote(manifest_tmp)}"
                ),
                timeout=20,
                allow_failure=True,
            )
            await self._run_cmd(self._docker_cmd("cp", manifest_tmp, f"{name}:/vendor/etc/vintf/manifest.xml"), timeout=20, allow_failure=True)

        rc_tmp = f"/tmp/damru-{safe_name}-redroid.common.rc"
        if await self._run_cmd(self._docker_cmd("cp", f"{name}:/vendor/etc/init/redroid.common.rc", rc_tmp), timeout=20, allow_failure=True) is not None:
            await self._run_cmd(
                self._wsl_sudo_cmd(
                    f"if grep -q 'Damru synthetic sensors HAL' {shlex.quote(rc_tmp)} 2>/dev/null; then "
                    f"awk '/# Damru synthetic sensors HAL:{{exit}} {{print}}' {shlex.quote(rc_tmp)} > {shlex.quote(rc_tmp)}.clean && "
                    f"mv {shlex.quote(rc_tmp)}.clean {shlex.quote(rc_tmp)}; fi"
                ),
                timeout=20,
                allow_failure=True,
            )
            await self._run_cmd(self._docker_cmd("cp", rc_tmp, f"{name}:/vendor/etc/init/redroid.common.rc"), timeout=20, allow_failure=True)

        # Vendor namespace must see the HIDL sensor interface libraries. Copy only
        # the three interface libs; copying generic system libs into /vendor can
        # destabilize other HAL services.
        copy_libs = "; ".join(
            f"cp /system/lib64/{lib} /vendor/lib64/{lib} 2>/dev/null || true"
            for lib in (
                "android.hardware.sensors@1.0.so",
                "android.hardware.sensors@2.0.so",
                "android.hardware.sensors@2.1.so",
            )
        )
        cleanup = " && ".join([
            "rm -f /vendor/etc/vintf/manifest/damru-sensors.xml /vendor/etc/init/android.hardware.sensors-service.damru.rc /vendor/bin/hw/android.hardware.sensors-service.damru",
            copy_libs,
            f"chmod 755 /vendor/bin/hw/{_SENSOR_MOCK_BIN}",
            "chmod 644 /vendor/etc/init/android.hardware.sensors@2.1-service-mock.rc /vendor/etc/vintf/manifest/android.hardware.sensors@2.1.xml /system/etc/init/sensorservice.rc",
        ])
        await self._run_cmd(self._docker_cmd("exec", name, "sh", "-lc", cleanup), timeout=60)

        if serial:
            await self._run_cmd(self._adb_cmd("push", f"{asset_dir}/vendor/bin/hw/{_SENSOR_MOCK_BIN}", "/data/local/tmp/damru-sensors-mock", serial=serial), timeout=60)
            await self._run_cmd(self._adb_cmd("push", f"{asset_dir}/vendor/etc/init/android.hardware.sensors@2.1-service-mock.rc", "/data/local/tmp/damru-sensors-mock.rc", serial=serial), timeout=60)
            await self._run_cmd(self._adb_cmd("push", f"{asset_dir}/vendor/etc/vintf/manifest/android.hardware.sensors@2.1.xml", "/data/local/tmp/damru-sensors-21.xml", serial=serial), timeout=60)
            await self._run_cmd(self._adb_cmd("push", sensorservice_rc, "/data/local/tmp/damru-sensorservice.rc", serial=serial), timeout=60)
            adb_install = " && ".join([
                "mkdir -p /vendor/bin/hw /vendor/etc/init /vendor/etc/vintf/manifest /system/etc/init",
                f"cp /data/local/tmp/damru-sensors-mock /vendor/bin/hw/{_SENSOR_MOCK_BIN}",
                "cp /data/local/tmp/damru-sensors-mock.rc /vendor/etc/init/android.hardware.sensors@2.1-service-mock.rc",
                "cp /data/local/tmp/damru-sensors-21.xml /vendor/etc/vintf/manifest/android.hardware.sensors@2.1.xml",
                "cp /data/local/tmp/damru-sensorservice.rc /system/etc/init/sensorservice.rc",
                "rm -f /vendor/etc/vintf/manifest/damru-sensors.xml /vendor/etc/init/android.hardware.sensors-service.damru.rc /vendor/bin/hw/android.hardware.sensors-service.damru",
                "cp /system/lib64/android.hardware.sensors@1.0.so /vendor/lib64/android.hardware.sensors@1.0.so 2>/dev/null || true",
                "cp /system/lib64/android.hardware.sensors@2.0.so /vendor/lib64/android.hardware.sensors@2.0.so 2>/dev/null || true",
                "cp /system/lib64/android.hardware.sensors@2.1.so /vendor/lib64/android.hardware.sensors@2.1.so 2>/dev/null || true",
                f"chmod 755 /vendor/bin/hw/{_SENSOR_MOCK_BIN}",
                "chmod 644 /vendor/etc/init/android.hardware.sensors@2.1-service-mock.rc /vendor/etc/vintf/manifest/android.hardware.sensors@2.1.xml /system/etc/init/sensorservice.rc /vendor/lib64/android.hardware.sensors@1.0.so /vendor/lib64/android.hardware.sensors@2.0.so /vendor/lib64/android.hardware.sensors@2.1.so 2>/dev/null || true",
            ])
            await self._run_cmd(self._adb_cmd("shell", "su", "0", "sh", "-c", adb_install, serial=serial), timeout=60)

    async def _install_aidl_sensor_hal(self, name: str, serial: str) -> None:
        """Install Damru's Android 14 AIDL sensor HAL into a Redroid container."""
        root = Path(__file__).resolve().parent.parent
        script = root / "native" / "sensors" / "install_sensors_hal.sh"
        if not script.exists():
            raise DamruError(f"Native sensor HAL installer missing: {script}")
        plain_serial = self._plain_serial(serial)
        if self._is_windows:
            script_path = self._to_wsl_path(str(script))
            repo_root = self._to_wsl_path(str(root))
            cmd = (
                f"cd {shlex.quote(repo_root)} && "
                f"DAMRU_SENSOR_ADB_SERIAL={shlex.quote(plain_serial)} "
                f"bash {shlex.quote(script_path)}"
            )
            await self._run_cmd(self._wsl_sudo_cmd(cmd), timeout=300)
        else:
            cmd = (
                f"cd {shlex.quote(str(root))} && "
                f"DAMRU_SENSOR_ADB_SERIAL={shlex.quote(plain_serial)} "
                f"bash {shlex.quote(str(script))}"
            )
            await self._run_cmd(["bash", "-lc", cmd], timeout=300)

    async def _install_input_node_boot_repair(self, name: str) -> None:
        """Install the boot-time /dev/input materializer into a container rootfs."""
        root = Path(__file__).resolve().parent.parent
        input_dir = root / "native" / "input"
        script = input_dir / "damru-input-node-fix.sh"
        rc_file = input_dir / "damru-input-node-fix.rc"
        if not script.exists() or not rc_file.exists():
            raise DamruError(f"Native input-node repair assets missing under {input_dir}")

        script_src = self._to_wsl_path(str(script)) if self._is_windows else str(script)
        rc_src = self._to_wsl_path(str(rc_file)) if self._is_windows else str(rc_file)
        await self._run_cmd(
            self._docker_cmd("exec", name, "mkdir", "-p", "/system/bin", "/system/etc/init"),
            timeout=20,
        )
        await self._run_cmd(self._docker_cmd("cp", script_src, f"{name}:{_INPUT_NODE_FIX_SCRIPT}"), timeout=60)
        await self._run_cmd(self._docker_cmd("cp", rc_src, f"{name}:{_INPUT_NODE_FIX_RC}"), timeout=60)
        await self._run_cmd(
            self._docker_cmd(
                "exec",
                name,
                "sh",
                "-lc",
                f"chmod 755 {_INPUT_NODE_FIX_SCRIPT}; chmod 644 {_INPUT_NODE_FIX_RC}",
            ),
            timeout=20,
        )

    async def _ensure_sensor_hal(self, serial: str, container_name: Optional[str] = None) -> bool:
        """Install Damru's native sensor HAL into the running Redroid image.

        Returns True when an install/restart was performed.
        """
        enable_aidl = (
            os.environ.get("DAMRU_ENABLE_NATIVE_SENSOR_HAL") == "1"
            or os.environ.get("DAMRU_EXPERIMENTAL_SENSOR_HAL", "1") == "1"
        )
        enable_hidl = os.environ.get("DAMRU_EXPERIMENTAL_HIDL_SENSOR_HAL", "1") == "1"
        if not enable_aidl and not enable_hidl:
            return False
        if await self._sensor_hal_present(serial):
            return False

        target_name = container_name
        if target_name is None:
            target = self._container_name_port_for_serial(serial)
            if target is not None:
                target_name = target[0]
        if target_name is None:
            logger.warning("Cannot map %s to a Damru container for sensor HAL install", serial)
            return False

        if enable_hidl:
            logger.info("Installing experimental HIDL sensor HAL into %s", target_name)
            await self._install_hidl_sensor_hal(target_name, serial=serial)
        else:
            logger.info("Installing native AIDL sensor HAL into %s", target_name)
            await self._install_aidl_sensor_hal(target_name, serial)
        return True
    # ── Container lifecycle ──

    async def _commit_sensor_hal_and_recreate(self, name: str, index: int) -> str:
        """Persist the HAL install, then boot a fresh container from it."""
        logger.info("Committing %s after native sensor HAL install", name)
        await self._run_cmd(
            self._docker_cmd("commit", name, REDROID_IMAGE),
            timeout=180,
        )
        await self._run_cmd(
            self._docker_cmd("rm", "-f", name),
            timeout=15,
            allow_failure=True,
        )
        return await self.start_container(index)

    async def _get_container_state(self, name: str) -> str:
        """Check container state. Returns 'running', 'exited', or 'none'."""
        out = await self._run_cmd(
            self._docker_cmd("inspect", "-f", "{{.State.Status}}", name),
            timeout=10, allow_failure=True,
        )
        status = out.strip().lower()
        if status in ("running", "exited", "created", "paused"):
            return status
        return "none"

    async def _container_exit_code(self, name: str) -> str:
        out = await self._run_cmd(
            self._docker_cmd("inspect", "-f", "{{.State.ExitCode}}", name),
            timeout=10,
            allow_failure=True,
        )
        return out.strip()

    def _boot_timeout_for_index(self, index: int) -> float:
        """Return a realistic Redroid boot timeout for the requested worker.

        WSL host-network workers are started sequentially but share CPU and I/O
        with every already-running Android userspace. Higher indexes can be
        healthy yet take longer than the default single-worker timeout before
        `sys.boot_completed` flips.
        """
        if self._is_windows and self._should_use_host_network():
            return float(max(CONTAINER_BOOT_TIMEOUT, min(600, CONTAINER_BOOT_TIMEOUT + (max(0, index) * 30))))
        return float(CONTAINER_BOOT_TIMEOUT)

    async def ensure_container(self, index: int) -> str:
        """Ensure container exists and is running. Reuses if possible.

        Returns ADB serial (HOST:PORT).
        """
        # Always verify binderfs before container operations — containers
        # crash (exit 255) when binderfs gets unmounted underneath them.
        await self._ensure_binderfs()

        name = f"{REDROID_CONTAINER_PREFIX}{index}"
        port = REDROID_BASE_PORT + index
        use_host_network = self._should_use_host_network()
        boot_timeout = self._boot_timeout_for_index(index)
        if use_host_network:
            conflicts = await self._detect_cross_distro_host_redroid_conflict()
            if conflicts:
                joined = "\n  ".join(conflicts)
                raise DamruError(
                    "Another WSL distro already has host-network Redroid containers running. "
                    "WSL host-network Redroid shares kernel sockets, so a second distro can fail "
                    "during Android boot (for example vold uevent socket address-in-use). "
                    "Stop those containers or use that same WSL distro before starting this one:\n  " + joined
                )
        state = await self._get_container_state(name)

        if state != "none":
            network_mode = await self._container_network_mode(name)
            if (use_host_network and network_mode != "host") or (not use_host_network and network_mode == "host"):
                target = "host" if use_host_network else "bridge"
                logger.warning("Recreating %s with %s networking", name, target)
                await self.stop_container(index)
                state = "none"

        if state == "running":
            if use_host_network:
                entrypoint = await self._container_entrypoint_path(name)
                if entrypoint != "/damru-redroid-init":
                    logger.info("Recreating running stale WSL host-network container %s with Damru init wrapper", name)
                    await self._run_cmd(
                        self._docker_cmd("rm", "-f", name),
                        timeout=15,
                        allow_failure=True,
                    )
                    return await self.start_container(index)
            # Container already running — just ensure ADB connected
            logger.info("Reusing running container %s", name)
            if use_host_network:
                await self._wait_for_container_boot_internal(name, timeout=boot_timeout)
                await self._remap_adbd_port(name, port)
                await self._repair_docker_bridge_nat()
            serial = await self._serial_for_container(name, port, use_host_network)
            await self._run_cmd(
                self._adb_cmd("connect", serial),
                timeout=10, allow_failure=True,
            )
            await self._wait_for_boot(serial, name=name, timeout=boot_timeout)
            await self._repair_docker_bridge_nat()
            try:
                await self._wait_for_package_service(serial, timeout=60)
            except DamruError as exc:
                logger.warning("Recreating unhealthy %s: %s", name, exc)
                return await self.restart_container(index)
            try:
                await self._wait_for_touchscreen_input(serial)
            except DamruError as exc:
                logger.warning("Recreating unhealthy %s: %s", name, exc)
                return await self.restart_container(index)
            if not await self._wait_for_android_dns_usable(serial):
                logger.warning("Android DNS not fully confirmed on %s after repair; reusing %s", serial, name)
            if await self._ensure_sensor_hal(serial):
                logger.info("Restarting %s to activate native sensor HAL", name)
                return await self._commit_sensor_hal_and_recreate(name, index)
            if index not in self._started_indices:
                self._started_indices.append(index)
            return serial

        elif state in ("exited", "created", "paused"):
            if state == "exited" and await self._container_exit_code(name) == "130":
                logger.info("Recreating stale %s after SIGINT exit", name)
                await self._run_cmd(
                    self._docker_cmd("rm", "-f", name),
                    timeout=15,
                    allow_failure=True,
                )
                return await self.start_container(index)
            if use_host_network and state in {"exited", "created"}:
                entrypoint = await self._container_entrypoint_path(name)
                if entrypoint != "/damru-redroid-init":
                    logger.info("Recreating stale WSL host-network container %s with Damru init wrapper", name)
                    await self._run_cmd(
                        self._docker_cmd("rm", "-f", name),
                        timeout=15,
                        allow_failure=True,
                    )
                    return await self.start_container(index)
            # Container exists but stopped — restart it
            logger.info("Restarting stopped container %s...", name)
            await self._run_cmd(
                self._docker_cmd("start", name),
                timeout=30, allow_failure=True,
            )
            if use_host_network:
                await self._wait_for_container_boot_internal(name, timeout=boot_timeout)
                await self._remap_adbd_port(name, port)
                await self._repair_docker_bridge_nat()
            serial = await self._serial_for_container(name, port, use_host_network)
            await self._run_cmd(
                self._adb_cmd("connect", serial),
                timeout=10, allow_failure=True,
            )
            await self._wait_for_boot(serial, name=name, timeout=boot_timeout)
            await self._repair_docker_bridge_nat()
            try:
                await self._wait_for_package_service(serial, timeout=60)
            except DamruError as exc:
                logger.warning("Recreating unhealthy %s: %s", name, exc)
                return await self.restart_container(index)
            try:
                await self._wait_for_touchscreen_input(serial)
            except DamruError as exc:
                logger.warning("Recreating unhealthy %s: %s", name, exc)
                return await self.restart_container(index)
            if not await self._wait_for_android_dns_usable(serial):
                logger.warning("Android DNS not fully confirmed on %s after repair; reusing %s", serial, name)
            if await self._ensure_sensor_hal(serial):
                logger.info("Restarting %s to activate native sensor HAL", name)
                return await self._commit_sensor_hal_and_recreate(name, index)
            if index not in self._started_indices:
                self._started_indices.append(index)
            return serial

        else:
            # Container doesn't exist — create new one
            return await self.start_container(index)

    async def ensure_all(self, count: int) -> List[str]:
        """Ensure N containers are running (reuse existing when possible).

        Returns list of ADB serials.
        NOTE: cleanup_extras disabled — never delete containers, always reuse.
        """
        if self._should_use_host_network():
            serials = []
            for i in range(count):
                serials.append(await self.ensure_container(i))
            await self._repair_docker_bridge_nat()
            return serials

        ensure_tasks = [self.ensure_container(i) for i in range(count)]
        serials = await asyncio.gather(*ensure_tasks)
        return serials

    async def cleanup_extras(self, count: int) -> None:
        """Disabled — never delete containers, always reuse."""
        return

    async def _ensure_wsl_redroid_pid_shift_wrapper(self) -> str:
        """Build the WSL host-network Redroid init wrapper if needed.

        Redroid's vold binds a netlink uevent socket using its process id as
        the port id. In Docker host-network mode, containers share the network
        namespace but keep separate PID namespaces, so multiple Redroid
        containers can reuse low internal PIDs and vold can fail with
        EADDRINUSE. The wrapper reserves low internal PIDs before execing
        Android init, keeping host networking while avoiding that collision.
        """
        if not self._is_windows:
            raise DamruError("The Redroid PID-shift wrapper is only needed on WSL")

        target = "/home/damru/bin/redroid-pid-shift"
        script = r'''
set -e
target=/home/damru/bin/redroid-pid-shift
source=/home/damru/bin/redroid_pid_shift.c
mkdir -p /home/damru/bin
if [ -x "$target" ] && strings "$target" 2>/dev/null | grep -q DAMRU_PID_SHIFT_CLEAN_V1; then exit 0; fi
if ! command -v gcc >/dev/null 2>&1; then
  echo "gcc is required to build Damru's WSL Redroid init wrapper. Run python -m damru install-deps -y." >&2
  exit 127
fi
cat > "$source" <<'C'
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    static const char *damru_guard = "DAMRU_PID_SHIFT_CLEAN_V1";
    (void)damru_guard;
    int count = 0;
    const char *env = getenv("DAMRU_PID_SHIFT_COUNT");
    if (env && *env) {
        int parsed = atoi(env);
        if (parsed > 0 && parsed < 1000) count = parsed;
    }
    for (int i = 0; i < count; i++) {
        pid_t pid = fork();
        if (pid == 0) {
            for (;;) sleep(86400);
            return 0;
        }
    }
    char **init_args = calloc((size_t)argc + 1, sizeof(char *));
    if (!init_args) {
        fprintf(stderr, "calloc failed\n");
        return 126;
    }
    init_args[0] = "/init";
    for (int i = 1; i < argc; i++) init_args[i] = argv[i];
    init_args[argc] = NULL;
    execv("/init", init_args);
    fprintf(stderr, "execv /init failed: %s\n", strerror(errno));
    return 127;
}
C
gcc -O2 -static -o "$target" "$source"
chmod 755 "$target"
'''
        await self._run_cmd(
            self._wsl_sudo_cmd(script),
            timeout=60,
        )
        return target

    async def start_container(self, index: int, *, _touch_retry: int = 1) -> str:
        """Start one redroid container and return its ADB serial."""
        name = f"{REDROID_CONTAINER_PREFIX}{index}"
        port = REDROID_BASE_PORT + index
        use_host_network = self._should_use_host_network()
        boot_timeout = self._boot_timeout_for_index(index)
        # Ensure the launch image exists before docker run (auto-pull/tag)
        await self.ensure_image(REDROID_IMAGE)

        # WSL host-network Redroid uses the WSL network namespace. Bring the
        # narrow Damru DNS/NAT repair online before Android netd starts so
        # Android can bind resolver state during boot instead of being fixed
        # only after the fact.
        if use_host_network:
            await self._repair_docker_bridge_nat()

        # Remove leftover container with same name
        await self._run_cmd(
            self._docker_cmd("rm", "-f", name),
            timeout=10, allow_failure=True,
        )
        await self._ensure_binderfs()

        # Start redroid container with binderfs, memfd, and resource limits
        logger.info(
            "Starting container %s (port %d, cpus=%.1f, mem=%s, gpu_mode=%s)...",
            name, port, REDROID_CPUS, REDROID_MEMORY, REDROID_GPU_MODE,
        )
        boot_args = [
            "androidboot.use_memfd=true",
            # Starts Redroid's native uinput service early enough for Android's
            # InputReader to expose a real direct-touch device.
            _REDROID_STREAM_BOOT_ARG,
            f"androidboot.redroid_gpu_mode={REDROID_GPU_MODE}",
            "androidboot.redroid_net_ndns=2",
            "androidboot.redroid_net_dns1=1.1.1.1",
            "androidboot.redroid_net_dns2=8.8.8.8",
        ]
        if REDROID_SETUPWIZARD_DISABLED:
            boot_args.append("ro.setupwizard.mode=DISABLED")

        init_args = boot_args
        pid_shift_wrapper = ""
        if use_host_network and self._is_windows:
            pid_shift_wrapper = await self._ensure_wsl_redroid_pid_shift_wrapper()
        if use_host_network and self._is_windows:
            init_args = ["qemu=1", "androidboot.hardware=redroid", *boot_args]

        run_args = [
            "run", "-d",
            "--name", name,
            "--privileged",
            "--restart=on-failure:3",
            "-v", "/dev/binderfs:/dev/binderfs",
        ]
        if not self._is_windows:
            run_args.extend(["--cpus", str(REDROID_CPUS), "--memory", REDROID_MEMORY])
        if use_host_network:
            logger.info("Using host networking with adbd remapped to port %d", port)
            run_args.extend(["--network", "host"])
        else:
            run_args.extend(["-p", f"{port}:5555"])
            if pid_shift_wrapper:
                run_args.extend([
                    "-e", f"DAMRU_PID_SHIFT_COUNT={96 + (index * 64)}",
                    "-v", f"{pid_shift_wrapper}:/damru-redroid-init:ro",
                    "--entrypoint", "/damru-redroid-init",
                ])
        run_args.extend([REDROID_IMAGE, *init_args])

        await self._run_cmd(
            self._docker_cmd(*run_args),
            timeout=60,
        )
        await self._materialize_input_event_nodes_early(name)

        try:
            if use_host_network:
                await self._wait_for_container_boot_internal(name, timeout=boot_timeout)
                await self._remap_adbd_port(name, port)
                await self._repair_docker_bridge_nat()
            else:
                await self._wait_for_container_boot_internal(name, timeout=boot_timeout)
            await self._seed_adb_authorized_keys_early(name)
            serial = await self._serial_for_container(name, port, use_host_network)

            # Connect ADB. On Windows, Redroid ADB runs inside WSL because direct
            # Windows ADB over Docker-published ports can stay stuck offline.
            await self._run_cmd(
                self._adb_cmd("connect", serial),
                timeout=10, allow_failure=True,
            )

            # Wait for boot
            logger.info("Waiting for %s to boot...", name)
            await self._wait_for_boot(serial, name=name, timeout=boot_timeout)
            await self._repair_docker_bridge_nat()
            await self._wait_for_package_service(serial, timeout=90)
            try:
                await self._wait_for_touchscreen_input(serial)
            except DamruError as exc:
                if _touch_retry > 0:
                    logger.warning("Recreating %s after native touchscreen startup race: %s", name, exc)
                    await self._run_cmd(
                        self._docker_cmd("rm", "-f", name),
                        timeout=15,
                        allow_failure=True,
                    )
                    return await self.start_container(index, _touch_retry=_touch_retry - 1)
                raise
            if not await self._wait_for_android_dns_usable(serial):
                logger.warning(
                    "Android DNS did not fully confirm on %s; continuing with repaired resolver props",
                    serial,
                )
            if await self._ensure_sensor_hal(serial):
                logger.info("Restarting %s to activate native sensor HAL", name)
                return await self._commit_sensor_hal_and_recreate(name, index)
        except Exception as exc:
            diagnostics = await self._container_boot_diagnostics(name)
            await self._run_cmd(
                self._docker_cmd("rm", "-f", name),
                timeout=15,
                allow_failure=True,
            )
            if diagnostics:
                raise DamruError(f"{exc}\n\nContainer diagnostics for {name}:\n{diagnostics}") from exc
            raise

        if index not in self._started_indices:
            self._started_indices.append(index)
        return serial

    async def start_all(self, count: int) -> List[str]:
        """Start N containers in parallel. Returns list of ADB serials."""
        if self._should_use_host_network():
            serials = []
            for i in range(count):
                serials.append(await self.start_container(i))
            await self._repair_docker_bridge_nat()
            return serials
        tasks = [self.start_container(i) for i in range(count)]
        return await asyncio.gather(*tasks)

    async def _wait_for_boot(
        self,
        serial: str,
        timeout: float = CONTAINER_BOOT_TIMEOUT,
        name: Optional[str] = None,
    ) -> None:
        """Poll getprop sys.boot_completed until "1"."""
        adb_cmd = self._adb_cmd("shell", "getprop", "sys.boot_completed", serial=serial)
        await self._run_cmd(self._adb_cmd("connect", serial), timeout=10, allow_failure=True)
        elapsed = 0.0
        interval = 2.0
        while elapsed < timeout:
            try:
                out = await self._run_cmd(
                    adb_cmd, timeout=5, allow_failure=True,
                )
                if out.strip() == "1":
                    logger.info("Container %s booted (%.0fs)", serial, elapsed)
                    return
                if elapsed >= 30 and await self._android_services_stable_adb(serial):
                    logger.info("Container %s Android services are ready before boot flag (%.0fs)", serial, elapsed)
                    return
            except Exception:
                pass
            if name:
                out = await self._run_cmd(
                    self._docker_cmd("exec", name, "getprop", "sys.boot_completed"),
                    timeout=5,
                    allow_failure=True,
                )
                if out.strip() == "1":
                    logger.info("Container %s booted internally (%.0fs)", name, elapsed)
                    await self._run_cmd(self._adb_cmd("connect", serial), timeout=10, allow_failure=True)
                    probe = await self._run_cmd(adb_cmd, timeout=5, allow_failure=True)
                    if probe.strip() == "1":
                        return
                if elapsed >= 30 and await self._android_services_stable_internal(name):
                    logger.info("Container %s Android services are ready internally before boot flag (%.0fs)", name, elapsed)
                    return
            await asyncio.sleep(interval)
            elapsed += interval

            if int(elapsed) % 20 == 0:
                await self._run_cmd(self._adb_cmd("connect", serial), timeout=10, allow_failure=True)

        await self._run_cmd(self._adb_cmd("connect", serial), timeout=10, allow_failure=True)
        out = await self._run_cmd(adb_cmd, timeout=10, allow_failure=True)
        if out.strip() == "1":
            logger.info("Container %s booted after final reconnect", serial)
            return
        if await self._android_services_stable_adb(serial):
            logger.info("Container %s Android services are ready after final reconnect", serial)
            return
        if name and await self._android_services_stable_internal(name):
            logger.info("Container %s Android services are ready internally after final reconnect", name)
            return

        raise DamruError(f"Container {serial} failed to boot within {timeout}s")

    async def _wait_for_container_boot_internal(
        self,
        name: str,
        timeout: float = CONTAINER_BOOT_TIMEOUT,
    ) -> None:
        elapsed = 0.0
        interval = 2.0
        while elapsed < timeout:
            out = await self._run_cmd(
                self._docker_cmd("exec", name, "getprop", "sys.boot_completed"),
                timeout=5,
                allow_failure=True,
            )
            if out.strip() == "1":
                logger.info("Container %s booted internally (%.0fs)", name, elapsed)
                return
            if elapsed >= 30 and await self._android_services_stable_internal(name):
                logger.info("Container %s Android services are ready before boot flag (%.0fs)", name, elapsed)
                return
            state = await self._run_cmd(
                self._docker_cmd("inspect", "-f", "{{.State.Status}} {{.State.ExitCode}}", name),
                timeout=5,
                allow_failure=True,
            )
            parts = state.strip().split()
            if parts and parts[0] == "exited":
                exit_code = parts[1] if len(parts) > 1 else "unknown"
                hint = ""
                if self._is_windows and exit_code == "129":
                    hint = (
                        " In WSL host-network mode this commonly means Android vold could not bind "
                        "the uevent socket because this host cannot run another Redroid worker concurrently. "
                        "Stop/delete another worker or reduce the requested worker total."
                    )
                raise DamruError(f"Container {name} exited during Android boot (exit {exit_code}).{hint}")
            await asyncio.sleep(interval)
            elapsed += interval
        raise DamruError(f"Container {name} failed to boot internally within {timeout}s")

    async def _materialize_input_event_nodes_early(self, name: str, timeout: float = 25.0) -> None:
        """Create /dev/input and event nodes before Android InputReader scans.

        Redroid can expose input devices in sysfs while /dev/input is still
        missing. InputReader starts early and will not build a phone-like touch
        device list if the directory is absent, so this runs immediately after
        docker run while Android continues booting in parallel.
        """
        script = (
            "timeout=${1:-25}; "
            "case \"$timeout\" in ''|*[!0-9]*) timeout=25;; esac; "
            "mkdir -p /dev/input; chmod 0755 /dev/input 2>/dev/null || true; "
            "end=$(( $(date +%s) + timeout )); "
            "while [ \"$(date +%s)\" -le \"$end\" ]; do "
            "touch_ready=0; "
            "for event_path in /sys/class/input/event*; do "
            "[ -r \"$event_path/dev\" ] || continue; "
            "event_name=\"${event_path##*/}\"; node=\"/dev/input/$event_name\"; "
            "major_minor=$(cat \"$event_path/dev\" 2>/dev/null || true); "
            "[ -n \"$major_minor\" ] || continue; "
            "major=\"${major_minor%:*}\"; minor=\"${major_minor#*:}\"; "
            "device_name=$(cat \"$event_path/device/name\" 2>/dev/null || true); "
            "[ -e \"$node\" ] || mknod \"$node\" c \"$major\" \"$minor\" 2>/dev/null || true; "
            "chown 0:1000 \"$node\" 2>/dev/null || true; "
            "chmod 0660 \"$node\" 2>/dev/null || true; "
            "chcon u:object_r:input_device:s0 \"$node\" 2>/dev/null || true; "
            "case \"$device_name\" in *touch*|*Touch*|*TOUCH*|redroid\\ vinput|damru-virtual-multitouch|damru\\ virtual\\ touchscreen) touch_ready=1;; esac; "
            "done; "
            "[ \"$touch_ready\" = 1 ] && exit 0; "
            "sleep 0.25; "
            "done; exit 0"
        )
        await self._run_cmd(
            self._docker_cmd(
                "exec",
                name,
                "sh",
                "-lc",
                script,
                "damru-input-node-fix",
                str(int(timeout)),
            ),
            timeout=timeout + 10,
            allow_failure=True,
        )

    @staticmethod
    def _candidate_adb_public_key_paths() -> list[Path]:
        paths: list[Path] = []
        vendor_keys = os.environ.get("ADB_VENDOR_KEYS", "")
        for raw in vendor_keys.split(os.pathsep):
            raw = raw.strip()
            if not raw:
                continue
            candidate = Path(raw).expanduser()
            if candidate.is_dir():
                paths.append(candidate / "adbkey.pub")
            elif candidate.name.endswith(".pub"):
                paths.append(candidate)
            else:
                paths.append(Path(str(candidate) + ".pub"))
        paths.append(Path.home() / ".android" / "adbkey.pub")
        return paths

    @classmethod
    def _host_adb_public_keys(cls) -> list[str]:
        keys: list[str] = []
        seen: set[str] = set()
        for path in cls._candidate_adb_public_key_paths():
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                key = line.strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                keys.append(key)
        return keys

    async def _seed_adb_authorized_keys_early(self, name: str, timeout: float = 10.0) -> None:
        """Seed fresh Redroid containers with this host's ADB public key."""
        keys = self._host_adb_public_keys()
        if not keys:
            await self._run_cmd(self._adb_cmd("start-server"), timeout=10, allow_failure=True)
            keys = self._host_adb_public_keys()
        if not keys:
            logger.warning("No host ADB public key found; %s may require manual ADB authorization", name)
            return
        payload = base64.b64encode(("\n".join(keys) + "\n").encode("utf-8")).decode("ascii")
        script = (
            "set -eu; "
            "mkdir -p /data/misc/adb; "
            f"printf %s {shlex.quote(payload)} | base64 -d > /data/misc/adb/adb_keys; "
            "chown system:shell /data/misc/adb /data/misc/adb/adb_keys 2>/dev/null || true; "
            "chmod 02750 /data/misc/adb 2>/dev/null || true; "
            "chmod 0640 /data/misc/adb/adb_keys 2>/dev/null || true; "
            "restorecon /data/misc/adb /data/misc/adb/adb_keys 2>/dev/null || true; "
            "setprop ctl.restart adbd 2>/dev/null || true"
        )
        await self._run_cmd(
            self._docker_cmd("exec", name, "sh", "-lc", script),
            timeout=timeout,
            allow_failure=True,
        )

    async def _touchscreen_input_ready(self, serial: str) -> bool:
        out = await self._run_cmd(
            self._adb_cmd(
                "shell",
                "dumpsys input 2>/dev/null | grep -q 'Sources: .*TOUCHSCREEN' && echo ready",
                serial=serial,
            ),
            timeout=10,
            allow_failure=True,
        )
        return out.strip() == "ready"

    async def _wait_for_touchscreen_input(self, serial: str, timeout: float = 30.0) -> None:
        """Let Redroid's native uinput service register before profile warmup.

        If profile hardening starts immediately after boot, Android can miss the
        `redroid vinput` uinput node even though it later appears in
        `/proc/bus/input/devices`. Waiting for InputReader avoids that native
        race without patching browser-visible JavaScript.
        """
        if os.environ.get("DAMRU_SKIP_TOUCHSCREEN_WAIT", "").strip() in {"1", "true", "TRUE", "yes", "YES"}:
            return
        elapsed = 0.0
        interval = 2.0
        while elapsed <= timeout:
            if await self._touchscreen_input_ready(serial):
                logger.info("Android touchscreen input ready on %s (%.0fs)", serial, elapsed)
                return
            if elapsed >= timeout:
                break
            await asyncio.sleep(interval)
            elapsed += interval
        message = f"Android touchscreen input was not visible on {serial} after {timeout:.0f}s"
        if os.environ.get("DAMRU_ALLOW_MISSING_TOUCHSCREEN_INPUT", "").strip() in {"1", "true", "TRUE", "yes", "YES"}:
            logger.warning("%s; continuing because DAMRU_ALLOW_MISSING_TOUCHSCREEN_INPUT is set", message)
            return
        raise DamruError(message)

    async def _android_services_ready_internal(self, name: str) -> bool:
        script = " && ".join([
            "pidof system_server >/dev/null",
            "service check activity | grep -q found",
            "service check activity_task | grep -q found",
            "service check package | grep -q found",
            "service check webviewupdate | grep -q found",
            "echo ready",
        ])
        out = await self._run_cmd(
            self._docker_cmd("exec", name, "sh", "-lc", script),
            timeout=8,
            allow_failure=True,
        )
        return out.strip() == "ready"

    async def _android_services_stable_internal(self, name: str, checks: int = 3) -> bool:
        for attempt in range(checks):
            if not await self._android_services_ready_internal(name):
                return False
            if attempt < checks - 1:
                await asyncio.sleep(3)
        return True

    async def _android_services_ready_adb(self, serial: str) -> bool:
        script = " && ".join([
            "pidof system_server >/dev/null",
            "service check activity | grep -q found",
            "service check activity_task | grep -q found",
            "service check package | grep -q found",
            "service check webviewupdate | grep -q found",
            "echo ready",
        ])
        out = await self._run_cmd(
            self._adb_cmd("shell", "sh", "-lc", script, serial=serial),
            timeout=8,
            allow_failure=True,
        )
        return out.strip() == "ready"

    async def _android_services_stable_adb(self, serial: str, checks: int = 3) -> bool:
        for attempt in range(checks):
            if not await self._android_services_ready_adb(serial):
                return False
            if attempt < checks - 1:
                await asyncio.sleep(3)
        return True

    async def _container_boot_diagnostics(self, name: str) -> str:
        checks = [
            ("inspect", self._docker_cmd("inspect", "-f", "status={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} error={{.State.Error}} started={{.State.StartedAt}} finished={{.State.FinishedAt}}", name), 8),
            ("boot props", self._docker_cmd("exec", name, "sh", "-lc", "getprop sys.boot_completed; getprop init.svc.zygote; getprop init.svc.zygote64; getprop init.svc.system_server; getprop init.svc.servicemanager"), 8),
            ("android services", self._docker_cmd("exec", name, "sh", "-lc", "service check activity; service check activity_task; service check package; service check webviewupdate"), 8),
            ("android ps", self._docker_cmd("exec", name, "sh", "-lc", "ps -A | grep -E 'zygote|system_server|vold|servicemanager|surfaceflinger|adbd' || true"), 8),
            ("docker logs", self._docker_cmd("logs", "--tail", "160", name), 12),
        ]
        sections: list[str] = []
        for label, cmd, timeout in checks:
            out = await self._run_cmd(cmd, timeout=timeout, allow_failure=True)
            text = out.strip()
            if text:
                sections.append(f"[{label}]\n{text}")
        return "\n\n".join(sections)[-12000:]

    async def _ensure_android_dns(self, serial: str) -> None:
        """Ensure Android userspace has usable DNS for non-proxied Chrome.

        Redroid accepts androidboot.redroid_net_dns* boot args, but on some
        WSL/custom-kernel boots net.dns1/net.dns2 stay empty. IP traffic still
        works in that state, while Chrome fails with ERR_NAME_NOT_RESOLVED.
        Proxy sessions can still override/block DNS later through the root
        DNS-leak prevention path.
        """
        use_wsl_dns_proxy = self._is_windows and self._should_use_host_network()
        dns_values = (("net.dns1", "127.0.0.1"), ("net.dns2", "1.1.1.1")) if use_wsl_dns_proxy else (("net.dns1", "1.1.1.1"), ("net.dns2", "8.8.8.8"))
        for key, value in dns_values:
            await self._run_cmd(self._adb_cmd("shell", "setprop", key, value, serial=serial), timeout=8, allow_failure=True)
        await self._run_cmd(
            self._adb_cmd("shell", "sh", "-lc", android_dns_repair_command(use_wsl_dns_proxy=use_wsl_dns_proxy), serial=serial),
            timeout=8,
            allow_failure=True,
        )
        logger.info("Ensured Android DNS on %s is %s / %s", serial, dns_values[0][1], dns_values[1][1])

    async def _android_dns_boot_ready(self, serial: str) -> bool:
        """Return True when Redroid booted with DNS wired into connectivity."""
        for _ in range(6):
            ndns = await self._run_cmd(
                self._adb_cmd("shell", "getprop", "ro.boot.redroid_net_ndns", serial=serial),
                timeout=8,
                allow_failure=True,
            )
            if ndns.strip() != "2":
                return False
            net_dns = await self._run_cmd(
                self._adb_cmd("shell", "getprop", "net.dns1", serial=serial),
                timeout=8,
                allow_failure=True,
            )
            connectivity = await self._run_cmd(
                self._adb_cmd("shell", "dumpsys", "connectivity", serial=serial),
                timeout=12,
                allow_failure=True,
            )
            if net_dns.strip() and "DnsAddresses: [ /" in connectivity:
                return True
            await asyncio.sleep(2)
        return False

    async def _android_dns_usable(self, serial: str) -> bool:
        """Return True when Android userspace has DNS wired into connectivity.

        Older containers may not expose ro.boot.redroid_net_ndns=2 because they
        were created before Damru added that boot arg. They should not be
        destroyed if runtime DNS is otherwise usable. Do not require ICMP ping:
        Redroid/WSL can block ping while Chrome HTTPS navigation works.
        """
        await self._ensure_android_dns(serial)
        net_dns = await self._run_cmd(
            self._adb_cmd("shell", "getprop", "net.dns1", serial=serial),
            timeout=8,
            allow_failure=True,
        )
        if not net_dns.strip():
            return False
        connectivity = await self._run_cmd(
            self._adb_cmd("shell", "dumpsys", "connectivity", serial=serial),
            timeout=12,
            allow_failure=True,
        )
        return "DnsAddresses: [ /" in connectivity or "Capabilities:" in connectivity

    async def _wait_for_android_dns_usable(self, serial: str, timeout: float = 60.0) -> bool:
        """Repair and poll Android DNS without treating failure as boot-fatal."""
        if self._is_windows and self._should_use_host_network():
            await self._repair_docker_bridge_nat()
        elapsed = 0.0
        while elapsed <= timeout:
            if await self._android_dns_boot_ready(serial):
                return True
            if await self._android_dns_usable(serial):
                return True
            await asyncio.sleep(3.0)
            elapsed += 3.0
        # Last best-effort repair: enough for Chrome on some Redroid builds even
        # when dumpsys connectivity never reports DnsAddresses.
        await self._ensure_android_dns(serial)
        net_dns = await self._run_cmd(
            self._adb_cmd("shell", "getprop", "net.dns1", serial=serial),
            timeout=8,
            allow_failure=True,
        )
        return bool(net_dns.strip())

    async def _remap_adbd_port(self, name: str, port: int) -> None:
        """Move Redroid adbd to a stable per-worker host-network port."""
        current = await self._run_cmd(
            self._docker_cmd("exec", name, "getprop", "service.adb.tcp.port"),
            timeout=5,
            allow_failure=True,
        )
        if current.strip() != str(port):
            await self._run_cmd(
                self._docker_cmd("exec", name, "setprop", "service.adb.tcp.port", str(port)),
                timeout=5,
            )
            await self._run_cmd(
                self._docker_cmd("exec", name, "setprop", "ctl.restart", "adbd"),
                timeout=5,
                allow_failure=True,
            )
            await asyncio.sleep(2)

        serial = self._make_wsl_serial("127.0.0.1", port) if self._is_windows else f"127.0.0.1:{port}"
        await self._run_cmd(self._adb_cmd("disconnect", serial), timeout=5, allow_failure=True)
        await self._run_cmd(self._adb_cmd("connect", serial), timeout=10, allow_failure=True)
        out = await self._run_cmd(
            self._adb_cmd("get-state", serial=serial),
            timeout=10,
            allow_failure=True,
        )
        if out.strip() != "device":
            raise DamruError(f"Redroid ADB did not become online on {serial}: {out.strip() or '<no output>'}")


    def _container_name_port_for_serial(self, serial: str) -> tuple[str, int] | None:
        plain = self._plain_serial(serial)
        try:
            port = int(plain.rsplit(':', 1)[1])
        except Exception:
            return None
        index = port - REDROID_BASE_PORT
        if index < 0:
            return None
        return f'{REDROID_CONTAINER_PREFIX}{index}', port

    @staticmethod
    def _patch_local_webview_native_library(lib_path: Path) -> list[str]:
        changed_patches: list[str] = []
        if os.environ.get("DAMRU_ENABLE_WEBVIEW_XRW_NATIVE_PATCH") == "1":
            try:
                if patch_x_requested_with_header_block(lib_path):
                    changed_patches.append("x-requested-with")
            except WebViewNativePatchError as exc:
                logger.warning("WebView X-Requested-With native patch skipped for %s: %s", lib_path, exc)
        try:
            if patch_linux_armv8l_platform_string(lib_path):
                changed_patches.append("platform-armv8l")
        except WebViewNativePatchError as exc:
            logger.warning("WebView platform native patch skipped for %s: %s", lib_path, exc)
        return changed_patches

    @staticmethod
    def _extract_webview_native_library(apk_path: Path, output_dir: Path) -> tuple[Path, str]:
        with zipfile.ZipFile(apk_path, "r") as zf:
            names = [name for name in zf.namelist() if is_webview_native_library_entry(name)]
            if not names:
                raise WebViewNativePatchError(f"WebView native library entry not found in {apk_path}")
            preferred = next((name for name in names if name == "lib/x86_64/libmonochrome_64.so"), names[0])
            parts = preferred.split("/")
            abi = parts[1] if len(parts) >= 3 and parts[0] == "lib" else "x86_64"
            output_path = output_dir / "libmonochrome_64.so"
            output_path.write_bytes(zf.read(preferred))
            return output_path, abi

    async def _replace_system_webview_apk(
        self,
        serial: str,
        webview_apk: Path,
        native_library_apk: Path | None = None,
    ) -> None:
        plain = self._plain_serial(serial)
        try:
            port = int(plain.rsplit(':', 1)[1])
        except Exception as exc:
            raise DamruError(
                'System WebView replacement requires a Damru Redroid worker serial such as 127.0.0.1:5600.'
            ) from exc
        name = ''
        out = await self._run_cmd(
            self._docker_cmd(
                'ps', '-a',
                '--filter', f'publish={port}',
                '--format', '{{.Names}}',
            ),
            timeout=10,
            allow_failure=True,
        )
        name = next((line.strip() for line in out.splitlines() if line.strip()), '')
        target = (name, port) if name else self._container_name_port_for_serial(serial)
        if target is None:
            raise DamruError(
                'System WebView replacement requires a Damru Redroid worker serial such as 127.0.0.1:5600.'
            )
        name, port = target
        src = self._to_wsl_path(str(webview_apk.resolve())) if self._is_windows else str(webview_apk.resolve())
        patched_lib: Path | None = None
        patched_lib_abi = "x86_64"
        native_source = native_library_apk or webview_apk
        tmpdir_obj = tempfile.TemporaryDirectory(prefix="damru-system-webview-lib-")
        tmpdir = Path(tmpdir_obj.name)
        try:
            try:
                patched_lib, patched_lib_abi = self._extract_webview_native_library(native_source, tmpdir)
                changed = self._patch_local_webview_native_library(patched_lib)
                if changed:
                    logger.info(
                        "Prepared patched system WebView native library from %s: %s",
                        native_source,
                        ", ".join(changed),
                    )
                else:
                    logger.info("System WebView native library already patched in %s", native_source)
            except WebViewNativePatchError as exc:
                logger.warning("System WebView native library extraction skipped: %s", exc)

            await self._run_cmd(
                self._docker_cmd('cp', src, f'{name}:/system/product/app/webview/webview.apk'),
                timeout=APK_INSTALL_TIMEOUT,
            )
            remote_tmp_lib = "/data/local/tmp/damru-system-webview-libmonochrome_64.so"
            if patched_lib is not None:
                lib_src = self._to_wsl_path(str(patched_lib.resolve())) if self._is_windows else str(patched_lib.resolve())
                await self._run_cmd(
                    self._docker_cmd('cp', lib_src, f'{name}:{remote_tmp_lib}'),
                    timeout=APK_INSTALL_TIMEOUT,
                )
                quoted_abi = shlex.quote(patched_lib_abi)
                quoted_tmp_lib = shlex.quote(remote_tmp_lib)
                await self._run_cmd(
                    self._docker_cmd(
                        'exec', name, 'sh', '-lc',
                        (
                            'mount -o remount,rw /system 2>/dev/null || true; '
                            'mkdir -p /system/product/app/webview/lib/'
                            f'{quoted_abi}; '
                            f'cat {quoted_tmp_lib} > /system/product/app/webview/lib/{quoted_abi}/libmonochrome_64.so; '
                            f'chown root:root /system/product/app/webview/lib/{quoted_abi}/libmonochrome_64.so; '
                            f'chmod 0644 /system/product/app/webview/lib/{quoted_abi}/libmonochrome_64.so; '
                            'chmod 0755 /system/product/app/webview/lib '
                            f'/system/product/app/webview/lib/{quoted_abi}; '
                            f'rm -f {quoted_tmp_lib}'
                        ),
                    ),
                    timeout=60,
                )
        finally:
            tmpdir_obj.cleanup()
        await self._run_cmd(
            self._docker_cmd(
                'exec', name, 'sh', '-lc',
                'chown root:root /system/product/app/webview/webview.apk; '
                'chmod 0644 /system/product/app/webview/webview.apk; '
                'rm -rf /system/product/app/webview/oat /data/dalvik-cache/*/system@product@app@webview@webview.apk@* 2>/dev/null || true',
            ),
            timeout=30,
            allow_failure=True,
        )
        port_map = await self._run_cmd(
            self._docker_cmd('inspect', '-f', '{{json .NetworkSettings.Ports}}', name),
            timeout=10,
            allow_failure=True,
        )
        await self._run_cmd(self._docker_cmd('restart', name), timeout=60)
        await asyncio.sleep(8)
        if '5555/tcp' in port_map:
            await self._run_cmd(
                self._docker_cmd('exec', name, 'sh', '-lc', 'setprop service.adb.tcp.port 5555; setprop ctl.restart adbd'),
                timeout=10,
                allow_failure=True,
            )
            await asyncio.sleep(3)
            plain = self._plain_serial(serial)
            await self._run_cmd(self._adb_cmd('disconnect', plain), timeout=5, allow_failure=True)
            await self._run_cmd(self._adb_cmd('connect', plain), timeout=10, allow_failure=True)
        else:
            await self._remap_adbd_port(name, port)
        await self._wait_for_package_service(serial)

    async def _patch_webview_x_requested_with_header(self, serial: str) -> None:
        if (
            os.environ.get("DAMRU_ENABLE_INSTALLED_WEBVIEW_NATIVE_PATCH") != "1"
            and os.environ.get("DAMRU_ENABLE_WEBVIEW_XRW_NATIVE_PATCH") != "1"
        ):
            logger.info("Installed WebView native library patch disabled by default")
            return
        find_command = (
            "for f in "
            "/data/app/*/app.vanadium.trichromelibrary_*/lib/*/libmonochrome_64.so "
            "/data/app/*/app.vanadium.trichromelibrary_*/lib/*/libmonochrome.so "
            "/data/app/*/com.google.android.trichromelibrary_*/lib/*/libmonochrome_64.so "
            "/data/app/*/com.google.android.trichromelibrary_*/lib/*/libmonochrome.so "
            "/data/app/*/*/lib/*/libmonochrome_64.so "
            "/data/app/*/*/lib/*/libmonochrome.so; do "
            '[ -f "$f" ] && echo "$f"; '
            "done | sort -u"
        )
        root_find_command = f"su 0 sh -c {shlex.quote(find_command)}"
        lib_paths = [
            line.strip()
            for line in (
                await self._run_cmd(
                    self._adb_cmd("shell", root_find_command, serial=serial),
                    timeout=20,
                    allow_failure=True,
                )
            ).strip().splitlines()
            if line.strip()
        ]
        if not lib_paths:
            logger.warning("WebView X-Requested-With native patch skipped: libmonochrome_64.so not found")
        else:
            for remote_lib in lib_paths:
                await self._patch_one_webview_x_requested_with_library(serial, remote_lib)
        # Do not live-mutate installed APK files under /data/app. APK-entry
        # edits can invalidate package/signature state for static shared
        # Trichrome libraries. The durable platform fix is to install a patched
        # extracted native library beside the system WebView APK during image
        # bake/replacement.

    async def _patch_one_webview_x_requested_with_library(self, serial: str, remote_lib: str) -> None:
        logger.info("Patching WebView native library in %s", remote_lib)
        with tempfile.TemporaryDirectory(prefix="damru-webview-patch-") as tmp:
            local_lib = Path(tmp) / "libmonochrome_64.so"
            remote_source_tmp = f"/data/local/tmp/damru-libmonochrome-native-source-{uuid.uuid4().hex}.so"
            quoted_lib = shlex.quote(remote_lib)
            quoted_source_tmp = shlex.quote(remote_source_tmp)
            copy_command = f"cat {quoted_lib} > {quoted_source_tmp}; chmod 0644 {quoted_source_tmp}"
            try:
                await self._run_cmd(
                    self._adb_cmd(
                        "shell",
                        f"su 0 sh -c {shlex.quote(copy_command)}",
                        serial=serial,
                    ),
                    timeout=60,
                )
                await self._run_cmd(
                    self._adb_cmd("pull", remote_source_tmp, str(local_lib), serial=serial),
                    timeout=APK_INSTALL_TIMEOUT,
                )
            finally:
                await self._run_cmd(
                    self._adb_cmd(
                        "shell",
                        f"su 0 sh -c {shlex.quote(f'rm -f {quoted_source_tmp}')}",
                        serial=serial,
                    ),
                    timeout=10,
                    allow_failure=True,
                )
            changed_patches: list[str] = []
            if os.environ.get("DAMRU_ENABLE_WEBVIEW_XRW_NATIVE_PATCH") == "1":
                try:
                    if patch_x_requested_with_header_block(local_lib):
                        changed_patches.append("x-requested-with")
                except WebViewNativePatchError as exc:
                    logger.warning("WebView X-Requested-With native patch skipped for %s: %s", remote_lib, exc)
            try:
                if patch_linux_armv8l_platform_string(local_lib):
                    changed_patches.append("platform-armv8l")
            except WebViewNativePatchError as exc:
                logger.warning("WebView platform native patch skipped for %s: %s", remote_lib, exc)
            if not changed_patches:
                logger.info("WebView native patches already present in %s", remote_lib)
                return
            remote_tmp = "/data/local/tmp/damru-libmonochrome-native-patched.so"
            await self._run_cmd(
                self._adb_cmd("push", str(local_lib), remote_tmp, serial=serial),
                timeout=APK_INSTALL_TIMEOUT,
            )
            quoted_tmp = shlex.quote(remote_tmp)
            await self._run_cmd(
                self._adb_cmd(
                    "shell",
                    "su 0 sh -c "
                    + shlex.quote(
                        f"owner=$(stat -c '%u:%g' {quoted_lib}); "
                        f"mode=$(stat -c '%a' {quoted_lib}); "
                        f"cat {quoted_tmp} > {quoted_lib}; "
                        f"chown \"$owner\" {quoted_lib}; "
                        f"chmod \"$mode\" {quoted_lib}; "
                        f"rm -f {quoted_tmp}; "
                        "am force-stop com.android.webview 2>/dev/null || true; "
                        "am force-stop com.android.chrome 2>/dev/null || true; "
                        "am force-stop com.android.browser 2>/dev/null || true; "
                        "am force-stop org.chromium.webview_shell 2>/dev/null || true; "
                        "killall webview_zygote 2>/dev/null || true"
                    ),
                    serial=serial,
                ),
                timeout=60,
            )
        logger.info("WebView native patches applied to %s: %s", remote_lib, ", ".join(changed_patches))

    async def _patch_one_webview_platform_apk(self, serial: str, remote_apk: str) -> None:
        logger.info("Patching WebView APK native library entry in %s", remote_apk)
        with tempfile.TemporaryDirectory(prefix="damru-webview-apk-patch-") as tmp:
            local_apk = Path(tmp) / "base.apk"
            await self._run_cmd(
                self._adb_cmd("pull", remote_apk, str(local_apk), serial=serial),
                timeout=APK_INSTALL_TIMEOUT,
            )
            try:
                changed = patch_linux_armv8l_platform_string_in_apk(local_apk)
            except WebViewNativePatchError as exc:
                logger.warning("WebView APK platform native patch skipped for %s: %s", remote_apk, exc)
                return
            if not changed:
                logger.info("WebView APK platform native patch already present in %s", remote_apk)
                return
            remote_tmp = "/data/local/tmp/damru-trichrome-platform-patched.apk"
            await self._run_cmd(
                self._adb_cmd("push", str(local_apk), remote_tmp, serial=serial),
                timeout=APK_INSTALL_TIMEOUT,
            )
            quoted_apk = shlex.quote(remote_apk)
            quoted_tmp = shlex.quote(remote_tmp)
            await self._run_cmd(
                self._adb_cmd(
                    "shell",
                    "su",
                    "0",
                    "sh",
                    "-lc",
                    (
                        f"owner=$(stat -c '%u:%g' {quoted_apk}); "
                        f"mode=$(stat -c '%a' {quoted_apk}); "
                        f"cat {quoted_tmp} > {quoted_apk}; "
                        f"chown \"$owner\" {quoted_apk}; "
                        f"chmod \"$mode\" {quoted_apk}; "
                        f"rm -f {quoted_tmp}; "
                        "am force-stop com.android.webview 2>/dev/null || true; "
                        "am force-stop com.android.chrome 2>/dev/null || true; "
                        "am force-stop com.android.browser 2>/dev/null || true; "
                        "am force-stop org.chromium.webview_shell 2>/dev/null || true; "
                        "killall webview_zygote 2>/dev/null || true"
                    ),
                    serial=serial,
                ),
                timeout=60,
            )
        logger.info("WebView APK platform native patch applied to %s", remote_apk)

    async def install_chrome(self, serial: str, apk_path: str) -> None:
        """Install Chrome on a container via ADB.

        Supports single APK and split APK (directory with .apk files).
        If directory contains google_trichrome_library.apk, installs it
        first (Chrome requires this static shared library).

        Split APKs are pushed to device first, then installed via
        pm install-create/install-write/install-commit using local file
        paths. This avoids abb_exec streaming (adb install-multiple)
        which is unreliable over ADB TCP with redroid containers.
        """
        p = Path(apk_path)
        logger.info("Installing Chrome on %s from %s...", serial, apk_path)
        await self._wait_for_package_service(serial)
        if p.is_dir():
            all_apks = sorted(p.glob("*.apk"))
            if not all_apks:
                raise DamruError(f"No .apk files in directory: {apk_path}")

            matching_webview = find_matching_webview_apk(p, apk_path)
            if matching_webview is None:
                raise DamruError(
                    f'Matching WebView APK missing for Chrome {p.name}. '
                    f'Place webview.apk or TrichromeWebView.apk inside {p} so Chrome/WebView stay version-aligned.'
                )
            vanadium_library = None
            for library_name in (
                'vanadium_trichrome_library.apk',
                'TrichromeLibrary.apk',
                'app_vanadium_trichromelibrary.apk',
            ):
                candidate = p / library_name
                if candidate.exists():
                    vanadium_library = candidate
                    break
            trichrome = p / "google_trichrome_library.apk"
            if vanadium_library is not None:
                logger.info('Installing matching WebView TrichromeLibrary on %s...', serial)
                try:
                    await self._run_cmd(
                        self._adb_cmd('install', '-r', '-d', str(vanadium_library), serial=serial),
                        timeout=APK_INSTALL_TIMEOUT,
                    )
                except DamruError as exc:
                    logger.warning('Optional Vanadium TrichromeLibrary install failed; continuing with Google library: %s', exc)
            logger.info('Replacing system WebView on %s from %s...', serial, matching_webview)
            await self._replace_system_webview_apk(
                serial,
                matching_webview,
                native_library_apk=vanadium_library or (trichrome if trichrome.exists() else None),
            )

            # Install TrichromeLibrary first if present (Chrome needs it)
            if trichrome.exists():
                logger.info("Installing TrichromeLibrary on %s...", serial)
                await self._run_cmd(
                    self._adb_cmd("install", "-r", "-d", str(trichrome), serial=serial),
                    timeout=APK_INSTALL_TIMEOUT,
                )
            if trichrome.exists() or vanadium_library is not None:
                await self._patch_webview_x_requested_with_header(serial)

            # Install Chrome split APKs (exclude trichrome library)
            chrome_apks = [
                a for a in all_apks
                if "trichrome" not in a.name.lower()
                and "webview" not in a.name.lower()
                and not a.name.lower().startswith("webview")
            ]
            if not chrome_apks:
                raise DamruError(f"No Chrome APKs found in: {apk_path}")

            await self._install_split_via_push(serial, chrome_apks)
            installed_chrome = await self.get_installed_chrome_version(serial)
            installed_webview = await self.get_installed_webview_version(serial)
            provider = await self.get_current_webview_provider(serial)
            if installed_chrome and installed_webview:
                if not self._chrome_webview_versions_match(installed_chrome, installed_webview):
                    provider_detail = provider or 'unknown'
                    raise DamruError(
                        f'Chrome/WebView version mismatch after install: '
                        f'Chrome {installed_chrome}, WebView {installed_webview}. '
                        f'Use a matching WebView APK for {p.name}. Provider: {provider_detail}'
                    )
            if trichrome.exists() or vanadium_library is not None:
                # Chrome/WebView split installs can create or replace extracted
                # Trichrome native-library paths after the first library patch.
                # Reapply here so the active /data/app provider libs carry the
                # same native XRW patch as the baked system WebView lib.
                await self._patch_webview_x_requested_with_header(serial)
            logger.info("Chrome installed on %s (%d split APKs)", serial, len(chrome_apks))
        else:
            await self._run_cmd(
                self._adb_cmd("install", "-r", "-d", str(p), serial=serial),
                timeout=APK_INSTALL_TIMEOUT,
            )
            logger.info("Chrome installed on %s", serial)

    async def _wait_for_package_service(self, serial: str, timeout: int = 90) -> None:
        """Wait until Android PackageManager accepts install commands."""
        deadline = asyncio.get_running_loop().time() + timeout
        last = ""
        while asyncio.get_running_loop().time() < deadline:
            out = await self._run_cmd(
                self._adb_cmd("shell", "service check package", serial=serial),
                timeout=8,
                allow_failure=True,
            )
            last = out.strip()
            if "Service package:" in last and "not found" not in last.lower():
                return
            await asyncio.sleep(3)
        raise DamruError(f"Android package service not ready on {serial}: {last or '<no output>'}")

    async def _install_split_via_push(self, serial: str, apks: list) -> None:
        """Install split APKs by pushing to device then using pm session API.

        Avoids adb install-multiple (abb_exec streaming) which causes
        'device offline' errors over ADB TCP with redroid containers.
        """
        remote_dir = "/data/local/tmp/chrome-install"
        await self._run_cmd(
            self._adb_cmd("shell", "mkdir", "-p", remote_dir, serial=serial),
            timeout=10,
        )

        # Push all APKs to device
        remotes = []
        total_size = 0
        for apk in apks:
            remote = f"{remote_dir}/{apk.name}"
            await self._run_cmd(
                self._adb_cmd("push", str(apk), remote, serial=serial),
                timeout=APK_INSTALL_TIMEOUT,
            )
            remotes.append(remote)
            total_size += apk.stat().st_size

        # Create pm install session
        out = await self._run_cmd(
            self._adb_cmd(
                "shell", "pm", "install-create", "-r", "-d", "-S", str(total_size),
                serial=serial,
            ),
            timeout=30,
        )
        # Parse session ID from "Success: created install session [1234567]"
        session_id = None
        for part in out.replace("[", " ").replace("]", " ").split():
            if part.isdigit():
                session_id = part
                break
        if not session_id:
            raise DamruError(f"Failed to create pm install session on {serial}: {out}")

        # Write each APK into session using local file path
        for i, remote in enumerate(remotes):
            out = await self._run_cmd(
                self._adb_cmd(
                    "shell", "pm", "install-write", "-S",
                    str(apks[i].stat().st_size),
                    session_id, f"split_{i}.apk", remote,
                    serial=serial,
                ),
                timeout=60,
            )
            if "success" not in out.lower():
                raise DamruError(
                    f"pm install-write failed for {remote} on {serial}: {out}"
                )

        # Commit the session
        out = await self._run_cmd(
            self._adb_cmd("shell", "pm", "install-commit", session_id, serial=serial),
            timeout=30,
        )
        if "success" not in out.lower():
            raise DamruError(f"pm install-commit failed on {serial}: {out}")

        # Clean up pushed APKs
        await self._run_cmd(
            self._adb_cmd("shell", "rm", "-rf", remote_dir, serial=serial),
            timeout=10, allow_failure=True,
        )

    async def stop_container(self, index: int) -> None:
        """Stop and remove a single container."""
        name = f"{REDROID_CONTAINER_PREFIX}{index}"
        await self._run_cmd(
            self._docker_cmd("rm", "-f", name),
            timeout=15, allow_failure=True,
        )

    async def stop_all(self) -> None:
        """Stop and remove all started containers."""
        tasks = [self.stop_container(i) for i in self._started_indices]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._started_indices.clear()

    # ── Orphan cleanup + health ──

    async def cleanup_orphans(self) -> None:
        """Remove leftover damru-worker-* containers from previous runs."""
        out = await self._run_cmd(
            self._docker_cmd(
                "ps", "-a",
                "--filter", f"name={REDROID_CONTAINER_PREFIX}",
                "--format", "{{.Names}}",
            ),
            timeout=10, allow_failure=True,
        )
        if not out:
            return
        orphans = [n.strip() for n in out.splitlines() if n.strip()]
        if orphans:
            logger.info("Cleaning %d orphaned container(s)", len(orphans))
            for name in orphans:
                await self._run_cmd(
                    self._docker_cmd("rm", "-f", name),
                    timeout=15, allow_failure=True,
                )

    async def restart_container(self, index: int) -> str:
        """Stop, remove, and re-create a container. Returns new serial."""
        await self.stop_container(index)
        # Remove from tracked indices so start_container doesn't duplicate
        if index in self._started_indices:
            self._started_indices.remove(index)
        return await self.start_container(index)

    async def restart_existing_container(self, index: int) -> str:
        """Restart an existing container without removing its writable layer."""
        await self._ensure_binderfs()
        name = f"{REDROID_CONTAINER_PREFIX}{index}"
        port = REDROID_BASE_PORT + index
        use_host_network = self._should_use_host_network()
        boot_timeout = self._boot_timeout_for_index(index)
        state = await self._get_container_state(name)
        if state == "none":
            return await self.start_container(index)

        logger.info("Restarting existing container %s without removing its writable layer", name)
        await self._run_cmd(
            self._docker_cmd("restart", name),
            timeout=60,
            allow_failure=False,
        )
        if use_host_network:
            await self._wait_for_container_boot_internal(name, timeout=boot_timeout)
            await self._remap_adbd_port(name, port)
            await self._repair_docker_bridge_nat()
        serial = await self._serial_for_container(name, port, use_host_network)
        await self._run_cmd(
            self._adb_cmd("connect", serial),
            timeout=10,
            allow_failure=True,
        )
        await self._wait_for_boot(serial, name=name, timeout=boot_timeout)
        await self._repair_docker_bridge_nat()
        if not await self._android_dns_usable(serial):
            raise DamruError(f"Android DNS is not usable after restarting {name}")
        await self._wait_for_package_service(serial, timeout=60)
        try:
            await self._wait_for_touchscreen_input(serial)
        except DamruError as exc:
            logger.warning("Recreating unhealthy %s after restart: %s", name, exc)
            return await self.restart_container(index)
        if index not in self._started_indices:
            self._started_indices.append(index)
        return serial

    async def is_container_alive(self, index: int) -> bool:
        """Check if a container is running."""
        name = f"{REDROID_CONTAINER_PREFIX}{index}"
        out = await self._run_cmd(
            self._docker_cmd("inspect", "-f", "{{.State.Running}}", name),
            timeout=10, allow_failure=True,
        )
        return out.strip().lower() == "true"

    # ── Chrome version detection + uninstall ──

    async def get_installed_chrome_version(self, serial: str) -> Optional[str]:
        """Get installed Chrome version string (e.g. '145.0.7632.75') or None."""
        out = await self._run_cmd(
            self._adb_cmd("shell", "dumpsys", "package", "com.android.chrome", serial=serial),
            timeout=10, allow_failure=True,
        )
        if not out or "Unable to find package" in out:
            return None
        if "com.google.android.apps.chrome.Main" not in out:
            logger.warning("Chrome package is present on %s but main activity is missing", serial)
            return None
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("versionName="):
                return line.split("=", 1)[1].strip()
        return None

    async def get_installed_webview_version(self, serial: str) -> Optional[str]:
        '''Get installed Android WebView provider version, when present.'''
        out = await self._run_cmd(
            self._adb_cmd('shell', 'dumpsys', 'package', 'com.android.webview', serial=serial),
            timeout=10,
            allow_failure=True,
        )
        if not out or 'Unable to find package' in out:
            return None
        for line in out.splitlines():
            line = line.strip()
            if line.startswith('versionName='):
                return line.split('=', 1)[1].strip()
        return None

    async def get_current_webview_provider(self, serial: str) -> Optional[str]:
        '''Return the active WebView provider package/version summary.'''
        out = await self._run_cmd(
            self._adb_cmd('shell', 'dumpsys', 'webviewupdate', serial=serial),
            timeout=10,
            allow_failure=True,
        )
        for line in out.splitlines():
            text = line.strip()
            if text.startswith('Current WebView package'):
                return text
        return None

    @staticmethod
    def _chrome_webview_versions_match(chrome_version: str, webview_version: str) -> bool:
        '''Chrome uses x.y.z.n; WebView builds may append .0 after the same base version.
        Match on first 3 version segments (x.y.z) to allow minor build skew.'''
        chrome = chrome_version.strip()
        webview = webview_version.strip()
        if webview == chrome or webview.startswith(f'{chrome}.'):
            return True
        # Allow minor build skew: match on first 3 segments
        c_parts = chrome.split('.')
        w_parts = webview.split('.')
        if len(c_parts) >= 3 and len(w_parts) >= 3:
            return c_parts[:3] == w_parts[:3]
        return False

    def _target_chrome_version_from_apk_path(self, apk_path: str) -> Optional[str]:
        """Return the bundle version when apk_path points at chrome-apks/<version>."""
        p = Path(apk_path)
        if p.is_dir() and list(p.glob("*.apk")):
            return p.name
        return None

    async def uninstall_chrome(self, serial: str) -> None:
        """Uninstall Chrome and TrichromeLibrary from a container."""
        for pkg in [
            "com.android.chrome",
            "com.google.android.trichrome.library",
        ]:
            out = await self._run_cmd(
                self._adb_cmd("shell", "pm", "uninstall", pkg, serial=serial),
                timeout=30, allow_failure=True,
            )
            if "success" in out.lower():
                logger.info("Uninstalled %s from %s", pkg, serial)
            elif "not installed" in out.lower() or "unknown package" in out.lower():
                pass  # already gone
            else:
                logger.debug("Uninstall %s on %s: %s", pkg, serial, out)

    # ── Chrome APK discovery ──

    def find_chrome_apk(
        self,
        explicit_path: Optional[str] = None,
        version: Optional[str] = None,
    ) -> str:
        """Find Chrome APK path (file or versioned split-APK directory).

        Directory structure:
          chrome-apks/
            145.0.7632.75/
              base.apk, split_chrome.apk, ...
            144.0.xxxx.xx/
              ...

        Args:
            explicit_path: Direct path to APK file or directory.
            version: Specific Chrome version. None = random from available.
        """
        import random as _random

        if explicit_path:
            p = Path(explicit_path)
            if p.exists():
                return str(p.resolve())
            raise DamruError(f"Chrome APK not found: {explicit_path}")

        # Look for chrome-apks/<version>/ directories
        for apk_root in candidate_apk_bundle_roots():
            if not apk_root.is_dir():
                continue

            versions = []
            for sub in sorted(apk_root.iterdir()):
                if sub.is_dir() and list(sub.glob("*.apk")):
                    versions.append(sub)

            if not versions:
                if list(apk_root.glob("*.apk")):
                    return str(apk_root.resolve())
                continue

            # WebView matching is optional; system WebView works.
            matched_versions = [v for v in versions if find_matching_webview_apk(v, str(apk_root)) is not None]

            if version:
                for v in versions:
                    if v.name == version:
                        logger.info("Chrome APK: v%s (WebView %s)", v.name,
                                    "matched" if v in matched_versions else "system")
                        return str(v.resolve())
                raise DamruError(
                    f"Chrome version {version} not found. "
                    f"Available: {[v.name for v in versions]}"
                )

            auto_versions = [v for v in versions if v.name not in _CHROME_APK_AUTO_SKIP_VERSIONS]
            if not auto_versions:
                auto_versions = [v for v in versions]
            if not auto_versions:
                raise DamruError("No usable Chrome APK version found.")

            picked = _random.choice(auto_versions)
            logger.info(
                "Chrome APK: v%s (random from %d auto-compatible available)",
                picked.name, len(auto_versions),
            )
            return str(picked.resolve())

        for apk_root in candidate_apk_bundle_roots():
            single = apk_root.parent / "chrome.apk"
            if single.exists():
                return str(single.resolve())

        raise DamruError(
            "Chrome APK not found. Either:\n"
            "  1. Place split APKs in damru/chrome-apks/<version>/\n"
            "  2. Place single chrome.apk in damru/\n"
            "  3. Provide chrome_apk= parameter"
        )

    # ── Image Baking ──

    async def bake_image(
        self,
        chrome_apk: Optional[str] = None,
        image_name: str = "damru-redroid:latest",
    ) -> str:
        """Pre-bake a Docker image with EVERYTHING pre-installed and pre-configured.

        Creates a custom image where every new container starts as "warm":
        Chrome is installed, FRE is dismissed, Preferences exist, fonts are
        pushed, eSpeak is configured, and production-like security props are set.

        This means has_preferences() = True on first boot → warm path always.
        No cold start ever — every session gets 10-15s setup.

        Steps:
          1.  Start temp container from base redroid image
          2.  Install Chrome + TrichromeLibrary APKs
          3.  Install eSpeak-NG (100+ offline TTS voices)
          4.  Push resetprop binary
          5.  Install native preload assets for optional runtime hooks
          6.  Install extra fonts to /system/fonts/
          7.  Configure eSpeak as default TTS engine
          8.  Backup original vulkan.pastel.so for GPU patching
          9.  Apply audio 48kHz fix
          10. Set production-like security props in build.prop (persistent)
          11. Launch Chrome → dismiss FRE → create Preferences
          12. Patch universal Preferences (DoH, WebRTC, DNS, etc.)
          13. docker commit → custom image
          14. Remove temp container

        Args:
            chrome_apk: Path to Chrome APK or split-APK directory.
            image_name: Name for the baked image (default: damru-redroid:latest).

        Returns:
            The image name/tag that was created.
        """
        import json as _json

        from .adb import ADB
        from .chrome import ChromeManager
        from .root import RootOps

        temp_name = "damru-bake-temp"
        port = 5699  # Use a high port to avoid conflicts

        logger.info("=== BAKING DAMRU IMAGE ===")
        base_image = os.environ.get("DAMRU_BAKE_BASE_IMAGE", "").strip()
        if not base_image:
            if os.environ.get("DAMRU_BAKE_FROM_LAUNCH_IMAGE") == "1" and image_name != REDROID_IMAGE:
                base_image = REDROID_IMAGE
            else:
                base_image = REDROID_BASE_IMAGE
        logger.info("Base image: %s", base_image)
        logger.info("Target image: %s", image_name)

        # Step 1: Start temp container
        await self._ensure_binderfs()
        await self.ensure_image(base_image)
        await self._run_cmd(
            self._docker_cmd("rm", "-f", temp_name),
            timeout=10, allow_failure=True,
        )
        await self._run_cmd(
            self._docker_cmd(
                "run", "-d",
                "--name", temp_name,
                "--privileged",
                "-v", "/dev/binderfs:/dev/binderfs",
                "-p", f"{port}:5555",
                base_image,
                "androidboot.use_memfd=true",
                _REDROID_STREAM_BOOT_ARG,
                f"androidboot.redroid_gpu_mode={REDROID_GPU_MODE}",
                "androidboot.redroid_net_dns1=1.1.1.1",
                "androidboot.redroid_net_dns2=8.8.8.8",
            ),
            timeout=60,
        )
        logger.info("Temp container started, connecting ADB...")
        serial = await self._serial_for_container(temp_name, port)

        # Connect ADB FIRST (required before shell commands work)
        for _attempt in range(5):
            out = await self._run_cmd(
                self._adb_cmd("connect", serial),
                timeout=10, allow_failure=True,
            )
            if "connected" in out.lower():
                break
            await asyncio.sleep(2)

        await self._wait_for_boot(serial, name=temp_name, timeout=CONTAINER_BOOT_TIMEOUT)

        try:
            logger.info("Installing boot-time input node repair into baked image")
            await self._install_input_node_boot_repair(temp_name)
        except Exception as exc:
            logger.warning("Input node boot repair install skipped: %s", exc)

        if (os.environ.get("DAMRU_ENABLE_NATIVE_SENSOR_HAL", "1") == "1" or os.environ.get("DAMRU_EXPERIMENTAL_SENSOR_HAL", "1") == "1") and not await self._sensor_hal_present(serial):
            try:
                logger.info("Installing native sensor HAL into baked image")
                await self._install_aidl_sensor_hal(temp_name, serial)
                logger.info("Restarting %s to activate native sensor HAL", temp_name)
                await self._run_cmd(self._docker_cmd("restart", temp_name), timeout=60)
                await asyncio.sleep(8)
                await self._run_cmd(self._adb_cmd("disconnect", serial), timeout=5, allow_failure=True)
                await self._run_cmd(self._adb_cmd("connect", serial), timeout=10, allow_failure=True)
                await self._wait_for_boot(serial, name=temp_name, timeout=CONTAINER_BOOT_TIMEOUT)
                await self._wait_for_package_service(serial, timeout=90)
            except Exception as _sensor_err:
                logger.warning("Native sensor HAL install failed (AIDL or NDK missing), continuing without it: %s", _sensor_err)

        try:
            adb = ADB(serial=serial)
            root = RootOps(adb)
            await root.check_root()

            # Step 2: Install Chrome
            apk_path = chrome_apk or self.find_chrome_apk()
            current_chrome = await self.get_installed_chrome_version(serial)
            target_chrome = self._target_chrome_version_from_apk_path(apk_path)
            if current_chrome and target_chrome and current_chrome == target_chrome:
                logger.info(
                    "Chrome %s is already installed on %s; skipping APK reinstall",
                    current_chrome,
                    serial,
                )
            else:
                logger.info("Installing Chrome from %s...", apk_path)
                await self.install_chrome(serial, apk_path)

            logger.info("Baking WebView native platform and touch repairs...")
            try:
                await root.ensure_installed_webview_apk_platform_patch()
            except Exception as exc:
                logger.warning("Installed WebView APK platform bake repair skipped: %s", exc)
            try:
                await root.ensure_system_webview_native_lib_patch()
            except Exception as exc:
                logger.warning("System WebView native lib bake repair skipped: %s", exc)
            try:
                await self._patch_webview_x_requested_with_header(serial)
            except Exception as exc:
                logger.warning("Installed WebView native XRW bake repair skipped: %s", exc)
            try:
                await root.ensure_multitouch_stack()
            except Exception as exc:
                logger.warning("Multitouch bake repair skipped: %s", exc)

            # Step 3: Install local TTS engines/voices
            logger.info("Installing local TTS engines...")
            await root.ensure_speech_voices()

            # Step 4: Push resetprop binary
            logger.info("Pushing resetprop binary...")
            await root._ensure_resetprop()

            # Step 5: Install native preload assets but do not activate wrap.*.
            logger.info("Installing native preload assets...")
            await root.install_native_preload_assets()

            # Step 6: Install extra fonts
            logger.info("Installing extra fonts...")
            await root.install_extra_fonts()

            # Step 7: Configure eSpeak as default TTS
            logger.info("Configuring TTS engine...")
            espeak_pkg = "com.reecedunn.espeak"
            for cmd in [
                f"settings put secure tts_default_synth {espeak_pkg}",
                "settings put secure tts_default_locale en-US",
                "settings put secure tts_default_rate 100",
                "settings put secure tts_default_pitch 100",
                f"settings put secure tts_enabled_plugins '{espeak_pkg}'",
            ]:
                await adb.shell(cmd, allow_failure=True)

            # Step 8: Backup original vulkan.pastel.so
            vulkan_so = "/vendor/lib64/hw/vulkan.pastel.so"
            backup_so = "/data/local/tmp/damru_vk_pastel_orig.so"
            vk_exists = "OK" in await adb.shell(
                f"test -f {vulkan_so} && echo OK", timeout=5, allow_failure=True,
            )
            if vk_exists:
                await adb.shell_root(f"cp {vulkan_so} {backup_so}")
                logger.info("Backed up original vulkan.pastel.so")

            # Step 9: Apply audio 48kHz fix
            await root.apply_audio_48khz()

            # Step 10: Keep fresh workers root-manageable during warmup.
            # Runtime profile application hardens these props again before
            # browser navigation. This image-level baseline is only the boot
            # state needed for native OS/WebView repairs.
            logger.info("Setting root-manageable startup security props in build.prop (persistent)...")
            await adb.shell(
                "su 0 mount -o remount,rw /system 2>/dev/null", allow_failure=True,
            )
            for prop_key, prop_value in (
                ("ro.debuggable", "1"),
                ("ro.secure", "0"),
                # Keep fresh workers ADB/root-connectable; runtime setup
                # hardens ro.adb.secure before browser navigation.
                ("ro.adb.secure", "0"),
                ("ro.build.type", "user"),
            ):
                prop_pattern = prop_key.replace(".", "[.]")
                await adb.shell_root(
                    "if grep -q '^%s=' /system/build.prop; then "
                    "sed -i 's|^%s=.*|%s=%s|' /system/build.prop; "
                    "else echo '%s=%s' >> /system/build.prop; fi"
                    % (prop_pattern, prop_pattern, prop_key, prop_value, prop_key, prop_value)
                )
            logger.info("Startup security props persisted: ro.debuggable=1 ro.secure=0 ro.adb.secure=0 ro.build.type=user")
            await adb.shell(
                "su 0 mount -o remount,ro /system 2>/dev/null", allow_failure=True,
            )

            # Step 11: Launch Chrome → dismiss FRE → create Preferences
            # This makes has_preferences() = True on every new container,
            # so ALL sessions take the warm (fast) path. No cold start ever.
            logger.info("Pre-launching Chrome to dismiss FRE...")
            chrome = ChromeManager(adb)
            await chrome.detect_package()
            await chrome.launch(startup_delay=5.0)
            await chrome.dismiss_fre(max_attempts=10)
            logger.info("FRE dismissed — Chrome profile created")
            await chrome.force_stop()
            await asyncio.sleep(1)

            # Step 12: Patch universal Preferences (DoH, WebRTC, privacy)
            # Per-session locale will overwrite intl.selected_languages later.
            logger.info("Patching universal Chrome Preferences...")
            prefs_path = f"/data/data/{chrome.package}/app_chrome/Default/Preferences"
            raw = await adb.shell(f"su 0 cat {prefs_path}", timeout=10, allow_failure=True)
            if raw and not raw.startswith("cat:") and "No such file" not in raw and "Permission denied" not in raw:
                try:
                    prefs = _json.loads(raw)
                except _json.JSONDecodeError:
                    prefs = {}
            else:
                prefs_dir = prefs_path.rsplit("/", 1)[0]
                await adb.shell_root(f"mkdir -p {prefs_dir}")
                prefs = {}

            # Universal privacy/security settings (same for all sessions)
            prefs.setdefault("webrtc", {})["ip_handling_policy"] = "default_public_interface_only"
            prefs.setdefault("dns_prefetching", {})["enabled"] = False
            prefs.setdefault("net", {})["network_prediction_options"] = 2
            prefs.setdefault("safebrowsing", {})["enabled"] = False
            prefs.setdefault("alternate_error_pages", {})["enabled"] = False
            prefs.setdefault("background_sync", {})["enabled"] = False
            prefs.setdefault("dns_over_https", {}).update({
                "mode": "off",  # Disabled - use proxy DNS for todetect.net
            })
            # Default language (overwritten per-session by patch_preferences)
            prefs.setdefault("intl", {})["selected_languages"] = "en-US,en"
            prefs.setdefault("intl", {})["accept_languages"] = "en-US,en"

            import base64 as _b64
            patched_json = _json.dumps(prefs, separators=(",", ":"))
            b64 = _b64.b64encode(patched_json.encode()).decode()
            tmp = "/data/local/tmp/damru_chrome_prefs.json"
            await adb.shell_root(f"echo '{b64}' | base64 -d > {tmp}")
            owner = await adb.shell(
                f"su 0 stat -c '%U:%G' /data/data/{chrome.package}",
                timeout=5, allow_failure=True,
            )
            await adb.shell_root(f"cp {tmp} {prefs_path}")
            if owner and ":" in owner and "stat:" not in owner:
                await adb.shell_root(f"chown {owner.strip()} {prefs_path}")
            await adb.shell_root(f"chmod 600 {prefs_path}")
            await adb.shell_root(f"rm -f {tmp}")
            logger.info("Universal Preferences baked (DoH, WebRTC, privacy)")

            # WebView Shell uses Android WebView's pref_store, not Chrome's
            # app_chrome/Default/Preferences. Patch it separately so local
            # WebView-based capture harnesses do not boot with default locale
            # and network prediction settings.
            try:
                webview_shell = ChromeManager(adb, package="org.chromium.webview_shell")
                await webview_shell.detect_package(retries=3, delay=1.0)
                await webview_shell.force_stop()
                await webview_shell.write_command_line([
                    "--disable-fre",
                    "--no-first-run",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-translate",
                    "--disable-sync",
                    "--metrics-recording-only",
                    "--lang=en-US",
                    "--accept-lang=en-US,en",
                    "--force-webrtc-ip-handling-policy=default_public_interface_only",
                    "--enforce-webrtc-ip-permission-check",
                    "--dns-prefetch-disable",
                    "--disable-background-networking",
                    "--disable-client-side-phishing-detection",
                    "--disable-component-update",
                    "--disable-domain-reliability",
                    "--no-pings",
                ])
                await webview_shell.patch_preferences("en-US", "en-US,en;q=0.9")
                await webview_shell.force_stop()
                logger.info("Universal WebView Shell Preferences baked")
            except Exception as exc:
                logger.warning("WebView Shell hardening was not baked: %s", exc)

            # Force-stop all apps to get a clean snapshot
            await adb.shell("am force-stop com.android.chrome", allow_failure=True)
            await adb.shell("am force-stop org.chromium.webview_shell", allow_failure=True)
            await asyncio.sleep(1)

            # Pre-commit cleanup: trim /data cache, temp files, logs to reduce image size
            logger.info("Cleaning up temp files in container before commit...")
            for clean_cmd in [
                "rm -rf /data/local/tmp/*.apk /data/local/tmp/*.zip /data/local/tmp/*.tar* 2>/dev/null; true",
                "rm -rf /data/dalvik-cache/arm64/* 2>/dev/null; true",
                "rm -rf /data/resource-cache/* 2>/dev/null; true",
                "rm -rf /data/system/package_cache/* 2>/dev/null; true",
                "rm -rf /data/anr/* 2>/dev/null; true",
                "rm -rf /data/backup/* 2>/dev/null; true",
                "rm -rf /data/cache/* 2>/dev/null; true",
                "rm -rf /data/tombstones/* 2>/dev/null; true",
                "rm -rf /data/vendor/wifi/* 2>/dev/null; true",
                "logcat -c 2>/dev/null; true",
                "pm trim-caches 999999999 2>/dev/null; true",
            ]:
                try:
                    await adb.shell_root(clean_cmd, timeout=10)
                except Exception:
                    pass

            # Step 13: docker commit → custom image
            logger.info("Committing image as %s (this may take a minute)...", image_name)
            await self._run_cmd(
                self._docker_cmd("commit", temp_name, image_name),
                timeout=180,
            )
            logger.info("=== IMAGE BAKED SUCCESSFULLY ===")
            logger.info("Image: %s", image_name)
            logger.info("Use in config.py: REDROID_IMAGE = \"%s\"", image_name)

        finally:
            # Step 14: Cleanup temp container
            await self._run_cmd(
                self._docker_cmd("rm", "-f", temp_name),
                timeout=15, allow_failure=True,
            )

        return image_name
