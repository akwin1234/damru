"""MuMuManager - MuMu emulator lifecycle for damru auto mode on Windows.

This manager controls MuMu instances via MuMuManager.exe and exposes:
  - instance discovery (info -v all)
  - launch/restart/shutdown
  - ADB endpoint discovery + connect
  - boot wait (sys.boot_completed)
  - optional APK install (single APK or split APK directory)

Containers/emulators are reused across sessions. Damru only recycles Chrome.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .async_core import DamruError
from .apk_assets import find_bundle_apk
from .config import (
    APK_INSTALL_TIMEOUT,
    CONTAINER_BOOT_TIMEOUT,
    MUMU_BOOT_FALLBACK_CPU,
    MUMU_BOOT_FALLBACK_MEMORY_GB,
    MUMU_BOOT_TIMEOUT,
    MUMU_CPU,
    MUMU_GPU_MODE,
    MUMU_GPU_MODEL,
    MUMU_PHONE_BRAND,
    MUMU_PHONE_MIIT,
    MUMU_PHONE_MODEL,
    MUMU_MEMORY_GB,
    MUMU_STRICT_RESOURCE_LIMIT,
    MUMU_SYSTEM_DISK_WRITABLE,
)
from .utils import logger


@dataclass
class MuMuInstance:
    """One MuMu instance and its runtime metadata."""

    index: int
    name: str
    is_main: bool
    is_process_started: bool
    is_android_started: bool
    adb_host: Optional[str] = None
    adb_port: Optional[int] = None

    @property
    def serial(self) -> Optional[str]:
        if self.adb_host and self.adb_port:
            return f"{self.adb_host}:{self.adb_port}"
        return None


class MuMuManager:
    """Manage MuMu instances for Damru pool mode='mumu'."""

    def __init__(self, manager_path: Optional[str] = None):
        self._manager_path = Path(
            manager_path
            or os.environ.get("MUMU_MANAGER_PATH", "")
            or self._detect_manager_path()
        )
        self._py_api_available = False
        self._fallback_indices = set()
        self._boot_profile_by_index: Dict[int, Tuple[int, int]] = {}
        self._hypervisor_candidates = [
            Path(r"C:\Program Files\MuMuVMMVbox\Hypervisor"),
            Path(r"C:\Program Files\Netease\MuMuPlayer\Hypervisor"),
        ]

    def _detect_manager_path(self) -> str:
        """Detect MuMuManager.exe in common installation paths."""
        candidates = [
            r"C:\Program Files\Netease\MuMuPlayer\nx_main\MuMuManager.exe",
            r"C:\Program Files\Netease\MuMuPlayer\shell\MuMuManager.exe",
            r"C:\Program Files\Netease\MuMu Player 12\shell\MuMuManager.exe",
        ]
        for p in candidates:
            if Path(p).exists():
                return p
        return ""

    def _vms_dir(self) -> Optional[Path]:
        """Return the MuMu VMs directory (parent of per-instance config folders)."""
        # Manager is at …/nx_main/MuMuManager.exe → install root is ../..
        # VMs live at <install_root>/vms/
        if not self._manager_path.exists():
            return None
        candidate = self._manager_path.parent.parent / "vms"
        return candidate if candidate.is_dir() else None

    def _shell_config_path(self, index: int) -> Optional[Path]:
        """Return path to shell_config.json for a given MuMu instance index."""
        vms = self._vms_dir()
        if vms is None:
            return None
        # MuMu names instance dirs as MuMuPlayerGlobal-12.0-{index}
        cfg = vms / f"MuMuPlayerGlobal-12.0-{index}" / "configs" / "shell_config.json"
        return cfg

    def patch_adb_debug(self, index: int) -> bool:
        """Patch shell_config.json to enable 'local & remote' ADB (mode=2).

        This corresponds to the 'Enable local & remote connection' option in
        MuMu's ADB debug settings panel. Without it, ADB connects locally only
        and root commands via 'su 0' may fail.  Returns True if patched/already-ok.
        """
        import json as _json
        path = self._shell_config_path(index)
        if path is None:
            logger.warning("Cannot locate shell_config.json for MuMu %d", index)
            return False
        if not path.exists():
            # Create minimal config if missing
            path.parent.mkdir(parents=True, exist_ok=True)
            cfg: dict = {}
        else:
            try:
                cfg = _json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to read %s: %s", path, exc)
                return False

        # Ensure player.advanced.adb_debug.mode == "2"
        cfg.setdefault("player", {}).setdefault("advanced", {}).setdefault("adb_debug", {})
        if cfg["player"]["advanced"]["adb_debug"].get("mode") == "2":
            return True  # already correct
        cfg["player"]["advanced"]["adb_debug"]["mode"] = "2"
        try:
            path.write_text(_json.dumps(cfg, indent=2), encoding="utf-8")
            logger.info("MuMu %d: ADB debug set to 'local & remote' (mode=2)", index)
            return True
        except Exception as exc:
            logger.warning("Failed to write %s: %s", path, exc)
            return False

    async def _run_cmd(
        self,
        args: List[str],
        timeout: float = 30.0,
        allow_failure: bool = False,
    ) -> str:
        """Run MuMuManager command and return stdout text."""
        if not self._manager_path.exists():
            raise DamruError(
                "MuMuManager.exe not found. Set mumu_manager_path= or "
                "config.MUMU_MANAGER_PATH."
            )

        cmd = [str(self._manager_path), *args]
        logger.debug("mumu: %s", " ".join(cmd))
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            if allow_failure:
                return ""
            raise DamruError(f"MuMuManager command timed out: {' '.join(cmd)}")

        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0 and not allow_failure:
            raise DamruError(f"MuMuManager failed: {' '.join(cmd)}\n{err or out}")
        return out or err

    def _parse_json(self, text: str) -> Dict:
        """Parse first JSON object from command output."""
        t = (text or "").strip()
        if not t:
            return {}
        try:
            return json.loads(t)
        except Exception:
            # Some MuMu builds may prepend log lines; parse from first "{".
            i = t.find("{")
            if i >= 0:
                try:
                    return json.loads(t[i:])
                except Exception:
                    pass
        return {}

    async def check_manager(self) -> None:
        """Validate MuMuManager availability and basic command surface."""
        if sys.platform != "win32":
            raise DamruError("MuMu auto mode is Windows-only")
        out = await self._run_cmd(["--help"], timeout=10, allow_failure=True)
        if "subcommand" not in out.lower() and "usage" not in out.lower():
            raise DamruError("MuMuManager did not return expected help output")
        # Optional backend 2: pip package mumu-emulator-api (import path: mumu.mumu)
        try:
            from mumu.mumu import Mumu  # noqa: F401
            self._py_api_available = True
        except Exception:
            self._py_api_available = False
        logger.info("MuMuManager: %s", self._manager_path)
        logger.info(
            "MuMu Python API backend: %s",
            "available" if self._py_api_available else "not installed (CLI fallback)",
        )

    async def repair_startup(self) -> None:
        """Best-effort startup repair steps from MuMu docs.

        Runs non-destructive repair helpers if present:
          - MuMuVMMSVC.exe
          - comregister
          - SupInstall.exe
        """
        for d in self._hypervisor_candidates:
            if not d.exists():
                continue

            svc = d / "MuMuVMMSVC.exe"
            if svc.exists():
                await self._run_plain_adb(
                    [str(svc)],
                    timeout=10,
                    allow_failure=True,
                )

            comregister = d / "comregister"
            if comregister.exists():
                await self._run_plain_adb(
                    ["cmd", "/c", f"cd /d \"{d}\" && comregister"],
                    timeout=30,
                    allow_failure=True,
                )

            supinstall = d / "SupInstall.exe"
            if supinstall.exists():
                await self._run_plain_adb(
                    ["cmd", "/c", f"cd /d \"{d}\" && SupInstall.exe"],
                    timeout=60,
                    allow_failure=True,
                )
            return

    async def get_settings(self, index: int, keys: List[str]) -> Dict[str, str]:
        """Read one or more MuMu settings keys for an instance."""
        args = ["setting", "-v", str(index)]
        for k in keys:
            args.extend(["-k", k])
        out = await self._run_cmd(args, timeout=20)
        data = self._parse_json(out)
        if not isinstance(data, dict):
            return {}
        return {k: str(v) for k, v in data.items()}

    async def _set_resources_cli(self, index: int, cpu: int, mem_gb: int) -> None:
        """Set MuMu CPU/memory using MuMuManager CLI settings."""
        await self._run_cmd(
            [
                "setting", "-v", str(index),
                "-k", "performance_mode", "-val", "custom",
                "-k", "performance_cpu.custom", "-val", str(int(cpu)),
                "-k", "performance_mem.custom", "-val", f"{float(mem_gb):.6f}",
                # Force portrait preset to avoid landscape instance configs.
                "-k", "resolution_mode", "-val", "phone.1",
                "-k", "window_auto_rotate", "-val", "true",
            ],
            timeout=20,
        )

    async def enforce_baseline_settings(self, index: int) -> None:
        """Apply baseline MuMu settings for stability and device coherence."""
        args = [
            "setting", "-v", str(index),
            "-k", "root_permission", "-val", "true",
            "-k", "resolution_mode", "-val", "phone.1",
            "-k", "window_auto_rotate", "-val", "true",
        ]
        # Optional static overrides from config (dynamic profile applies later).
        if MUMU_GPU_MODE:
            args.extend(["-k", "gpu_mode", "-val", str(MUMU_GPU_MODE)])
        if MUMU_GPU_MODEL:
            args.extend(["-k", "gpu_model.custom", "-val", str(MUMU_GPU_MODEL)])
        if MUMU_PHONE_BRAND:
            args.extend(["-k", "phone_brand", "-val", str(MUMU_PHONE_BRAND)])
        if MUMU_PHONE_MODEL:
            args.extend(["-k", "phone_model", "-val", str(MUMU_PHONE_MODEL)])
        if MUMU_PHONE_MIIT:
            args.extend(["-k", "phone_miit", "-val", str(MUMU_PHONE_MIIT)])

        if MUMU_SYSTEM_DISK_WRITABLE:
            args.extend(["-k", "system_disk_readonly", "-val", "false"])
        await self._run_cmd(args, timeout=30, allow_failure=True)
        # Verify GPU keys; if custom is blank, fall back to stable "middle" preset.
        gpu = await self.get_settings(index, ["gpu_mode", "gpu_model.custom"])
        if not gpu.get("gpu_model.custom", "").strip():
            await self._run_cmd(
                ["setting", "-v", str(index), "-k", "gpu_mode", "-val", "middle"],
                timeout=20,
                allow_failure=True,
            )
            logger.warning("MuMu %d baseline GPU custom empty; fallback gpu_mode=middle", index)

    def _infer_gpu_model(self, renderer: str) -> str:
        """Infer MuMu GPU model string from device WebGL renderer."""
        r = (renderer or "").strip()
        if not r:
            return "Adreno (TM) 640"

        m = re.search(r"(Adreno\s*\(TM\)\s*\d+)", r, flags=re.IGNORECASE)
        if m:
            token = m.group(1)
            return re.sub(r"\s+", " ", token).replace("adreno", "Adreno")

        m = re.search(r"(Mali[-\w\s]+)", r, flags=re.IGNORECASE)
        if m:
            token = m.group(1).strip()
            return re.sub(r"\s+", " ", token)

        m = re.search(r"(Xclipse\s*\d+)", r, flags=re.IGNORECASE)
        if m:
            return re.sub(r"\s+", " ", m.group(1).strip())

        return "Adreno (TM) 640"

    async def find_index_by_serial(self, serial: str) -> Optional[int]:
        """Resolve MuMu vm index from ADB serial."""
        if not serial:
            return None
        instances = await self.list_instances()
        for inst in instances:
            if inst.serial == serial:
                return inst.index
        return None

    async def apply_dynamic_profile(self, index: int, device) -> None:
        """Apply MuMu identity/gpu settings from selected device profile."""
        if not device:
            return
        gpu_model = self._infer_gpu_model(getattr(device, "webgl_renderer", ""))
        phone_model = getattr(device, "name", "") or getattr(device, "model", "")
        brand = str(getattr(device, "brand", "") or "Samsung")
        miit = str(getattr(device, "model", "") or phone_model)

        # MuMu can only emulate Adreno GPU drivers at hardware level.
        # For Adreno: use custom mode with exact renderer string (any Adreno variant works).
        # For Mali/Xclipse: use high preset — renderer.config handles the WebGL string override.
        norm = gpu_model.lower()
        if "adreno" in norm and gpu_model:
            gpu_mode = "custom"
            gpu_custom_value = gpu_model
        else:
            gpu_mode = "high"
            gpu_custom_value = ""

        desired = {
            "phone_brand": brand,
            "phone_model": str(phone_model),
            "phone_miit": miit,
            "gpu_mode": gpu_mode,
            "gpu_model.custom": str(gpu_custom_value),
            "resolution_mode": "phone.1",
        }
        current = await self.get_settings(index, list(desired.keys()))

        def _cmp(key: str, cur: str, want: str) -> bool:
            """True when values match (float comparison for numeric keys)."""
            c, w = (cur or "").strip(), str(want).strip()
            if c == w:
                return True
            if key in ("performance_mem.custom", "performance_cpu.custom"):
                try:
                    return abs(float(c) - float(w)) < 0.01
                except (ValueError, TypeError):
                    pass
            return False

        changed = any(not _cmp(k, current.get(k, ""), v) for k, v in desired.items())

        # Apply settings without restarting MuMu — identity props (model/brand/version)
        # are applied via resetprop live, and renderer.config handles WebGL spoofing.
        # MuMu GPU mode changes persist for next natural restart only.
        args = ["setting", "-v", str(index)]
        args.extend(["-k", "phone_brand", "-val", brand])
        args.extend(["-k", "phone_model", "-val", str(phone_model)])
        args.extend(["-k", "phone_miit", "-val", miit])
        args.extend(["-k", "gpu_mode", "-val", gpu_mode])
        if gpu_mode == "custom":
            args.extend(["-k", "gpu_model.custom", "-val", str(gpu_custom_value)])
        args.extend(["-k", "resolution_mode", "-val", "phone.1"])
        args.extend(["-k", "window_auto_rotate", "-val", "true"])
        if MUMU_SYSTEM_DISK_WRITABLE:
            args.extend(["-k", "system_disk_readonly", "-val", "false"])
        await self._run_cmd(args, timeout=30, allow_failure=True)
        if changed:
            logger.debug("MuMu %d settings updated (no restart — takes effect next boot)", index)

        # Safety fallback if custom GPU value ends up empty.
        gpu = await self.get_settings(index, ["gpu_mode", "gpu_model.custom"])
        if gpu.get("gpu_mode", "").strip() == "custom" and not gpu.get("gpu_model.custom", "").strip():
            await self._run_cmd(
                ["setting", "-v", str(index), "-k", "gpu_mode", "-val", "middle"],
                timeout=20,
                allow_failure=True,
            )
            logger.warning("MuMu %d rejected profile GPU custom; fallback gpu_mode=middle", index)
        else:
            logger.info(
                "MuMu %d dynamic profile applied: %s %s, gpu_mode=%s gpu_custom=%s",
                index, brand, phone_model, gpu.get("gpu_mode", "?"), gpu.get("gpu_model.custom", ""),
            )

    async def apply_dynamic_profile_by_serial(self, serial: str, device) -> bool:
        """Resolve vm index from serial and apply dynamic profile."""
        idx = await self.find_index_by_serial(serial)
        if idx is None:
            return False
        await self.apply_dynamic_profile(idx, device)
        return True

    async def _set_boot_fallback_profile(self, index: int) -> None:
        """Set a stable MuMu profile used when 1/1 cold-boot loops at 98%."""
        cpu = int(MUMU_BOOT_FALLBACK_CPU)
        mem = int(MUMU_BOOT_FALLBACK_MEMORY_GB)
        await self._set_resources_cli(index, cpu=cpu, mem_gb=mem)
        logger.warning(
            "MuMu %d switched to fallback resources: %d CPU / %d GB",
            index, cpu, mem,
        )

    def _boot_recovery_chain(self, index: int) -> List[Tuple[int, int]]:
        """Return low-to-high recovery resource profiles for a MuMu instance."""
        low_cpu = max(1, int(MUMU_CPU))
        low_mem = max(1, int(MUMU_MEMORY_GB))
        configured = (
            max(2, int(MUMU_BOOT_FALLBACK_CPU)),
            max(2, int(MUMU_BOOT_FALLBACK_MEMORY_GB)),
        )
        chain = [
            (low_cpu, low_mem),  # requested minimum (e.g., 1/1)
            (max(2, low_cpu), max(2, low_mem)),  # common stable floor
            (max(2, low_cpu), max(3, low_mem)),  # slight RAM bump
            configured,  # last-resort profile
        ]
        # Prefer previously working profile first for this index.
        preferred = self._boot_profile_by_index.get(index)
        if preferred and preferred in chain:
            chain = [preferred] + [x for x in chain if x != preferred]

        dedup: List[Tuple[int, int]] = []
        for item in chain:
            if item not in dedup:
                dedup.append(item)
        return dedup

    async def _apply_resource_profile(self, index: int, cpu: int, mem_gb: int) -> None:
        """Apply one CPU/RAM profile using both backends with CLI fallback."""
        set_ok = await self._set_resources_python_api(index, cpu, mem_gb)
        if not set_ok:
            await self._set_resources_cli(index, cpu, mem_gb)
        self._boot_profile_by_index[index] = (int(cpu), int(mem_gb))
        logger.warning(
            "MuMu %d boot recovery profile applied: %d CPU / %d GB",
            index, int(cpu), int(mem_gb),
        )

    async def _set_resources_python_api(self, index: int, cpu: int, mem_gb: int) -> bool:
        """Set MuMu CPU/memory using mumu-emulator-api package if installed."""
        if not self._py_api_available:
            return False

        def _apply() -> bool:
            from mumu.mumu import Mumu
            mm = Mumu(str(self._manager_path)).select(index)
            mm.performance.set(cpu_num=int(cpu), mem_gb=int(mem_gb))
            return True

        try:
            await asyncio.to_thread(_apply)
            return True
        except Exception as e:
            logger.warning("MuMu Python API resource set failed on index %d: %s", index, e)
            return False

    async def enforce_resources(self, index: int, cpu: Optional[int] = None, mem_gb: Optional[int] = None) -> bool:
        """Enforce MuMu VM resources (applies before boot, restarts if needed).

        Returns True if any change was applied.
        """
        # Default safe behavior: do not force 1/1 on cold boots because some
        # hosts get stuck at 98% startup. Keep portrait-only settings enforced.
        if not MUMU_STRICT_RESOURCE_LIMIT:
            await self._run_cmd(
                [
                    "setting", "-v", str(index),
                    "-k", "resolution_mode", "-val", "phone.1",
                    "-k", "window_auto_rotate", "-val", "true",
                ],
                timeout=20,
                allow_failure=True,
            )
            return False

        target_cpu = int(cpu if cpu is not None else MUMU_CPU)
        target_mem = int(mem_gb if mem_gb is not None else MUMU_MEMORY_GB)
        if (index in self._fallback_indices) and not MUMU_STRICT_RESOURCE_LIMIT:
            return False

        settings = await self.get_settings(index, ["vm_cpu", "vm_mem"])
        cur_cpu = settings.get("vm_cpu", "").strip()
        cur_mem = settings.get("vm_mem", "").strip()
        try:
            mem_equal = abs(float(cur_mem or "0") - float(target_mem)) < 0.01
        except Exception:
            mem_equal = False
        if cur_cpu == str(target_cpu) and mem_equal:
            return False

        instances = await self.list_instances()
        row = next((i for i in instances if i.index == index), None)
        if row and (row.is_process_started or row.is_android_started):
            logger.info("MuMu %d resources mismatch (%s CPU/%s GB) -> restarting for %s CPU/%s GB",
                        index, cur_cpu or "?", cur_mem or "?", target_cpu, target_mem)
            await self.shutdown_instance(index)
            await asyncio.sleep(3)

        # Use both backends: Python API first, then raw CLI fallback.
        set_ok = await self._set_resources_python_api(index, target_cpu, target_mem)
        if not set_ok:
            await self._set_resources_cli(index, target_cpu, target_mem)

        verify = await self.get_settings(
            index,
            [
                "performance_mode",
                "performance_cpu.custom",
                "performance_mem.custom",
                "resolution_mode",
                "window_auto_rotate",
            ],
        )
        logger.info(
            "MuMu %d profile: mode=%s cpu=%s mem=%s resolution=%s auto_rotate=%s",
            index,
            verify.get("performance_mode", "?"),
            verify.get("performance_cpu.custom", "?"),
            verify.get("performance_mem.custom", "?"),
            verify.get("resolution_mode", "?"),
            verify.get("window_auto_rotate", "?"),
        )
        return True

    async def list_instances(self) -> List[MuMuInstance]:
        """List all MuMu instances via `info -v all`."""
        out = await self._run_cmd(["info", "-v", "all"], timeout=20)
        data = self._parse_json(out)
        instances: List[MuMuInstance] = []

        for key in sorted(data.keys(), key=lambda x: int(x) if str(x).isdigit() else 10**9):
            row = data.get(key, {})
            try:
                idx = int(row.get("index", key))
            except Exception:
                continue

            instances.append(
                MuMuInstance(
                    index=idx,
                    name=row.get("name", f"MuMu-{idx}"),
                    is_main=bool(row.get("is_main", False)),
                    is_process_started=bool(row.get("is_process_started", False)),
                    is_android_started=bool(row.get("is_android_started", False)),
                    adb_host=row.get("adb_host_ip") or row.get("adb_host"),
                    adb_port=int(row.get("adb_port")) if row.get("adb_port") is not None else None,
                )
            )
        return instances

    async def create_instances(self, number: int) -> List[int]:
        """Create N MuMu instances. Returns created indices.

        New instances default to 2 CPU cores, 1 GB RAM, writable root.
        """
        if number <= 0:
            return []
        out = await self._run_cmd(["create", "-n", str(number)], timeout=60)
        data = self._parse_json(out)
        created: List[int] = []
        for idx, row in data.items():
            if isinstance(row, dict) and row.get("errcode") == 0:
                try:
                    created.append(int(idx))
                except Exception:
                    continue

        # Apply sensible defaults to each newly created instance
        for idx in created:
            await self._run_cmd(
                [
                    "setting", "-v", str(idx),
                    "-k", "performance_mode",      "-val", "custom",
                    "-k", "performance_cpu.custom", "-val", "2",
                    "-k", "performance_mem.custom", "-val", "1.000000",
                    "-k", "root_permission",        "-val", "true",
                    "-k", "system_disk_readonly",   "-val", "false",
                    "-k", "resolution_mode",        "-val", "phone.1",
                    "-k", "window_auto_rotate",     "-val", "true",
                ],
                timeout=30,
                allow_failure=True,
            )
            logger.info("MuMu %d defaults applied: 2 CPU / 1 GB RAM / writable root", idx)
            # Enable ADB local+remote so root commands work over TCP
            self.patch_adb_debug(idx)

        return created

    async def launch_instance(self, index: int) -> None:
        """Launch MuMu instance."""
        await self._run_cmd(["control", "-v", str(index), "launch"], timeout=30)

    async def shutdown_instance(self, index: int) -> None:
        """Shutdown MuMu instance."""
        await self._run_cmd(
            ["control", "-v", str(index), "shutdown"],
            timeout=30,
            allow_failure=True,
        )

    async def restart_instance(self, index: int) -> None:
        """Restart MuMu instance."""
        await self._run_cmd(["control", "-v", str(index), "restart"], timeout=40)

    async def _query_adb_endpoint(self, index: int) -> Optional[str]:
        """Resolve ADB host:port for an instance."""
        out = await self._run_cmd(["adb", "-v", str(index)], timeout=20, allow_failure=True)
        data = self._parse_json(out)
        if not data:
            return None

        # Format A: {"adb_host":"127.0.0.1","adb_port":16416}
        if "adb_host" in data and "adb_port" in data:
            return f"{data['adb_host']}:{data['adb_port']}"

        # Format B: {"1":{"adb_host":"...","adb_port":...}, ...}
        row = data.get(str(index))
        if isinstance(row, dict) and "adb_host" in row and "adb_port" in row:
            return f"{row['adb_host']}:{row['adb_port']}"

        return None

    async def connect_adb(self, serial: str) -> None:
        """Connect ADB to MuMu endpoint."""
        # Clear stale/offline entries first.
        _ = await self._run_plain_adb(
            ["adb", "disconnect", serial],
            timeout=10,
            allow_failure=True,
        )
        cmd = ["adb", "connect", serial]
        logger.debug("adb: %s", " ".join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        out = (stdout.decode("utf-8", errors="replace") + stderr.decode("utf-8", errors="replace")).lower()
        if proc.returncode != 0 and "already connected" not in out:
            raise DamruError(f"adb connect failed for {serial}: {out.strip()}")

    async def wait_for_boot(self, serial: str, timeout: float = MUMU_BOOT_TIMEOUT) -> None:
        """Wait until Android boot completes (`sys.boot_completed` == 1)."""
        elapsed = 0.0
        interval = 2.0
        while elapsed < timeout:
            proc = await asyncio.create_subprocess_exec(
                "adb", "-s", serial, "shell", "getprop", "sys.boot_completed",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            out = stdout.decode("utf-8", errors="replace").strip()
            err = stderr.decode("utf-8", errors="replace").strip().lower()
            if "offline" in err or "no devices" in err:
                await self.connect_adb(serial)
                await asyncio.sleep(interval)
                elapsed += interval
                continue
            if out == "1":
                logger.info("MuMu %s booted (%.0fs)", serial, elapsed)
                return
            await asyncio.sleep(interval)
            elapsed += interval
        raise DamruError(f"MuMu {serial} failed to boot within {timeout}s")

    async def _wait_for_endpoint(self, index: int, timeout: float = CONTAINER_BOOT_TIMEOUT) -> str:
        """Wait for MuMu instance to expose ADB host:port."""
        elapsed = 0.0
        interval = 2.0
        while elapsed < timeout:
            instances = await self.list_instances()
            row = next((i for i in instances if i.index == index), None)
            serial = row.serial if row else None
            if not serial:
                serial = await self._query_adb_endpoint(index)
            if serial:
                return serial
            await asyncio.sleep(interval)
            elapsed += interval
        raise DamruError(f"MuMu index {index} has no ADB endpoint after {timeout}s")

    async def ensure_instance(self, index: int) -> str:
        """Ensure one instance is running and return ADB serial."""
        await self.enforce_baseline_settings(index)
        await self.enforce_resources(index)
        recovery_chain = self._boot_recovery_chain(index)
        last_err = None
        max_attempts = max(2, 1 + len(recovery_chain))
        for attempt in range(max_attempts):
            # Attempt 0 keeps current resources. Later attempts step through
            # low->high fallback profiles to find the minimum bootable config.
            if attempt > 0:
                cpu, mem = recovery_chain[min(attempt - 1, len(recovery_chain) - 1)]
                await self.shutdown_instance(index)
                await asyncio.sleep(3)
                await self._apply_resource_profile(index, cpu=cpu, mem_gb=mem)
                self._fallback_indices.add(index)

            instances = await self.list_instances()
            row = next((i for i in instances if i.index == index), None)
            if not row:
                raise DamruError(f"MuMu instance index {index} not found")

            if not row.is_process_started or not row.is_android_started:
                logger.info("Launching MuMu instance %d (%s)", row.index, row.name)
                await self.launch_instance(row.index)
                await asyncio.sleep(3)

            try:
                serial = await self._wait_for_endpoint(index, timeout=90)
                await self.connect_adb(serial)
                await self.wait_for_boot(serial)
                return serial
            except Exception as e:
                last_err = e
                logger.warning(
                    "MuMu index %d boot/connect failed (attempt %d/%d): %s",
                    index, attempt + 1, max_attempts, e,
                )
                # Recovery for "stuck at xx%%" launches.
                await self.repair_startup()
                await self.shutdown_instance(index)
                await asyncio.sleep(5)

        raise DamruError(f"MuMu instance {index} failed to become ready: {last_err}")

    async def ensure_all(
        self,
        count: int,
        indices: Optional[List[int]] = None,
        auto_create: bool = False,
    ) -> List[tuple]:
        """Ensure N MuMu instances are ready.

        Returns list of (vm_index, serial).
        """
        if count <= 0:
            count = 1

        instances = await self.list_instances()
        if not instances:
            raise DamruError("No MuMu instances found")

        if indices:
            target = list(dict.fromkeys(int(i) for i in indices))
        else:
            # Prefer non-main instances; main instance is fallback only.
            non_main = sorted([i.index for i in instances if not i.is_main])
            main = sorted([i.index for i in instances if i.is_main])
            target = non_main + main

        if len(target) < count and auto_create:
            missing = count - len(target)
            created = await self.create_instances(missing)
            if created:
                logger.info("Created MuMu instances: %s", created)
                target.extend(created)

        if len(target) < count:
            raise DamruError(
                f"Need {count} MuMu instance(s), found {len(target)}. "
                f"Set config.MUMU_INSTANCE_INDICES or enable MUMU_AUTO_CREATE."
            )

        target = target[:count]
        pairs: List[tuple] = []
        for idx in target:
            serial = await self.ensure_instance(idx)
            pairs.append((idx, serial))
        return pairs

    async def install_apk(self, serial: str, apk_path: str) -> None:
        """Install APK on MuMu (single APK or split-APK directory)."""
        p = Path(apk_path)
        if not p.exists():
            raise DamruError(f"APK path not found: {apk_path}")

        if p.is_dir():
            all_apks = sorted(p.glob("*.apk"))
            if not all_apks:
                raise DamruError(f"No .apk files in directory: {apk_path}")

            webview = find_bundle_apk("TrichromeWebView.apk", apk_path)
            if webview is not None:
                await self._run_plain_adb(
                    ["adb", "-s", serial, "install", "-r", str(webview)],
                    timeout=APK_INSTALL_TIMEOUT,
                    allow_failure=True,
                )

            # Install TrichromeLibrary first if present.
            trichrome = p / "google_trichrome_library.apk"
            if trichrome.exists():
                await self._run_plain_adb(
                    ["adb", "-s", serial, "install", "-r", str(trichrome)],
                    timeout=APK_INSTALL_TIMEOUT,
                )

            # Chrome package split set (exclude trichrome library apk).
            chrome_apks = [a for a in all_apks if "trichrome" not in a.name.lower()]
            if not chrome_apks:
                raise DamruError(f"No Chrome split APKs found in: {apk_path}")

            await self._install_split_via_push(serial, chrome_apks)
            return

        await self._run_plain_adb(
            ["adb", "-s", serial, "install", "-r", str(p)],
            timeout=APK_INSTALL_TIMEOUT,
        )

    async def _run_plain_adb(
        self,
        cmd: List[str],
        timeout: float = 30.0,
        allow_failure: bool = False,
    ) -> str:
        """Run an adb command unrelated to MuMuManager."""
        logger.debug("adb: %s", " ".join(cmd))
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            if allow_failure:
                return ""
            raise DamruError(f"adb command timed out: {' '.join(cmd)}")
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0 and not allow_failure:
            raise DamruError(f"adb failed: {' '.join(cmd)}\n{err or out}")
        return out

    async def _install_split_via_push(self, serial: str, apks: List[Path]) -> None:
        """Install split APKs via pm session API."""
        remote_dir = "/data/local/tmp/chrome-install"
        await self._run_plain_adb(
            ["adb", "-s", serial, "shell", "mkdir", "-p", remote_dir],
            timeout=10,
        )

        remotes: List[str] = []
        total_size = 0
        for apk in apks:
            remote = f"{remote_dir}/{apk.name}"
            await self._run_plain_adb(
                ["adb", "-s", serial, "push", str(apk), remote],
                timeout=APK_INSTALL_TIMEOUT,
            )
            remotes.append(remote)
            total_size += apk.stat().st_size

        out = await self._run_plain_adb(
            ["adb", "-s", serial, "shell", "pm", "install-create", "-r", "-S", str(total_size)],
            timeout=30,
        )
        session_id = None
        for part in out.replace("[", " ").replace("]", " ").split():
            if part.isdigit():
                session_id = part
                break
        if not session_id:
            raise DamruError(f"Failed to create install session on {serial}: {out}")

        for i, remote in enumerate(remotes):
            size = apks[i].stat().st_size
            # Keep original split/base names so package parser can resolve deps.
            write_name = apks[i].name
            out = await self._run_plain_adb(
                [
                    "adb", "-s", serial, "shell", "pm", "install-write",
                    "-S", str(size), session_id, write_name, remote,
                ],
                timeout=60,
            )
            if "success" not in out.lower():
                raise DamruError(f"install-write failed for {remote} on {serial}: {out}")

        out = await self._run_plain_adb(
            ["adb", "-s", serial, "shell", "pm", "install-commit", session_id],
            timeout=30,
        )
        if "success" not in out.lower():
            raise DamruError(f"install-commit failed on {serial}: {out}")

        await self._run_plain_adb(
            ["adb", "-s", serial, "shell", "rm", "-rf", remote_dir],
            timeout=10,
            allow_failure=True,
        )
