import pytest

from damru.adb import ADB, ADBError


def _device(serial: str, status: str = "device") -> dict[str, str]:
    return {
        "serial": serial,
        "status": status,
        "model": "",
        "device": "",
    }


def _stub_devices(monkeypatch: pytest.MonkeyPatch, devices: list[dict[str, str]]) -> None:
    async def fake_list_devices(self: ADB) -> list[dict[str, str]]:
        return devices

    monkeypatch.setattr(ADB, "list_devices", fake_list_devices)


@pytest.mark.asyncio
async def test_detect_device_prefers_tcp_virtual_serial(monkeypatch):
    monkeypatch.delenv("DAMRU_ALLOW_PHYSICAL", raising=False)
    _stub_devices(
        monkeypatch,
        [
            _device("USB123"),
            _device("127.0.0.1:5600"),
            _device("emulator-5554"),
        ],
    )

    assert await ADB().detect_device() == "127.0.0.1:5600"


@pytest.mark.asyncio
async def test_detect_device_uses_emulator_when_no_tcp_serial(monkeypatch):
    monkeypatch.delenv("DAMRU_ALLOW_PHYSICAL", raising=False)
    _stub_devices(
        monkeypatch,
        [
            _device("USB123"),
            _device("emulator-5554"),
        ],
    )

    assert await ADB().detect_device() == "emulator-5554"


@pytest.mark.asyncio
async def test_detect_device_refuses_physical_serial_by_default(monkeypatch):
    monkeypatch.delenv("DAMRU_ALLOW_PHYSICAL", raising=False)
    _stub_devices(monkeypatch, [_device("USB123")])

    with pytest.raises(ADBError, match="Refusing to auto-select a physical USB ADB device"):
        await ADB().detect_device()


@pytest.mark.asyncio
async def test_detect_device_allows_physical_serial_with_explicit_env(monkeypatch):
    monkeypatch.setenv("DAMRU_ALLOW_PHYSICAL", "1")
    _stub_devices(monkeypatch, [_device("USB123")])

    assert await ADB().detect_device() == "USB123"
