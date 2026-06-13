from pathlib import Path
import zipfile

import pytest

from damru.webview_native_patch import (
    WebViewNativePatchError,
    is_webview_native_library_entry,
    patch_linux_armv8l_platform_string_in_apk,
    patch_linux_armv8l_platform_string,
    patch_x_requested_with_header_block,
)


def _sample_library(path: Path) -> tuple[int, int]:
    data = bytearray(b"\x90" * 2048)
    header_offset = 0x300
    data[header_offset:header_offset + len(b"X-Requested-With")] = b"X-Requested-With"

    guard_offset = 0x120
    data[guard_offset:guard_offset + 11] = b"\x48\x85\xc0\x74\x76\x83\x78\x04\x00\x74\x70"
    lea_offset = 0x160
    disp = header_offset - (lea_offset + 7)
    data[lea_offset:lea_offset + 7] = b"\x48\x8d\x35" + disp.to_bytes(4, "little", signed=True)
    path.write_bytes(data)
    return guard_offset + 3, header_offset


def _add_default_cors_exempt_path(path: Path, *, already_patched: bool = False) -> int:
    data = bytearray(path.read_bytes())
    headers_lea_offset = 0x500
    data[headers_lea_offset:headers_lea_offset + 7] = b"\x48\x8d\xbb\x98\x02\x00\x00"
    cmp_offset = 0x528
    data[cmp_offset:cmp_offset + 7] = b"\x48\x3b\x83\xa0\x02\x00\x00"
    branch_offset = cmp_offset + 7
    data[branch_offset] = 0xEB if already_patched else 0x75
    data[branch_offset + 1] = 0x4A
    cors_exempt_offset = 0x560
    data[cors_exempt_offset:cors_exempt_offset + 7] = b"\x4c\x8d\xab\xb0\x02\x00\x00"
    path.write_bytes(data)
    return branch_offset


def test_patch_x_requested_with_header_block_turns_guard_into_unconditional_jump(tmp_path):
    lib = tmp_path / "libmonochrome_64.so"
    patch_offset, _ = _sample_library(lib)

    assert patch_x_requested_with_header_block(lib) is True

    patched = lib.read_bytes()
    assert patched[patch_offset] == 0xEB


def test_patch_x_requested_with_header_block_patches_default_cors_exempt_path(tmp_path):
    lib = tmp_path / "libmonochrome_64.so"
    legacy_patch_offset, _ = _sample_library(lib)
    default_branch_offset = _add_default_cors_exempt_path(lib)

    assert patch_x_requested_with_header_block(lib) is True

    patched = lib.read_bytes()
    assert patched[legacy_patch_offset] == 0xEB
    assert patched[default_branch_offset] == 0xEB


def test_patch_x_requested_with_header_block_patches_default_when_legacy_already_patched(tmp_path):
    lib = tmp_path / "libmonochrome_64.so"
    legacy_patch_offset, _ = _sample_library(lib)
    data = bytearray(lib.read_bytes())
    data[legacy_patch_offset] = 0xEB
    lib.write_bytes(data)
    default_branch_offset = _add_default_cors_exempt_path(lib)

    assert patch_x_requested_with_header_block(lib) is True

    patched = lib.read_bytes()
    assert patched[legacy_patch_offset] == 0xEB
    assert patched[default_branch_offset] == 0xEB


def test_patch_x_requested_with_header_block_is_idempotent(tmp_path):
    lib = tmp_path / "libmonochrome_64.so"
    _sample_library(lib)
    _add_default_cors_exempt_path(lib)

    assert patch_x_requested_with_header_block(lib) is True
    assert patch_x_requested_with_header_block(lib) is False


def test_patch_x_requested_with_header_block_refuses_ambiguous_strings(tmp_path):
    lib = tmp_path / "libmonochrome_64.so"
    _, header_offset = _sample_library(lib)
    data = bytearray(lib.read_bytes())
    data[header_offset + 64:header_offset + 64 + len(b"X-Requested-With")] = b"X-Requested-With"
    lib.write_bytes(data)

    with pytest.raises(WebViewNativePatchError, match="multiple"):
        patch_x_requested_with_header_block(lib)


def test_patch_linux_armv8l_platform_string_replaces_typo(tmp_path):
    lib = tmp_path / "libmonochrome_64.so"
    lib.write_bytes(b"prefix Linux armv81 suffix")

    assert patch_linux_armv8l_platform_string(lib) is True

    assert b"Linux armv8l" in lib.read_bytes()
    assert b"Linux armv81" not in lib.read_bytes()


def test_patch_linux_armv8l_platform_string_is_idempotent(tmp_path):
    lib = tmp_path / "libmonochrome_64.so"
    lib.write_bytes(b"prefix Linux armv8l suffix")

    assert patch_linux_armv8l_platform_string(lib) is False


def test_patch_linux_armv8l_platform_string_refuses_unknown_binary(tmp_path):
    lib = tmp_path / "libmonochrome_64.so"
    lib.write_bytes(b"prefix Linux x86_64 suffix")

    with pytest.raises(WebViewNativePatchError, match="platform string not found"):
        patch_linux_armv8l_platform_string(lib)


def test_patch_linux_armv8l_platform_string_in_apk_rewrites_lib_entry(tmp_path):
    apk = tmp_path / "base.apk"
    with zipfile.ZipFile(apk, "w") as zf:
        zf.writestr("AndroidManifest.xml", b"manifest")
        zf.writestr("lib/x86_64/libmonochrome_64.so", b"prefix Linux armv81 suffix")

    assert patch_linux_armv8l_platform_string_in_apk(apk) is True

    with zipfile.ZipFile(apk, "r") as zf:
        data = zf.read("lib/x86_64/libmonochrome_64.so")
    assert b"Linux armv8l" in data
    assert b"Linux armv81" not in data


def test_patch_linux_armv8l_platform_string_in_apk_is_idempotent(tmp_path):
    apk = tmp_path / "base.apk"
    with zipfile.ZipFile(apk, "w") as zf:
        zf.writestr("lib/x86_64/libmonochrome_64.so", b"prefix Linux armv8l suffix")

    assert patch_linux_armv8l_platform_string_in_apk(apk) is False


def test_webview_native_library_entry_accepts_current_and_legacy_names() -> None:
    assert is_webview_native_library_entry("lib/x86_64/libmonochrome_64.so")
    assert is_webview_native_library_entry("lib/x86_64/libmonochrome.so")
    assert not is_webview_native_library_entry("lib/x86_64/libother.so")


def test_patch_linux_armv8l_platform_string_in_apk_accepts_libmonochrome_without_64(tmp_path):
    apk = tmp_path / "base.apk"
    with zipfile.ZipFile(apk, "w") as zf:
        zf.writestr("lib/x86_64/libmonochrome.so", b"prefix Linux armv81 suffix")

    assert patch_linux_armv8l_platform_string_in_apk(apk) is True

    with zipfile.ZipFile(apk, "r") as zf:
        data = zf.read("lib/x86_64/libmonochrome.so")
    assert b"Linux armv8l" in data
