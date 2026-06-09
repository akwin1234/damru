"""APK asset discovery for raw/unbaked Redroid flows."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from importlib import resources

_WEBVIEW_APK_NAMES = (
    'TrichromeWebView.apk',
    'AndroidSystemWebView.apk',
    'WebView.apk',
    'webview.apk',
)


def _package_root() -> Path:
    return Path(__file__).resolve().parent

def bundled_magisk_apk() -> Optional[Path]:
    """Return the Magisk APK shipped with Damru, when package data is available."""
    try:
        ref = resources.files("damru.assets").joinpath("magisk.apk")
        with resources.as_file(ref) as path:
            if path.is_file() and path.stat().st_size > 1_000_000:
                return path.resolve()
    except Exception:
        pass

    fallback = _package_root() / "assets" / "magisk.apk"
    if fallback.is_file() and fallback.stat().st_size > 1_000_000:
        return fallback.resolve()
    return None


def _configured_chrome_apk() -> Optional[str]:
    try:
        from . import config

        value = getattr(config, "CHROME_APK", None)
        return str(value) if value else None
    except Exception:
        return None


def candidate_apk_bundle_roots(explicit_chrome_apk: Optional[str] = None) -> list[Path]:
    """Return likely chrome-apks bundle roots in priority order.

    ``explicit_chrome_apk`` may point at the bundle root, a Chrome version
    directory under the bundle root, or a single APK file.
    """
    candidates: list[Path] = []
    explicit = explicit_chrome_apk or _configured_chrome_apk()
    if explicit:
        p = Path(explicit).expanduser()
        if p.name == "chrome-apks":
            candidates.append(p)
        elif p.parent.name == "chrome-apks":
            candidates.append(p.parent)
        elif p.is_file():
            candidates.append(p.parent)
        else:
            candidates.append(p)

    pkg = _package_root()
    cwd = Path.cwd()
    candidates.append(Path("/home/damru/chrome-apks"))
    for root in (cwd, cwd.parent, pkg, pkg.parent, pkg.parent.parent, Path.home()):
        candidates.append(root / "chrome-apks")

    seen: set[str] = set()
    unique: list[Path] = []
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path.absolute())
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def find_apk_bundle_root(explicit_chrome_apk: Optional[str] = None) -> Optional[Path]:
    """Find the root that contains Chrome versions plus WebView/TTS APKs."""
    for root in candidate_apk_bundle_roots(explicit_chrome_apk):
        if not root.is_dir():
            continue
        has_top_level_apk = any(root.glob("*.apk"))
        has_version_apk = any(p.is_dir() and any(p.glob("*.apk")) for p in root.iterdir())
        if has_top_level_apk or has_version_apk:
            return root.resolve()
    return None


def find_bundle_apk(name: str, explicit_chrome_apk: Optional[str] = None) -> Optional[Path]:
    """Find a named APK in the chrome-apks bundle root."""
    root = find_apk_bundle_root(explicit_chrome_apk)
    if root is None:
        return None
    direct = root / name
    if direct.is_file():
        return direct.resolve()
    lowered = name.lower()
    for apk in root.glob("*.apk"):
        if apk.name.lower() == lowered:
            return apk.resolve()
    return None


def find_matching_webview_apk(version_dir: str | Path, explicit_chrome_apk: Optional[str] = None) -> Optional[Path]:
    '''Find a WebView APK that belongs to the same Chrome version directory.'''
    p = Path(version_dir)
    if not p.is_dir():
        return None
    lowered = {name.lower() for name in _WEBVIEW_APK_NAMES}
    for name in _WEBVIEW_APK_NAMES:
        direct = p / name
        if direct.is_file():
            return direct.resolve()
    for apk in p.glob('*.apk'):
        apk_name = apk.name.lower()
        if apk_name in lowered or 'webview' in apk_name:
            return apk.resolve()
    return None

def find_any_bundle_apk(names: list[str], explicit_chrome_apk: Optional[str] = None) -> Optional[Path]:
    """Find the first available APK from a list of acceptable names."""
    for name in names:
        found = find_bundle_apk(name, explicit_chrome_apk)
        if found is not None:
            return found
    root = find_apk_bundle_root(explicit_chrome_apk)
    if root is None:
        return None
    lowered = [name.lower() for name in names]
    for apk in root.glob("*.apk"):
        apk_name = apk.name.lower()
        if any(name in apk_name for name in lowered):
            return apk.resolve()
    return None


def validate_apk_bundle(root: Path) -> tuple[bool, str]:
    """Validate that a bundle root has Chrome, WebView, and TTS assets."""
    if not root.is_dir():
        return False, f"missing bundle directory: {root}"

    chrome_dirs = [p for p in root.iterdir() if p.is_dir() and any(p.glob("*.apk"))]
    if not chrome_dirs and not any(root.glob("*.apk")):
        return False, f"no APK files found under {root}"

    required = [
        "google_tts.apk",
        "espeak.apk",
        "rhvoice.apk",
        "magisk.apk",
    ]
    missing = [name for name in required if find_bundle_apk(name, str(root)) is None]
    if missing:
        return False, f"missing APK bundle asset(s): {', '.join(missing)} in {root}"

    if not chrome_dirs:
        return False, f"missing Chrome split-APK version directory under {root}"

    matched_webview = [
        chrome_dir.name
        for chrome_dir in chrome_dirs
        if find_matching_webview_apk(chrome_dir, str(root)) is not None
    ]
    missing_webview = [chrome_dir.name for chrome_dir in chrome_dirs if chrome_dir.name not in matched_webview]
    if not matched_webview:
        return False, (
            'missing matching WebView APK in Chrome version directories: '
            + ', '.join(missing_webview)
            + f' in {root}'
        )

    if missing_webview:
        return True, (
            f'{root.resolve()} ({len(matched_webview)} Chrome/WebView matched; '
            f'skipping Chrome-only directories: {", ".join(missing_webview)})'
        )

    return True, str(root)
