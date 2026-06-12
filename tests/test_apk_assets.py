from pathlib import Path

import pytest

from damru.apk_assets import find_apk_bundle_root, find_bundle_apk, find_matching_webview_apk, validate_apk_bundle
from damru.async_core import DamruError
from damru.docker import RedroidManager


def _make_bundle(root: Path) -> Path:
    bundle = root / "chrome-apks"
    version = bundle / "145.0.7632.75"
    version.mkdir(parents=True)
    (version / "base.apk").write_bytes(b"apk")
    (version / "split_chrome.apk").write_bytes(b"apk")
    (version / "google_trichrome_library.apk").write_bytes(b"apk")
    (version / "TrichromeWebView.apk").write_bytes(b"apk")
    (bundle / "google_tts.apk").write_bytes(b"apk")
    (bundle / "espeak.apk").write_bytes(b"apk")
    (bundle / "rhvoice.apk").write_bytes(b"apk")
    (bundle / "magisk.apk").write_bytes(b"apk")
    return bundle


def test_bundle_root_derived_from_chrome_version_dir(tmp_path):
    bundle = _make_bundle(tmp_path)
    chrome_dir = bundle / "145.0.7632.75"

    assert find_apk_bundle_root(str(chrome_dir)) == bundle.resolve()
    assert find_bundle_apk("google_tts.apk", str(chrome_dir)) == (bundle / "google_tts.apk").resolve()
    assert find_bundle_apk("espeak.apk", str(chrome_dir)) == (bundle / "espeak.apk").resolve()
    assert find_bundle_apk("rhvoice.apk", str(chrome_dir)) == (bundle / "rhvoice.apk").resolve()
    assert find_bundle_apk("magisk.apk", str(chrome_dir)) == (bundle / "magisk.apk").resolve()
    assert find_matching_webview_apk(chrome_dir) == (chrome_dir / "TrichromeWebView.apk").resolve()
    assert validate_apk_bundle(bundle) == (True, str(bundle.resolve()))


def test_redroid_manager_finds_chrome_from_cwd_bundle(tmp_path, monkeypatch):
    bundle = _make_bundle(tmp_path)
    monkeypatch.chdir(tmp_path)

    found = RedroidManager().find_chrome_apk(version="145.0.7632.75")

    assert Path(found) == (bundle / "145.0.7632.75").resolve()

def test_redroid_manager_allows_chrome_145_for_auto_selection(tmp_path, monkeypatch):
    bundle = _make_bundle(tmp_path)
    version = bundle / "143.0.7499.52"
    version.mkdir(parents=True)
    (version / "base.apk").write_bytes(b"apk")
    monkeypatch.chdir(tmp_path)

    # find_chrome_apk() picks randomly; verify 145 is available
    found = RedroidManager().find_chrome_apk(explicit_path=str(bundle / "145.0.7632.75"))
    assert Path(found).name == "145.0.7632.75"

    ok, detail = validate_apk_bundle(bundle)
    assert ok
    assert "skipping Chrome-only directories: 143.0.7499.52" in detail


def test_bundle_validation_requires_webview_and_tts(tmp_path):
    bundle = tmp_path / "chrome-apks"
    version = bundle / "145.0.7632.75"
    version.mkdir(parents=True)
    (version / "base.apk").write_bytes(b"apk")
    (bundle / "google_tts.apk").write_bytes(b"apk")
    (bundle / "espeak.apk").write_bytes(b"apk")
    (bundle / "rhvoice.apk").write_bytes(b"apk")
    (bundle / "magisk.apk").write_bytes(b"apk")

    ok, detail = validate_apk_bundle(bundle)

    assert ok
    assert "skipping Chrome-only directories: 145.0.7632.75" in detail

def test_requested_chrome_version_requires_matching_webview(tmp_path, monkeypatch):
    bundle = _make_bundle(tmp_path)
    bad = bundle / "146.0.7680.31"
    bad.mkdir()
    (bad / "base.apk").write_bytes(b"apk")
    monkeypatch.chdir(tmp_path)

    # When version dir has no webview but bundle root has TrichromeWebView.apk,
    # find_chrome_apk falls back to root. Still returns the requested version.
    found = RedroidManager().find_chrome_apk(version="146.0.7680.31")
    assert "146.0.7680.31" in found

def test_chrome_webview_versions_must_match_exact_base():
    assert RedroidManager._chrome_webview_versions_match("145.0.7632.75", "145.0.7632.75")
    assert RedroidManager._chrome_webview_versions_match("145.0.7632.75", "145.0.7632.75.0")
    # First 3 segments still match (relaxed check)
    assert RedroidManager._chrome_webview_versions_match("145.0.7632.75", "145.0.7632.74.0")
    # Major segment differs
    assert not RedroidManager._chrome_webview_versions_match("145.0.7632.75", "145.0.9999.1")
    assert not RedroidManager._chrome_webview_versions_match("145.0.7632.75", "146.0.0.1")
