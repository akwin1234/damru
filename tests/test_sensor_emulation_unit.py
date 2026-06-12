import asyncio
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from damru.async_core import AsyncDamru

ROOT = Path(__file__).resolve().parents[1]


def test_sensor_sample_uses_cdp_expected_shapes():
    damru = AsyncDamru.__new__(AsyncDamru)
    damru._sensor_seed = 0.25

    orientation, readings = damru._sensor_sample(1.0)

    assert set(orientation) == {"alpha", "beta", "gamma"}
    assert 0 <= orientation["alpha"] < 360
    assert -90 <= orientation["beta"] <= 90
    assert -90 <= orientation["gamma"] <= 90

    for sensor_type in ("accelerometer", "linear-acceleration", "gravity", "gyroscope", "magnetometer"):
        assert set(readings[sensor_type]) == {"xyz"}
        assert set(readings[sensor_type]["xyz"]) == {"x", "y", "z"}

    for sensor_type in ("absolute-orientation", "relative-orientation"):
        assert set(readings[sensor_type]) == {"quaternion"}
        quat = readings[sensor_type]["quaternion"]
        assert set(quat) == {"x", "y", "z", "w"}
        norm = math.sqrt(sum(v * v for v in quat.values()))
        assert norm == pytest.approx(1.0, abs=0.000001)

    gravity_z = readings["gravity"]["xyz"]["z"]
    assert 7.9 <= gravity_z <= 9.82
    assert abs(readings["linear-acceleration"]["xyz"]["x"]) < 0.08
    assert abs(readings["gyroscope"]["xyz"]["x"]) < 0.05

def test_sensor_motion_is_session_unique_and_smooth():
    a = AsyncDamru.__new__(AsyncDamru)
    b = AsyncDamru.__new__(AsyncDamru)
    a._sensor_seed = 0.25
    b._sensor_seed = 0.25
    a._sensor_motion = a._new_sensor_motion()
    b._sensor_motion = b._new_sensor_motion()

    a0, _ = a._sensor_sample(1.0)
    a1, _ = a._sensor_sample(1.77)
    b0, _ = b._sensor_sample(1.0)

    assert a0 != b0
    assert abs(a1["beta"] - a0["beta"]) < 3.0
    assert abs(a1["gamma"] - a0["gamma"]) < 3.0


async def test_apply_sensor_emulation_sends_orientation_and_readings():
    calls = []

    class FakeSession:
        async def send(self, method, params=None):
            calls.append((method, params or {}))

    class FakePage:
        def __init__(self):
            self._closed = False

        def is_closed(self):
            return self._closed

    class FakeContext:
        def __init__(self):
            self.pages = [FakePage()]
            self.handlers = []

        async def new_cdp_session(self, page):
            return FakeSession()

        def on(self, event, handler):
            self.handlers.append((event, handler))

    damru = AsyncDamru.__new__(AsyncDamru)
    damru._context = FakeContext()
    damru._sensor_tasks = []
    damru._sensor_seed = 0.0

    await damru._apply_sensor_emulation()
    await asyncio.sleep(0.05)

    for task in damru._sensor_tasks:
        task.cancel()
    await asyncio.gather(*damru._sensor_tasks, return_exceptions=True)

    methods = [method for method, _ in calls]
    assert "DeviceOrientation.setDeviceOrientationOverride" in methods
    assert methods.count("Emulation.setSensorOverrideEnabled") >= 6
    assert methods.count("Emulation.setSensorOverrideReadings") >= 6
    assert any(
        method == "Emulation.setSensorOverrideReadings"
        and params["type"] == "accelerometer"
        and set(params["reading"]) == {"xyz"}
        for method, params in calls
    )
    assert any(
        method == "Emulation.setSensorOverrideReadings"
        and params["type"] == "absolute-orientation"
        and set(params["reading"]) == {"quaternion"}
        for method, params in calls
    )

def test_native_sensor_hal_manifest_is_valid_aidl_vintf():
    path = ROOT / "native" / "sensors" / "manifest" / "damru-sensors.xml"
    tree = ET.parse(path)
    hal = tree.getroot().find("hal")

    assert hal is not None
    assert hal.attrib["format"] == "aidl"
    assert hal.findtext("name") == "android.hardware.sensors"
    assert hal.findtext("version") == "2"
    assert hal.findtext("fqname") == "ISensors/default"

def test_native_sensor_hal_uses_profile_seed_and_no_js_patch():
    source = (ROOT / "native" / "damru_sensors_service.cpp").read_text(encoding="utf-8")
    assert "persist.damru.sensor.seed" in source
    assert "AServiceManager_addService" in source
    assert "AidlMessageQueue" in source
    assert "Object.defineProperty" not in source
