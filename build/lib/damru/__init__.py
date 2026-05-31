"""damru - Stealth browser automation on Android via ADB + root.

Usage:
    from damru import Damru, AsyncDamru

    with Damru(device="pixel_8_pro", proxy="socks5://host:port") as browser:
        page = browser.new_page()
        page.goto("https://example.com")
"""

# Patch playwright's crPage.js before anything imports playwright.
# This must happen before .async_core / .core which import playwright.
from .playwright_patch import ensure_patched as _ensure_pw_patched
_ensure_pw_patched()

from .async_core import AsyncDamru, DamruError
from .core import Damru
from .devices import AndroidDevice, get_device, get_random_device, list_device_names
from .pool import DamruPool, DamruPoolSync

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
]
