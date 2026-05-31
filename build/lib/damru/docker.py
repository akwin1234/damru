"""RedroidManager — container lifecycle for damru auto mode.

Redroid needs Linux kernel modules (binder via binderfs) so:
  - Windows: all docker commands run via WSL2 (auto-installs Docker if missing)
  - Linux: docker commands run directly (auto-installs if missing)

Requirements for WSL2:
  - Custom WSL2 kernel with CONFIG_ANDROID_BINDER_IPC=y, CONFIG_ANDROID_BINDERFS=y
  - Kernel modules: ip_tables, iptable_nat, xt_addrtype, ipt_MASQUERADE, bridge, veth
  - Binderfs mounted at /dev/binderfs
  - iptables-nft backend (not iptables-legacy)

Containers are started once at pool init and stay alive.
Only Chrome is recycled per session (stop -> clear -> new fingerprint -> restart).
Containers are cleaned up on pool exit.

All credentials/settings come from config.py (single source of truth).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import List, Optional

from .async_core import DamruError
from .config import (
    CONTAINER_BOOT_TIMEOUT,
    DOCKER_CMD_TIMEOUT,
    APK_INSTALL_TIMEOUT,
    REDROID_BASE_PORT,
    REDROID_CONTAINER_PREFIX,
    REDROID_CPUS,
    REDROID_GPU_MODE,
    REDROID_IMAGE,
    REDROID_MEMORY,
    REDROID_SETUPWIZARD_DISABLED,
    WSL_DISTRO,
    WSL_PASSWORD,
    WSL_USERNAME,
)
from .utils import logger


class RedroidManager:
    """Manage redroid Docker containers for damru auto mode.

    Auto-installs Docker + dependencies if missing.
    All config from damru/config.py.
    """

    def __init__(self, wsl_distro: Optional[str] = None):
        self._is_windows = sys.platform == "win32"
        self._wsl_distro = wsl_distro or WSL_DISTRO
        self._wsl_user = WSL_USERNAME
        self._wsl_pass = WSL_PASSWORD
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

    # ── Command helpers ──

    def _docker_cmd(self, *args: str) -> List[str]:
        """Build docker command. On Windows, run via WSL2 distro."""
        if self._is_windows:
            return ["wsl", "-d", self._wsl_distro, "docker", *args]
        return ["docker", *args]

    def _wsl_sudo_cmd(self, cmd: str) -> List[str]:
        """Build a sudo command inside WSL2 with password piped in."""
        if self._is_windows:
            return [
                "wsl", "-d", self._wsl_distro, "--",
                "bash", "-c",
                f"echo '{self._wsl_pass}' | sudo -S {cmd}",
            ]
        return ["bash", "-c", f"echo '{self._wsl_pass}' | sudo -S {cmd}"]

    async def _run_cmd(
        self,
        cmd: List[str],
        timeout: float = DOCKER_CMD_TIMEOUT,
        allow_failure: bool = False,
    ) -> str:
        """Run a shell command and return stdout."""
        logger.debug("cmd: %s", " ".join(cmd))
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            if allow_failure:
                return ""
            raise DamruError(f"Command timed out: {' '.join(cmd)}")

        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0 and not allow_failure:
            raise DamruError(f"Command failed: {' '.join(cmd)}\n{err}")

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
            self._wsl_sudo_cmd("service docker start"),
            timeout=15, allow_failure=True,
        )

        # Re-check
        try:
            out = await self._run_cmd(
                self._docker_cmd("info", "--format", "{{.OSType}}"),
                timeout=15,
            )
            if "linux" in out.lower():
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
            "ip_tables", "iptable_nat", "iptable_filter", "iptable_raw",
            "iptable_mangle", "nf_nat", "nf_conntrack",
            "xt_nat", "xt_addrtype", "xt_conntrack", "xt_owner",
            "ipt_MASQUERADE", "bridge", "br_netfilter", "veth",
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
        # Check if already mounted
        out = await self._run_cmd(
            self._wsl_sudo_cmd("mount | grep binderfs"),
            timeout=5, allow_failure=True,
        )
        if "binderfs" in out:
            logger.debug("Binderfs already mounted")
            return

        # Mount binderfs
        await self._run_cmd(
            self._wsl_sudo_cmd("mkdir -p /dev/binderfs"),
            timeout=5, allow_failure=True,
        )
        await self._run_cmd(
            self._wsl_sudo_cmd("mount -t binder binder /dev/binderfs"),
            timeout=5, allow_failure=True,
        )

        # Verify
        out = await self._run_cmd(
            self._wsl_sudo_cmd("ls /dev/binderfs/binder"),
            timeout=5, allow_failure=True,
        )
        if "binder" in out or out.strip():
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
            # Use iptables-nft (required for custom WSL2 kernels)
            ("update-alternatives --set iptables /usr/sbin/iptables-nft", 10),
            ("update-alternatives --set ip6tables /usr/sbin/ip6tables-nft", 10),
            ("service docker start", 15),
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

        logger.info("Docker auto-installed and running!")

    # ── Container lifecycle ──

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

    async def ensure_container(self, index: int) -> str:
        """Ensure container exists and is running. Reuses if possible.

        Returns ADB serial (HOST:PORT).
        """
        # Always verify binderfs before container operations — containers
        # crash (exit 255) when binderfs gets unmounted underneath them.
        await self._ensure_binderfs()

        name = f"{REDROID_CONTAINER_PREFIX}{index}"
        port = REDROID_BASE_PORT + index
        await self._get_adb_host()
        serial = self._make_serial(port)

        state = await self._get_container_state(name)

        if state == "running":
            # Container already running — just ensure ADB connected
            logger.info("Reusing running container %s", name)
            await self._run_cmd(
                ["adb", "connect", serial],
                timeout=10, allow_failure=True,
            )
            if index not in self._started_indices:
                self._started_indices.append(index)
            return serial

        elif state in ("exited", "created", "paused"):
            # Container exists but stopped — restart it
            logger.info("Restarting stopped container %s...", name)
            await self._run_cmd(
                self._docker_cmd("start", name),
                timeout=30, allow_failure=True,
            )
            await self._run_cmd(
                ["adb", "connect", serial],
                timeout=10, allow_failure=True,
            )
            await self._wait_for_boot(serial, timeout=CONTAINER_BOOT_TIMEOUT)
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
        ensure_tasks = [self.ensure_container(i) for i in range(count)]
        serials = await asyncio.gather(*ensure_tasks)
        return serials

    async def cleanup_extras(self, count: int) -> None:
        """Disabled — never delete containers, always reuse."""
        return

    async def start_container(self, index: int) -> str:
        """Start one redroid container and return its ADB serial."""
        name = f"{REDROID_CONTAINER_PREFIX}{index}"
        port = REDROID_BASE_PORT + index

        # Remove leftover container with same name
        await self._run_cmd(
            self._docker_cmd("rm", "-f", name),
            timeout=10, allow_failure=True,
        )

        # Start redroid container with binderfs, memfd, and resource limits
        logger.info(
            "Starting container %s (port %d, cpus=%.1f, mem=%s, gpu_mode=%s)...",
            name, port, REDROID_CPUS, REDROID_MEMORY, REDROID_GPU_MODE,
        )
        boot_args = [
            "androidboot.use_memfd=true",
            f"androidboot.redroid_gpu_mode={REDROID_GPU_MODE}",
        ]
        if REDROID_SETUPWIZARD_DISABLED:
            boot_args.append("ro.setupwizard.mode=DISABLED")

        await self._run_cmd(
            self._docker_cmd(
                "run", "-d",
                "--name", name,
                "--privileged",
                "--cpus", str(REDROID_CPUS),
                "--memory", REDROID_MEMORY,
                "--restart=on-failure:3",
                "-v", "/dev/binderfs:/dev/binderfs",
                "-p", f"{port}:5555",
                REDROID_IMAGE,
                *boot_args,
            ),
            timeout=60,
        )

        self._started_indices.append(index)
        await self._get_adb_host()
        serial = self._make_serial(port)

        # Connect ADB (runs on Windows host, connects to WSL2's ADB IP)
        await self._run_cmd(
            ["adb", "connect", serial],
            timeout=10, allow_failure=True,
        )

        # Wait for boot
        logger.info("Waiting for %s to boot...", name)
        await self._wait_for_boot(serial, timeout=CONTAINER_BOOT_TIMEOUT)

        return serial

    async def start_all(self, count: int) -> List[str]:
        """Start N containers in parallel. Returns list of ADB serials."""
        tasks = [self.start_container(i) for i in range(count)]
        return await asyncio.gather(*tasks)

    async def _wait_for_boot(self, serial: str, timeout: float = CONTAINER_BOOT_TIMEOUT) -> None:
        """Poll getprop sys.boot_completed until "1"."""
        adb_cmd = ["adb", "-s", serial, "shell", "getprop", "sys.boot_completed"]
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
            except Exception:
                pass
            await asyncio.sleep(interval)
            elapsed += interval

        raise DamruError(f"Container {serial} failed to boot within {timeout}s")

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

        if p.is_dir():
            all_apks = sorted(p.glob("*.apk"))
            if not all_apks:
                raise DamruError(f"No .apk files in directory: {apk_path}")

            # Install TrichromeLibrary first if present (Chrome needs it)
            trichrome = p / "google_trichrome_library.apk"
            if trichrome.exists():
                logger.info("Installing TrichromeLibrary on %s...", serial)
                await self._run_cmd(
                    ["adb", "-s", serial, "install", "-r", str(trichrome)],
                    timeout=APK_INSTALL_TIMEOUT,
                )

            # Install Chrome split APKs (exclude trichrome library)
            chrome_apks = [
                a for a in all_apks
                if "trichrome" not in a.name.lower()
            ]
            if not chrome_apks:
                raise DamruError(f"No Chrome APKs found in: {apk_path}")

            await self._install_split_via_push(serial, chrome_apks)
            logger.info("Chrome installed on %s (%d split APKs)", serial, len(chrome_apks))
        else:
            await self._run_cmd(
                ["adb", "-s", serial, "install", "-r", str(p)],
                timeout=APK_INSTALL_TIMEOUT,
            )
            logger.info("Chrome installed on %s", serial)

    async def _install_split_via_push(self, serial: str, apks: list) -> None:
        """Install split APKs by pushing to device then using pm session API.

        Avoids adb install-multiple (abb_exec streaming) which causes
        'device offline' errors over ADB TCP with redroid containers.
        """
        remote_dir = "/data/local/tmp/chrome-install"
        await self._run_cmd(
            ["adb", "-s", serial, "shell", "mkdir", "-p", remote_dir],
            timeout=10,
        )

        # Push all APKs to device
        remotes = []
        total_size = 0
        for apk in apks:
            remote = f"{remote_dir}/{apk.name}"
            await self._run_cmd(
                ["adb", "-s", serial, "push", str(apk), remote],
                timeout=APK_INSTALL_TIMEOUT,
            )
            remotes.append(remote)
            total_size += apk.stat().st_size

        # Create pm install session
        out = await self._run_cmd(
            ["adb", "-s", serial, "shell",
             "pm", "install-create", "-r", "-S", str(total_size)],
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
                ["adb", "-s", serial, "shell",
                 "pm", "install-write", "-S",
                 str(apks[i].stat().st_size),
                 session_id, f"split_{i}.apk", remote],
                timeout=60,
            )
            if "success" not in out.lower():
                raise DamruError(
                    f"pm install-write failed for {remote} on {serial}: {out}"
                )

        # Commit the session
        out = await self._run_cmd(
            ["adb", "-s", serial, "shell",
             "pm", "install-commit", session_id],
            timeout=30,
        )
        if "success" not in out.lower():
            raise DamruError(f"pm install-commit failed on {serial}: {out}")

        # Clean up pushed APKs
        await self._run_cmd(
            ["adb", "-s", serial, "shell", "rm", "-rf", remote_dir],
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
            ["adb", "-s", serial, "shell",
             "dumpsys", "package", "com.android.chrome"],
            timeout=10, allow_failure=True,
        )
        if not out or "Unable to find package" in out:
            return None
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("versionName="):
                return line.split("=", 1)[1].strip()
        return None

    async def uninstall_chrome(self, serial: str) -> None:
        """Uninstall Chrome and TrichromeLibrary from a container."""
        for pkg in [
            "com.android.chrome",
            "com.google.android.trichrome.library",
        ]:
            out = await self._run_cmd(
                ["adb", "-s", serial, "shell", "pm", "uninstall", pkg],
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

        pkg_dir = Path(__file__).parent
        search_dirs = [pkg_dir, pkg_dir.parent, pkg_dir.parent.parent]

        # Look for chrome-apks/<version>/ directories
        for d in search_dirs:
            apk_root = d / "chrome-apks"
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

            if version:
                for v in versions:
                    if v.name == version:
                        logger.info("Chrome APK: v%s", v.name)
                        return str(v.resolve())
                raise DamruError(
                    f"Chrome version {version} not found. "
                    f"Available: {[v.name for v in versions]}"
                )

            picked = _random.choice(versions)
            logger.info(
                "Chrome APK: v%s (random from %d available)",
                picked.name, len(versions),
            )
            return str(picked.resolve())

        for d in search_dirs:
            single = d / "chrome.apk"
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
        pushed, eSpeak is configured, ro.debuggable=1 is persistent.

        This means has_preferences() = True on first boot → warm path always.
        No cold start ever — every session gets 10-15s setup.

        Steps:
          1.  Start temp container from base redroid image
          2.  Install Chrome + TrichromeLibrary APKs
          3.  Install eSpeak-NG (100+ offline TTS voices)
          4.  Push resetprop binary
          5.  Install extra fonts to /system/fonts/
          6.  Configure eSpeak as default TTS engine
          7.  Backup original vulkan.pastel.so for GPU patching
          8.  Apply audio 48kHz fix
          9.  Set ro.debuggable=1 in build.prop (persistent)
          10. Launch Chrome → dismiss FRE → create Preferences
          11. Patch universal Preferences (DoH, WebRTC, DNS, etc.)
          12. docker commit → custom image
          13. Remove temp container

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
        await self._get_adb_host()
        serial = self._make_serial(port)

        logger.info("=== BAKING DAMRU IMAGE ===")
        logger.info("Base image: %s", REDROID_IMAGE)
        logger.info("Target image: %s", image_name)

        # Step 1: Start temp container
        await self._ensure_binderfs()
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
                REDROID_IMAGE,
                "androidboot.use_memfd=true",
                f"androidboot.redroid_gpu_mode={REDROID_GPU_MODE}",
            ),
            timeout=60,
        )
        logger.info("Temp container started, connecting ADB...")

        # Connect ADB FIRST (required before shell commands work)
        for _attempt in range(5):
            out = await self._run_cmd(
                ["adb", "connect", serial],
                timeout=10, allow_failure=True,
            )
            if "connected" in out.lower():
                break
            await asyncio.sleep(2)

        await self._wait_for_boot(serial, timeout=CONTAINER_BOOT_TIMEOUT)

        try:
            adb = ADB(serial=serial)
            root = RootOps(adb)
            await root.check_root()

            # Step 2: Install Chrome
            apk_path = chrome_apk or self.find_chrome_apk()
            logger.info("Installing Chrome from %s...", apk_path)
            await self.install_chrome(serial, apk_path)

            # Step 3: Install eSpeak-NG
            logger.info("Installing eSpeak-NG...")
            await root.ensure_espeak_tts()

            # Step 4: Push resetprop binary
            logger.info("Pushing resetprop binary...")
            await root._ensure_resetprop()

            # Step 5: Install extra fonts
            logger.info("Installing extra fonts...")
            await root.install_extra_fonts()

            # Step 6: Configure eSpeak as default TTS
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

            # Step 7: Backup original vulkan.pastel.so
            vulkan_so = "/vendor/lib64/hw/vulkan.pastel.so"
            backup_so = "/data/local/tmp/damru_vk_pastel_orig.so"
            vk_exists = "OK" in await adb.shell(
                f"test -f {vulkan_so} && echo OK", timeout=5, allow_failure=True,
            )
            if vk_exists:
                await adb.shell_root(f"cp {vulkan_so} {backup_so}")
                logger.info("Backed up original vulkan.pastel.so")

            # Step 8: Apply audio 48kHz fix
            await root.apply_audio_48khz()

            # Step 9: Set ro.debuggable=1 persistently in build.prop
            # (resetprop is in-memory only — build.prop survives docker commit)
            logger.info("Setting ro.debuggable=1 in build.prop (persistent)...")
            await adb.shell(
                "su 0 mount -o remount,rw /system 2>/dev/null", allow_failure=True,
            )
            dbg_check = await adb.shell(
                "grep 'ro.debuggable=' /system/build.prop",
                timeout=5, allow_failure=True,
            )
            if "ro.debuggable=1" not in dbg_check:
                if "ro.debuggable=" in dbg_check:
                    await adb.shell_root(
                        "sed -i 's/ro.debuggable=0/ro.debuggable=1/' /system/build.prop",
                    )
                else:
                    await adb.shell_root(
                        "echo 'ro.debuggable=1' >> /system/build.prop",
                    )
                logger.info("ro.debuggable=1 set in build.prop")
            await adb.shell(
                "su 0 mount -o remount,ro /system 2>/dev/null", allow_failure=True,
            )

            # Step 10: Launch Chrome → dismiss FRE → create Preferences
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

            # Step 11: Patch universal Preferences (DoH, WebRTC, privacy)
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

            # Force-stop all apps to get a clean snapshot
            await adb.shell("am force-stop com.android.chrome", allow_failure=True)
            await asyncio.sleep(1)

            # Step 12: docker commit → custom image
            logger.info("Committing image as %s (this may take a minute)...", image_name)
            await self._run_cmd(
                self._docker_cmd("commit", temp_name, image_name),
                timeout=180,
            )
            logger.info("=== IMAGE BAKED SUCCESSFULLY ===")
            logger.info("Image: %s", image_name)
            logger.info("Use in config.py: REDROID_IMAGE = \"%s\"", image_name)

        finally:
            # Step 13: Cleanup temp container
            await self._run_cmd(
                self._docker_cmd("rm", "-f", temp_name),
                timeout=15, allow_failure=True,
            )

        return image_name
