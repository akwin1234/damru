"""Experimental containerd/ctr Redroid runtime for Damru auto mode.

This backend intentionally mirrors Damru's Docker launch surface: privileged
Redroid, binderfs bind mount, host networking, PID-shift init wrapper, fixed
ADB ports, ADB root, Android DNS repair, and normal Damru Chrome/profile setup.
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import List, Optional

from .async_core import DamruError
from .config import (
    CONTAINER_BOOT_TIMEOUT,
    CONTAINERD_ADDRESS,
    CONTAINERD_NAMESPACE,
    REDROID_BASE_IMAGE,
    REDROID_BASE_PORT,
    REDROID_CONTAINER_PREFIX,
    REDROID_CPUS,
    REDROID_GPU_MODE,
    REDROID_IMAGE,
    REDROID_MEMORY,
    REDROID_SETUPWIZARD_DISABLED,
)
from .docker import RedroidManager
from .utils import logger


def _ctr_ref(image: str) -> str:
    if "/" not in image:
        return f"docker.io/library/{image}"
    first = image.split("/", 1)[0]
    if "." in first or ":" in first or first == "localhost":
        return image
    return f"docker.io/{image}"


def _memory_bytes(value: str) -> int:
    text = str(value).strip().lower()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([kmgt]?i?b?|)", text)
    if not m:
        return 2 * 1024 * 1024 * 1024
    number = float(m.group(1))
    unit = m.group(2).rstrip("b")
    scale = {
        "": 1,
        "k": 1000,
        "ki": 1024,
        "m": 1000**2,
        "mi": 1024**2,
        "g": 1000**3,
        "gi": 1024**3,
        "t": 1000**4,
        "ti": 1024**4,
    }.get(unit, 1)
    return int(number * scale)


class ContainerdRedroidManager(RedroidManager):
    """Manage Redroid workers with ctr/containerd.

    Scope: Linux/WSL host-network workers. CNI/port-mapped containerd is not
    used because plain ctr does not provide Docker-compatible port publishing.
    """

    runtime_name = "containerd"

    def __init__(self, wsl_distro: Optional[str] = None):
        super().__init__(wsl_distro=wsl_distro)
        self._containerd_address = CONTAINERD_ADDRESS or self._default_containerd_address()
        self._containerd_namespace = CONTAINERD_NAMESPACE or self._default_containerd_namespace()

    def _default_containerd_address(self) -> str:
        if self._is_windows:
            return "/var/run/docker/containerd/containerd.sock"
        return os.environ.get("CONTAINERD_ADDRESS", "/run/containerd/containerd.sock")

    def _default_containerd_namespace(self) -> str:
        if "docker/containerd" in self._containerd_address:
            return "moby"
        return "damru"

    def _ctr_cmd(self, *args: str) -> List[str]:
        parts = ["ctr", "-a", self._containerd_address, "-n", self._containerd_namespace, *args]
        if self._is_windows:
            return ["wsl", "-d", self._wsl_distro, "-u", "root", "--", *parts]
        return parts

    def _ctr_exec_cmd(self, name: str, *args: str) -> List[str]:
        exec_id = f"damru-{int(time.time() * 1000)}-{os.getpid()}"
        return self._ctr_cmd("tasks", "exec", "--exec-id", exec_id, name, *args)

    async def _run_ctr_exec(self, name: str, *args: str, timeout: int = 10, allow_failure: bool = False) -> str:
        return await self._run_cmd(self._ctr_exec_cmd(name, *args), timeout=timeout, allow_failure=allow_failure)

    async def check_docker(self) -> bool:
        """Compatibility entrypoint used by existing auto-mode code."""
        out = await self._run_cmd(self._ctr_cmd("version"), timeout=10, allow_failure=True)
        if out.strip():
            logger.info("containerd runtime available at %s namespace=%s", self._containerd_address, self._containerd_namespace)
            await self._ensure_binderfs()
            return True
        if self._is_windows and "docker/containerd" in self._containerd_address:
            await self._run_cmd(self._start_docker_cmd(), timeout=180, allow_failure=True)
            out = await self._run_cmd(self._ctr_cmd("version"), timeout=10, allow_failure=True)
            if out.strip():
                await self._ensure_binderfs()
                return True
        raise DamruError(
            "containerd runtime is not reachable. Start containerd or set "
            "DAMRU_CONTAINERD_ADDRESS to a working containerd socket."
        )

    async def validate_redroid_multi_container_support(self, count: int) -> None:
        await self._ensure_binderfs()
        if count > 1 and self._is_windows:
            conflicts = await self._detect_cross_distro_host_redroid_conflict()
            if conflicts:
                raise DamruError("Another WSL distro already has Redroid host-network workers running: " + "; ".join(conflicts))

    async def _image_exists(self, image: str) -> bool:
        ref = _ctr_ref(image)
        out = await self._run_cmd(self._ctr_cmd("images", "list", "-q"), timeout=10, allow_failure=True)
        images = {line.strip() for line in out.splitlines() if line.strip()}
        return ref in images or image in images

    async def ensure_image(self, image: str) -> None:
        ref = _ctr_ref(image)
        if await self._image_exists(image):
            return
        if image == REDROID_IMAGE:
            local_tar = Path(__file__).resolve().parent.parent / "damru-redroid-latest.tar"
            if local_tar.exists():
                tar_arg = self._to_wsl_path(str(local_tar)) if self._is_windows else str(local_tar)
                logger.info("Importing baked image into containerd: %s", tar_arg)
                await self._run_cmd(self._ctr_cmd("images", "import", tar_arg), timeout=1200)
                if await self._image_exists(image):
                    return
            base_ref = _ctr_ref(REDROID_BASE_IMAGE)
            logger.warning("Baked image missing in containerd; pulling %s", base_ref)
            await self._run_cmd(self._ctr_cmd("images", "pull", base_ref), timeout=900)
            await self._run_cmd(self._ctr_cmd("images", "tag", base_ref, ref), timeout=30, allow_failure=True)
            return
        await self._run_cmd(self._ctr_cmd("images", "pull", ref), timeout=900)

    async def _task_running(self, name: str) -> bool:
        out = await self._run_cmd(self._ctr_cmd("tasks", "list"), timeout=10, allow_failure=True)
        for line in out.splitlines():
            if line.split()[:1] == [name] and "RUNNING" in line:
                return True
        return False

    async def _container_exists_ctr(self, name: str) -> bool:
        out = await self._run_cmd(self._ctr_cmd("containers", "list", "-q"), timeout=10, allow_failure=True)
        return name in {line.strip() for line in out.splitlines() if line.strip()}

    async def _get_container_state(self, name: str) -> str:
        if await self._task_running(name):
            return "running"
        if await self._container_exists_ctr(name):
            return "created"
        return "none"

    async def list_worker_states(self) -> dict[int, str]:
        containers = await self._run_cmd(self._ctr_cmd("containers", "list", "-q"), timeout=10, allow_failure=True)
        running = await self._run_cmd(self._ctr_cmd("tasks", "list"), timeout=10, allow_failure=True)
        running_names = {line.split()[0] for line in running.splitlines() if line.split()}
        workers: dict[int, str] = {}
        for name in containers.splitlines():
            name = name.strip()
            if not name.startswith(REDROID_CONTAINER_PREFIX):
                continue
            suffix = name.removeprefix(REDROID_CONTAINER_PREFIX)
            if suffix.isdigit():
                workers[int(suffix)] = "running" if name in running_names else "created"
        return workers

    async def _ensure_redroid_pid_shift_wrapper(self) -> str:
        target = "/home/damru/bin/redroid-pid-shift"
        script = r"""
set -e
target=/home/damru/bin/redroid-pid-shift
source=/home/damru/bin/redroid_pid_shift.c
mkdir -p /home/damru/bin
if [ -x "$target" ]; then exit 0; fi
if ! command -v gcc >/dev/null 2>&1; then
  echo "gcc is required to build Damru's Redroid init wrapper. Run python -m damru install-deps -y." >&2
  exit 127
fi
cat > "$source" <<'C'
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    int count = 96;
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
    if (!init_args) return 126;
    init_args[0] = "/init";
    for (int i = 1; i < argc; i++) init_args[i] = argv[i];
    init_args[argc] = NULL;
    execv("/init", init_args);
    fprintf(stderr, "execv /init failed: %s
", strerror(errno));
    return 127;
}
C
gcc -O2 -static -o "$target" "$source"
chmod 755 "$target"
"""
        await self._run_cmd(self._wsl_sudo_cmd(script), timeout=60)
        return target

    async def _wait_for_container_boot_internal(self, name: str, timeout: float = CONTAINER_BOOT_TIMEOUT) -> None:
        elapsed = 0.0
        while elapsed < timeout:
            out = await self._run_ctr_exec(name, "getprop", "sys.boot_completed", timeout=5, allow_failure=True)
            if out.strip() == "1":
                return
            if elapsed >= 30 and await self._android_services_stable_internal(name):
                return
            if not await self._task_running(name):
                raise DamruError(f"containerd task {name} exited during Android boot")
            await asyncio.sleep(2)
            elapsed += 2
        raise DamruError(f"containerd worker {name} failed to boot within {timeout}s")

    async def _android_services_ready_internal(self, name: str) -> bool:
        script = " && ".join([
            "pidof system_server >/dev/null",
            "service check activity | grep -q found",
            "service check activity_task | grep -q found",
            "service check package | grep -q found",
            "service check webviewupdate | grep -q found",
            "echo ready",
        ])
        out = await self._run_ctr_exec(name, "sh", "-lc", script, timeout=8, allow_failure=True)
        return out.strip() == "ready"

    async def _remap_adbd_port(self, name: str, port: int) -> None:
        await self._run_ctr_exec(name, "setprop", "service.adb.tcp.port", str(port), timeout=8, allow_failure=True)
        await self._run_ctr_exec(name, "setprop", "ctl.restart", "adbd", timeout=8, allow_failure=True)
        await asyncio.sleep(3)

    async def _ensure_adb_root(self, serial: str) -> None:
        await self._run_cmd(self._adb_cmd("connect", serial), timeout=10, allow_failure=True)
        await self._run_cmd(self._adb_cmd("root", serial=serial), timeout=10, allow_failure=True)
        await asyncio.sleep(2)
        await self._run_cmd(self._adb_cmd("connect", serial), timeout=10, allow_failure=True)
        out = await self._run_cmd(self._adb_cmd("shell", "id", serial=serial), timeout=8, allow_failure=True)
        if "uid=0" not in out:
            raise DamruError(f"containerd worker {serial} did not expose root ADB")

    async def _prepare_running_worker(self, index: int, name: str, port: int) -> str:
        timeout = self._boot_timeout_for_index(index)
        await self._wait_for_container_boot_internal(name, timeout=timeout)
        await self._remap_adbd_port(name, port)
        serial = await self._serial_for_container(name, port, use_host_network=True)
        await self._ensure_adb_root(serial)
        await self._wait_for_boot(serial, name=None, timeout=timeout)
        await self._ensure_android_dns(serial)
        await self._wait_for_package_service(serial, timeout=90)
        if index not in self._started_indices:
            self._started_indices.append(index)
        return serial

    async def ensure_container(self, index: int) -> str:
        await self._ensure_binderfs()
        name = f"{REDROID_CONTAINER_PREFIX}{index}"
        port = REDROID_BASE_PORT + index
        state = await self._get_container_state(name)
        if state == "running":
            logger.info("Reusing containerd worker %s", name)
            return await self._prepare_running_worker(index, name, port)
        if state != "none":
            await self.stop_container(index)
        return await self.start_container(index)

    async def start_container(self, index: int) -> str:
        await self.ensure_image(REDROID_IMAGE)
        await self._ensure_binderfs()
        wrapper = await self._ensure_redroid_pid_shift_wrapper()
        name = f"{REDROID_CONTAINER_PREFIX}{index}"
        port = REDROID_BASE_PORT + index
        await self.stop_container(index)
        boot_args = [
            "qemu=1",
            "androidboot.hardware=redroid",
            "androidboot.use_memfd=true",
            f"androidboot.redroid_gpu_mode={REDROID_GPU_MODE}",
            "androidboot.redroid_net_ndns=2",
            "androidboot.redroid_net_dns1=1.1.1.1",
            "androidboot.redroid_net_dns2=8.8.8.8",
        ]
        if REDROID_SETUPWIZARD_DISABLED:
            boot_args.append("ro.setupwizard.mode=DISABLED")
        run_args = [
            "run", "-d",
            "--privileged",
            "--net-host",
            "--cpus", str(REDROID_CPUS),
            "--memory-limit", str(_memory_bytes(REDROID_MEMORY)),
            "--env", f"DAMRU_PID_SHIFT_COUNT={96 + (index * 64)}",
            "--mount", "type=bind,src=/dev/binderfs,dst=/dev/binderfs,options=rbind:rw",
            "--mount", f"type=bind,src={wrapper},dst=/damru-redroid-init,options=rbind:ro",
            _ctr_ref(REDROID_IMAGE),
            name,
            "/damru-redroid-init",
            *boot_args,
        ]
        logger.info("Starting containerd worker %s (port %d)", name, port)
        await self._run_cmd(self._ctr_cmd(*run_args), timeout=60)
        return await self._prepare_running_worker(index, name, port)

    async def ensure_all(self, count: int) -> List[str]:
        serials = []
        for index in range(count):
            serials.append(await self.ensure_container(index))
        return serials

    async def pause_container(self, index: int) -> None:
        name = f"{REDROID_CONTAINER_PREFIX}{index}"
        await self._run_cmd(self._ctr_cmd("tasks", "kill", name), timeout=15, allow_failure=True)

    async def stop_container(self, index: int) -> None:
        name = f"{REDROID_CONTAINER_PREFIX}{index}"
        await self._run_cmd(self._ctr_cmd("tasks", "kill", name), timeout=15, allow_failure=True)
        await self._run_cmd(self._ctr_cmd("tasks", "rm", "-f", name), timeout=15, allow_failure=True)
        await self._run_cmd(self._ctr_cmd("containers", "rm", name), timeout=15, allow_failure=True)
        if index in self._started_indices:
            self._started_indices.remove(index)

    async def cleanup_orphans(self) -> None:
        for index in sorted((await self.list_worker_states()).keys()):
            await self.stop_container(index)

    async def restart_container(self, index: int) -> str:
        await self.stop_container(index)
        return await self.start_container(index)

    async def is_container_alive(self, index: int) -> bool:
        return await self._task_running(f"{REDROID_CONTAINER_PREFIX}{index}")
