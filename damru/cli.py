"""Command line interface for Damru."""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import html
import importlib.util
import json
import os
import platform
import re
import shutil
import shlex
import socket
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from pathlib import PureWindowsPath
from .apk_assets import bundled_magisk_apk, find_apk_bundle_root, validate_apk_bundle
from .netfix import android_dns_repair_command, wsl_runtime_network_repair_lines, wsl_runtime_network_repair_script

_DAMRU_IMAGE_TAR = "damru-redroid-latest.tar"
_DAMRU_IMAGE_SHA256 = ""  # Set to empty; checksums verified per-download, not against a hardcoded constant
_DAMRU_IMAGE_URL = "https://damru.dev/assets/damru-baked.tar.gz"
_DAMRU_APKS_ZIP = "chrome-apks.zip"
_DAMRU_APKS_URL = "https://damru.dev/assets/chrome-apks.zip"
_DAMRU_APKS_MIRROR_URL = "https://damru.dev/assets/chrome-apks.zip"
_CHROME_APK_AUTO_SKIP_VERSIONS: set[str] = set()


def _is_windows() -> bool:
    return sys.platform == "win32"

def _is_wsl_linux() -> bool:
    if _is_windows() or platform.system() != "Linux":
        return False
    try:
        release = platform.uname().release.lower()
        if "microsoft" in release or "wsl" in release:
            return True
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except Exception:
        return False

def _needs_wsl_iptables_backend() -> bool:
    return _is_windows() or _is_wsl_linux()


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _configured_wsl_distro() -> str:
    env_distro = os.environ.get("DAMRU_WSL_DISTRO")
    if env_distro:
        return env_distro
    try:
        from . import config

        return config.WSL_DISTRO
    except Exception:
        return "Ubuntu"


def _ensure_wsl2_distro(distro: str) -> bool:
    """Ensure the configured Windows distro is WSL2 before Linux setup."""
    if not _is_windows():
        return True
    probe = _run(["wsl", "-d", distro, "-u", "root", "--", "uname", "-r"], timeout=30)
    kernel = (probe.stdout or probe.stderr).strip()
    if probe.returncode == 0 and "WSL2" in kernel:
        return True

    print(
        f"WSL distro '{distro}' is not running a WSL2 kernel ({kernel or 'unknown kernel'}). "
        "Converting it to WSL2 before installing Redroid dependencies."
    )
    _run(["wsl", "--set-default-version", "2"], timeout=120)
    result = _run(["wsl", "--set-version", distro, "2"], timeout=900)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0:
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)
        return False
    _run(["wsl", "--terminate", distro], timeout=60)
    probe = _run(["wsl", "-d", distro, "-u", "root", "--", "uname", "-r"], timeout=60)
    kernel = (probe.stdout or probe.stderr).strip()
    if probe.returncode == 0 and "WSL2" in kernel:
        print(f"WSL distro '{distro}' is now running kernel {kernel}.")
        return True
    print(
        f"WSL distro '{distro}' still is not WSL2 ({kernel or 'unknown kernel'}). "
        "Redroid requires WSL2/Linux kernel features such as binderfs.",
        file=sys.stderr,
    )
    return False


def _run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        errors="replace",
    )

def _run_with_env(cmd: list[str], timeout: int = 30, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        errors="replace",
        env=merged_env,
    )

def _run_bytes(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        cmd,
        capture_output=True,
        timeout=timeout,
    )


def _linux_cmd(script: str, root_user: bool = False) -> list[str]:
    if _is_windows():
        encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
        wrapped = f"printf %s {encoded} | base64 -d | bash"
        cmd = ["wsl", "-d", _configured_wsl_distro()]
        if root_user:
            cmd.extend(["-u", "root"])
        cmd.extend(["--", "bash", "-lc", wrapped])
        return cmd
    return ["bash", "-lc", script]


def _linux_run(
    script: str,
    timeout: int = 30,
    input_text: str | None = None,
    root_user: bool = False,
) -> subprocess.CompletedProcess[str]:
    if input_text is None:
        return _run(_linux_cmd(script, root_user=root_user), timeout=timeout)
    return subprocess.run(
        _linux_cmd(script, root_user=root_user),
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        errors="replace",
    )

def _adb_cmd(serial: str | None, *args: str) -> list[str]:
    if not serial and args and args[0] in {"connect", "disconnect"} and len(args) > 1:
        target = args[1]
        if target.startswith("wsl:"):
            if _is_windows():
                return ["wsl", "-d", _configured_wsl_distro(), "--", "adb", args[0], target[4:]]
            args = (args[0], target[4:], *args[2:])

    if serial and serial.startswith("wsl:"):
        plain = serial[4:]
        routed_args = _translate_wsl_adb_file_args(args)
        if _is_windows():
            return ["wsl", "-d", _configured_wsl_distro(), "--", "adb", "-s", plain, *routed_args]
        serial = plain
        args = tuple(routed_args)

    base = ["adb"]
    if serial:
        base.extend(["-s", serial])
    base.extend(args)

    if _is_windows() and shutil.which("adb") is None:
        quoted = " ".join(shlex.quote(part) for part in base)
        return _linux_cmd(quoted)
    return base

def _to_wsl_path(value: str) -> str:
    if re.match(r"^[A-Za-z]:[\\/]", value):
        p = PureWindowsPath(value)
        drive = p.drive.rstrip(":").lower()
        rest = "/".join(p.parts[1:])
        return f"/mnt/{drive}/{rest}"
    return value

def _translate_wsl_adb_file_args(args: tuple[str, ...]) -> list[str]:
    translated = list(args)
    if not translated:
        return translated
    if translated[0] == "push" and len(translated) >= 3:
        translated[1] = _to_wsl_path(translated[1])
    elif translated[0] == "pull" and len(translated) >= 3:
        translated[2] = _to_wsl_path(translated[2])
    elif translated[0] == "exec-out" and len(translated) >= 2:
        pass
    elif translated[0] in {"install", "install-multiple", "install-multi-package"}:
        translated = [_to_wsl_path(part) for part in translated]
    return translated

def _run_adb_text(serial: str | None, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return _run(_adb_cmd(serial, *args), timeout=timeout)

def _run_adb_bytes(serial: str | None, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[bytes]:
    # PowerShell/Windows pipes can corrupt PNG bytes from `wsl -- adb exec-out`.
    # Use WSL shell redirection for screencap byte streams and read the file back.
    if _is_windows() and serial and serial.startswith("wsl:") and args[:2] == ("exec-out", "screencap"):
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp_path = tmp.name
        wsl_tmp = _to_wsl_path(tmp_path)
        plain = serial[4:]
        script = " ".join(
            shlex.quote(part)
            for part in ["adb", "-s", plain, *args]
        ) + " > " + shlex.quote(wsl_tmp)
        proc = _run(_linux_cmd(script), timeout=timeout)
        data = b""
        if Path(tmp_path).exists():
            data = Path(tmp_path).read_bytes()
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass
        return subprocess.CompletedProcess(proc.args, proc.returncode, data, proc.stderr.encode(errors="replace"))
    return _run_bytes(_adb_cmd(serial, *args), timeout=timeout)

def _adb_devices_text() -> str:
    outputs: list[str] = []
    result = _run_adb_text(None, "devices", "-l", timeout=20)
    if result.returncode == 0:
        outputs.append(result.stdout)
    linux = _linux_run("adb devices -l", timeout=20) if _is_windows() else subprocess.CompletedProcess([], 1, "", "")
    if linux.returncode == 0:
        lines = []
        for line in linux.stdout.splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) >= 2 and parts[0] != "List":
                lines.append(f"wsl:{parts[0]} {parts[1]}")
            else:
                lines.append(line)
        outputs.append("\n".join(lines))
    if not outputs:
        return result.stdout
    header = "List of devices attached"
    merged = [header]
    seen = set()
    for text in outputs:
        for line in text.splitlines()[1:]:
            if not line.strip() or line in seen:
                continue
            seen.add(line)
            merged.append(line)
    return "\n".join(merged) + "\n"

def _resolve_serial(serial: str | None) -> str | None:
    if serial:
        # Strip wsl: prefix on non-WSL platforms; keep it on Windows/WSL
        if serial.startswith("wsl:") and sys.platform != "win32":
            serial = serial[4:]
        return serial
    for line in _adb_devices_text().splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            return parts[0]
    return None

def _ensure_adb_connected(serial: str | None) -> None:
    if serial and ":" in serial:
        _run_adb_text(None, "connect", serial, timeout=15)


def _status(ok: bool, label: str, detail: str = "") -> bool:
    mark = "OK" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{mark}] {label}{suffix}")
    return ok


def _warn(label: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"[WARN] {label}{suffix}")


def _check_command_linux(command: str) -> bool:
    return _linux_run(f"command -v {command} >/dev/null 2>&1").returncode == 0

def _check_command_host_or_linux(command: str) -> bool:
    if shutil.which(command) is not None:
        return True
    return _check_command_linux(command)

def _docker_info_ok(timeout: int = 20) -> bool:
    deadline = time.time() + timeout
    while True:
        if _linux_run("docker info >/dev/null 2>&1", timeout=10, root_user=_is_windows()).returncode == 0:
            return True
        if time.time() >= deadline:
            return False
        time.sleep(2)

def _repair_wsl_main_route_rule() -> None:
    if not _is_windows():
        return
    script = wsl_runtime_network_repair_script()
    try:
        result = _linux_run(script, timeout=30, root_user=True)
    except subprocess.TimeoutExpired:
        _warn("WSL route repair", "timed out; continuing, fix-wsl/check-env will retry")
        return
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "continuing, fix-wsl/check-env will retry"
        _warn("WSL route repair", detail)

def _wsl_dns_repair_lines() -> list[str]:
    return [
        "repair_dns(){",
        "  if timeout 5 getent hosts archive.ubuntu.com >/dev/null 2>&1; then return 0; fi",
        "  cp /etc/resolv.conf /etc/resolv.conf.damru.bak 2>/dev/null || true",
        "  printf 'nameserver 1.1.1.1\\nnameserver 8.8.8.8\\n' > /etc/resolv.conf",
        "  timeout 5 getent hosts archive.ubuntu.com >/dev/null 2>&1 || true",
        "}",
        "apt_update(){ apt-get update -y || { repair_dns; apt-get update -y; }; }",
        "repair_dns",
    ]

def _docker_bridge_available() -> bool:
    result = _linux_run(
        "docker network ls --format '{{.Name}}' | grep -qx bridge",
        timeout=10,
        root_user=_is_windows(),
    )
    return result.returncode == 0

def _modprobe_detail(module: str) -> tuple[bool, str]:
    result = _linux_run(
        f"modprobe {shlex.quote(module)}",
        timeout=10,
        root_user=_is_windows(),
    )
    detail = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    return result.returncode == 0, detail


def _ensure_binderfs_mounted() -> None:
    script = "\n".join([
        "set +e",
        "modprobe binder_linux devices=binder,hwbinder,vndbinder 2>/dev/null || true",
        "mkdir -p /dev/binderfs",
        "if mount | grep -q ' /dev/binderfs ' && test -e /dev/binderfs/binder-control && test -e /dev/binderfs/binder && test -e /dev/binderfs/hwbinder && test -e /dev/binderfs/vndbinder; then exit 0; fi",
        "if mount | grep -q ' /dev/binderfs ' && ! test -e /dev/binderfs/binder-control; then umount /dev/binderfs >/dev/null 2>&1 || true; fi",
        "mount | grep -q ' /dev/binderfs ' || mount -t binder binder /dev/binderfs >/dev/null 2>&1 || true",
        "test -e /dev/binderfs/binder-control && test -e /dev/binderfs/binder && test -e /dev/binderfs/hwbinder && test -e /dev/binderfs/vndbinder",
    ])
    if _is_windows():
        _linux_run(script, timeout=20, root_user=True)
    elif hasattr(os, "geteuid") and os.geteuid() == 0:
        _linux_run(script, timeout=20)

def _kernel_config_text() -> str:
    result = _linux_run(
        "if [ -r /proc/config.gz ]; then zcat /proc/config.gz; fi; "
        "if [ -r /boot/config-$(uname -r) ]; then cat /boot/config-$(uname -r); fi",
        timeout=10,
        root_user=_is_windows(),
    )
    return result.stdout or ""

def _binderfs_mount_populated() -> bool:
    result = _linux_run(
        "test -e /dev/binderfs/binder-control && test -e /dev/binderfs/binder && test -e /dev/binderfs/hwbinder && test -e /dev/binderfs/vndbinder",
        timeout=10,
        root_user=_is_windows(),
    )
    return result.returncode == 0

def _redroid_multi_container_status(binderfs_ok: bool) -> tuple[bool, str]:
    from .docker import _kernel_config_enabled

    config = _kernel_config_text()
    binder_ipc = _kernel_config_enabled(config, "CONFIG_ANDROID_BINDER_IPC")
    binderfs = _kernel_config_enabled(config, "CONFIG_ANDROID_BINDERFS")
    populated = _binderfs_mount_populated()

    problems: list[str] = []
    if binder_ipc is False:
        problems.append("CONFIG_ANDROID_BINDER_IPC disabled")
    if binderfs is False:
        problems.append("CONFIG_ANDROID_BINDERFS disabled")
    if not binderfs_ok:
        problems.append("/dev/binderfs not mounted")
    elif not populated:
        problems.append("/dev/binderfs not populated")
    if problems:
        return False, "; ".join(problems) + "; use max_devices=1 or boot a binderfs-enabled kernel"
    if binderfs is None:
        return True, "binderfs mounted; kernel config not readable, run a two-worker smoke test"
    return True, "binderfs-backed multi-worker Redroid supported"

def _iptables_backend_lines(sudo: str = "") -> list[str]:
    prefix = f"{sudo} " if sudo else ""
    return [
        "if command -v update-alternatives >/dev/null 2>&1; then",
        "  if command -v iptables-legacy >/dev/null 2>&1; then",
        f"    {prefix}update-alternatives --set iptables /usr/sbin/iptables-legacy 2>/dev/null || true",
        f"    {prefix}update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy 2>/dev/null || true",
        "  elif command -v iptables-nft >/dev/null 2>&1; then",
        f"    {prefix}update-alternatives --set iptables /usr/sbin/iptables-nft 2>/dev/null || true",
        f"    {prefix}update-alternatives --set ip6tables /usr/sbin/ip6tables-nft 2>/dev/null || true",
        "  fi",
        "fi",
    ]

def _iptables_nft_backend_lines(sudo: str = "") -> list[str]:
    prefix = f"{sudo} " if sudo else ""
    return [
        "if command -v update-alternatives >/dev/null 2>&1; then",
        "  if command -v iptables-nft >/dev/null 2>&1; then",
        f"    {prefix}update-alternatives --set iptables /usr/sbin/iptables-nft 2>/dev/null || true",
        f"    {prefix}update-alternatives --set ip6tables /usr/sbin/ip6tables-nft 2>/dev/null || true",
        "  fi",
        "fi",
    ]

def _preferred_iptables_backend_lines(sudo: str = "") -> list[str]:
    if _needs_wsl_iptables_backend():
        return _iptables_backend_lines(sudo)
    return _iptables_nft_backend_lines(sudo)

def _wsl_iptables_sanitize_lines(sudo: str = "") -> list[str]:
    if not _needs_wsl_iptables_backend():
        return []
    prefix = f"{sudo} " if sudo else ""
    return [
        f"if {prefix}iptables -S 2>/dev/null | grep -Eq '(^-A (oem_|fw_|bw_|st_|tetherctrl_)|^-N (oem_|fw_|bw_|st_|tetherctrl_))'; then",
        f"  {prefix}iptables -F 2>/dev/null || true",
        f"  {prefix}iptables -t nat -F 2>/dev/null || true",
        f"  {prefix}iptables -P FORWARD ACCEPT 2>/dev/null || true",
        "fi",
    ]

def _restart_docker_lines(sudo: str = "") -> list[str]:
    prefix = f"{sudo} " if sudo else ""
    return [
        "if docker info >/dev/null 2>/dev/null; then",
        "  if command -v systemctl >/dev/null 2>&1 && [ \"$(ps -p 1 -o comm= 2>/dev/null)\" = systemd ]; then",
        f"    {prefix}systemctl reset-failed docker docker.socket containerd 2>/dev/null || true",
        f"    {prefix}systemctl start docker.socket 2>/dev/null || true",
        f"    {prefix}systemctl start containerd 2>/dev/null || true",
        f"    {prefix}systemctl restart docker 2>/dev/null || true",
        "  else",
        f"    {prefix}service docker restart 2>/dev/null || true",
        "  fi",
        "fi",
    ]


def _docker_bridge_nat_repair_lines(sudo: str = "") -> list[str]:
    prefix = f"{sudo} " if sudo else ""
    if prefix:
        return [f"{prefix}bash -lc {shlex.quote(wsl_runtime_network_repair_script())}"]
    return wsl_runtime_network_repair_lines()

def _repair_runtime_internet(serial: str | None = None, quiet: bool = False) -> bool:
    """Repair host WSL networking and Android DNS for a worker."""
    if _is_windows():
        _repair_wsl_main_route_rule()
    if serial:
        _repair_wsl_worker_adbd_port(serial)
        _ensure_adb_connected(serial)
        _run_adb_text(
            serial,
            "shell",
            "sh",
            "-lc",
            android_dns_repair_command(use_wsl_dns_proxy=False)
            + "; locale=$(getprop persist.sys.locale); "
            + "[ -n \"$locale\" ] || { setprop persist.sys.locale en-US; setprop persist.sys.language en; setprop persist.sys.country US; }; true",
            timeout=8,
        )
        if _is_windows():
            _repair_wsl_main_route_rule()
    ok = True
    if _is_windows():
        dns_probe = _linux_run("timeout 10 getent hosts example.com >/dev/null 2>&1", timeout=15, root_user=True)
        ip_probe = _linux_run(
            "timeout 8 python3 -c \"import socket; s=socket.create_connection(('example.com',443),5); s.close()\" >/dev/null 2>&1",
            timeout=10,
            root_user=True,
        )
        ok = ok and dns_probe.returncode == 0 and ip_probe.returncode == 0
    if serial:
        boot_prop = _run_adb_text(serial, "shell", "getprop", "sys.boot_completed", timeout=8)
        state = _run_adb_text(serial, "get-state", timeout=8)
        ok = ok and state.returncode == 0 and "device" in (state.stdout or "") and (boot_prop.stdout or "").strip() == "1" and _android_dns_present(serial)
    if not quiet:
        _status(ok, "Runtime internet", f"serial={serial}" if serial else "host/Docker")
    return ok

def _android_dns_present(serial: str) -> bool:
    dns1 = (_run_adb_text(serial, "shell", "getprop", "net.dns1", timeout=8).stdout or "").strip()
    dns2 = (_run_adb_text(serial, "shell", "getprop", "net.dns2", timeout=8).stdout or "").strip()
    if dns1 or dns2:
        return True
    connectivity = _run_adb_text(serial, "shell", "dumpsys", "connectivity", timeout=12)
    return "DnsAddresses: [ /" in ((connectivity.stdout or "") + (connectivity.stderr or ""))

def _repair_wsl_worker_adbd_port(serial: str) -> None:
    """Repair per-worker adbd TCP port when WSL host-network ADB is down."""
    if not _is_windows():
        return
    match = re.search(r"(?:wsl:)?127\.0\.0\.1:(\d+)$", serial)
    if not match:
        return
    port = int(match.group(1))
    try:
        from . import config

        base_port = int(getattr(config, "REDROID_BASE_PORT", 5600))
        prefix = str(getattr(config, "REDROID_CONTAINER_PREFIX", "damru-worker-"))
    except Exception:
        base_port = 5600
        prefix = "damru-worker-"
    index = port - base_port
    if index < 0 or index > 500:
        return
    name = f"{prefix}{index}"
    script = "\n".join([
        "set +e",
        f"name={shlex.quote(name)}",
        f"port={port}",
        "[ \"$(docker inspect -f '{{.State.Running}}' \"$name\" 2>/dev/null)\" = true ] || exit 0",
        "[ \"$(docker inspect -f '{{.HostConfig.NetworkMode}}' \"$name\" 2>/dev/null)\" = host ] || exit 0",
        "current=$(docker exec \"$name\" getprop service.adb.tcp.port 2>/dev/null | tr -d '\\r')",
        "if [ \"$current\" != \"$port\" ]; then",
        "  docker exec \"$name\" setprop service.adb.tcp.port \"$port\" >/dev/null 2>&1 || true",
        "  docker exec \"$name\" setprop ctl.restart adbd >/dev/null 2>&1 || true",
        "  sleep 2",
        "fi",
        "docker exec \"$name\" sh -lc \"setprop net.dns1 127.0.0.1; setprop net.dns2 1.1.1.1\" >/dev/null 2>&1 || true",
    ])
    _linux_run(script, timeout=20, root_user=True)


def _decode_wsl_list_output(data: bytes) -> list[str]:
    if data.startswith(b"\xff\xfe") or data.count(b"\x00") > max(0, len(data) // 4):
        raw = data.decode("utf-16le", errors="ignore")
    else:
        raw = data.decode(errors="ignore").replace("\x00", "")
    return [line.strip(" \r") for line in raw.splitlines() if line.strip(" \r")]


def _cross_distro_host_redroid_conflicts() -> list[str]:
    if not _is_windows() or shutil.which("wsl") is None:
        return []
    current = _configured_wsl_distro()
    result = _run_bytes(["wsl", "-l", "-q"], timeout=20)
    if result.returncode != 0:
        return []
    conflicts: list[str] = []
    for distro in _decode_wsl_list_output(result.stdout):
        if distro == current:
            continue
        probe = _run([
            "wsl", "-d", distro, "-u", "root", "--", "bash", "-lc",
            "docker ps --filter network=host --format '{{.Names}} {{.Image}}' 2>/dev/null | grep -E '(^| )damru-|redroid' || true",
        ], timeout=15)
        if probe.stdout.strip():
            for line in probe.stdout.strip().splitlines():
                conflicts.append(f"{distro}: {line}")
    return conflicts
def _docker_bridge_internet_ok(timeout: int = 30) -> bool:
    result = _linux_run(
        "docker run --rm alpine sh -c 'ping -c 1 -W 3 8.8.8.8 >/dev/null'",
        timeout=timeout,
        root_user=_is_windows(),
    )
    return result.returncode == 0

def _start_docker_lines(sudo: str = "", attempts: int = 60) -> list[str]:
    prefix = f"{sudo} " if sudo else ""
    docker_info = f"{prefix}docker info"
    return [
        *_preferred_iptables_backend_lines(sudo),
        *_wsl_iptables_sanitize_lines(sudo),
        f"if ! {docker_info} >/dev/null 2>/dev/null && command -v systemctl >/dev/null 2>&1 && [ \"$(ps -p 1 -o comm= 2>/dev/null)\" = systemd ]; then",
        f"  {prefix}systemctl reset-failed docker docker.socket containerd 2>/dev/null || true",
        f"  {prefix}systemctl start docker.socket 2>/dev/null || true",
        f"  {prefix}systemctl start containerd 2>/dev/null || true",
        f"  {prefix}systemctl start docker 2>/dev/null || true",
        "fi",
        f"if ! {docker_info} >/dev/null 2>/dev/null; then {prefix}service docker start 2>/dev/null || true; fi",
        f"if ! {docker_info} >/dev/null 2>/dev/null; then",
        f"  {prefix}pkill dockerd 2>/dev/null || true",
        f"  {prefix}pkill containerd 2>/dev/null || true",
        f"  {prefix}rm -f /var/run/docker.pid /var/run/docker.sock",
        f"  {prefix}nohup dockerd --host=unix:///var/run/docker.sock >/tmp/damru-dockerd.log 2>/tmp/damru-dockerd.err &",
        f"  for i in {{1..{min(attempts, 15)}}}; do",
        f"    {docker_info} >/dev/null 2>/dev/null && break",
        "    sleep 2",
        "  done",
        "fi",
        f"if ! {docker_info} >/dev/null 2>/dev/null; then",
        f"  {prefix}pkill dockerd 2>/dev/null || true",
        f"  {prefix}pkill containerd 2>/dev/null || true",
        f"  {prefix}rm -f /var/run/docker.pid /var/run/docker.sock",
        f"  {prefix}nohup dockerd --iptables=false --ip6tables=false --bridge=none --host=unix:///var/run/docker.sock >/tmp/damru-dockerd-noiptables.log 2>/tmp/damru-dockerd-noiptables.err &",
        f"  for i in {{1..{attempts}}}; do",
        f"    {docker_info} >/dev/null 2>/dev/null && break",
        "    sleep 2",
        "  done",
        "fi",
        *_docker_bridge_nat_repair_lines(sudo),
    ]


def _chrome_apks_available() -> tuple[bool, str]:
    bundle_root = find_apk_bundle_root()
    if bundle_root is not None:
        _ensure_shipped_magisk_in_bundle(bundle_root)
        return validate_apk_bundle(bundle_root)

    try:
        from . import config

        if config.CHROME_APK:
            explicit = Path(config.CHROME_APK)
            return explicit.exists(), str(explicit)
    except Exception:
        pass

    candidates = [
        _repo_root() / "chrome-apks",
        Path.cwd() / "chrome-apks",
        Path.cwd().parent / "chrome-apks",
    ]
    for root in candidates:
        if any(root.glob("*.apk")) or any(
            p.is_dir() and any(p.glob("*.apk")) for p in root.glob("*")
        ):
            return True, str(root)
    return False, "set CHROME_APK or place APKs under ./chrome-apks/<version>/"


def _playwright_patch_status() -> tuple[bool, str]:
    try:
        if importlib.util.find_spec("playwright") is None:
            return False, "playwright package not installed; run install-deps or pip install playwright"

        from . import playwright_patch

        bundled_ok = playwright_patch._BUNDLED_CRPAGE.is_file()
        if not bundled_ok:
            return False, f"bundled patch missing: {playwright_patch._BUNDLED_CRPAGE}"

        target = playwright_patch._find_installed_crpage()
        if target is None:
            return False, "installed Playwright crPage.js path not found; use playwright>=1.40,<1.60"

        if not playwright_patch._is_patched(target):
            playwright_patch.ensure_patched()

        patched = playwright_patch._is_patched(target)
        return patched, str(target)
    except Exception as exc:
        return False, str(exc)


@dataclass
class PreflightCheck:
    id: str
    label: str
    status: str
    detail: str = ""
    fix: str = ""


def _preflight_status(ok: bool, strict: bool = False, warn: bool = False) -> str:
    if ok:
        return "pass"
    if warn and not strict:
        return "warn"
    return "fail"


def _preflight_add(checks: list[PreflightCheck], check_id: str, label: str, status: str, detail: str = "", fix: str = "") -> None:
    checks.append(PreflightCheck(check_id, label, status, detail, fix))


def _preflight_config() -> dict[str, object]:
    try:
        from . import config
    except Exception:
        return {}
    return {
        "mode": getattr(config, "MODE", "auto"),
        "num_devices": int(getattr(config, "NUM_DEVICES", 1) or 1),
        "image": getattr(config, "REDROID_IMAGE", "damru-redroid:latest"),
        "base_port": int(getattr(config, "REDROID_BASE_PORT", 5600) or 5600),
        "chrome_apk": getattr(config, "CHROME_APK", None),
    }


def _preflight_linux_readonly(script: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return _linux_run(script, timeout=timeout, root_user=_is_windows())


def _preflight_command_exists(command: str, timeout: int) -> tuple[bool, str]:
    result = _preflight_linux_readonly("command -v " + shlex.quote(command), timeout)
    return result.returncode == 0, (result.stdout or result.stderr).strip()


def _preflight_docker_image_exists(image: str, timeout: int) -> tuple[bool, str]:
    result = _preflight_linux_readonly("docker image inspect " + shlex.quote(image) + " >/dev/null 2>&1", timeout)
    return result.returncode == 0, image


def _preflight_playwright_patch_status() -> tuple[bool, str]:
    try:
        if importlib.util.find_spec("playwright") is None:
            return False, "playwright package not installed"
        from . import playwright_patch
        if not playwright_patch._BUNDLED_CRPAGE.is_file():
            return False, "bundled patch missing: " + str(playwright_patch._BUNDLED_CRPAGE)
        target = playwright_patch._find_installed_crpage()
        if target is None:
            return False, "installed Playwright crPage.js path not found"
        if not playwright_patch._is_patched(target):
            return False, "not patched: " + str(target)
        return True, str(target)
    except Exception as exc:
        return False, str(exc)


def _preflight_apk_status() -> tuple[bool, str]:
    bundle_root = find_apk_bundle_root()
    if bundle_root is not None:
        return validate_apk_bundle(bundle_root)
    chrome_apk = _preflight_config().get("chrome_apk")
    if chrome_apk:
        p = Path(str(chrome_apk)).expanduser()
        return p.exists(), str(p)
    return False, "no APK bundle found; baked image users can ignore this unless raw Redroid is used"


def _preflight_linux_mem_total_gb(timeout: int) -> float | None:
    result = _preflight_linux_readonly("awk '/MemTotal/ {printf \"%.2f\", $2/1024/1024}' /proc/meminfo", timeout)
    try:
        return float((result.stdout or "").strip()) if result.returncode == 0 else None
    except ValueError:
        return None


def _preflight_linux_disk_free_gb(timeout: int) -> float | None:
    result = _preflight_linux_readonly("df -Pk / | awk 'NR==2 {printf \"%.2f\", $4/1024/1024}'", timeout)
    try:
        return float((result.stdout or "").strip()) if result.returncode == 0 else None
    except ValueError:
        return None


def _preflight_parse_adb_devices(text: str) -> list[tuple[str, str, str]]:
    devices: list[tuple[str, str, str]] = []
    for line in text.splitlines()[1:]:
        if not line.strip():
            continue
        parts = line.split(maxsplit=2)
        if len(parts) >= 2:
            devices.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
    return devices


def _preflight_is_redroid_serial(serial: str, detail: str = "") -> bool:
    clean = serial[4:] if serial.startswith("wsl:") else serial
    return clean.startswith("127.0.0.1:") or "redroid" in detail.lower()


def _preflight_adb_devices(timeout: int) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]], str]:
    try:
        text = _adb_devices_text()
    except subprocess.TimeoutExpired:
        return [], [], "adb devices timed out"
    except Exception as exc:
        return [], [], str(exc)
    devices = _preflight_parse_adb_devices(text)
    online = [item for item in devices if item[1] == "device"]
    physical = [item for item in online if not _preflight_is_redroid_serial(item[0], item[2])]
    return online, physical, text.strip()


def _preflight_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _preflight_ports(base_port: int, count: int, timeout: int) -> tuple[bool, str]:
    ports = [base_port + i for i in range(max(1, count))]
    local_busy = [port for port in ports if _preflight_port_open(port)]
    docker = _preflight_linux_readonly("docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -E 'damru|redroid' || true", timeout)
    detail = []
    if local_busy:
        detail.append("host ports already listening: " + ", ".join(str(p) for p in local_busy))
    if docker.stdout.strip():
        detail.append("running Docker workers detected")
    return not local_busy, "; ".join(detail) if detail else f"ports {ports[0]}-{ports[-1]} look free"


def _preflight_wsl_kernel_status(timeout: int) -> tuple[str, str, str]:
    if _is_wsl_linux():
        kernel = platform.uname().release
        try:
            from .docker import _kernel_config_enabled

            config_text = _kernel_config_text()
            binder_ipc = _kernel_config_enabled(config_text, "CONFIG_ANDROID_BINDER_IPC")
            binderfs = _kernel_config_enabled(config_text, "CONFIG_ANDROID_BINDERFS")
        except Exception:
            binder_ipc = None
            binderfs = None
        if binder_ipc is True and binderfs is True:
            return "pass", f"WSL2 Linux kernel with binderfs support: {kernel}", ""
        if binder_ipc is False or binderfs is False:
            return (
                "fail",
                f"WSL2 Linux kernel lacks Android binderfs support: {kernel}",
                "From Windows run 'python -m damru wsl-kernel install', then 'wsl --shutdown'.",
            )
        return (
            "warn",
            f"WSL2 Linux kernel detected; kernel config not readable: {kernel}",
            "Run 'python -m damru check-env' or a two-worker smoke test to confirm binderfs support.",
        )
    if not _is_windows():
        return "skip", "native Linux; WSL kernel not used", ""
    if shutil.which("wsl") is None:
        return "fail", "wsl.exe not found", "Install WSL2 Ubuntu before running Damru on Windows."
    distro = _configured_wsl_distro()
    result = _run(["wsl", "-d", distro, "-u", "root", "--", "uname", "-r"], timeout=timeout)
    kernel = (result.stdout or result.stderr).strip()
    if result.returncode != 0:
        return "fail", "cannot run WSL distro '" + distro + "': " + kernel, "Set DAMRU_WSL_DISTRO or run 'python -m damru setup'."
    if "WSL2" not in kernel:
        return "fail", kernel or "unknown kernel", "Convert the distro to WSL2."
    config_result = _run(
        [
            "wsl",
            "-d",
            distro,
            "-u",
            "root",
            "--",
            "sh",
            "-lc",
            "if [ -r /proc/config.gz ]; then zcat /proc/config.gz; elif [ -r /boot/config-$(uname -r) ]; then cat /boot/config-$(uname -r); fi",
        ],
        timeout=timeout,
    )
    try:
        from .docker import _kernel_config_enabled

        binder_ipc = _kernel_config_enabled(config_result.stdout or "", "CONFIG_ANDROID_BINDER_IPC")
        binderfs = _kernel_config_enabled(config_result.stdout or "", "CONFIG_ANDROID_BINDERFS")
    except Exception:
        binder_ipc = None
        binderfs = None
    if binder_ipc is True and binderfs is True:
        return "pass", distro + ": WSL2 kernel with binderfs support: " + kernel, ""
    if binder_ipc is False or binderfs is False:
        return "fail", distro + ": WSL2 kernel lacks Android binderfs support: " + kernel, "Run 'python -m damru wsl-kernel install', then 'wsl --shutdown'."
    bundled_ok, bundled_detail = _verify_bundled_wsl_kernel()
    if bundled_ok and _BUNDLED_WSL_KERNEL_NAME in kernel:
        return "pass", distro + ": " + kernel, ""
    if bundled_ok:
        return "warn", distro + ": " + kernel + "; bundled kernel available at " + bundled_detail, "Run 'python -m damru wsl-kernel install' for Redroid WSL support."
    return "warn", distro + ": " + kernel + "; bundled kernel unavailable: " + bundled_detail, "Reinstall Damru package assets."


def _preflight_summary(checks: list[PreflightCheck]) -> dict[str, int]:
    return {status: sum(1 for check in checks if check.status == status) for status in ("pass", "warn", "fail", "skip")}


def _render_preflight_human(checks: list[PreflightCheck]) -> None:
    print("Damru Preflight")
    print("Read-only checks only. No Docker install, image pull/load, container start, mount, modprobe, or iptables changes.\n")
    width = max((len(check.label) for check in checks), default=1)
    for check in checks:
        mark = check.status.upper().ljust(4)
        detail = "  " + check.detail if check.detail else ""
        print(f"{mark} {check.label.ljust(width)}{detail}")
        if check.fix and check.status in {"warn", "fail"}:
            print("     Fix: " + check.fix)
    summary = _preflight_summary(checks)
    print(f"\nSummary: FAIL {summary['fail']}, WARN {summary['warn']}, PASS {summary['pass']}, SKIP {summary['skip']}")


def _check_preflight(args: argparse.Namespace) -> int:
    timeout = max(1, int(getattr(args, "timeout", 3) or 3))
    strict = bool(getattr(args, "strict", False))
    checks: list[PreflightCheck] = []
    cfg = _preflight_config()
    count = int(cfg.get("num_devices", 1) or 1)
    image = str(cfg.get("image", "damru-redroid:latest"))
    base_port = int(cfg.get("base_port", 5600) or 5600)

    host_ok = _is_windows() or platform.system() == "Linux"
    host_detail = "Windows/WSL" if _is_windows() else f"{platform.system()} {platform.release()}"
    _preflight_add(checks, "host_os", "Host OS", _preflight_status(host_ok), host_detail, "Use Windows 10/11 with WSL2 Ubuntu or native Ubuntu 24.")
    wsl_status, wsl_detail, wsl_fix = _preflight_wsl_kernel_status(timeout)
    _preflight_add(checks, "wsl_kernel", "WSL kernel", wsl_status, wsl_detail, wsl_fix)
    py_ok = sys.version_info >= (3, 10)
    _preflight_add(checks, "python", "Python >= 3.10", _preflight_status(py_ok), platform.python_version(), "Install Python 3.10+.")
    try:
        import importlib.metadata as importlib_metadata
        damru_detail = importlib_metadata.version("damru")
    except Exception:
        damru_detail = "source checkout"
    _preflight_add(checks, "damru_package", "Damru package", "pass", damru_detail)
    pw_ok = importlib.util.find_spec("playwright") is not None
    _preflight_add(checks, "playwright", "Python package: playwright", _preflight_status(pw_ok), "installed" if pw_ok else "missing", "Run 'python -m damru install-deps -y' or 'pip install playwright>=1.40,<1.60'.")
    patch_ok, patch_detail = _preflight_playwright_patch_status()
    _preflight_add(checks, "playwright_patch", "Damru Playwright patch", _preflight_status(patch_ok), patch_detail, "Run 'python -m damru install-deps -y' to apply the patch.")

    for command in ("bash", "docker", "adb"):
        ok, detail = _preflight_command_exists(command, timeout)
        _preflight_add(checks, "cmd_" + command, "Linux command: " + command, _preflight_status(ok), detail or ("found" if ok else "missing"), "Run 'python -m damru install-deps -y'.")
    for command in ("curl", "wget", "jq"):
        ok, detail = _preflight_command_exists(command, timeout)
        _preflight_add(checks, "cmd_" + command, "Linux command: " + command, _preflight_status(ok, strict=strict, warn=True), detail or ("found" if ok else "missing"), "Run 'python -m damru install-deps -y'.")

    docker_ok = _preflight_linux_readonly("docker info >/dev/null 2>&1", timeout).returncode == 0
    _preflight_add(checks, "docker_daemon", "Docker daemon", _preflight_status(docker_ok), "running" if docker_ok else "not reachable", "Start Docker or run 'python -m damru install-deps -y'.")
    if docker_ok:
        bridge_ok = _preflight_linux_readonly("docker network inspect bridge >/dev/null 2>&1", timeout).returncode == 0
        _preflight_add(checks, "docker_bridge", "Docker bridge network", _preflight_status(bridge_ok), "available" if bridge_ok else "missing", "Run 'python -m damru fix-wsl' on WSL or repair Docker networking.")
        image_ok, image_detail = _preflight_docker_image_exists(image, timeout)
        _preflight_add(checks, "redroid_image", "Redroid image", _preflight_status(image_ok), image_detail if image_ok else image + " not found", "Run 'python -m damru install-image --download'.")
    else:
        _preflight_add(checks, "docker_bridge", "Docker bridge network", "skip", "Docker daemon unavailable")
        _preflight_add(checks, "redroid_image", "Redroid image", "skip", "Docker daemon unavailable")

    binder = _preflight_linux_readonly("test -e /dev/binder && test -e /dev/hwbinder && test -e /dev/vndbinder", timeout).returncode == 0
    binderfs = _preflight_linux_readonly("test -d /dev/binderfs && mount | grep -q ' /dev/binderfs ' && test -e /dev/binderfs/binder-control && test -e /dev/binderfs/binder && test -e /dev/binderfs/hwbinder && test -e /dev/binderfs/vndbinder", timeout).returncode == 0
    wsl_auto_mountable_binderfs = _is_wsl_linux() and wsl_status == "pass" and not binderfs
    if binder:
        binder_detail = "/dev/binder /dev/hwbinder /dev/vndbinder"
    elif binderfs:
        binder_detail = "binderfs device namespace available"
    elif wsl_auto_mountable_binderfs:
        binder_detail = "binderfs not mounted yet; WSL kernel supports it"
    else:
        binder_detail = "missing one or more binder devices"
    binder_status = _preflight_status(binder or binderfs, strict=strict, warn=wsl_auto_mountable_binderfs)
    binder_fix = "Run 'python -m damru fix-wsl' to mount binderfs before checking again." if wsl_auto_mountable_binderfs else "Use Ubuntu with binder-enabled kernel; on WSL install Damru's bundled kernel."
    _preflight_add(checks, "binder_devices", "Android binder devices", binder_status, binder_detail, binder_fix)
    multi_ok, multi_detail = _redroid_multi_container_status(binderfs)
    if wsl_auto_mountable_binderfs and not multi_ok:
        multi_detail = "/dev/binderfs not mounted yet; Damru can mount it during fix-wsl or worker start"
    multi_status = _preflight_status(multi_ok, strict=strict, warn=wsl_auto_mountable_binderfs)
    multi_fix = "Run 'python -m damru fix-wsl' or start a worker; Damru mounts binderfs before Redroid launch." if wsl_auto_mountable_binderfs else "Run 'python -m damru fix-wsl' on WSL or use a binderfs-enabled Ubuntu kernel."
    _preflight_add(checks, "binderfs", "binderfs multi-worker support", multi_status, multi_detail, multi_fix)

    apk_ok, apk_detail = _preflight_apk_status()
    image_pass = any(c.id == "redroid_image" and c.status == "pass" for c in checks)
    apk_status = "pass" if apk_ok else ("warn" if image_pass and not strict else "fail")
    _preflight_add(checks, "apk_bundle", "APK bundle", apk_status, apk_detail, "Run 'python -m damru install-apks --download' for raw/unbaked Redroid.")

    disk_gb = _preflight_linux_disk_free_gb(timeout)
    disk_need = max(12, 8 + count * 8)
    disk_ok = disk_gb is not None and disk_gb >= disk_need
    _preflight_add(checks, "disk_space", "Disk free", _preflight_status(disk_ok, strict=strict, warn=disk_gb is not None), f"{disk_gb:.1f} GB free; recommended >= {disk_need} GB" if disk_gb is not None else "unknown", "Free disk space before loading Redroid images/workers.")
    mem_gb = _preflight_linux_mem_total_gb(timeout)
    mem_need = max(4, count * 2)
    mem_ok = mem_gb is not None and mem_gb >= mem_need
    _preflight_add(checks, "memory", "RAM", _preflight_status(mem_ok, strict=strict, warn=mem_gb is not None), f"{mem_gb:.1f} GB total; recommended >= {mem_need} GB" if mem_gb is not None else "unknown", "Use fewer workers or a larger VM/WSL memory limit.")
    cpu = os.cpu_count() or 0
    cpu_need = max(2, count * 2)
    _preflight_add(checks, "cpu", "CPU cores", _preflight_status(cpu >= cpu_need, strict=strict, warn=True), f"{cpu}; recommended >= {cpu_need}", "Use fewer workers or a larger VM.")
    ports_ok, ports_detail = _preflight_ports(base_port, count, timeout)
    _preflight_add(checks, "ports", "ADB port range", _preflight_status(ports_ok, strict=strict, warn=True), ports_detail, "Stop stale Damru workers or set DAMRU_REDROID_BASE_PORT.")

    if getattr(args, "no_adb", False):
        _preflight_add(checks, "adb_devices", "ADB devices", "skip", "--no-adb")
    else:
        online, physical, detail = _preflight_adb_devices(timeout)
        status = "pass" if not physical else ("fail" if strict else "warn")
        label_detail = f"online={len(online)}, physical/non-Redroid={len(physical)}"
        if not online and detail:
            label_detail = detail
        _preflight_add(checks, "adb_devices", "ADB devices", status, label_detail, "Disconnect physical devices or target explicit Redroid serials.")

    mode = str(cfg.get("mode", "auto"))
    cfg_ok = mode in {"auto", "manual", "mumu"} and count >= 1 and base_port > 0
    _preflight_add(checks, "config", "Damru config", _preflight_status(cfg_ok), f"mode={mode}, num_devices={count}, image={image}, base_port={base_port}", "Run 'python -m damru setup'.")

    if strict:
        for check in checks:
            if check.status == "warn":
                check.status = "fail"
    summary = _preflight_summary(checks)
    payload = {"ok": summary["fail"] == 0, "summary": summary, "checks": [asdict(check) for check in checks]}
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
    else:
        _render_preflight_human(checks)
    if summary["fail"] == 0:
        return 0
    if any(check.id in {"host_os", "wsl_kernel", "config"} and check.status == "fail" for check in checks):
        return 2
    return 1

def _config_path() -> Path:
    from . import config

    return Path(config.__file__).resolve()


def _detect_wsl_user(distro: str) -> str:
    if not _is_windows() or shutil.which("wsl") is None:
        return ""
    result = _run(["wsl", "-d", distro, "--", "bash", "-lc", "id -un"], timeout=10)
    return result.stdout.strip() if result.returncode == 0 else ""

def _is_placeholder_wsl_user(value: str | None) -> bool:
    if not value:
        return True
    return value.strip().upper() in {"YOUR_WSL_USERNAME_HERE", "YOUR_USERNAME", "USERNAME"}


def _replace_config_value(text: str, name: str, value: object) -> str:
    if isinstance(value, str):
        rendered = repr(value)
    elif value is None:
        rendered = "None"
    else:
        rendered = str(value)

    pattern = rf"^{name}\s*=\s*.*$"
    replacement = f"{name} = {rendered}"
    if re.search(pattern, text, flags=re.MULTILINE):
        return re.sub(pattern, replacement, text, flags=re.MULTILINE)
    return text.rstrip() + f"\n{replacement}\n"


def _write_config(updates: dict[str, object]) -> Path:
    path = _config_path()
    text = path.read_text(encoding="utf-8")
    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8", newline="\n")
    for key, value in updates.items():
        text = _replace_config_value(text, key, value)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _check_env(args: argparse.Namespace) -> int:
    failures = 0
    asset_failures = 0

    if _is_windows():
        wsl = shutil.which("wsl") is not None
        failures += not _status(wsl, "WSL launcher", "native Windows Docker is not used")
        if not wsl:
            return 1

        distro = _configured_wsl_distro()
        distro_ok = _run(["wsl", "-d", distro, "--", "true"], timeout=10).returncode == 0
        failures += not _status(distro_ok, f"WSL distro '{distro}'")
        if not distro_ok:
            return 1
        _repair_wsl_main_route_rule()
    else:
        failures += not _status(platform.system() == "Linux", "Linux host")

    failures += not _status(sys.version_info >= (3, 10), "Python >= 3.10", platform.python_version())

    try:
        import playwright  # noqa: F401

        playwright_ok = True
    except Exception:
        playwright_ok = False
    failures += not _status(playwright_ok, "Python package: playwright")

    patch_ok, patch_detail = _playwright_patch_status()
    failures += not _status(patch_ok, "Damru Playwright crPage.js patch", patch_detail)

    for command in ("adb", "docker", "curl", "wget", "jq"):
        failures += not _status(_check_command_linux(command), f"Linux command: {command}")

    if getattr(args, "viewer", False):
        if _check_command_host_or_linux("scrcpy"):
            _status(True, "Optional viewer command: scrcpy", "needed only for 'python -m damru view'")
        else:
            _warn("Optional viewer command: scrcpy", "run 'python -m damru install-viewer' to enable 'python -m damru view'")

    docker_ok = _docker_info_ok(timeout=1)
    failures += not _status(docker_ok, "Docker daemon inside Linux/WSL")
    if docker_ok:
        bridge_ok = _docker_bridge_available()
        if bridge_ok:
            detail = (
                "available; Windows auto mode uses bridge networking with published ADB ports"
                if _is_windows()
                else "multi-worker Redroid can use mapped ADB ports"
            )
            _status(True, "Docker bridge/NAT networking", detail)
            if _is_windows():
                _linux_run(
                    "\n".join(["set +e", *_docker_bridge_nat_repair_lines()]),
                    timeout=30,
                    root_user=True,
                )
                internet_ok = _docker_bridge_internet_ok(timeout=20)
                if internet_ok:
                    _status(True, "Docker bridge container internet", "bridge containers can reach 8.8.8.8")
                else:
                    failures += 1
                    _status(False, "Docker bridge container internet", "run 'python -m damru fix-wsl'")
        else:
            _warn(
                "Docker bridge/NAT networking",
                "unavailable; install the supported WSL kernel or repair Docker bridge/NAT",
            )
    elif _is_windows():
        xt_addrtype_ok, xt_detail = _modprobe_detail("xt_addrtype")
        _status(
            xt_addrtype_ok,
            "WSL kernel module: xt_addrtype",
            "required by Docker bridge/NAT networking",
        )
        if xt_detail:
            _warn("xt_addrtype diagnostic", xt_detail.splitlines()[-1])

    if _is_windows() and docker_ok:
        conflicts = _cross_distro_host_redroid_conflicts()
        if conflicts:
            failures += 1
            _status(
                False,
                "Cross-distro WSL host-network fallback conflict",
                "stop these containers or use the same WSL distro: " + "; ".join(conflicts),
            )
        else:
            _status(True, "Cross-distro WSL host-network fallback conflict", "none detected")

    _ensure_binderfs_mounted()
    _ensure_binderfs_mounted()
    binderfs_ok = _linux_run(
        "test -d /dev/binderfs && mount | grep -q ' /dev/binderfs ' && test -e /dev/binderfs/binder-control && test -e /dev/binderfs/binder && test -e /dev/binderfs/hwbinder && test -e /dev/binderfs/vndbinder",
        timeout=10,
        root_user=_is_windows(),
    ).returncode == 0
    failures += not _status(binderfs_ok, "binderfs mounted at /dev/binderfs")

    multi_ok, multi_detail = _redroid_multi_container_status(binderfs_ok)
    failures += not _status(multi_ok, "Redroid multi-container binderfs support", multi_detail)

    try:
        from .config import REDROID_IMAGE
    except Exception:
        REDROID_IMAGE = "damru-redroid:latest"
    image_ok = _linux_run(
        f"docker images -q {REDROID_IMAGE} | grep -q .",
        timeout=20,
        root_user=_is_windows(),
    ).returncode == 0
    if image_ok:
        _status(True, f"Redroid image: {REDROID_IMAGE}")
    else:
        _warn(f"Redroid image: {REDROID_IMAGE}", "missing is OK if auto-pull is intended")

    chrome_ok, chrome_detail = _chrome_apks_available()
    if chrome_ok:
        _status(True, "Chrome APKs", chrome_detail)
    elif image_ok:
        _warn("Chrome APKs", "not required when the loaded Damru image already contains Chrome")
    else:
        failures += 1
        asset_failures += 1
        _status(False, "Chrome APKs", chrome_detail)

    if args.adb:
        adb_ok = _linux_run("adb devices | awk 'NR>1 && $2 == \"device\" {found=1} END {exit !found}'").returncode == 0
        failures += not _status(adb_ok, "Online ADB device")

    if failures:
        if asset_failures:
            print("\nLoad the baked Damru Redroid image with: python -m damru install-image")
            print("Or install raw Chrome APK assets with: python -m damru install-apks --download")
        print("Run 'python -m damru install-deps' for common Linux/WSL dependencies.")
        if _is_windows() and not docker_ok:
            print("Run 'python -m damru fix-wsl' to retry safe WSL Docker/binderfs fixes and print kernel guidance.")
        return 1
    return 0


_BUNDLED_WSL_KERNEL_NAME = "wsl2-kernel-redroid-natfix-20260602"
_BUNDLED_WSL_KERNEL_CONFIG = "wsl2-kernel-redroid-natfix-20260602.config"


def _bundled_wsl_kernel_dir() -> Path:
    return Path(__file__).resolve().parent / "wsl_kernel"


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _bundled_wsl_kernel_paths() -> tuple[Path, Path, Path]:
    root = _bundled_wsl_kernel_dir()
    return root / _BUNDLED_WSL_KERNEL_NAME, root / _BUNDLED_WSL_KERNEL_CONFIG, root / "SHA256SUMS"


def _verify_bundled_wsl_kernel() -> tuple[bool, str]:
    kernel, config, sums = _bundled_wsl_kernel_paths()
    for path in (kernel, config, sums):
        if not path.exists():
            return False, f"missing bundled artifact: {path}"
    expected: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            expected[parts[1]] = parts[0].lower()
    for path in (kernel, config):
        actual = _file_sha256(path).lower()
        want = expected.get(path.name)
        if want != actual:
            return False, f"checksum mismatch for {path.name}: expected {want}, got {actual}"
    return True, str(kernel)


def _windows_home() -> Path:
    home = os.environ.get("USERPROFILE")
    if home:
        return Path(home)
    return Path.home()


def _wslconfig_path() -> Path:
    return _windows_home() / ".wslconfig"


def _windows_path_for_wslconfig(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\")


def _set_wslconfig_value(text: str, section: str, key: str, value: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    in_section = False
    section_seen = False
    key_written = False
    section_header = f"[{section}]".lower()

    for line in lines:
        stripped = line.strip()
        is_header = stripped.startswith("[") and stripped.endswith("]")
        if is_header:
            if in_section and not key_written:
                out.append(f"{key}={value}")
                key_written = True
            in_section = stripped.lower() == section_header
            section_seen = section_seen or in_section
            out.append(line)
            continue

        if in_section and stripped.lower().startswith(f"{key.lower()}="):
            if not key_written:
                out.append(f"{key}={value}")
                key_written = True
            continue
        out.append(line)

    if not section_seen:
        if out and out[-1].strip():
            out.append("")
        out.append(f"[{section}]")
        out.append(f"{key}={value}")
    elif in_section and not key_written:
        out.append(f"{key}={value}")

    return "\n".join(out).rstrip() + "\n"



_WSL_KERNEL_RISK_PHRASE = "I UNDERSTAND WSL KERNEL RISK"


def _red_warning(text: str) -> str:
    return f"\033[41;97m{text}\033[0m"


def _print_wsl_kernel_risk_notice() -> None:
    lines = [
        "DAMRU WSL CUSTOM KERNEL WARNING",
        "Recommended: use a fresh/dedicated WSL distro for Damru Redroid.",
        "This changes Windows .wslconfig so WSL boots Damru's bundled custom kernel.",
        "A custom WSL kernel can break Docker, networking, modules, or other WSL workloads.",
        "Damru backs up .wslconfig and kernel artifacts, but cannot guarantee your WSL data or distro stays usable.",
        "Native Linux/Ubuntu does not use this WSL kernel installer.",
    ]
    width = max(len(line) for line in lines) + 4
    print(_red_warning(" " * width))
    for line in lines:
        print(_red_warning("  " + line.ljust(width - 4) + "  "))
    print(_red_warning(" " * width))


def _confirm_wsl_kernel_risk(args: argparse.Namespace) -> bool:
    _print_wsl_kernel_risk_notice()
    if getattr(args, "confirm_wsl_kernel_risk", False):
        return True
    if getattr(args, "yes", False):
        print(
            "Refusing to install WSL kernel with --yes alone. Add "
            "--confirm-wsl-kernel-risk if this is intentional.",
            file=sys.stderr,
        )
        return False
    print(f"Type exactly this phrase to continue: {_WSL_KERNEL_RISK_PHRASE}")
    answer = input("> ").strip()
    if answer != _WSL_KERNEL_RISK_PHRASE:
        print("Cancelled. WSL kernel was not changed.")
        return False
    return True
def _install_bundled_wsl_kernel(args: argparse.Namespace) -> int:
    if not _is_windows():
        print("Bundled WSL kernel install is only needed from Windows hosts.")
        return 1
    ok, detail = _verify_bundled_wsl_kernel()
    if not ok:
        print(f"Bundled WSL kernel unavailable: {detail}", file=sys.stderr)
        return 1

    kernel_src, config_src, _ = _bundled_wsl_kernel_paths()
    dest_dir = _windows_home() / ".damru" / "wsl-kernels"
    kernel_dest = dest_dir / kernel_src.name
    config_dest = dest_dir / config_src.name
    wslconfig = _wslconfig_path()
    timestamp = time.strftime("%Y%m%d-%H%M%S")

    print("Damru will install the bundled WSL2 Redroid/NAT kernel with backups.")
    print(f"  Kernel source: {kernel_src}")
    print(f"  Kernel target: {kernel_dest}")
    print(f"  WSL config:    {wslconfig}")
    if not _confirm_wsl_kernel_risk(args):
        return 1

    dest_dir.mkdir(parents=True, exist_ok=True)
    for src, dest in ((kernel_src, kernel_dest), (config_src, config_dest)):
        if dest.exists() and _file_sha256(dest) != _file_sha256(src):
            backup = dest.with_name(f"{dest.name}.backup-{timestamp}")
            shutil.copy2(dest, backup)
            print(f"Backed up existing artifact: {backup}")
        shutil.copy2(src, dest)

    if wslconfig.exists():
        backup = wslconfig.with_name(f".wslconfig.backup-{timestamp}")
        shutil.copy2(wslconfig, backup)
        text = wslconfig.read_text(encoding="utf-8", errors="replace")
        print(f"Backed up .wslconfig: {backup}")
    else:
        text = ""

    updated = _set_wslconfig_value(
        text,
        "wsl2",
        "kernel",
        _windows_path_for_wslconfig(kernel_dest),
    )
    updated = _set_wslconfig_value(updated, "wsl2", "dnsTunneling", "true")
    updated = _set_wslconfig_value(updated, "wsl2", "networkingMode", "NAT")
    wslconfig.write_text(updated, encoding="utf-8")

    print("Bundled WSL kernel installed and .wslconfig updated.")
    print("Enabled WSL DNS tunneling for reliable apt, pip, and Docker container DNS.")
    print("Restart WSL before testing the new kernel:")
    print("  wsl --shutdown")
    print("Then run:")
    print("  python -m damru fix-wsl")
    print("  python -m damru check-env --viewer")
    return 0


def _wsl_kernel_status(args: argparse.Namespace) -> int:
    ok, detail = _verify_bundled_wsl_kernel()
    _status(ok, "Bundled Damru WSL kernel artifact", detail)
    if _is_windows():
        wslconfig = _wslconfig_path()
        if wslconfig.exists():
            text = wslconfig.read_text(encoding="utf-8", errors="replace")
            kernel_line = next((line.strip() for line in text.splitlines() if line.strip().lower().startswith("kernel=")), "")
            _status(bool(kernel_line), "Current .wslconfig kernel entry", kernel_line or "not set")
        else:
            _warn("Current .wslconfig", "not present")
        if shutil.which("wsl"):
            result = _linux_run("uname -r", timeout=10)
            if result.returncode == 0:
                _status(True, "Active WSL kernel", result.stdout.strip())
            else:
                _warn("Active WSL kernel", (result.stderr or result.stdout).strip() or "unable to query")
    return 0 if ok else 1


def _print_wsl_kernel_guidance(kernel: str = "") -> None:
    if kernel:
        print(f"WSL kernel: {kernel}")
    print(
        "\nDocker/Redroid needs WSL2 kernel support for bridge/NAT networking "
        "and Android binderfs. Damru can install packages, select a Docker-compatible iptables backend, "
        "mount binderfs, and try modprobe, but it cannot create missing kernel "
        "modules from Python."
    )
    print(
        "Required kernel pieces include nft_compat, xt_addrtype, "
        "ip_tables/iptable_nat, nf_nat, bridge/br_netfilter, veth, "
        "and binder/binderfs. If modprobe "
        "reports 'Module xt_addrtype not found', install or boot a WSL2 kernel "
        "built with those options, or run 'python -m damru wsl-kernel install --yes "
        "--confirm-wsl-kernel-risk', then 'wsl --shutdown' and retry."
    )
    print(
        "If you use .wslconfig kernelModules=... with a custom kernel, the modules "
        "must be built for the exact active uname -r. 'Exec format error' from "
        "modprobe means the module VHD is for a different WSL kernel and cannot "
        "fix Docker bridge/NAT for that custom kernel."
    )

def _fix_wsl(args: argparse.Namespace) -> int:
    if _is_windows() and shutil.which("wsl") is None:
        print("WSL is required. Install Ubuntu with: wsl --install -d Ubuntu")
        return 1
    if not _is_windows() and platform.system() != "Linux":
        print("Damru Redroid repair is supported only on Linux or WSL2.")
        return 1

    print("Applying safe Docker/Redroid Linux fixes. Native Windows Docker is not used.")
    _repair_wsl_main_route_rule()
    failures = 0
    backend_lines = _preferred_iptables_backend_lines()
    script = "\n".join([
        "set +e",
        "uname -r",
        *backend_lines,
        *_restart_docker_lines(),
        "modprobe binder_linux devices=binder,hwbinder,vndbinder 2>/dev/null || true",
        "modprobe xt_addrtype 2>/dev/null || true",
        "modprobe ip_tables 2>/dev/null || true",
        "modprobe iptable_nat 2>/dev/null || true",
        "modprobe br_netfilter 2>/dev/null || true",
        "mkdir -p /dev/binderfs",
        "mount | grep -q ' /dev/binderfs ' || mount -t binder binder /dev/binderfs 2>&1",
        *_start_docker_lines(attempts=10),
        *_docker_bridge_nat_repair_lines(),
        "sleep 2",
        "docker info >/dev/null 2>/dev/null",
        "test -d /dev/binderfs && mount | grep -q ' /dev/binderfs '",
    ])
    if _is_windows():
        result = _linux_run(script, timeout=120, root_user=True)
    else:
        result = _linux_run("sudo bash -lc " + shlex.quote(script), timeout=120)
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    if output:
        print(output)

    time.sleep(2)
    docker_ok = _docker_info_ok(timeout=20)
    if _is_windows() and docker_ok:
        conflicts = _cross_distro_host_redroid_conflicts()
        if conflicts:
            failures += 1
            _status(
                False,
                "Cross-distro WSL host-network fallback conflict",
                "stop these containers or use the same WSL distro: " + "; ".join(conflicts),
            )
        else:
            _status(True, "Cross-distro WSL host-network fallback conflict", "none detected")

    _ensure_binderfs_mounted()
    binderfs_ok = _linux_run(
        "test -d /dev/binderfs && mount | grep -q ' /dev/binderfs ' && test -e /dev/binderfs/binder-control && test -e /dev/binderfs/binder && test -e /dev/binderfs/hwbinder && test -e /dev/binderfs/vndbinder",
        timeout=10,
        root_user=_is_windows(),
    ).returncode == 0
    xt_ok, xt_detail = _modprobe_detail("xt_addrtype")
    kernel = _linux_run("uname -r", timeout=10).stdout.strip()

    failures += not _status(docker_ok, "Docker daemon inside Linux/WSL")
    failures += not _status(binderfs_ok, "binderfs mounted at /dev/binderfs")
    if docker_ok:
        if _docker_bridge_available():
            _status(True, "Docker bridge/NAT networking", "multi-worker port mapping available")
            if _is_windows():
                internet_ok = _docker_bridge_internet_ok(timeout=45)
                failures += not _status(
                    internet_ok,
                    "Docker bridge container internet",
                    "bridge containers can reach 8.8.8.8",
                )
        else:
            _warn(
                "Docker bridge/NAT networking",
                "unavailable; Docker is running in no-iptables/no-bridge fallback",
            )
    else:
        failures += not _status(xt_ok, "Kernel module: xt_addrtype", "required by Docker bridge/NAT networking")
        if xt_detail:
            _warn("xt_addrtype diagnostic", xt_detail.splitlines()[-1])

    if failures:
        _print_wsl_kernel_guidance(kernel)
        if _is_windows() and getattr(args, "install_kernel", False):
            print("Installing bundled Damru WSL kernel because repair still failed.")
            return _install_bundled_wsl_kernel(argparse.Namespace(yes=getattr(args, "yes", False), confirm_wsl_kernel_risk=getattr(args, "confirm_wsl_kernel_risk", False)))
        return 1
    print("WSL/Linux Docker and binderfs repair checks passed.")
    return 0


def _install_deps(args: argparse.Namespace) -> int:
    if _is_windows() and shutil.which("wsl") is None:
        print("WSL is required. Install Ubuntu with: wsl --install -d Ubuntu")
        return 1

    wsl_distro = _configured_wsl_distro()
    if _is_windows() and not _ensure_wsl2_distro(wsl_distro):
        return 1

    distro_note = f" in WSL distro '{wsl_distro}'" if _is_windows() else ""
    display_commands = [
        "sudo apt-get update -y",
        "sudo apt-get install -y android-tools-adb docker.io curl wget git jq cpio gcc iptables kmod ca-certificates acl",
        "sudo modprobe binder_linux devices=binder,hwbinder,vndbinder 2>/dev/null || true",
        "sudo modprobe xt_addrtype 2>/dev/null || true",
        "sudo systemctl/service/dockerd start fallback",
        "sudo mkdir -p /dev/binderfs",
        "mount | grep -q ' /dev/binderfs ' || sudo mount -t binder binder /dev/binderfs",
    ]
    iptables_backend = "legacy" if _needs_wsl_iptables_backend() else "nft"
    display_commands[2:2] = [
        f"sudo update-alternatives --set iptables /usr/sbin/iptables-{iptables_backend} || true",
        f"sudo update-alternatives --set ip6tables /usr/sbin/ip6tables-{iptables_backend} || true",
    ]
    if _is_windows():
        display_commands = [c.replace("sudo ", "") for c in display_commands]
    else:
        display_commands.insert(
            2,
            "sudo apt-get install -y linux-modules-extra-$(uname -r)  # native Ubuntu when available",
        )

    print(f"Damru will install Linux dependencies{distro_note}. Docker is never installed in native Windows.")
    for command in display_commands:
        print(f"  {command}")

    if not args.yes:
        answer = input("Continue [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Cancelled.")
            return 1

    _repair_wsl_main_route_rule()

    input_text = None
    if args.sudo_password_stdin and not _is_windows():
        password = sys.stdin.readline()
        if not password:
            print("No sudo password received on stdin.", file=sys.stderr)
            return 1
        input_text = password

    backend_lines = _preferred_iptables_backend_lines()
    sudo_backend_lines = _preferred_iptables_backend_lines("sudo")
    sudo_cmd_backend_lines = _preferred_iptables_backend_lines("sudo_cmd")

    if _is_windows():
        wsl_owner = _detect_wsl_user(wsl_distro) or "root"
        if _is_placeholder_wsl_user(wsl_owner):
            wsl_owner = "root"
        script_lines = [
            "set -e",
            *_wsl_dns_repair_lines(),
            "apt_update",
            "apt-get install -y android-tools-adb docker.io curl wget git jq cpio gcc iptables kmod ca-certificates acl python3-venv",
            f"mkdir -p /home/damru && chown {shlex.quote(wsl_owner)}:{shlex.quote(wsl_owner)} /home/damru 2>/dev/null || true",
            *backend_lines,
            *_restart_docker_lines(),
            "modprobe binder_linux devices=binder,hwbinder,vndbinder 2>/dev/null || true",
            "modprobe xt_addrtype 2>/dev/null || true",
            *_start_docker_lines(),
            "mkdir -p /dev/binderfs",
            "mount | grep -q ' /dev/binderfs ' || mount -t binder binder /dev/binderfs",
        ]
    elif args.sudo_password_stdin:
        script_lines = [
            "set -e",
            "IFS= read -r DAMRU_SUDO_PASSWORD",
            "sudo_cmd(){ printf '%s\\n' \"$DAMRU_SUDO_PASSWORD\" | sudo -S \"$@\"; }",
            "sudo_cmd apt-get update -y",
            "sudo_cmd apt-get install -y android-tools-adb docker.io curl wget git jq cpio gcc iptables kmod ca-certificates acl python3-venv",
            "if apt-cache show \"linux-modules-extra-$(uname -r)\" >/dev/null 2>&1; then sudo_cmd apt-get install -y \"linux-modules-extra-$(uname -r)\"; fi",
            "sudo_cmd mkdir -p /home/damru && if [ -n \"${USER:-}\" ]; then sudo_cmd chown \"$USER:$USER\" /home/damru 2>/dev/null || true; fi",
            "if [ -n \"${USER:-}\" ]; then sudo_cmd usermod -aG docker \"$USER\" 2>/dev/null || true; fi",
            *sudo_cmd_backend_lines,
            *_restart_docker_lines("sudo_cmd"),
            "sudo_cmd modprobe binder_linux devices=binder,hwbinder,vndbinder 2>/dev/null || true",
            "sudo_cmd modprobe xt_addrtype 2>/dev/null || true",
            *_start_docker_lines("sudo_cmd"),
            "if [ -n \"${USER:-}\" ] && [ -S /var/run/docker.sock ]; then sudo_cmd setfacl -m u:${USER}:rw /var/run/docker.sock 2>/dev/null || sudo_cmd chmod 666 /var/run/docker.sock 2>/dev/null || true; fi",
            "sudo_cmd mkdir -p /dev/binderfs",
            "mount | grep -q ' /dev/binderfs ' || sudo_cmd mount -t binder binder /dev/binderfs",
        ]
    else:
        script_lines = [
            "set -e",
            "sudo apt-get update -y",
            "sudo apt-get install -y android-tools-adb docker.io curl wget git jq cpio gcc iptables kmod ca-certificates acl python3-venv",
            "if apt-cache show \"linux-modules-extra-$(uname -r)\" >/dev/null 2>&1; then sudo apt-get install -y \"linux-modules-extra-$(uname -r)\"; fi",
            "sudo mkdir -p /home/damru && if [ -n \"${USER:-}\" ]; then sudo chown \"$USER:$USER\" /home/damru 2>/dev/null || true; fi",
            "if [ -n \"${USER:-}\" ]; then sudo usermod -aG docker \"$USER\" 2>/dev/null || true; fi",
            *sudo_backend_lines,
            *_restart_docker_lines("sudo"),
            "sudo modprobe binder_linux devices=binder,hwbinder,vndbinder 2>/dev/null || true",
            "sudo modprobe xt_addrtype 2>/dev/null || true",
            *_start_docker_lines("sudo"),
            "if [ -n \"${USER:-}\" ] && [ -S /var/run/docker.sock ]; then sudo setfacl -m u:${USER}:rw /var/run/docker.sock 2>/dev/null || sudo chmod 666 /var/run/docker.sock 2>/dev/null || true; fi",
            "sudo mkdir -p /dev/binderfs",
            "mount | grep -q ' /dev/binderfs ' || sudo mount -t binder binder /dev/binderfs",
        ]

    script = "\n".join(script_lines)
    result = _linux_run(
        script,
        timeout=1800,
        input_text=input_text,
        root_user=_is_windows(),
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0:
        missing = [
            command
            for command in ("adb", "docker", "curl", "wget", "git", "jq", "cpio", "gcc", "iptables", "modprobe")
            if not _check_command_linux(command)
        ]
        if missing:
            if result.stderr.strip():
                print(result.stderr.strip(), file=sys.stderr)
            print(f"Missing Linux commands after install attempt: {', '.join(missing)}", file=sys.stderr)
            return result.returncode
        print(
            "Linux package step returned an error, but required commands are already present; continuing.",
            file=sys.stderr,
        )

    failures = 0
    docker_ok = _docker_info_ok(timeout=240)
    if _is_windows() and docker_ok:
        conflicts = _cross_distro_host_redroid_conflicts()
        if conflicts:
            failures += 1
            _status(
                False,
                "Cross-distro WSL host-network fallback conflict",
                "stop these containers or use the same WSL distro: " + "; ".join(conflicts),
            )
        else:
            _status(True, "Cross-distro WSL host-network fallback conflict", "none detected")

    if failures:
        return 1

    binderfs_ok = _linux_run(
        "test -d /dev/binderfs && mount | grep -q ' /dev/binderfs ' && test -e /dev/binderfs/binder-control && test -e /dev/binderfs/binder && test -e /dev/binderfs/hwbinder && test -e /dev/binderfs/vndbinder",
        timeout=10,
    ).returncode == 0

    if not docker_ok:
        if not _is_windows():
            sudo_docker_ok = _linux_run(
                "sudo docker info >/dev/null 2>/dev/null",
                timeout=20,
            ).returncode == 0
            if sudo_docker_ok:
                print(
                    "Docker works with sudo, but this shell cannot access /var/run/docker.sock yet. "
                    "Damru added the current user to the docker group when possible; open a new login shell "
                    "or reconnect SSH, then rerun 'python -m damru check-env'.",
                    file=sys.stderr,
                )
                return 1
        print(
            "Docker installed but the daemon is not running inside Linux/WSL. "
            "On WSL this usually means the kernel lacks Docker netfilter "
            "modules such as xt_addrtype/ip_tables. Run 'python -m damru "
            "check-env' for details.",
            file=sys.stderr,
        )
        return 1
    if not binderfs_ok:
        print("binderfs is not mounted/populated at /dev/binderfs.", file=sys.stderr)
        return 1

    print("Installing Damru Python dependencies into the active interpreter...")
    pip_env: dict[str, str] = {}
    tooling_result = _run_with_env(
        [sys.executable, "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"],
        timeout=600,
        env=pip_env,
    )
    if tooling_result.returncode != 0:
        if tooling_result.stderr.strip():
            print(tooling_result.stderr.strip(), file=sys.stderr)
        return tooling_result.returncode
    repo_root = _repo_root()
    if (repo_root / "pyproject.toml").exists():
        pip_result = _run_with_env(
            [sys.executable, "-m", "pip", "install", "-e", str(repo_root)],
            timeout=600,
            env=pip_env,
        )
        if pip_result.stdout.strip():
            print(pip_result.stdout.strip())
    else:
        pip_result = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="No pyproject.toml near installed package")
    if pip_result.returncode != 0:
        print("Editable install unavailable; installing runtime dependencies directly.")
        dep_result = _run_with_env(
            [
                sys.executable, "-m", "pip", "install",
                "playwright>=1.40,<1.60", "requests>=2.28", "pysocks>=1.7", "websockets>=12",
            ],
            timeout=600,
            env=pip_env,
        )
        if dep_result.stdout.strip():
            print(dep_result.stdout.strip())
        if dep_result.returncode != 0:
            if dep_result.stderr.strip():
                print(dep_result.stderr.strip(), file=sys.stderr)
            return dep_result.returncode

    patch_ok, patch_detail = _playwright_patch_status()
    if not patch_ok:
        print(f"Playwright crPage.js patch failed: {patch_detail}", file=sys.stderr)
        return 1
    print(f"Playwright crPage.js patch OK: {patch_detail}")

    try:
        from .config import REDROID_IMAGE
    except Exception:
        REDROID_IMAGE = "damru-redroid:latest"
    image_ok = _linux_run(
        f"docker images -q {shlex.quote(REDROID_IMAGE)} | grep -q .",
        timeout=20,
        root_user=_is_windows(),
    ).returncode == 0
    if not image_ok and _find_image_tar() is not None:
        print("Found local damru-redroid-latest.tar; loading baked Redroid image...")
        image_code = _install_image(argparse.Namespace(tar=None, download=False, url=_DAMRU_IMAGE_URL, output=None))
        if image_code != 0:
            return image_code
        image_ok = True
    if not image_ok:
        chrome_ok, _ = _chrome_apks_available()
        if not chrome_ok:
            print("No baked image or Chrome APKs found; downloading raw Chrome APK bundle...")
            apk_code = _install_apks(argparse.Namespace(
                zip=None,
                download=True,
                url=_DAMRU_APKS_URL,
                mirror_url=_DAMRU_APKS_MIRROR_URL,
                output=None,
                force=False,
            ))
            if apk_code != 0:
                return apk_code

    print("Dependencies installed. Run 'python -m damru check-env' to verify.")
    return 0


def _prompt(default: object, label: str) -> str:
    suffix = f" [{default}]" if default not in (None, "") else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or ("" if default is None else str(default))


def _setup(args: argparse.Namespace) -> int:
    try:
        from . import config
    except Exception as exc:
        print(f"Could not load damru.config: {exc}", file=sys.stderr)
        return 1

    mode = args.mode or getattr(config, "MODE", "auto")
    num_devices = args.num_devices or getattr(config, "NUM_DEVICES", 1)
    chrome_apk = args.chrome_apk if args.chrome_apk is not None else getattr(config, "CHROME_APK", None)
    wsl_distro = args.wsl_distro or getattr(config, "WSL_DISTRO", "Ubuntu")
    wsl_username = args.wsl_username or getattr(config, "WSL_USERNAME", "")

    if not args.yes:
        print("Damru setup writes damru/config.py and can install Linux/WSL dependencies.")
        mode = _prompt(mode, "Mode (auto/manual/mumu)")
        num_devices = int(_prompt(num_devices, "Number of devices"))
        chrome_value = _prompt(chrome_apk or "", "Chrome APK path or split-APK dir (blank = auto-search)")
        chrome_apk = chrome_value or None

        if _is_windows():
            wsl_distro = _prompt(wsl_distro, "WSL distro")
            detected_user = _detect_wsl_user(wsl_distro)
            wsl_username = _prompt(wsl_username or detected_user, "WSL username")
            print("WSL sudo password is not needed; Damru uses 'wsl -u root' for Linux setup.")

    updates: dict[str, object] = {
        "MODE": mode,
        "NUM_DEVICES": int(num_devices),
        "CHROME_APK": chrome_apk,
    }
    if _is_windows():
        if _is_placeholder_wsl_user(wsl_username):
            wsl_username = _detect_wsl_user(wsl_distro)
        updates.update({
            "WSL_DISTRO": wsl_distro,
            "WSL_USERNAME": wsl_username,
            "WSL_PASSWORD": "",
        })

    path = _write_config(updates)
    print(f"Config updated: {path}")

    if not args.skip_deps:
        install_code = _install_deps(argparse.Namespace(
            yes=True,
            sudo_password_stdin=getattr(args, "sudo_password_stdin", False),
        ))
        if install_code != 0:
            if _is_windows() and getattr(args, "install_wsl_kernel", False):
                return _install_bundled_wsl_kernel(argparse.Namespace(yes=True, confirm_wsl_kernel_risk=getattr(args, "confirm_wsl_kernel_risk", False)))
            return install_code

    check_code = _check_env(argparse.Namespace(adb=args.adb, viewer=False))
    if check_code != 0 and _is_windows() and getattr(args, "install_wsl_kernel", False):
        return _install_bundled_wsl_kernel(argparse.Namespace(yes=True, confirm_wsl_kernel_risk=getattr(args, "confirm_wsl_kernel_risk", False)))
    return check_code


def _benchmark(args: argparse.Namespace) -> int:
    from .benchmark import main as benchmark_main

    benchmark_args: list[str] = []
    for option in ("device", "serial", "proxy", "timezone", "locale", "screenshots", "output"):
        value = getattr(args, option)
        if value is not None:
            benchmark_args.extend([f"--{option.replace('_', '-')}", value])
    if args.tests:
        benchmark_args.append("--tests")
        benchmark_args.extend(args.tests)
    if args.debug:
        benchmark_args.append("--debug")

    return int(benchmark_main(benchmark_args) or 0)


def _bake_image(args: argparse.Namespace) -> int:
    import asyncio

    from .docker import RedroidManager

    async def _run_bake() -> None:
        await RedroidManager(wsl_distro=args.wsl_distro).bake_image(
            chrome_apk=args.chrome_apk,
            image_name=args.image,
        )

    asyncio.run(_run_bake())
    return 0

def _candidate_image_tars(explicit: str | None = None) -> list[Path]:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    for root in (Path.cwd(), Path.cwd().parent, _repo_root(), _repo_root().parent, Path.home(), Path.home() / "Downloads"):
        candidates.append(root / _DAMRU_IMAGE_TAR)
    seen: set[str] = set()
    unique: list[Path] = []
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path.absolute())
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique

def _find_image_tar(explicit: str | None = None) -> Path | None:
    for path in _candidate_image_tars(explicit):
        if path.is_file():
            return path.resolve()
    return None

def _download_file(url: str, target: Path) -> None:
    import requests

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()
    downloaded = 0
    with tmp.open("wb") as fh:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            fh.write(chunk)
            downloaded += len(chunk)
            if downloaded and downloaded % (100 * 1024 * 1024) < 1024 * 1024:
                print(f"Downloaded {downloaded // (1024 * 1024)} MB...")
    tmp.replace(target)

def _install_image(args: argparse.Namespace) -> int:
    try:
        from .config import REDROID_IMAGE
    except Exception:
        REDROID_IMAGE = "damru-redroid:latest"

    if not _docker_info_ok(timeout=20):
        print("Docker is not running. Run 'python -m damru install-deps -y' first.", file=sys.stderr)
        return 1

    _was_downloaded = False
    tar_path = _find_image_tar(args.tar)
    if tar_path is None:
        if not args.download:
            searched = "\n  ".join(str(p) for p in _candidate_image_tars(args.tar))
            print(f"Could not find {_DAMRU_IMAGE_TAR}. Searched:\n  {searched}", file=sys.stderr)
            print("Place the tarball there or run: python -m damru install-image --download", file=sys.stderr)
            return 1
        target = Path(args.output or (Path.cwd() / _DAMRU_IMAGE_TAR)).expanduser().resolve()
        print(f"Downloading baked image to {target}")
        try:
            _download_file(args.url, target)
        except Exception as exc:
            print(f"Image download failed: {exc}", file=sys.stderr)
            print(f"Manual download URL: {args.url}", file=sys.stderr)
            return 1
        tar_path = target
        # Skip SHA256 check for freshly downloaded files (new baked images)
        _was_downloaded = True
    digest = _file_sha256(tar_path)
    if _was_downloaded:
        pass  # skip SHA check for downloaded files
    elif _DAMRU_IMAGE_SHA256 and digest.lower() != _DAMRU_IMAGE_SHA256.lower():
        print(f"Warning: Image checksum mismatch for {tar_path.name}: expected {_DAMRU_IMAGE_SHA256}, got {digest}", file=sys.stderr)
        print("Continuing anyway — checksums are advisory for pre-placed tarballs.")

    linux_tar = _to_wsl_path(str(tar_path)) if _is_windows() else str(tar_path)
    print(f"Loading {tar_path} into Docker as {REDROID_IMAGE}...")
    load = _linux_run(f"docker load -i {shlex.quote(linux_tar)}", timeout=1800, root_user=_is_windows())
    if load.stdout.strip():
        print(load.stdout.strip())
    if load.returncode != 0:
        if load.stderr.strip():
            print(load.stderr.strip(), file=sys.stderr)
        return load.returncode

    image_ok = _linux_run(f"docker images -q {shlex.quote(REDROID_IMAGE)} | grep -q .", timeout=20, root_user=_is_windows()).returncode == 0
    if not image_ok:
        print(f"Docker loaded the tarball, but {REDROID_IMAGE} was not found.", file=sys.stderr)
        return 1
    print(f"Redroid image ready: {REDROID_IMAGE}")
    return 0

def _candidate_apk_zips(explicit: str | None = None) -> list[Path]:
    names = [_DAMRU_APKS_ZIP, "damru-chrome-apks-latest.zip"]
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    for root in (Path.cwd(), Path.cwd().parent, _repo_root(), _repo_root().parent, Path.home(), Path.home() / "Downloads"):
        for name in names:
            candidates.append(root / name)
    seen: set[str] = set()
    unique: list[Path] = []
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path.absolute())
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique

def _find_apk_zip(explicit: str | None = None) -> Path | None:
    for path in _candidate_apk_zips(explicit):
        if path.is_file():
            return path.resolve()
    return None

def _chrome_apk_version_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [p for p in sorted(root.iterdir()) if p.is_dir() and any(p.glob("*.apk"))]

def _preferred_chrome_apk_version_dir(version_dirs: list[Path]) -> Path | None:
    if not version_dirs:
        return None
    compatible = [
        p for p in version_dirs
        if p.name not in _CHROME_APK_AUTO_SKIP_VERSIONS
        and not p.name.startswith("145.")
        and not p.name.startswith("146.")
    ]
    candidates = compatible or version_dirs
    # Prefer the latest version that has a matching webview.apk inside
    _WEBVIEW_NAMES = {'webview.apk', 'trichromewebview.apk'}
    with_webview = [
        p for p in candidates
        if any(apk.name.lower() in _WEBVIEW_NAMES for apk in p.glob('*.apk'))
    ]
    return (with_webview or candidates)[-1]

def _ensure_shipped_magisk_in_bundle(root: Path) -> None:
    """Copy Damru's shipped Magisk APK into an extracted APK bundle if missing."""
    target = root / "magisk.apk"
    if target.is_file() and target.stat().st_size > 1_000_000:
        return
    source = bundled_magisk_apk()
    if source is None:
        return
    root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

def _safe_extract_zip(zf: zipfile.ZipFile, target: Path) -> None:
    target = target.resolve()
    for member in zf.infolist():
        destination = (target / member.filename).resolve()
        if destination != target and target not in destination.parents:
            raise ValueError(f"ZIP entry escapes extract directory: {member.filename}")
    zf.extractall(target)

def _install_apks(args: argparse.Namespace) -> int:
    ok, detail = _chrome_apks_available()
    if ok and not getattr(args, "force", False):
        print(f"Chrome APKs already available: {detail}")
        return 0

    zip_path = _find_apk_zip(args.zip)
    if zip_path is None:
        if not args.download:
            searched = "\n  ".join(str(p) for p in _candidate_apk_zips(args.zip))
            print(f"Could not find {_DAMRU_APKS_ZIP}. Searched:\n  {searched}", file=sys.stderr)
            print("Run: python -m damru install-apks --download", file=sys.stderr)
            return 1
        target_zip = Path(args.zip or (Path.cwd() / _DAMRU_APKS_ZIP)).expanduser().resolve()
        for url in (args.url, args.mirror_url):
            if not url:
                continue
            print(f"Downloading Chrome APK bundle from {url}")
            try:
                _download_file(url, target_zip)
                zip_path = target_zip
                break
            except Exception as exc:
                print(f"Download failed: {exc}", file=sys.stderr)
        if zip_path is None:
            return 1

    if not zipfile.is_zipfile(zip_path):
        print(f"Not a valid ZIP archive: {zip_path}", file=sys.stderr)
        return 1

    if args.output:
        output_root = Path(args.output).expanduser().resolve()
    elif _is_windows():
        output_root = (Path.cwd() / "chrome-apks").resolve()
    else:
        output_root = Path("/home/damru/chrome-apks").resolve()
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n and not n.endswith("/")]
        if not any(n.lower().endswith(".apk") for n in names):
            print(f"ZIP does not contain APK files: {zip_path}", file=sys.stderr)
            return 1
        top_levels = {n.split("/", 1)[0] for n in names if "/" in n}
        extract_dir = output_root.parent if top_levels == {"chrome-apks"} else output_root
        extract_dir.mkdir(parents=True, exist_ok=True)
        _safe_extract_zip(zf, extract_dir)

    apk_root = output_root
    if not apk_root.is_dir() and (output_root.parent / "chrome-apks").is_dir():
        apk_root = output_root.parent / "chrome-apks"
    _ensure_shipped_magisk_in_bundle(apk_root)
    bundle_ok, bundle_detail = validate_apk_bundle(apk_root)
    if not bundle_ok:
        print(f"Invalid APK bundle after extraction: {bundle_detail}", file=sys.stderr)
        return 1
    version_dirs = _chrome_apk_version_dirs(apk_root)

    auto_roots = {_repo_root() / "chrome-apks", Path.cwd() / "chrome-apks", Path.cwd().parent / "chrome-apks"}
    if apk_root.resolve() not in {p.resolve() for p in auto_roots}:
        config_target = _preferred_chrome_apk_version_dir(version_dirs) or apk_root
        config_value = _to_wsl_path(str(config_target)) if _is_windows() else str(config_target)
        _write_config({"CHROME_APK": config_value})
        print(f"Config updated: CHROME_APK = {config_value}")

    print(f"Chrome APKs ready: {apk_root}")
    return 0


def _devices(args: argparse.Namespace) -> int:
    print(_adb_devices_text().strip())
    return 0

def _fix_internet(args: argparse.Namespace) -> int:
    if getattr(args, "all", False):
        ok = _repair_runtime_internet(None, quiet=False)
        serials = _running_damru_worker_serials()
        seen: set[str] = set()
        for item in serials:
            if item in seen:
                continue
            seen.add(item)
            ok = _repair_runtime_internet(item, quiet=False) and ok
        return 0 if ok else 1
    serial = _resolve_serial(args.serial) if getattr(args, "serial", None) else None
    ok = _repair_runtime_internet(serial, quiet=False)
    return 0 if ok else 1

def _running_damru_worker_serials() -> list[str]:
    try:
        from . import config

        prefix = str(getattr(config, "REDROID_CONTAINER_PREFIX", "damru-worker-"))
        base_port = int(getattr(config, "REDROID_BASE_PORT", 5600))
    except Exception:
        prefix = "damru-worker-"
        base_port = 5600
    script = f"docker ps --filter name={shlex.quote(prefix)} --format '{{{{.Names}}}}' 2>/dev/null || true"
    proc = _linux_run(script, timeout=15, root_user=True) if _is_windows() else _run(["bash", "-lc", script], timeout=15)
    serials: list[str] = []
    for line in (proc.stdout or "").splitlines():
        name = line.strip()
        if not name.startswith(prefix):
            continue
        suffix = name.removeprefix(prefix)
        if suffix.isdigit():
            serial = f"127.0.0.1:{base_port + int(suffix)}"
            serials.append(f"wsl:{serial}" if _is_windows() else serial)
    return sorted(serials, key=lambda item: int(item.rsplit(":", 1)[-1]))

def _random_profile(args: argparse.Namespace) -> int:
    if getattr(args, "all", False):
        serials = _running_damru_worker_serials()
        if not serials:
            print("No running Damru workers found.", file=sys.stderr)
            return 1
        ok = True
        for serial in serials:
            code = _random_profile(argparse.Namespace(
                serial=serial,
                all=False,
                profile_tier=getattr(args, "profile_tier", "premium"),
                proxy=getattr(args, "proxy", None),
                http_proxy=getattr(args, "http_proxy", None),
                chrome_version=getattr(args, "chrome_version", None),
            ))
            ok = ok and code == 0
        return 0 if ok else 1
    serial = _resolve_serial(args.serial)
    if not serial:
        print("No online ADB device found. Use --serial or start a Redroid device first.", file=sys.stderr)
        return 1
    _repair_runtime_internet(serial, quiet=True)

    async def _apply() -> str:
        from .adb import ADB
        from .chrome import ChromeManager
        from .devices import get_random_device
        from .docker import RedroidManager
        from .profiles import build_profile
        from .proxy import build_accept_language
        from .root import RootOps

        adb = ADB(serial)
        real_android = await adb.get_prop("ro.build.version.release")
        device = get_random_device(
            android_version=real_android.strip() or None,
            profile_tier=getattr(args, "profile_tier", "premium"),
        )
        explicit_proxy = getattr(args, "proxy", None)
        explicit_http_proxy = getattr(args, "http_proxy", None)
        current_http_proxy = explicit_http_proxy
        if not explicit_proxy and not current_http_proxy:
            current_http_proxy = await adb.shell("settings get global http_proxy", allow_failure=True)
        current_http_proxy = (current_http_proxy or "").strip()
        if current_http_proxy in {"", "null", ":0"}:
            current_http_proxy = None
        profile = build_profile(device, proxy=explicit_proxy, http_proxy=current_http_proxy)
        root = RootOps(adb)
        await root.check_root()
        chrome = ChromeManager(adb)
        await chrome.detect_package(retries=8, delay=1.0)
        await chrome.force_stop()
        await chrome.clear_all_data()
        chrome_note = ""
        docker = RedroidManager()
        current_chrome = await docker.get_installed_chrome_version(serial)
        installed_chrome = current_chrome
        desired_chrome_version = getattr(args, "chrome_version", None)
        try:
            apk_path = docker.find_chrome_apk(None, version=desired_chrome_version)
        except Exception:
            if desired_chrome_version:
                raise
            apk_path = None
            chrome_note = "; chrome=kept (APK rotation unavailable)"
        if apk_path:
            for _ in range(8):
                if desired_chrome_version:
                    break
                candidate = docker.find_chrome_apk(None)
                if Path(candidate).name != current_chrome:
                    apk_path = candidate
                    break
            from .apk_assets import find_matching_webview_apk

            if Path(apk_path).is_dir() and find_matching_webview_apk(apk_path, apk_path) is None:
                raise RuntimeError(
                    f"Matching WebView APK missing for Chrome {Path(apk_path).name}; current Chrome was kept."
                )
            await docker.install_chrome(serial, apk_path)
            installed_chrome = await docker.get_installed_chrome_version(serial)
            await chrome.detect_package(retries=8, delay=1.0)
            await chrome.force_stop()
            await chrome.clear_all_data()
            chrome_note = f"; chrome={installed_chrome or Path(apk_path).name}"
        await root.apply_device_props(device, safe_only=True, parallel=True)
        await root.apply_version_release(device)
        await root.apply_timezone(profile.timezone)
        await root.apply_locale(profile.locale)
        applied_proxy = _apply_android_proxy(serial, explicit_proxy, current_http_proxy)
        await adb.shell(f"wm size {profile.screen_width}x{profile.screen_height}", allow_failure=True)
        await adb.shell(f"wm density {profile.density_dpi}", allow_failure=True)
        accept_lang = build_accept_language(profile.locale)
        await chrome.write_command_line(profile.chrome_flags)
        await chrome.patch_preferences(profile.locale, accept_lang)
        from .chrome import WEBVIEW_SHELL_PACKAGE
        from .profile_apply import _build_webview_user_agent

        if await chrome.webview_shell_installed(WEBVIEW_SHELL_PACKAGE):
            await adb.shell(f"am force-stop {WEBVIEW_SHELL_PACKAGE}", allow_failure=True)
            await root.setup_memory_preload(WEBVIEW_SHELL_PACKAGE)
            await chrome.write_webview_command_line(
                profile.chrome_flags,
                user_agent=_build_webview_user_agent(device, installed_chrome or current_chrome),
            )
            await chrome.patch_webview_preferences(profile.locale, accept_lang, WEBVIEW_SHELL_PACKAGE)
        if applied_proxy:
            await asyncio.gather(
                root.apply_webrtc_block(chrome.package),
                root.apply_webrtc_block(WEBVIEW_SHELL_PACKAGE),
            )
        await chrome.force_stop()
        proxy_note = f"; proxy={applied_proxy}" if applied_proxy else ""
        return f"{profile.description}; {profile.screen_width}x{profile.screen_height}@{profile.density_dpi}; tz={profile.timezone}; locale={profile.locale}{proxy_note}{chrome_note}"

    try:
        import asyncio
        detail = asyncio.run(_apply())
    except Exception as exc:
        print(f"Random profile failed: {exc}", file=sys.stderr)
        return 1
    print(f"Random stealth profile applied on {serial}: {detail}")
    return 0

def _force_profile(args: argparse.Namespace) -> int:
    serial = _resolve_serial(args.serial)
    if not serial:
        print("No online ADB device found. Use --serial or start a Redroid device first.", file=sys.stderr)
        return 1
    _repair_runtime_internet(serial, quiet=True)

    async def _apply():
        from .profile_apply import force_device_profile

        return await force_device_profile(
            serial,
            args.device,
            proxy=getattr(args, "proxy", None),
            http_proxy=getattr(args, "http_proxy", None),
            timezone=getattr(args, "timezone", None),
            locale=getattr(args, "locale", None),
            configure_chrome=not getattr(args, "no_chrome", False),
            browser_package=getattr(args, "browser_package", "com.android.chrome"),
            clear_chrome=not getattr(args, "no_clear_chrome", False),
            rotate_chrome=getattr(args, "rotate_chrome", False),
            chrome_version=getattr(args, "chrome_version", None),
            apply_cpu=not getattr(args, "no_cpu", False),
            apply_gpu=not getattr(args, "no_gpu", False),
            apply_memory=not getattr(args, "no_memory", False),
            clear_proxy=getattr(args, "clear_proxy", False),
        )

    try:
        import asyncio
        result = asyncio.run(_apply())
    except Exception as exc:
        print(f"Force profile failed: {exc}", file=sys.stderr)
        return 1

    proxy_note = f"; proxy={result.android_http_proxy}" if result.android_http_proxy else ""
    chrome_note = f"; {result.chrome_note}" if result.chrome_note else ""
    print(
        f"Forced profile applied on {serial}: {result.description}; "
        f"{result.screen_width}x{result.screen_height}@{result.density_dpi}; "
        f"tz={result.timezone}; locale={result.locale}{proxy_note}{chrome_note}"
    )
    return 0

def _ui_stealth_check_all(args: argparse.Namespace) -> int:
    serials = _running_damru_worker_serials()
    if not serials:
        print("No running Damru workers found.", file=sys.stderr)
        return 1
    output_root = Path(args.output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    ok = True
    for serial in serials:
        safe = serial.replace(":", "-").replace("/", "-")
        target = output_root / safe
        target.mkdir(parents=True, exist_ok=True)
        print(f"Running stealth checker on {serial}...")
        code = _benchmark(argparse.Namespace(
            device=None,
            serial=serial,
            proxy=args.proxy,
            timezone=None,
            locale=None,
            tests=None,
            screenshots=str(target),
            output=str(target / "proof.json"),
            debug=False,
        ))
        print(f"{serial}: {'OK' if code == 0 else 'FAILED'}")
        ok = ok and code == 0
    print(f"Stealth checker all output: {output_root}")
    return 0 if ok else 1

def _screenshot(args: argparse.Namespace) -> int:
    serial = _resolve_serial(args.serial)
    if not serial:
        print("No online ADB device found. Use --serial or start a Redroid device first.", file=sys.stderr)
        return 1
    _ensure_adb_connected(serial)

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    result = _run_adb_bytes(serial, "exec-out", "screencap", "-p", timeout=30)
    if result.returncode != 0 or not result.stdout:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        print(stderr or "ADB screencap failed.", file=sys.stderr)
        return result.returncode or 1
    output.write_bytes(result.stdout)
    print(f"Screenshot saved: {output}")
    return 0

def _chrome_package_installed(serial: str, package: str) -> bool:
    result = _run_adb_text(serial, "shell", "pm", "path", package, timeout=15)
    return result.returncode == 0 and f"package:" in (result.stdout or "")

def _ensure_chrome_for_open_url(serial: str, package: str) -> int:
    if _chrome_package_installed(serial, package):
        return 0

    chrome_ok, _ = _chrome_apks_available()
    if not chrome_ok:
        print("Chrome is not installed on the worker; downloading APK bundle first...", file=sys.stderr)
        apk_code = _install_apks(argparse.Namespace(
            zip=None,
            download=True,
            url=_DAMRU_APKS_URL,
            mirror_url=_DAMRU_APKS_MIRROR_URL,
            output=None,
            force=False,
        ))
        if apk_code != 0:
            return apk_code

    print("Chrome is not installed on the worker; installing from APK bundle...", file=sys.stderr)
    try:
        import asyncio

        from .docker import RedroidManager

        manager = RedroidManager()
        apk_path = manager.find_chrome_apk()
        asyncio.run(manager.install_chrome(serial, apk_path))
    except Exception as exc:
        print(f"Chrome auto-install failed: {exc}", file=sys.stderr)
        return 1

    if not _chrome_package_installed(serial, package):
        print(f"Chrome auto-install finished, but {package} is still not installed.", file=sys.stderr)
        return 1
    return 0

def _proxy_bridge_upstream(proxy: str | None, http_proxy: str | None = None) -> str | None:
    from .proxy_runtime import proxy_bridge_upstream

    return proxy_bridge_upstream(proxy, http_proxy)

def _android_proxy_host(serial: str) -> str:
    from .proxy_runtime import android_proxy_host_from_route

    result = _run_adb_text(serial, "shell", "ip", "route", "show", "default", timeout=8)
    text = result.stdout or result.stderr or ""
    return android_proxy_host_from_route(text)

def _ensure_proxy_bridge(serial: str, upstream: str) -> str:
    from .proxy_runtime import ensure_proxy_bridge

    port = ensure_proxy_bridge(upstream)
    return f"{_android_proxy_host(serial)}:{port}"

def _apply_webrtc_block_sync(serial: str, chrome_package: str = "com.android.chrome") -> None:
    async def _run_block() -> None:
        from .adb import ADB
        from .root import RootOps

        adb = ADB(serial)
        root = RootOps(adb)
        await root.check_root()
        await root.apply_webrtc_block(chrome_package)

    import asyncio

    asyncio.run(_run_block())

def _dismiss_chrome_prompts_sync(serial: str, chrome_package: str = "com.android.chrome") -> None:
    async def _dismiss() -> None:
        from .adb import ADB
        from .chrome import ChromeManager

        chrome = ChromeManager(ADB(serial), package=chrome_package)
        await chrome.dismiss_fre(max_attempts=4)

    import asyncio

    asyncio.run(_dismiss())

def _apply_android_proxy(serial: str, proxy: str | None = None, http_proxy: str | None = None) -> str | None:
    from .proxy import resolve_system_proxy

    bridge_upstream = _proxy_bridge_upstream(proxy, http_proxy)
    system_proxy = _ensure_proxy_bridge(serial, bridge_upstream) if bridge_upstream else resolve_system_proxy(proxy=proxy, http_proxy=http_proxy)
    if not system_proxy:
        if proxy or http_proxy:
            raise ValueError("Proxy cannot be applied to Android. Use an HTTP proxy URL or host:port.")
        return None
    host, _, port = system_proxy.rpartition(":")
    if not host or not port.isdigit():
        raise ValueError("Proxy must resolve to host:port for Android.")
    for parts in (
        ("settings", "put", "global", "http_proxy", system_proxy),
        ("settings", "put", "global", "global_http_proxy_host", host),
        ("settings", "put", "global", "global_http_proxy_port", port),
    ):
        result = _run_adb_text(serial, "shell", *parts, timeout=12)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "Failed to apply Android proxy.").strip())
    return system_proxy

def _locale_hint_for_url(url: str) -> str | None:
    try:
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return None
    if host.endswith(".com.br"):
        return "pt-BR"
    return None

def _open_url(args: argparse.Namespace) -> int:
    serial = _resolve_serial(args.serial)
    if not serial:
        print("No online ADB device found. Use --serial or start a Redroid device first.", file=sys.stderr)
        return 1
    url = str(args.url or "").strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        print("--url must start with http:// or https://", file=sys.stderr)
        return 1
    _ensure_adb_connected(serial)
    _repair_runtime_internet(serial, quiet=True)
    package = str(getattr(args, "package", None) or "com.android.chrome").strip()
    chrome_code = _ensure_chrome_for_open_url(serial, package)
    if chrome_code != 0:
        return chrome_code
    try:
        system_proxy = _apply_android_proxy(serial, getattr(args, "proxy", None), getattr(args, "http_proxy", None))
    except Exception as exc:
        print(f"Proxy setup failed: {exc}", file=sys.stderr)
        return 1
    if system_proxy:
        try:
            _apply_webrtc_block_sync(serial, package)
        except Exception as exc:
            print(f"WebRTC leak guard failed: {exc}", file=sys.stderr)
            return 1
        _run_adb_text(serial, "shell", "am", "force-stop", package, timeout=10)
        print(f"Android proxy applied: {system_proxy}")
    candidates: list[tuple[str, tuple[str, ...]]] = [
        (package, ("com.google.android.apps.chrome.Main", "org.chromium.chrome.browser.ChromeTabbedActivity")),
    ]
    if package == "com.android.chrome":
        candidates.extend(
            [
                ("com.chrome.beta", ("com.google.android.apps.chrome.Main",)),
                ("com.chrome.dev", ("com.google.android.apps.chrome.Main",)),
                ("com.chrome.canary", ("com.google.android.apps.chrome.Main",)),
                ("org.chromium.chrome", ("org.chromium.chrome.browser.ChromeTabbedActivity", "com.google.android.apps.chrome.Main")),
            ]
        )

    result: subprocess.CompletedProcess[str] | None = None
    launched_package = ""
    last_error = ""
    for candidate_package, activities in candidates:
        for activity_name in activities:
            activity = f"{candidate_package}/{activity_name}"
            result = _run_adb_text(
                serial,
                "shell",
                "am",
                "start",
                "-W",
                "-f",
                "0x10008000",
                "--activity-clear-top",
                "-n",
                activity,
                "-a",
                "android.intent.action.VIEW",
                "-d",
                url,
                timeout=30,
            )
            output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
            failed_output = (
                "Error:" in output
                or "Error type" in output
                or "Exception" in output
                or "does not exist" in output
                or "not found" in output.lower()
            )
            if result.returncode == 0 and not failed_output:
                launched_package = candidate_package
                break
            last_error = output or last_error
        if launched_package:
            break

    if not launched_package:
        print(last_error or "Chrome is not installed or could not handle the URL.", file=sys.stderr)
        return result.returncode if result else 1

    focus_text = ""
    deadline = time.time() + 12
    while time.time() < deadline:
        focus = _run_adb_text(serial, "shell", "dumpsys", "window", timeout=10)
        activity = _run_adb_text(serial, "shell", "dumpsys", "activity", "activities", timeout=10)
        focus_text = "\n".join(part for part in (focus.stdout, focus.stderr, activity.stdout, activity.stderr) if part)
        if launched_package in focus_text:
            break
        time.sleep(0.75)
    else:
        print(
            f"Chrome launch returned success, but Android focus is not {launched_package}. "
            "Refusing to fall back to WebView or another generic URL handler.",
            file=sys.stderr,
        )
        return 1

    _dismiss_chrome_prompts_sync(serial, launched_package)

    print(f"Opened URL in Chrome ({launched_package}) on {serial}: {url}")
    return 0

def _stealth_open_url(args: argparse.Namespace) -> int:
    serial = _resolve_serial(args.serial)
    if not serial:
        print("No online ADB device found. Use --serial or start a Redroid device first.", file=sys.stderr)
        return 1
    url = str(args.url or "").strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        print("--url must start with http:// or https://", file=sys.stderr)
        return 1
    _ensure_adb_connected(serial)
    _repair_runtime_internet(serial, quiet=True)

    async def _run_stealth() -> str:
        from .async_core import AsyncDamru

        mode = str(getattr(args, "mode", "playwright") or "playwright").lower()
        if mode == "cdp" and os.environ.get("DAMRU_EXPERIMENTAL_RAW_WORKER_CDP") is None:
            os.environ["DAMRU_EXPERIMENTAL_RAW_WORKER_CDP"] = "1"

        damru = AsyncDamru(
            device=getattr(args, "device", None),
            serial=serial,
            proxy=getattr(args, "proxy", None),
            http_proxy=getattr(args, "http_proxy", None),
            timezone=getattr(args, "timezone", None),
            locale=getattr(args, "locale", None) or _locale_hint_for_url(url),
            profile_tier=getattr(args, "profile_tier", None),
            keep_chrome_on_exit=True,
            force_cold_start=bool(getattr(args, "cold_start", False)),
            debug=getattr(args, "debug", False),
        )
        context = await damru.__aenter__()
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            if mode in {"native", "cdp", "reattach"}:
                # Some protected mobile sites detect active DevTools/CDP
                # navigation. Apply the profile first, then let Android Chrome
                # perform a native VIEW intent. In cdp mode CDP stays attached
                # so timezone/UA/hardware/touch overrides are live for the
                # native-opened target page. In native mode CDP is fully
                # detached. In reattach mode CDP is detached during load and
                # reconnected afterwards for inspection/automation.
                await page.goto("about:blank", wait_until="domcontentloaded", timeout=15000)
                if mode in {"native", "reattach"}:
                    await damru.disconnect_cdp()

                package = "com.android.chrome"
                activities = (
                    "com.google.android.apps.chrome.Main",
                    "org.chromium.chrome.browser.ChromeTabbedActivity",
                )
                last_error = ""
                for activity_name in activities:
                    result = _run_adb_text(
                        serial,
                        "shell",
                        "am",
                        "start",
                        "-W",
                        "--activity-clear-top",
                        "-n",
                        f"{package}/{activity_name}",
                        "-a",
                        "android.intent.action.VIEW",
                        "-d",
                        url,
                        timeout=45,
                    )
                    output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
                    failed = result.returncode != 0 or "Error:" in output or "Exception" in output
                    if failed:
                        last_error = output or last_error
                        continue

                    await asyncio.sleep(max(0, int(getattr(args, "settle_ms", 3000))) / 1000)
                    if mode == "native":
                        return "native Android Chrome navigation"

                    context2 = await damru.reconnect_cdp() if mode == "reattach" else context
                    pages = list(context2.pages)
                    target_page = None
                    for candidate in pages:
                        if candidate.url and candidate.url != "about:blank":
                            target_page = candidate
                            if url.split("#", 1)[0] in candidate.url:
                                break
                    if target_page is None:
                        target_page = pages[-1] if pages else None
                    if target_page is None:
                        return "native navigation; CDP reattached with no pages"

                    target_device = getattr(getattr(damru, "_profile", None), "device", None)
                    if target_device is not None:
                        with contextlib.suppress(Exception):
                            await asyncio.gather(
                                damru._apply_devtools_evasion(),
                                damru._apply_hardware_overrides(target_device),
                                damru._apply_touch_emulation(target_device),
                                damru._apply_network_emulation(),
                                damru._apply_storage_quota_override(target_device),
                                damru._apply_timezone_override(),
                                damru._apply_ua_override(
                                    target_device,
                                    chrome_version=getattr(damru, "_spoofed_chrome_version", None),
                                    android_version=getattr(damru, "_spoofed_android_version", None),
                                ),
                                damru._arm_worker_core_override(target_device.hardware_concurrency),
                            )
                            if os.environ.get("DAMRU_EXPERIMENTAL_CDP_SENSORS") == "1":
                                with contextlib.suppress(Exception):
                                    await damru._apply_sensor_emulation()

                    with contextlib.suppress(Exception):
                        await damru._apply_timezone_override()
                    profile_locale = getattr(getattr(damru, "_profile", None), "locale", None)
                    if profile_locale:
                        with contextlib.suppress(Exception):
                            await damru._apply_locale_override(profile_locale)
                    sync_payload = getattr(damru, "_sync_ua_payload", None)
                    if sync_payload:
                        with contextlib.suppress(Exception):
                            s = await context2.new_cdp_session(target_page)
                            await s.send("Emulation.setUserAgentOverride", sync_payload)

                    title = await target_page.title()
                    return title or "native navigation; CDP reattached"
                raise RuntimeError(last_error or "Chrome could not handle native URL navigation")
            elif mode == "playwright":
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(max(0, int(getattr(args, "settle_ms", 3000))))
                return await page.title()
            else:
                raise RuntimeError(f"Unsupported stealth-open-url mode: {mode}")
        finally:
            await damru.__aexit__(None, None, None)

    try:
        import asyncio
        title = asyncio.run(_run_stealth())
    except Exception as exc:
        print(f"Stealth open failed: {exc}", file=sys.stderr)
        return 1
    print(f"Opened URL with Damru stealth session on {serial}: {url}")
    if title:
        print(f"Title: {title}")
    return 0

def _quick_stealth_check(args: argparse.Namespace) -> int:
    serial = _resolve_serial(args.serial)
    if not serial:
        print("No online ADB device found. Use --serial or start a Redroid device first.", file=sys.stderr)
        return 1
    _ensure_adb_connected(serial)
    _repair_runtime_internet(serial, quiet=True)

    def prop(name: str) -> str:
        proc = _run_adb_text(serial, "shell", "getprop", name, timeout=8)
        return (proc.stdout or "").strip()

    def adb_shell(*parts: str) -> str:
        proc = _run_adb_text(serial, "shell", *parts, timeout=12)
        return (proc.stdout or proc.stderr or "").strip()

    wm_size = adb_shell("wm", "size")
    wm_density = adb_shell("wm", "density")
    checks = {
        "adb_online": _run_adb_text(serial, "get-state", timeout=8).stdout.strip() == "device",
        "boot_completed": prop("sys.boot_completed") == "1",
        "chrome_installed": _chrome_package_installed(serial, "com.android.chrome"),
        "dns_present": _android_dns_present(serial),
        "timezone_present": bool(prop("persist.sys.timezone")),
        "locale_present": bool(prop("persist.sys.locale") or prop("persist.sys.language")),
        "model_present": bool(prop("ro.product.model")),
        "fingerprint_present": bool(prop("ro.build.fingerprint")),
    }
    report = {
        "serial": serial,
        "ok": all(checks.values()),
        "checks": checks,
        "android": {
            "brand": prop("ro.product.brand"),
            "manufacturer": prop("ro.product.manufacturer"),
            "model": prop("ro.product.model"),
            "device": prop("ro.product.device"),
            "release": prop("ro.build.version.release"),
            "sdk": prop("ro.build.version.sdk"),
            "fingerprint": prop("ro.build.fingerprint"),
            "timezone": prop("persist.sys.timezone"),
            "locale": prop("persist.sys.locale") or "-".join(filter(None, [prop("persist.sys.language"), prop("persist.sys.country")])),
            "dns1": prop("net.dns1"),
            "dns2": prop("net.dns2"),
            "screen": wm_size.splitlines()[-1] if wm_size else "",
            "density": wm_density.splitlines()[-1] if wm_density else "",
            "http_proxy": adb_shell("settings", "get", "global", "http_proxy"),
        },
    }
    output = Path(args.output).expanduser().resolve() if args.output else None
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    rows = "".join(
        f"<tr><td>{html.escape(key)}</td><td class=\"{'ok' if value else 'bad'}\">{'OK' if value else 'FAIL'}</td></tr>"
        for key, value in checks.items()
    )
    js = (
        "const n=navigator;const rows=["
        "['webdriver',String(n.webdriver)],['userAgent',n.userAgent],['platform',n.platform],"
        "['languages',(n.languages||[]).join(', ')],['hardwareConcurrency',String(n.hardwareConcurrency)],"
        "['deviceMemory',String(n.deviceMemory||'')],['timezone',Intl.DateTimeFormat().resolvedOptions().timeZone],"
        "['screen',screen.width+'x'+screen.height+' dpr='+devicePixelRatio]];"
        "document.getElementById('js').innerHTML=rows.map(function(r){return '<tr><td>'+r[0]+'</td><td>'+r[1]+'</td></tr>';}).join('');"
    )
    page = (
        "<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Damru Quick Checker</title>"
        "<style>body{font-family:Arial,sans-serif;margin:22px;background:#f7f8f4;color:#121713}table{border-collapse:collapse;width:100%;margin:14px 0;background:white}td{border:1px solid #dbe3d7;padding:9px}.ok{color:#14733c;font-weight:700}.bad{color:#b42318;font-weight:700}code{word-break:break-all}</style>"
        f"<h1>Damru Quick Checker</h1><p>Serial: <code>{html.escape(serial)}</code></p>"
        f"<h2>Runtime checks</h2><table>{rows}</table>"
        f"<h2>Android profile</h2><pre>{html.escape(json.dumps(report['android'], indent=2))}</pre>"
        f"<h2>Browser JS</h2><table id=js></table><script>{js}</script>"
    )
    import urllib.parse
    data_url = "data:text/html;charset=utf-8," + urllib.parse.quote(page)
    _run_adb_text(serial, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", data_url, timeout=20)
    print(json.dumps(report, indent=2, sort_keys=True))
    if output:
        print(f"Quick checker report saved: {output}")
    print("Quick checker page opened in Chrome.")
    return 0 if report["ok"] else 1

def _record(args: argparse.Namespace) -> int:
    serial = _resolve_serial(args.serial)
    if not serial:
        print("No online ADB device found. Use --serial or start a Redroid device first.", file=sys.stderr)
        return 1
    _ensure_adb_connected(serial)
    if args.time_limit < 1 or args.time_limit > 180:
        print("--time-limit must be between 1 and 180 seconds.", file=sys.stderr)
        return 1

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    remote = f"/sdcard/damru-record-{int(time.time())}.mp4"
    print(f"Recording {args.time_limit}s from {serial}...")
    rec = _run_adb_text(serial, "shell", "screenrecord", "--time-limit", str(args.time_limit), remote, timeout=args.time_limit + 30)
    if rec.returncode != 0:
        if rec.stderr.strip():
            print(rec.stderr.strip(), file=sys.stderr)
        return rec.returncode

    pulled = _run_adb_text(serial, "pull", remote, str(output), timeout=60)
    _run_adb_text(serial, "shell", "rm", "-f", remote, timeout=10)
    if pulled.returncode != 0:
        if pulled.stderr.strip():
            print(pulled.stderr.strip(), file=sys.stderr)
        return pulled.returncode
    print(f"Video saved: {output}")
    return 0

def _scrcpy_cmd(serial: str | None, args: argparse.Namespace) -> list[str] | None:
    exe = shutil.which("scrcpy")
    if exe:
        cmd = [exe]
        if serial:
            cmd.extend(["--serial", serial[4:] if _is_windows() and serial.startswith("wsl:") else serial])
        if args.no_control:
            cmd.append("--no-control")
        if args.max_size:
            cmd.extend(["--max-size", str(args.max_size)])
        return cmd

    if _check_command_linux("scrcpy"):
        linux_parts = ["scrcpy"]
        if serial:
            linux_parts.extend(["--serial", serial[4:] if serial.startswith("wsl:") else serial])
        if args.no_control:
            linux_parts.append("--no-control")
        if args.max_size:
            linux_parts.extend(["--max-size", str(args.max_size)])
        return _linux_cmd(" ".join(shlex.quote(part) for part in linux_parts))
    return None

def _view(args: argparse.Namespace) -> int:
    serial = _resolve_serial(args.serial)
    if not serial:
        print("No online ADB device found. Use --serial or start a Redroid device first.", file=sys.stderr)
        return 1
    _ensure_adb_connected(serial)
    cmd = _scrcpy_cmd(serial, args)
    if cmd is None:
        print("scrcpy was not found. Install it or run 'python -m damru install-viewer'.", file=sys.stderr)
        return 1
    print("Starting scrcpy. Close the scrcpy window to return to the CLI.")
    return subprocess.run(cmd).returncode

def _install_viewer(args: argparse.Namespace) -> int:
    if _check_command_host_or_linux("scrcpy"):
        print("scrcpy is already available.")
        return 0
    if _is_windows():
        print("Installing scrcpy inside WSL. Native Windows scrcpy is still smoother if you install it later.")
        _repair_wsl_main_route_rule()
        try:
            result = _linux_run(
                "\n".join([*_wsl_dns_repair_lines(), "apt_update", "apt-get install -y scrcpy"]),
                timeout=1800,
                root_user=True,
            )
        except subprocess.TimeoutExpired:
            print("Timed out while installing scrcpy in WSL. Retry 'python -m damru install-viewer'.", file=sys.stderr)
            return 1
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.returncode != 0:
            if result.stderr.strip():
                print(result.stderr.strip(), file=sys.stderr)
            return result.returncode
        repair = _linux_run("\n".join([
            "mkdir -p /dev/binderfs",
            "mount | grep -q ' /dev/binderfs ' || mount -t binder binder /dev/binderfs 2>/dev/null || true",
            *_docker_bridge_nat_repair_lines(),
        ]), timeout=60, root_user=True)
        if repair.returncode != 0 and repair.stderr.strip():
            print(repair.stderr.strip(), file=sys.stderr)
        print("scrcpy installed in WSL.")
        return 0

    print("Installing scrcpy on Linux...")
    try:
        result = _linux_run("sudo apt-get update -y && sudo apt-get install -y scrcpy", timeout=1800)
    except subprocess.TimeoutExpired:
        print("Timed out while installing scrcpy. Retry 'python -m damru install-viewer'.", file=sys.stderr)
        return 1
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0:
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)
        return result.returncode
    print("scrcpy installed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="damru", description="Damru command line tools")
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="guided first-run config and dependency setup")
    setup.add_argument("-y", "--yes", action="store_true", help="accept defaults and run noninteractively")
    setup.add_argument("--skip-deps", action="store_true", help="write config without installing dependencies")
    setup.add_argument(
        "--sudo-password-stdin",
        action="store_true",
        help="read one sudo password line from stdin while setup installs native Linux dependencies",
    )
    setup.add_argument("--adb", action="store_true", help="also require an online ADB device during final check")
    setup.add_argument("--mode", choices=["auto", "manual", "mumu"], default=None, help="Damru mode to write to config")
    setup.add_argument("--num-devices", type=int, default=None, help="number of devices/containers")
    setup.add_argument("--chrome-apk", default=None, help="APK file or split-APK directory")
    setup.add_argument("--wsl-distro", default=None, help="WSL distro to use on Windows")
    setup.add_argument("--wsl-username", default=None, help="WSL username to write to config")
    setup.add_argument("--install-wsl-kernel", action="store_true", help="install bundled WSL2 Redroid/NAT kernel when Windows WSL checks fail")
    setup.add_argument("--confirm-wsl-kernel-risk", action="store_true", help="required with -y/--yes before setup may switch the WSL kernel")
    setup.set_defaults(func=_setup)

    check = sub.add_parser("check-env", help="validate Linux/WSL dependencies and Damru assets")
    check.add_argument("--adb", action="store_true", help="also require at least one online ADB device")
    check.add_argument("--viewer", action="store_true", help="also check optional scrcpy viewer support")
    check.set_defaults(func=_check_env)

    check_group = sub.add_parser("check", help="read-only Damru checks")
    check_sub = check_group.add_subparsers(dest="check_command", required=True)
    preflight = check_sub.add_parser("preflight", help="fast read-only Docker/ADB/binderfs/image readiness checks")
    preflight.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    preflight.add_argument("--strict", action="store_true", help="treat warnings as failures")
    preflight.add_argument("--no-adb", action="store_true", help="skip ADB device listing")
    preflight.add_argument("--timeout", type=int, default=3, help="per-check timeout seconds; default 3")
    preflight.set_defaults(func=_check_preflight)
    install = sub.add_parser("install-deps", help="install common Linux/WSL dependencies")
    install.add_argument("-y", "--yes", action="store_true", help="run without an interactive confirmation")
    install.add_argument(
        "--sudo-password-stdin",
        action="store_true",
        help="read one sudo password line from stdin for noninteractive WSL/Linux setup",
    )
    install.set_defaults(func=_install_deps)

    fix = sub.add_parser("fix-wsl", help="retry safe WSL/Linux Docker, binderfs, and netfilter fixes")
    fix.add_argument("--install-kernel", action="store_true", help="install bundled WSL2 Redroid/NAT kernel if normal repair still fails")
    fix.add_argument("-y", "--yes", action="store_true", help="run repair noninteractively")
    fix.add_argument("--confirm-wsl-kernel-risk", action="store_true", help="required with -y/--yes before fix-wsl may switch the WSL kernel")
    fix.set_defaults(func=_fix_wsl)

    bench = sub.add_parser("benchmark", help="run the Damru benchmark suite")
    bench.add_argument("--device", "-d", default=None, help="device name or 'random'")
    bench.add_argument("--serial", "-s", default=None, help="ADB serial")
    bench.add_argument("--proxy", "-p", default=None, help="SOCKS5 proxy URL")
    bench.add_argument("--timezone", default=None, help="IANA timezone")
    bench.add_argument("--locale", default=None, help="BCP-47 locale")
    bench.add_argument("--tests", "-t", nargs="*", default=None, help="specific tests to run")
    bench.add_argument("--screenshots", default=None, help="directory for screenshots")
    bench.add_argument("--output", "-o", default=None, help="JSON output path")
    bench.add_argument("--debug", action="store_true", help="enable debug logging")
    bench.set_defaults(func=_benchmark)

    bake = sub.add_parser("bake-image", help="bake a warm Redroid Docker image inside Linux/WSL")
    bake.add_argument("--chrome-apk", default=None, help="APK file or split-APK directory")
    bake.add_argument("--image", default="damru-redroid:latest", help="target Docker image tag")
    bake.add_argument("--wsl-distro", default=None, help="WSL distro to use on Windows")
    bake.set_defaults(func=_bake_image)

    install_image = sub.add_parser("install-image", help="load or download the baked Damru Redroid image")
    install_image.add_argument("--tar", default=None, help="path to damru-redroid-latest.tar; auto-detected when omitted")
    install_image.add_argument("--download", action="store_true", help="download the image tarball if it is not found locally")
    install_image.add_argument("--url", default=_DAMRU_IMAGE_URL, help="Google Drive image URL used with --download")
    install_image.add_argument("--output", default=None, help="download target path; default is ./damru-redroid-latest.tar")
    install_image.set_defaults(func=_install_image)

    install_apks = sub.add_parser("install-apks", help="download and extract raw Chrome/WebView/TTS APK assets")
    install_apks.add_argument("--zip", default=None, help="path to chrome-apks.zip; auto-detected when omitted")
    install_apks.add_argument("--download", action="store_true", help="download the APK bundle if it is not found locally")
    install_apks.add_argument("--url", default=_DAMRU_APKS_URL, help="primary direct APK bundle URL")
    install_apks.add_argument("--mirror-url", default=_DAMRU_APKS_MIRROR_URL, help="manual-download fallback APK bundle URL")
    install_apks.add_argument("--output", default=None, help="extract target directory; default is ./chrome-apks")
    install_apks.add_argument("--force", action="store_true", help="re-extract even if Chrome APKs are already available")
    install_apks.set_defaults(func=_install_apks)

    devices = sub.add_parser("devices", help="list ADB devices from Linux/WSL")
    devices.set_defaults(func=_devices)

    fix_internet = sub.add_parser("fix-internet", help="repair WSL/Redroid internet and DNS for a worker")
    fix_internet.add_argument("--serial", "-s", default=None, help="ADB serial; omitted means host/WSL repair only")
    fix_internet.add_argument("--all", action="store_true", help="repair host/WSL internet and all online ADB workers")
    fix_internet.set_defaults(func=_fix_internet)

    random_profile = sub.add_parser("random-profile", help="apply a random stealth profile to an ADB worker")
    random_profile.add_argument("--serial", "-s", default=None, help="ADB serial; defaults to the first online device")
    random_profile.add_argument("--all", action="store_true", help="apply random profiles to all running Damru workers")
    random_profile.add_argument(
        "--profile-tier",
        default="premium",
        help="random pool: premium (default), premium_verified, premium_new, medium, experimental, extended, or all",
    )
    random_profile.add_argument("--proxy", default=None, help="proxy URL used for geo/timezone/locale and Android HTTP proxy")
    random_profile.add_argument("--http-proxy", default=None, help="explicit Android HTTP proxy host:port or URL")
    random_profile.add_argument("--chrome-version", default=None, help="force a Chrome/WebView APK version from chrome-apks/<version>; default is random")
    random_profile.set_defaults(func=_random_profile)

    force_profile = sub.add_parser("force-profile", help="apply a named stealth profile to an ADB worker")
    force_profile.add_argument("--serial", "-s", default=None, help="ADB serial; defaults to the first online device")
    force_profile.add_argument("--device", "-d", required=True, help="device profile name, model, or slug")
    force_profile.add_argument("--proxy", default=None, help="proxy URL used for geo/timezone/locale")
    force_profile.add_argument("--http-proxy", default=None, help="explicit Android HTTP proxy host:port or URL")
    force_profile.add_argument("--timezone", default=None, help="explicit IANA timezone, e.g. America/Sao_Paulo")
    force_profile.add_argument("--locale", default=None, help="explicit BCP-47 locale, e.g. pt-BR")
    force_profile.add_argument(
        "--browser-package",
        default="com.android.chrome",
        help="Chromium package to harden; use org.chromium.webview_shell for WebView Shell",
    )
    force_profile.add_argument("--no-chrome", action="store_true", help="skip Chrome command-line/preferences setup")
    force_profile.add_argument("--no-clear-chrome", action="store_true", help="keep existing Chrome data")
    force_profile.add_argument("--rotate-chrome", action="store_true", help="rotate Chrome from the validated APK bundle")
    force_profile.add_argument("--chrome-version", default=None, help="use a specific Chrome/WebView APK version with --rotate-chrome")
    force_profile.add_argument("--no-cpu", action="store_true", help="skip CPU core spoofing")
    force_profile.add_argument("--no-gpu", action="store_true", help="skip native Vulkan GPU spoofing")
    force_profile.add_argument("--no-memory", action="store_true", help="skip native memory preload spoofing")
    force_profile.add_argument("--clear-proxy", action="store_true", help="clear Android system HTTP proxy instead of preserving it")
    force_profile.set_defaults(func=_force_profile)

    stealth_all = sub.add_parser("ui-stealth-check-all", help=argparse.SUPPRESS)
    stealth_all.add_argument("--output-root", required=True, help=argparse.SUPPRESS)
    stealth_all.add_argument("--proxy", default=None, help=argparse.SUPPRESS)
    stealth_all.set_defaults(func=_ui_stealth_check_all)

    shot = sub.add_parser("screenshot", help="capture a PNG screenshot from an ADB device")
    shot.add_argument("--serial", "-s", default=None, help="ADB serial; defaults to the first online device")
    shot.add_argument("--output", "-o", default="damru-screenshot.png", help="output PNG path")
    shot.set_defaults(func=_screenshot)

    quick = sub.add_parser("quick-check", help="run a fast local Android/Chrome stealth sanity check")
    quick.add_argument("--serial", "-s", default=None, help="ADB serial; defaults to the first online device")
    quick.add_argument("--output", "-o", default=None, help="optional JSON report path")
    quick.set_defaults(func=_quick_stealth_check)

    open_url = sub.add_parser("open-url", help="open a URL on an ADB device")
    open_url.add_argument("--serial", "-s", default=None, help="ADB serial; defaults to the first online device")
    open_url.add_argument("--url", required=True, help="http:// or https:// URL to open")
    open_url.add_argument("--package", default="com.android.chrome", help="browser package to launch; default is Chrome")
    open_url.add_argument("--proxy", default=None, help="HTTP/SOCKS proxy URL; HTTP endpoint is applied to Android before navigation")
    open_url.add_argument("--http-proxy", default=None, help="explicit Android HTTP proxy host:port or URL")
    open_url.set_defaults(func=_open_url)

    stealth_open_url = sub.add_parser("stealth-open-url", help="open a URL through a full Damru stealth session")
    stealth_open_url.add_argument("--serial", "-s", default=None, help="ADB serial; defaults to the first online device")
    stealth_open_url.add_argument("--url", required=True, help="http:// or https:// URL to open")
    stealth_open_url.add_argument("--proxy", default=None, help="HTTP/SOCKS proxy URL")
    stealth_open_url.add_argument("--http-proxy", default=None, help="explicit Android HTTP proxy host:port or URL")
    stealth_open_url.add_argument("--device", default=None, help="device profile name/model/slug; omitted means random premium profile")
    stealth_open_url.add_argument(
        "--profile-tier",
        default=None,
        help="random profile pool when --device is omitted: premium, medium, experimental, all, etc.",
    )
    stealth_open_url.add_argument(
        "--mode",
        choices=("cdp", "reattach", "native", "playwright"),
        default="playwright",
        help="cdp keeps CDP live during native open; reattach detaches for native load then reconnects; native leaves CDP detached; playwright uses page.goto",
    )
    stealth_open_url.add_argument("--locale", default=None, help="explicit BCP-47 locale; .com.br URLs default to pt-BR when omitted")
    stealth_open_url.add_argument("--timezone", default=None, help="explicit IANA timezone; omitted means auto from proxy or default profile geo")
    stealth_open_url.add_argument("--reuse-profile", dest="cold_start", action="store_false", help="reuse existing Chrome/profile state; default")
    stealth_open_url.add_argument("--cold-start", dest="cold_start", action="store_true", help="clear Chrome and rebuild profile before opening")
    stealth_open_url.set_defaults(cold_start=False)
    stealth_open_url.add_argument("--settle-ms", type=int, default=3000, help="milliseconds to wait after navigation before leaving Chrome open")
    stealth_open_url.add_argument("--debug", action="store_true", help="enable debug logging")
    stealth_open_url.set_defaults(func=_stealth_open_url)

    record = sub.add_parser("record", help="record a short MP4 video from an ADB device")
    record.add_argument("--serial", "-s", default=None, help="ADB serial; defaults to the first online device")
    record.add_argument("--output", "-o", default="damru-record.mp4", help="output MP4 path")
    record.add_argument("--time-limit", type=int, default=30, help="recording duration in seconds, max 180")
    record.set_defaults(func=_record)

    view = sub.add_parser("view", help="open optional scrcpy live viewer for a Redroid/ADB device")
    view.add_argument("--serial", "-s", default=None, help="ADB serial; defaults to the first online device")
    view.add_argument("--no-control", action="store_true", help="view only; do not send input events")
    view.add_argument("--max-size", type=int, default=None, help="scrcpy max display size")
    view.set_defaults(func=_view)

    wsl_kernel = sub.add_parser("wsl-kernel", help="manage bundled Damru WSL2 kernel artifact")
    wsl_kernel_sub = wsl_kernel.add_subparsers(dest="wsl_kernel_command", required=True)
    wsl_kernel_status = wsl_kernel_sub.add_parser("status", help="show bundled and active WSL kernel state")
    wsl_kernel_status.set_defaults(func=_wsl_kernel_status)
    wsl_kernel_install = wsl_kernel_sub.add_parser("install", help="backup .wslconfig and install bundled WSL2 Redroid/NAT kernel")
    wsl_kernel_install.add_argument("-y", "--yes", action="store_true", help="run without normal prompts")
    wsl_kernel_install.add_argument("--confirm-wsl-kernel-risk", action="store_true", help="required with -y/--yes before installing the WSL kernel")
    wsl_kernel_install.set_defaults(func=_install_bundled_wsl_kernel)

    viewer = sub.add_parser("install-viewer", help="check or install optional scrcpy viewer tooling")
    viewer.add_argument("-y", "--yes", action="store_true", help="accepted for non-interactive install scripts")
    viewer.set_defaults(func=_install_viewer)

    ui = sub.add_parser("ui", help="open the local Damru web control panel")
    ui.add_argument("--port", type=int, default=8765, help="localhost port for the UI")
    ui.add_argument("--no-open", action="store_true", help="do not open a browser automatically")
    ui.set_defaults(func=_ui)

    ui_worker = sub.add_parser("ui-worker", help=argparse.SUPPRESS)
    ui_worker.add_argument("action", choices=["start", "add", "resume", "resume-all", "pause", "delete", "restart", "stop-all", "delete-all"], help=argparse.SUPPRESS)
    ui_worker.add_argument("--count", type=int, default=None, help=argparse.SUPPRESS)
    ui_worker.add_argument("--index", type=int, default=0, help=argparse.SUPPRESS)
    ui_worker.set_defaults(func=_ui_worker)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


def _ui(args: argparse.Namespace) -> int:
    from .ui.server import run_ui

    return run_ui(port=args.port, open_browser=not args.no_open)


def _ui_worker(args: argparse.Namespace) -> int:
    import asyncio

    from . import config
    from .async_core import DamruError
    from .docker import RedroidManager

    async def _run() -> int:
        manager = RedroidManager()
        async def _existing_workers() -> dict[int, str]:
            out = await manager._run_cmd(
                manager._docker_cmd("ps", "-a", "--filter", f"name={config.REDROID_CONTAINER_PREFIX}", "--format", "{{.Names}} {{.State}}"),
                timeout=10,
                allow_failure=True,
            )
            workers: dict[int, str] = {}
            for line in out.splitlines():
                parts = line.strip().split(maxsplit=1)
                if not parts:
                    continue
                name = parts[0]
                if not name.startswith(config.REDROID_CONTAINER_PREFIX):
                    continue
                suffix = name.removeprefix(config.REDROID_CONTAINER_PREFIX)
                if suffix.isdigit():
                    workers[int(suffix)] = parts[1] if len(parts) > 1 else "unknown"
            return workers

        async def _stale_bridge_reuse_indices() -> list[int]:
            out = await manager._run_cmd(
                manager._docker_cmd("ps", "-a", "--filter", f"name={config.REDROID_CONTAINER_PREFIX}", "--format", "{{.Names}} {{.State}} {{.Networks}}"),
                timeout=10,
                allow_failure=True,
            )
            indices: list[int] = []
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) < 3:
                    continue
                name, state, network = parts[0], parts[1], parts[2]
                if state == "running" or network != "host" or not name.startswith(config.REDROID_CONTAINER_PREFIX):
                    continue
                suffix = name.removeprefix(config.REDROID_CONTAINER_PREFIX)
                if suffix.isdigit():
                    indices.append(int(suffix))
            return sorted(indices)

        async def _existing_indices() -> list[int]:
            return sorted((await _existing_workers()).keys())

        if args.action == "start":
            count = int(args.count or getattr(config, "NUM_DEVICES", 1) or 1)
            if count < 1:
                raise SystemExit("--count must be >= 1")
            await manager.check_docker()
            await manager.validate_redroid_multi_container_support(count)
            serials = await manager.ensure_all(count)
            print("Started/reused Damru worker(s):")
            for serial in serials:
                print(f"  {serial}")
            return 0
        if args.action == "add":
            add_count = int(args.count or 1)
            if add_count < 1:
                raise SystemExit("--count must be >= 1")
            await manager.check_docker()
            added: list[tuple[int, str]] = []
            workers = await _existing_workers()
            indices = set(workers)
            index = 0
            stale = await _stale_bridge_reuse_indices()
            for _ in range(add_count):
                if stale:
                    index = stale.pop(0)
                    indices.discard(index)
                else:
                    while index in indices:
                        index += 1
                await manager.validate_redroid_multi_container_support(index + 1)
                serial = await manager.ensure_container(index)
                added.append((index, serial))
                indices.add(index)
                index += 1
            print("Added Damru worker(s):")
            for index, serial in added:
                print(f"  {index}: {serial}")
            return 0
        if args.action == "resume":
            index = int(args.index)
            await manager.check_docker()
            await manager.validate_redroid_multi_container_support(index + 1)
            serial = await manager.ensure_container(index)
            print(f"Started Damru worker {index}: {serial}")
            return 0
        if args.action == "resume-all":
            await manager.check_docker()
            workers = await _existing_workers()
            if not workers:
                count = int(args.count or getattr(config, "NUM_DEVICES", 1) or 1)
                await manager.validate_redroid_multi_container_support(count)
                serials = await manager.ensure_all(count)
                print("Started Damru worker(s):")
                for serial in serials:
                    print(f"  {serial}")
                return 0
            resumed: list[tuple[int, str]] = []
            for index, state in sorted(workers.items()):
                if state == "running":
                    continue
                await manager.validate_redroid_multi_container_support(index + 1)
                serial = await manager.ensure_container(index)
                resumed.append((index, serial))
            if resumed:
                print("Started stopped Damru worker(s):")
                for index, serial in resumed:
                    print(f"  {index}: {serial}")
            else:
                print("All existing Damru workers are already running")
            return 0
        if args.action == "pause":
            index = int(args.index)
            name = f"{config.REDROID_CONTAINER_PREFIX}{index}"
            await manager._run_cmd(manager._docker_cmd("stop", name), timeout=30, allow_failure=True)
            print(f"Stopped Damru worker {index}; container kept")
            return 0
        if args.action == "delete":
            await manager.stop_container(int(args.index))
            print(f"Deleted Damru worker {int(args.index)}")
            return 0
        if args.action == "restart":
            serial = await manager.restart_container(int(args.index))
            print(f"Restarted Damru worker {int(args.index)}: {serial}")
            return 0
        if args.action == "stop-all":
            indices = await _existing_indices()
            for index in indices:
                name = f"{config.REDROID_CONTAINER_PREFIX}{index}"
                await manager._run_cmd(manager._docker_cmd("stop", name), timeout=30, allow_failure=True)
            print("Stopped all Damru worker containers; containers kept")
            return 0
        if args.action == "delete-all":
            await manager.cleanup_orphans()
            print("Deleted all Damru worker containers")
            return 0
        raise SystemExit(f"Unsupported worker action: {args.action}")

    try:
        return asyncio.run(_run())
    except DamruError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
