from pathlib import Path

from damru.apk_assets import find_apk_bundle_root, find_bundle_apk, validate_apk_bundle
from damru.docker import RedroidManager


def _make_bundle(root: Path) -> Path:
    bundle = root / "chrome-apks"
    version = bundle / "145.0.7632.75"
    version.mkdir(parents=True)
    (version / "base.apk").write_bytes(b"apk")
    (version / "split_chrome.apk").write_bytes(b"apk")
    (version / "google_trichrome_library.apk").write_bytes(b"apk")
    (bundle / "TrichromeWebView.apk").write_bytes(b"apk")
    (bundle / "google_tts.apk").write_bytes(b"apk")
    (bundle / "espeak.apk").write_bytes(b"apk")
    (bundle / "rhvoice.apk").write_bytes(b"apk")
    (bundle / "magisk.apk").write_bytes(b"apk")
    return bundle


def test_bundle_root_derived_from_chrome_version_dir(tmp_path):
    bundle = _make_bundle(tmp_path)
    chrome_dir = bundle / "145.0.7632.75"

    assert find_apk_bundle_root(str(chrome_dir)) == bundle.resolve()
    assert find_bundle_apk("TrichromeWebView.apk", str(chrome_dir)) == (bundle / "TrichromeWebView.apk").resolve()
    assert find_bundle_apk("google_tts.apk", str(chrome_dir)) == (bundle / "google_tts.apk").resolve()
    assert find_bundle_apk("espeak.apk", str(chrome_dir)) == (bundle / "espeak.apk").resolve()
    assert find_bundle_apk("rhvoice.apk", str(chrome_dir)) == (bundle / "rhvoice.apk").resolve()
    assert find_bundle_apk("magisk.apk", str(chrome_dir)) == (bundle / "magisk.apk").resolve()
    assert validate_apk_bundle(bundle) == (True, str(bundle.resolve()))


def test_redroid_manager_finds_chrome_from_cwd_bundle(tmp_path, monkeypatch):
    bundle = _make_bundle(tmp_path)
    monkeypatch.chdir(tmp_path)

    found = RedroidManager().find_chrome_apk(version="145.0.7632.75")

    assert Path(found) == (bundle / "145.0.7632.75").resolve()


def test_bundle_validation_requires_webview_and_tts(tmp_path):
    bundle = tmp_path / "chrome-apks"
    version = bundle / "145.0.7632.75"
    version.mkdir(parents=True)
    (version / "base.apk").write_bytes(b"apk")

    ok, detail = validate_apk_bundle(bundle)

    assert not ok
    assert "TrichromeWebView.apk" in detail
    assert "google_tts.apk" in detail
    assert "espeak.apk" in detail
    assert "rhvoice.apk" in detail
    assert "magisk.apk" in detail
