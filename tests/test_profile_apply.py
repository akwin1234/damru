import argparse

import pytest

from damru import profile_apply
from damru import cli


class FakeADB:
    calls: list[tuple] = []

    def __init__(self, serial: str):
        self.serial = serial
        self.calls.append(("adb.init", serial))

    async def shell(self, command: str, *args, **kwargs) -> str:
        self.calls.append(("adb.shell", command, kwargs))
        if command == "settings get global http_proxy":
            return "null"
        return ""


class FakeRootOps:
    calls: list[tuple] = []

    def __init__(self, adb: FakeADB):
        self.adb = adb
        self.calls.append(("root.init", adb.serial))

    async def check_root(self) -> bool:
        self.calls.append(("root.check",))
        return True

    async def apply_device_props(self, device, safe_only: bool = True, parallel: bool = False) -> None:
        self.calls.append(("root.props", device.name, safe_only, parallel))

    async def apply_version_release(self, device) -> None:
        self.calls.append(("root.version", device.android_version))

    async def apply_timezone(self, timezone: str) -> None:
        self.calls.append(("root.timezone", timezone))

    async def apply_locale(self, locale: str) -> None:
        self.calls.append(("root.locale", locale))

    async def apply_cpu_cores_spoof(self, target_cores: int) -> None:
        self.calls.append(("root.cpu", target_cores))

    async def apply_gpu_binary_spoof(self, device) -> None:
        self.calls.append(("root.gpu", device.name, device.webgl_renderer))

    async def apply_memory_spoof(self, target_gb: float) -> None:
        self.calls.append(("root.memory", target_gb))

    async def setup_memory_preload(self, chrome_package: str) -> None:
        self.calls.append(("root.memory_preload", chrome_package))

    async def apply_webrtc_block(self, chrome_package: str) -> None:
        self.calls.append(("root.webrtc", chrome_package))


class FakeChromeManager:
    calls: list[tuple] = []

    def __init__(self, adb: FakeADB, package: str | None = None):
        self.adb = adb
        self.package = package or "com.android.chrome"
        self.calls.append(("chrome.init", adb.serial, self.package))

    async def detect_package(self, retries: int = 30, delay: float = 2.0) -> str:
        self.calls.append(("chrome.detect", retries, delay))
        return self.package

    async def force_stop(self) -> None:
        self.calls.append(("chrome.force_stop",))

    async def clear_all_data(self) -> None:
        self.calls.append(("chrome.clear",))

    async def get_version(self) -> str:
        self.calls.append(("chrome.version",))
        return "148.0.7778.217"

    async def write_command_line(self, flags: list[str]) -> None:
        self.calls.append(("chrome.flags", tuple(flags)))

    async def patch_preferences(self, locale: str, accept_lang: str) -> None:
        self.calls.append(("chrome.prefs", locale, accept_lang))


@pytest.fixture(autouse=True)
def _reset_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeADB.calls = []
    FakeRootOps.calls = []
    FakeChromeManager.calls = []
    monkeypatch.setattr(profile_apply, "ADB", FakeADB)
    monkeypatch.setattr(profile_apply, "RootOps", FakeRootOps)
    monkeypatch.setattr(profile_apply, "ChromeManager", FakeChromeManager)


@pytest.mark.unit
async def test_force_device_profile_applies_named_profile() -> None:
    result = await profile_apply.force_device_profile(
        "127.0.0.1:5600",
        "xiaomi_redmi_9a",
        timezone="America/Sao_Paulo",
        locale="pt-BR",
    )

    assert result.device_name == "Xiaomi Redmi 9A"
    assert result.model == "M2006C3LG"
    assert result.screen_width == 720
    assert result.screen_height == 1600
    assert result.density_dpi == 320
    assert result.timezone == "America/Sao_Paulo"
    assert result.locale == "pt-BR"
    assert result.chrome_package == "com.android.chrome"
    assert result.chrome_version == "148.0.7778.217"

    assert ("root.props", "Xiaomi Redmi 9A", True, True) in FakeRootOps.calls
    assert ("root.version", "11") in FakeRootOps.calls
    assert ("root.cpu", 8) in FakeRootOps.calls
    assert any(call[:2] == ("root.gpu", "Xiaomi Redmi 9A") for call in FakeRootOps.calls)
    assert ("root.memory", 2) in FakeRootOps.calls
    assert ("root.memory_preload", "com.android.chrome") in FakeRootOps.calls
    assert any(call[0] == "chrome.flags" for call in FakeChromeManager.calls)
    assert ("chrome.prefs", "pt-BR", "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7") in FakeChromeManager.calls
    shell_commands = [call[1] for call in FakeADB.calls if call[0] == "adb.shell"]
    assert "wm size 720x1600" in shell_commands
    assert "wm density 320" in shell_commands


@pytest.mark.unit
async def test_force_device_profile_can_skip_chrome_and_cpu() -> None:
    result = await profile_apply.force_device_profile(
        "127.0.0.1:5600",
        "motorola_moto_g_5s_plus",
        timezone="America/Sao_Paulo",
        locale="pt-BR",
        configure_chrome=False,
        apply_cpu=False,
        clear_proxy=True,
    )

    assert result.device_name == "Motorola Moto G (5S) Plus"
    assert result.model == "Moto G (5S) Plus"
    assert result.chrome_package is None
    assert result.chrome_version is None
    assert result.chrome_note == "chrome=skipped"
    assert not FakeChromeManager.calls
    assert not any(call[0] == "root.cpu" for call in FakeRootOps.calls)
    assert any(call[0] == "root.gpu" for call in FakeRootOps.calls)
    assert not any(call[0] == "root.memory" for call in FakeRootOps.calls)
    shell_commands = [call[1] for call in FakeADB.calls if call[0] == "adb.shell"]
    assert "settings put global http_proxy :0" in shell_commands
    assert "settings delete global global_http_proxy_host" in shell_commands
    assert "settings delete global global_http_proxy_port" in shell_commands
    assert "wm size 1080x1920" in shell_commands
    assert "wm density 480" in shell_commands


@pytest.mark.unit
async def test_force_device_profile_can_harden_webview_shell() -> None:
    result = await profile_apply.force_device_profile(
        "127.0.0.1:5600",
        "xiaomi_redmi_9a",
        timezone="America/Sao_Paulo",
        locale="pt-BR",
        browser_package="org.chromium.webview_shell",
        clear_chrome=False,
    )

    assert result.chrome_package == "org.chromium.webview_shell"
    assert result.chrome_note == "org.chromium.webview_shell=148.0.7778.217"
    assert ("chrome.init", "127.0.0.1:5600", "org.chromium.webview_shell") in FakeChromeManager.calls
    assert ("chrome.prefs", "pt-BR", "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7") in FakeChromeManager.calls
    assert ("root.memory_preload", "org.chromium.webview_shell") in FakeRootOps.calls


@pytest.mark.unit
def test_force_profile_cli_wires_named_profile(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    called = {}

    async def fake_force_device_profile(serial: str, device_name: str, **kwargs):
        called.update({"serial": serial, "device_name": device_name, **kwargs})
        return profile_apply.AppliedDeviceProfile(
            serial=serial,
            description="Xiaomi Redmi 9A (Redmi M2006C3LG, Android 11)",
            device_name="Xiaomi Redmi 9A",
            model="M2006C3LG",
            screen_width=720,
            screen_height=1600,
            density_dpi=320,
            timezone="America/Sao_Paulo",
            locale="pt-BR",
            chrome_note="chrome=skipped",
        )

    monkeypatch.setattr(cli, "_resolve_serial", lambda value: "127.0.0.1:5600")
    monkeypatch.setattr(cli, "_repair_runtime_internet", lambda serial, quiet: True)
    monkeypatch.setattr(profile_apply, "force_device_profile", fake_force_device_profile)

    code = cli._force_profile(
        argparse.Namespace(
            serial=None,
            device="xiaomi_redmi_9a",
            proxy=None,
            http_proxy=None,
            timezone="America/Sao_Paulo",
            locale="pt-BR",
            no_chrome=True,
            no_clear_chrome=False,
            rotate_chrome=False,
            no_cpu=True,
            no_gpu=False,
            no_memory=False,
            clear_proxy=True,
        )
    )

    assert code == 0
    assert called["serial"] == "127.0.0.1:5600"
    assert called["device_name"] == "xiaomi_redmi_9a"
    assert called["configure_chrome"] is False
    assert called["apply_cpu"] is False
    assert called["apply_gpu"] is True
    assert called["apply_memory"] is True
    assert called["clear_proxy"] is True
    assert "Forced profile applied on 127.0.0.1:5600" in capsys.readouterr().out
