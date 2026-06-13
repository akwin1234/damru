"""Native WebView provider patches used during Redroid image baking."""
from __future__ import annotations

from pathlib import Path
import tempfile
import zipfile


X_REQUESTED_WITH = b"X-Requested-With"
LINUX_ARMV8L_TYPO = b"Linux armv81"
LINUX_ARMV8L = b"Linux armv8l"
WEBVIEW_NATIVE_LIBRARY_NAMES = ("libmonochrome_64.so", "libmonochrome.so")
_REQUEST_HEADERS_LEA = b"\x48\x8d\xbb\x98\x02\x00\x00"
_REQUEST_LAZY_INIT_SKIP_CMP = b"\x48\x3b\x83\xa0\x02\x00\x00"
_CORS_EXEMPT_HEADERS_LEA = b"\x4c\x8d\xab\xb0\x02\x00\x00"


class WebViewNativePatchError(RuntimeError):
    """Raised when a native WebView patch cannot be applied safely."""


def is_webview_native_library_entry(filename: str) -> bool:
    return any(filename.endswith(f"/{name}") for name in WEBVIEW_NATIVE_LIBRARY_NAMES)


def _rip_relative_lea_xrefs(data: bytes, target: int) -> list[int]:
    hits: list[int] = []
    # lea reg, [rip+disp32], with optional REX prefix. The reg field varies,
    # but mod=00/rm=101 in the ModRM byte identifies RIP-relative addressing.
    for rex in range(0x40, 0x50):
        for reg in range(8):
            needle = bytes((rex, 0x8D, 0x05 | (reg << 3)))
            start = 0
            while True:
                pos = data.find(needle, start)
                if pos < 0:
                    break
                disp_pos = pos + len(needle)
                if disp_pos + 4 <= len(data):
                    disp = int.from_bytes(data[disp_pos:disp_pos + 4], "little", signed=True)
                    if disp_pos + 4 + disp == target:
                        hits.append(pos)
                start = pos + 1
    return sorted(set(hits))


def _patch_origin_matched_requested_with_header_block(data: bytearray) -> tuple[bool, bool]:
    """Patch the origin-matched/custom-header XRW append path.

    Returns (changed, found). Raises when the canonical string is present but
    the nearby append guard cannot be identified safely.
    """
    header_offset = data.find(X_REQUESTED_WITH)
    if header_offset < 0:
        raise WebViewNativePatchError("X-Requested-With string not found in WebView native library")
    if data.find(X_REQUESTED_WITH, header_offset + 1) >= 0:
        raise WebViewNativePatchError("multiple X-Requested-With strings found; refusing ambiguous patch")

    xrefs = _rip_relative_lea_xrefs(data, header_offset)
    if not xrefs:
        raise WebViewNativePatchError("no RIP-relative reference to X-Requested-With found")

    patched = False
    for xref in xrefs:
        window_start = max(0, xref - 128)
        window = data[window_start:xref]
        guard_at = window.rfind(b"\x48\x85\xc0")
        if guard_at < 0:
            continue
        patch_offset = window_start + guard_at + 3
        # Keep the original short-jump displacement, but make the branch
        # unconditional. This skips only the header block guarded by rax.
        if data[patch_offset] == 0xEB:
            return False, True
        if data[patch_offset] != 0x74:
            continue
        data[patch_offset] = 0xEB
        return True, True

    raise WebViewNativePatchError("could not find X-Requested-With append guard to patch")


def _patch_default_cors_exempt_requested_with_header_block(data: bytearray) -> tuple[bool, bool]:
    """Patch WebView's default CORS-exempt XRW package-name append path.

    Modern Android WebView also sets `X-Requested-With` from
    `AwProxyingURLLoaderFactory::SetRequestedWithHeader()`, using the host app
    package name when no origin-matched header is already present. The branch
    below skips the package-name SetHeader block while preserving request flow.
    """
    changed = False
    found = False
    start = 0
    while True:
        lea_pos = data.find(_REQUEST_HEADERS_LEA, start)
        if lea_pos < 0:
            break
        window_end = min(len(data), lea_pos + 160)
        cmp_pos = data.find(_REQUEST_LAZY_INIT_SKIP_CMP, lea_pos, window_end)
        if cmp_pos < 0:
            start = lea_pos + 1
            continue
        branch_offset = cmp_pos + len(_REQUEST_LAZY_INIT_SKIP_CMP)
        if branch_offset + 2 > len(data):
            start = lea_pos + 1
            continue
        branch_byte = data[branch_offset]
        if branch_byte not in (0x75, 0xEB):
            start = lea_pos + 1
            continue
        cors_exempt_pos = data.find(
            _CORS_EXEMPT_HEADERS_LEA,
            branch_offset,
            min(len(data), branch_offset + 128),
        )
        if cors_exempt_pos < 0:
            start = lea_pos + 1
            continue

        found = True
        if branch_byte == 0x75:
            # Keep the short-jump displacement, but always take the skip over
            # the host_package_name() SetHeader block.
            data[branch_offset] = 0xEB
            changed = True
        start = lea_pos + 1
    return changed, found


def patch_x_requested_with_header_block(path: str | Path) -> bool:
    """Disable Chromium's WebView embedding-app X-Requested-With appends.

    Returns True when bytes were modified and False when the library already
    contains the patch. The patch handles both known native paths:
    origin-matched/custom-header XRW handling and the newer default
    CORS-exempt package-name header append.
    """
    target = Path(path)
    data = bytearray(target.read_bytes())
    origin_error: WebViewNativePatchError | None = None
    try:
        origin_changed, origin_found = _patch_origin_matched_requested_with_header_block(data)
    except WebViewNativePatchError as exc:
        origin_error = exc
        origin_changed = False
        origin_found = False

    default_changed, default_found = _patch_default_cors_exempt_requested_with_header_block(data)
    if origin_changed or default_changed:
        target.write_bytes(data)
        return True
    if origin_found or default_found:
        return False
    if origin_error is not None:
        raise origin_error
    raise WebViewNativePatchError("could not find any X-Requested-With append block to patch")


def patch_linux_armv8l_platform_string(path: str | Path) -> bool:
    """Fix Chromium's Android navigator.platform typo in x86_64 WebView builds."""
    target = Path(path)
    data = bytearray(target.read_bytes())
    typo_count = data.count(LINUX_ARMV8L_TYPO)
    if typo_count == 0:
        if data.count(LINUX_ARMV8L):
            return False
        raise WebViewNativePatchError("Linux armv81 platform string not found in WebView native library")
    data[:] = data.replace(LINUX_ARMV8L_TYPO, LINUX_ARMV8L)
    target.write_bytes(data)
    return True


def patch_linux_armv8l_platform_string_in_apk(path: str | Path) -> bool:
    """Patch the libmonochrome entry inside a Trichrome/WebView APK."""
    target = Path(path)
    changed = False
    found = False
    with tempfile.TemporaryDirectory(prefix="damru-webview-apk-patch-") as tmp:
        patched_apk = Path(tmp) / target.name
        with zipfile.ZipFile(target, "r") as source, zipfile.ZipFile(patched_apk, "w") as dest:
            for info in source.infolist():
                data = source.read(info.filename)
                if is_webview_native_library_entry(info.filename):
                    found = True
                    if LINUX_ARMV8L_TYPO in data:
                        data = data.replace(LINUX_ARMV8L_TYPO, LINUX_ARMV8L)
                        changed = True
                out_info = zipfile.ZipInfo(info.filename, info.date_time)
                out_info.comment = info.comment
                out_info.extra = info.extra
                out_info.internal_attr = info.internal_attr
                out_info.external_attr = info.external_attr
                out_info.create_system = info.create_system
                out_info.compress_type = info.compress_type
                out_info.flag_bits = info.flag_bits
                dest.writestr(out_info, data)
        if not found:
            raise WebViewNativePatchError("WebView native library entry not found in WebView APK")
        if not changed:
            with zipfile.ZipFile(target, "r") as source:
                if any(
                    is_webview_native_library_entry(info.filename) and LINUX_ARMV8L in source.read(info.filename)
                    for info in source.infolist()
                ):
                    return False
            raise WebViewNativePatchError("Linux armv81 platform string not found in WebView APK")
        patched_apk.replace(target)
    return True
