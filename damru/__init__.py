"""damru - Stealth browser automation on Android via ADB + root.

Usage:
    from damru import Damru, AsyncDamru

    with Damru(device="pixel_8_pro", proxy="socks5://host:port") as browser:
        page = browser.new_page()
        page.goto("https://example.com")
"""

__version__ = "0.1.0"
__all__ = [
    "Damru",
    "AsyncDamru",
    "DamruPool",
    "DamruPoolSync",
    "DamruError",
    "AndroidDevice",
    "get_device",
    "get_random_device",
    "list_device_names",
    "force_device_profile",
    "AppliedDeviceProfile",
]

_LAZY_EXPORTS = set(__all__)


def _patch_windows_asyncio_shutdown_noise() -> None:
    """Suppress a Windows Proactor destructor bug after successful WSL subprocess use."""
    import sys

    if sys.platform != "win32":
        return
    try:
        import asyncio.base_subprocess as base_subprocess
        import asyncio.proactor_events as proactor_events
    except Exception:
        return

    def _wrap_del(cls) -> None:
        if getattr(cls, "_damru_close_pipe_patch", False):
            return
        original = getattr(cls, "__del__", None)
        if original is None:
            return

        def _quiet_del(self):
            try:
                original(self)
            except ValueError as exc:
                if "I/O operation on closed pipe" not in str(exc):
                    raise

        cls.__del__ = _quiet_del
        cls._damru_close_pipe_patch = True

    _wrap_del(proactor_events._ProactorBasePipeTransport)
    _wrap_del(base_subprocess.BaseSubprocessTransport)

def _load_exports() -> None:
    # Patch Playwright's crPage.js before importing modules that import Playwright.
    # Keeping this lazy lets `python -m damru check-env` run on fresh machines
    # where Playwright is not installed yet.
    from .playwright_patch import ensure_patched as _ensure_pw_patched

    _ensure_pw_patched()

    from .async_core import AsyncDamru, DamruError
    from .core import Damru
    from .devices import AndroidDevice, get_device, get_random_device, list_device_names
    from .pool import DamruPool, DamruPoolSync
    from .profile_apply import AppliedDeviceProfile, force_device_profile

    globals().update(
        {
            "Damru": Damru,
            "AsyncDamru": AsyncDamru,
            "DamruPool": DamruPool,
            "DamruPoolSync": DamruPoolSync,
            "DamruError": DamruError,
            "AndroidDevice": AndroidDevice,
            "get_device": get_device,
            "get_random_device": get_random_device,
            "list_device_names": list_device_names,
            "force_device_profile": force_device_profile,
            "AppliedDeviceProfile": AppliedDeviceProfile,
        }
    )

def __getattr__(name: str):
    if name in _LAZY_EXPORTS:
        _load_exports()
        return globals()[name]
    raise AttributeError(f"module 'damru' has no attribute {name!r}")


_patch_windows_asyncio_shutdown_noise()
