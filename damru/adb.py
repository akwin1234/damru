"""ADB command wrapper for damru.

All Android Debug Bridge interaction goes through this module.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Optional

from .utils import logger


class ADBError(Exception):
    """ADB command failed."""


class ADB:
    """Wrapper around the `adb` CLI binary."""

    def __init__(self, serial: Optional[str] = None):
        self.serial = serial

    async def _run(
        self,
        args: List[str],
        timeout: float = 15.0,
        allow_failure: bool = False,
    ) -> str:
        """Run an adb command and return stdout."""
        cmd = ["adb"]
        if self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(args)

        logger.debug("adb: %s", " ".join(cmd))

        # On Windows with Git bash, MSYS can mangle /dev-style paths.
        # Set MSYS_NO_PATHCONV to prevent this.
        import os
        env = os.environ.copy()
        env["MSYS_NO_PATHCONV"] = "1"

        async def _exec(command: List[str], timeout_s: float) -> tuple[int, str, str]:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            out_s = stdout.decode("utf-8", errors="replace").strip()
            err_s = stderr.decode("utf-8", errors="replace").strip()
            return proc.returncode, out_s, err_s

        try:
            rc, out, err = await _exec(cmd, timeout)
        except asyncio.TimeoutError:
            if allow_failure:
                return ""
            raise ADBError(f"adb command timed out: {' '.join(cmd)}")

        if rc == 0:
            return out
        if allow_failure:
            return out

        # MuMu/Windows can intermittently return rc=255 with empty stderr/stdout
        # on stale transports; reconnect once and retry the original command.
        transport_bad = rc == 255 and bool(self.serial)
        low = f"{out}\n{err}".lower()
        if not transport_bad:
            transport_bad = (
                bool(self.serial)
                and ("device offline" in low or "device not found" in low or "no devices/emulators found" in low)
            )

        if transport_bad and args and args[0] not in {"connect", "disconnect", "start-server", "kill-server", "devices"}:
            reconnect_timeout = min(max(timeout, 5.0), 15.0)
            try:
                await _exec(["adb", "disconnect", self.serial], reconnect_timeout)
            except Exception:
                pass
            try:
                await _exec(["adb", "connect", self.serial], reconnect_timeout)
            except Exception:
                pass
            await asyncio.sleep(0.3)

            try:
                rc2, out2, err2 = await _exec(cmd, timeout)
            except asyncio.TimeoutError:
                raise ADBError(f"adb command timed out after reconnect: {' '.join(cmd)}")

            if rc2 == 0:
                return out2

            first_detail = (err or out or "<no output>").strip()
            second_detail = (err2 or out2 or "<no output>").strip()
            raise ADBError(
                f"adb failed (rc={rc2}): {second_detail} | "
                f"first_error(rc={rc})={first_detail} | cmd={' '.join(cmd)}"
            )

        detail = (err or out or "<no output>").strip()
        raise ADBError(f"adb failed (rc={rc}): {detail} | cmd={' '.join(cmd)}")

    # ---- Shell commands ----

    async def shell(self, command: str, timeout: float = 15.0, allow_failure: bool = False) -> str:
        """Run `adb shell <command>`."""
        return await self._run(["shell", command], timeout=timeout, allow_failure=allow_failure)

    async def shell_root(self, command: str, timeout: float = 15.0) -> str:
        """Run a shell command as root.

        Uses whichever root method was detected by is_rooted():
          - "direct": adbd running as root, just run the command
          - "su_c": Magisk/SuperSU style (su -c '<cmd>')
          - "su_0": AOSP/redroid style (su 0 <cmd>)
        Falls back to trying all methods if not yet detected.
        """
        method = getattr(self, "_root_method", None)

        if method == "direct":
            return await self._run(["shell", command], timeout=timeout)
        elif method == "su_c":
            escaped = command.replace("'", "'\"'\"'")
            return await self._run(
                ["shell", f"su -c '{escaped}'"], timeout=timeout
            )
        elif method == "su_0":
            escaped = command.replace("'", "'\"'\"'")
            return await self._run(
                ["shell", f"su 0 sh -c '{escaped}'"], timeout=timeout
            )

        # Not yet detected — try each method
        escaped = command.replace("'", "'\"'\"'")
        try:
            return await self._run(
                ["shell", f"su -c '{escaped}'"], timeout=timeout
            )
        except ADBError:
            pass
        try:
            escaped = command.replace("'", "'\"'\"'")
            return await self._run(
                ["shell", f"su 0 sh -c '{escaped}'"], timeout=timeout
            )
        except ADBError:
            pass
        return await self._run(["shell", command], timeout=timeout)

    # ---- Device discovery ----

    async def list_devices(self) -> List[Dict[str, str]]:
        """List all connected ADB devices."""
        out = await self._run(["devices", "-l"], timeout=10)
        devices: List[Dict[str, str]] = []
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial = parts[0]
            status = parts[1]
            props: Dict[str, str] = {}
            for p in parts[2:]:
                if ":" in p:
                    k, v = p.split(":", 1)
                    props[k] = v
            devices.append({
                "serial": serial,
                "status": status,
                "model": props.get("model", ""),
                "device": props.get("device", ""),
            })
        return devices

    async def detect_device(self) -> str:
        """Auto-detect and return serial of first online device.

        Prefers emulator-* serials, then first available.
        """
        devices = await self.list_devices()
        online = [d for d in devices if d["status"] == "device"]
        if not online:
            raise ADBError("No Android devices found. Start an emulator or connect a device.")
        # Prefer emulator
        for d in online:
            if d["serial"].startswith("emulator-"):
                return d["serial"]
        return online[0]["serial"]

    async def ensure_server(self) -> None:
        """Start ADB server if not running."""
        await self._run(["start-server"], timeout=10, allow_failure=True)

    # ---- Properties ----

    async def get_prop(self, name: str) -> str:
        """Get a single Android system property."""
        return await self.shell(f"getprop {name}", allow_failure=True)

    async def get_device_info(self) -> Dict[str, Any]:
        """Get device model, brand, android version, screen size, density."""
        props = {
            "model": "ro.product.model",
            "brand": "ro.product.brand",
            "android_version": "ro.build.version.release",
            "sdk_version": "ro.build.version.sdk",
            "abi": "ro.product.cpu.abi",
        }
        info: Dict[str, Any] = {"serial": self.serial}
        for key, prop in props.items():
            info[key] = await self.get_prop(prop)

        # Screen size
        size_out = await self.shell("wm size", allow_failure=True)
        m = re.search(r"(\d+)x(\d+)", size_out)
        if m:
            info["width"] = int(m.group(1))
            info["height"] = int(m.group(2))

        # Density
        density_out = await self.shell("wm density", allow_failure=True)
        m = re.search(r"(\d+)", density_out)
        if m:
            info["density"] = int(m.group(1))

        return info

    # ---- Root detection ----

    async def is_rooted(self) -> bool:
        """Check if device has root access.

        Detects root method and caches it for shell_root():
          - "direct": adbd running as root (adb root or emulator default)
          - "su_c": Magisk/SuperSU style (su -c '<cmd>')
          - "su_0": AOSP/redroid style (su 0 <cmd>)
        """
        # Check if adb is already running as root
        try:
            out = await self.shell("id", timeout=5, allow_failure=True)
            if "uid=0" in out:
                self._root_method = "direct"
                return True
        except Exception:
            pass

        # Try Magisk/SuperSU su -c
        try:
            out = await self.shell("su -c id", timeout=5, allow_failure=True)
            if "uid=0" in out:
                self._root_method = "su_c"
                return True
        except Exception:
            pass

        # Try AOSP/redroid su 0 (with retry for post-restart recovery)
        for _su0_attempt in range(3):
            try:
                out = await self.shell("su 0 id", timeout=5, allow_failure=True)
                if "uid=0" in out:
                    self._root_method = "su_0"
                    return True
            except Exception:
                pass
            if _su0_attempt < 2:
                import asyncio
                await asyncio.sleep(2)

        # Try adb root (restarts adbd as root)
        # SKIP for TCP-connected devices (Docker containers) — adb root
        # restarts adbd which breaks Docker port forwarding permanently.
        serial = self.serial
        if serial and ":" in serial:
            logger.debug("Skipping adb root for TCP device %s (breaks Docker port forwarding)", serial)
        else:
            try:
                out = await self._run(["root"], timeout=10, allow_failure=True)
                if "root" in out.lower() and "cannot" not in out.lower():
                    import asyncio
                    await asyncio.sleep(2)
                    if serial and ":" in serial:
                        await self._run(
                            ["connect", serial], timeout=10, allow_failure=True
                        )
                        await asyncio.sleep(1)
                    out = await self.shell("id", timeout=5, allow_failure=True)
                    if "uid=0" in out:
                        self._root_method = "direct"
                        return True
            except Exception:
                pass

        return False

    async def has_resetprop(self) -> bool:
        """Check if Magisk's resetprop is available."""
        out = await self.shell("which resetprop", timeout=5, allow_failure=True)
        return "resetprop" in out

    # ---- Port forwarding ----

    async def forward(self, local_port: int, remote: str) -> None:
        """Set up port forwarding: adb forward tcp:PORT remote."""
        await self._run(["forward", f"tcp:{local_port}", remote])

    async def remove_forward(self, local_port: int) -> None:
        """Remove port forwarding."""
        await self._run(
            ["forward", "--remove", f"tcp:{local_port}"],
            allow_failure=True,
        )

    # ---- File operations ----

    async def push(self, local_path: str, remote_path: str) -> None:
        """Push a file to the device."""
        await self._run(["push", local_path, remote_path], timeout=60)

    async def install_apk(self, apk_path: str) -> None:
        """Install an APK on the device."""
        await self._run(["install", "-r", apk_path], timeout=120)
