"""Command line interface for Damru."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import os
import platform
import re
import shutil
import shlex
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from pathlib import PureWindowsPath
from .apk_assets import bundled_magisk_apk, find_apk_bundle_root, validate_apk_bundle

_DAMRU_IMAGE_TAR = "damru-redroid-latest.tar"
_DAMRU_IMAGE_SHA256 = "19bfe988e58d41fa031b7df3ebd3a1cb8213cf376b5972c0749a40b42df9feb2"
_DAMRU_IMAGE_URL = "https://drive.google.com/file/d/1AzSTOlGpSfqHB-F-Yty2JqbOEMlgFT5F/view?usp=sharing"
_DAMRU_APKS_ZIP = "chrome-apks.zip"
_DAMRU_APKS_URL = "https://cosmicresidential.com/chrome-apks.zip"
_DAMRU_APKS_MIRROR_URL = "https://drive.google.com/file/d/1xh5Z-LXqUIEjO08KKjhaB_89KS2pBWZq/view?usp=sharing"
_CHROME_APK_AUTO_SKIP_VERSIONS = {"145.0.7632.75"}


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
            return ["wsl", "-d", _configured_wsl_distro(), "--", "adb", args[0], target[4:]]

    if serial and serial.startswith("wsl:"):
        plain = serial[4:]
        routed_args = _translate_wsl_adb_file_args(args)
        return ["wsl", "-d", _configured_wsl_distro(), "--", "adb", "-s", plain, *routed_args]

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
    linux = _linux_run("adb devices -l", timeout=20)
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
        "test -d /dev/binderfs && mount | grep -q ' /dev/binderfs ' && exit 0",
        "modprobe binder_linux devices=binder,hwbinder,vndbinder 2>/dev/null || true",
        "mkdir -p /dev/binderfs",
        "mount | grep -q ' /dev/binderfs ' || mount -t binder binder /dev/binderfs >/dev/null 2>&1 || true",
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
        "test -e /dev/binderfs/binder-control -o -e /dev/binderfs/binder",
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
        f"    {prefix}systemctl restart docker 2>/dev/null || true",
        "  else",
        f"    {prefix}service docker restart 2>/dev/null || true",
        "  fi",
        "fi",
    ]


def _docker_bridge_nat_repair_lines(sudo: str = "") -> list[str]:
    prefix = f"{sudo} " if sudo else ""
    return [
        "if docker info >/dev/null 2>/dev/null && docker network inspect bridge >/dev/null 2>/dev/null; then",
        f"  {prefix}sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true",
        "  docker_subnet=$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Subnet}}' 2>/dev/null)",
        "  docker_if=$(docker network inspect bridge --format '{{.Options.com.docker.network.bridge.name}}' 2>/dev/null)",
        "  [ -n \"$docker_if\" ] || docker_if=docker0",
        "  [ \"$docker_if\" != \"<no value>\" ] || docker_if=docker0",
        "  if [ -n \"$docker_subnet\" ] && ip link show \"$docker_if\" >/dev/null 2>&1; then",
        f"    {prefix}iptables -C FORWARD -i \"$docker_if\" -j ACCEPT 2>/dev/null || {prefix}iptables -I FORWARD 1 -i \"$docker_if\" -j ACCEPT 2>/dev/null || true",
        f"    {prefix}iptables -C FORWARD -o \"$docker_if\" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || {prefix}iptables -I FORWARD 1 -o \"$docker_if\" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true",
        f"    {prefix}iptables -t nat -C POSTROUTING -s \"$docker_subnet\" ! -o \"$docker_if\" -j MASQUERADE 2>/dev/null || {prefix}iptables -t nat -A POSTROUTING -s \"$docker_subnet\" ! -o \"$docker_if\" -j MASQUERADE 2>/dev/null || true",
        "  fi",
        "fi",
    ]


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
        f"if ! {docker_info} >/dev/null 2>/dev/null; then {prefix}pkill dockerd 2>/dev/null || true; {prefix}pkill containerd 2>/dev/null || true; {prefix}rm -f /var/run/docker.pid /var/run/docker.sock; fi",
        "if command -v systemctl >/dev/null 2>&1 && [ \"$(ps -p 1 -o comm= 2>/dev/null)\" = systemd ]; then "
        f"{prefix}systemctl start docker 2>/dev/null || true; fi",
        f"if ! {docker_info} >/dev/null 2>/dev/null; then {prefix}service docker start 2>/dev/null || true; fi",
        f"if ! {docker_info} >/dev/null 2>/dev/null; then",
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
                "available; Windows auto mode uses host-network ADB remapping for reliability"
                if _is_windows()
                else "multi-worker Redroid can use mapped ADB ports"
            )
            _status(True, "Docker bridge/NAT networking", detail)
            if _is_windows():
                internet_ok = _docker_bridge_internet_ok(timeout=20)
                if internet_ok:
                    _status(True, "Docker bridge container internet", "bridge containers can reach 8.8.8.8")
                else:
                    failures += 1
                    _status(False, "Docker bridge container internet", "run 'python -m damru fix-wsl'")
        else:
            _warn(
                "Docker bridge/NAT networking",
                "unavailable; Damru can use one-worker host-network fallback only",
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
                "Cross-distro WSL host-network Redroid conflict",
                "stop these containers or use the same WSL distro: " + "; ".join(conflicts),
            )
        else:
            _status(True, "Cross-distro WSL host-network Redroid conflict", "none detected")

    _ensure_binderfs_mounted()
    _ensure_binderfs_mounted()
    binderfs_ok = _linux_run(
        "test -d /dev/binderfs && mount | grep -q ' /dev/binderfs '",
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
                "Cross-distro WSL host-network Redroid conflict",
                "stop these containers or use the same WSL distro: " + "; ".join(conflicts),
            )
        else:
            _status(True, "Cross-distro WSL host-network Redroid conflict", "none detected")

    _ensure_binderfs_mounted()
    binderfs_ok = _linux_run(
        "test -d /dev/binderfs && mount | grep -q ' /dev/binderfs '",
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
        script_lines = [
            "set -e",
            *_wsl_dns_repair_lines(),
            "apt_update",
            "apt-get install -y android-tools-adb docker.io curl wget git jq cpio gcc iptables kmod ca-certificates acl python3-venv",
            f"mkdir -p /home/damru && chown {shlex.quote(WSL_USERNAME or 'root')}:{shlex.quote(WSL_USERNAME or 'root')} /home/damru 2>/dev/null || true",
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
            "if ! sudo_cmd docker info >/dev/null 2>/dev/null; then sudo_cmd service docker start 2>/dev/null || true; fi",
            "if ! sudo_cmd docker info >/dev/null 2>/dev/null; then",
            "  printf '%s\\n' \"$DAMRU_SUDO_PASSWORD\" | sudo -S nohup dockerd --host=unix:///var/run/docker.sock >/tmp/damru-dockerd.log 2>/tmp/damru-dockerd.err &",
            "  for i in {1..60}; do",
            "    sudo_cmd docker info >/dev/null 2>/dev/null && break",
            "    sleep 2",
            "  done",
            "fi",
            "if ! sudo_cmd docker info >/dev/null 2>/dev/null; then",
            "  sudo_cmd pkill dockerd 2>/dev/null || true",
            "  sudo_cmd pkill containerd 2>/dev/null || true",
            "  sudo_cmd rm -f /var/run/docker.pid /var/run/docker.sock",
            "  printf '%s\\n' \"$DAMRU_SUDO_PASSWORD\" | sudo -S nohup dockerd --iptables=false --ip6tables=false --bridge=none --host=unix:///var/run/docker.sock >/tmp/damru-dockerd-noiptables.log 2>/tmp/damru-dockerd-noiptables.err &",
            "  for i in {1..60}; do",
            "    sudo_cmd docker info >/dev/null 2>/dev/null && break",
            "    sleep 2",
            "  done",
            "fi",
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
        timeout=600,
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
                "Cross-distro WSL host-network Redroid conflict",
                "stop these containers or use the same WSL distro: " + "; ".join(conflicts),
            )
        else:
            _status(True, "Cross-distro WSL host-network Redroid conflict", "none detected")

    if failures:
        return 1

    binderfs_ok = _linux_run(
        "test -d /dev/binderfs && mount | grep -q ' /dev/binderfs '",
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
        print("binderfs is not mounted at /dev/binderfs.", file=sys.stderr)
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
        if pip_result.stderr.strip() and (repo_root / "pyproject.toml").exists():
            print(pip_result.stderr.strip(), file=sys.stderr)
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

    benchmark_main(benchmark_args)
    return 0


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

def _download_google_drive_file(url: str, target: Path) -> None:
    import requests

    file_id_match = re.search(r"/d/([^/]+)/", url) or re.search(r"[&]id=([^&]+)", url)
    if not file_id_match:
        raise RuntimeError("unsupported Drive URL; pass --url with a Google Drive file link")
    session = requests.Session()
    response = session.get(
        "https://drive.google.com/uc",
        params={"export": "download", "id": file_id_match.group(1)},
        stream=True,
        timeout=60,
    )
    token = next((value for key, value in response.cookies.items() if key.startswith("download_warning")), None)
    if token:
        response.close()
        response = session.get(
            "https://drive.google.com/uc",
            params={"export": "download", "id": file_id_match.group(1), "confirm": token},
            stream=True,
            timeout=60,
        )
    response.raise_for_status()

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
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

def _download_file(url: str, target: Path) -> None:
    if "drive.google.com" in url:
        _download_google_drive_file(url, target)
        return

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
            _download_google_drive_file(args.url, target)
        except Exception as exc:
            print(f"Image download failed: {exc}", file=sys.stderr)
            print(f"Manual download URL: {args.url}", file=sys.stderr)
            return 1
        tar_path = target

    digest = _file_sha256(tar_path)
    if digest.lower() != _DAMRU_IMAGE_SHA256.lower():
        print(f"Image checksum mismatch for {tar_path.name}: expected {_DAMRU_IMAGE_SHA256}, got {digest}", file=sys.stderr)
        return 1

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
    compatible = [p for p in version_dirs if p.name not in _CHROME_APK_AUTO_SKIP_VERSIONS]
    return (compatible or version_dirs)[-1]

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
            cmd.extend(["--serial", serial])
        if args.no_control:
            cmd.append("--no-control")
        if args.max_size:
            cmd.extend(["--max-size", str(args.max_size)])
        return cmd

    if _check_command_linux("scrcpy"):
        linux_parts = ["scrcpy"]
        if serial:
            linux_parts.extend(["--serial", serial])
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

    shot = sub.add_parser("screenshot", help="capture a PNG screenshot from an ADB device")
    shot.add_argument("--serial", "-s", default=None, help="ADB serial; defaults to the first online device")
    shot.add_argument("--output", "-o", default="damru-screenshot.png", help="output PNG path")
    shot.set_defaults(func=_screenshot)

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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
