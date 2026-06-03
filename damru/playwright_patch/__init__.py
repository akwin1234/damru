"""Playwright crPage.js stealth patch for damru.

This module patches Playwright's Chromium crPage.js to add a Runtime
enable/disable dance controlled by the PLAYWRIGHT_STEALTH_RUNTIME env var.

The patch is idempotent: it detects whether the installed crPage.js already
contains the stealth modifications and skips patching if so.

How it works:
  - On import, ``ensure_patched()`` locates the installed playwright package's
    crPage.js (at ``playwright/driver/package/lib/server/chromium/crPage.js``).
  - It checks whether the file already contains the ``PLAYWRIGHT_STEALTH_RUNTIME``
    marker string.  If yes, it is already patched and nothing happens.
  - If not, it copies the bundled (pre-patched) crPage.js from this directory
    over the installed version.
  - A SHA-256 hash comparison is done first so we only write when the content
    actually differs.
"""

import hashlib
import importlib.util
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Marker string present in our patched crPage.js -- used for quick detection.
_PATCH_MARKER = "PLAYWRIGHT_STEALTH_RUNTIME_DAMRU_DYNAMIC_V2"
_ENV_MARKER = "PLAYWRIGHT_STEALTH_RUNTIME"

# Location of the bundled (already-patched) crPage.js shipped with damru.
_BUNDLED_CRPAGE = Path(__file__).parent / "crPage.js"

# Relative path from the playwright package root to crPage.js.
_CRPAGE_REL = Path("driver") / "package" / "lib" / "server" / "chromium" / "crPage.js"


def _find_installed_crpage() -> Path | None:
    """Return the absolute path to the installed playwright's crPage.js, or None."""
    try:
        # Use the playwright package's __file__ to find its install location.
        # This works regardless of virtualenv, global install, etc.
        spec = importlib.util.find_spec("playwright")
        if spec is None or spec.origin is None:
            logger.warning("playwright package not found -- cannot patch crPage.js")
            return None
        playwright_root = Path(spec.origin).parent
        target = playwright_root / _CRPAGE_REL
        if target.is_file():
            return target
        logger.warning("crPage.js not found at expected path: %s", target)
        return None
    except Exception as exc:
        logger.warning("Failed to locate playwright crPage.js: %s", exc)
        return None


def _sha256(path: Path) -> str:
    """Return hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _is_patched(path: Path) -> bool:
    """Check whether the file at *path* already contains our patch marker."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            # Read in chunks to avoid loading huge files in one shot.
            for chunk in iter(lambda: f.read(65536), ""):
                if _PATCH_MARKER in chunk:
                    return True
        return False
    except Exception:
        return False


def _patch_text(source: str) -> str:
    """Patch the installed Playwright file while preserving its version shape."""
    runtime_enable = 'this._client.send("Runtime.enable", {}),'
    replacement = (
        f'(process.env.{_ENV_MARKER}  '
        'this._client.send("Runtime.enable", {}).then(() => { '
        f'/* {_PATCH_MARKER} */ '
        'this._stealthDisableTimer = setTimeout(() => { '
        'this._client.send("Runtime.disable", {}).catch(() => {}); '
        '}, 100); }) : this._client.send("Runtime.enable", {})),'
    )
    if _PATCH_MARKER in source:
        return source
    if runtime_enable not in source:
        raise RuntimeError("Playwright crPage.js Runtime.enable hook point not found")
    patched = source.replace(runtime_enable, replacement, 1)

    frame_nav = (
        'this._page.frameManager.frameCommittedNewDocumentNavigation('
        'framePayload.id, framePayload.url + (framePayload.urlFragment || ""), '
        'framePayload.name || "", framePayload.loaderId, initial);'
    )
    frame_nav_patch = (
        f'if (process.env.{_ENV_MARKER}) {{ clearTimeout(this._stealthDisableTimer); '
        'this._client.send("Runtime.enable", {}).catch(() => {}); }\n    '
        + frame_nav
    )
    if frame_nav in patched:
        patched = patched.replace(frame_nav, frame_nav_patch, 1)

    context_created = (
        'const frame = contextPayload.auxData  '
        'this._page.frameManager.frame(contextPayload.auxData.frameId) : null;'
    )
    context_created_patch = (
        f'if (process.env.{_ENV_MARKER}) {{ clearTimeout(this._stealthDisableTimer); '
        'this._stealthDisableTimer = setTimeout(() => { '
        'this._client.send("Runtime.disable", {}).catch(() => {}); }, 10); }\n    '
        + context_created
    )
    if context_created in patched:
        patched = patched.replace(context_created, context_created_patch, 1)

    return patched


def ensure_patched() -> bool:
    """Ensure the installed playwright crPage.js has the damru stealth patch.

    Returns True if the patch was applied (or was already present), False if
    patching could not be performed (e.g. playwright not installed).
    """
    if not _BUNDLED_CRPAGE.is_file():
        logger.warning(
            "Bundled crPage.js not found at %s -- cannot apply playwright patch",
            _BUNDLED_CRPAGE,
        )
        return False

    target = _find_installed_crpage()
    if target is None:
        return False

    # Fast path: already patched by the current in-place patcher.
    if _is_patched(target):
        logger.debug("Playwright crPage.js already patched -- skipping")
        return True

    # Apply the patch to the installed Playwright file. Older Damru builds copied
    # a full bundled crPage.js, which can drift from Playwright internals. If that
    # old patch is present and a backup exists, start from the backup first.
    try:
        # Create a backup of the original (just in case), but don't fail on it.
        backup = target.with_suffix(".js.damru_backup")
        if not backup.exists():
            try:
                shutil.copy2(target, backup)
                logger.info("Backed up original crPage.js to %s", backup)
            except Exception as exc:
                logger.debug("Could not create backup: %s", exc)

        source_path = target
        target_text = _read_text(target)
        if _ENV_MARKER in target_text and _PATCH_MARKER not in target_text and backup.exists():
            source_path = backup

        patched = _patch_text(_read_text(source_path))
        _write_text(target, patched)
        logger.info("Applied damru stealth patch to %s", target)
        return True
    except PermissionError:
        logger.error(
            "Permission denied when patching %s -- try running with elevated "
            "privileges or install playwright in a user-writable location.",
            target,
        )
        return False
    except Exception as exc:
        logger.error("Failed to patch crPage.js: %s", exc)
        return False
