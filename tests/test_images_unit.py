"""Unit tests for RedroidManager image management.

The subprocess boundary (_run_cmd) is stubbed so these run without Docker.
Behaviour under test: which docker commands ensure_image / _image_exists
issue, and when. _is_windows is forced False so _docker_cmd is
deterministic regardless of the host running the tests.
"""
import asyncio
import base64
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from damru.async_core import DamruError
from damru.config import REDROID_BASE_IMAGE, REDROID_IMAGE
from damru.docker import RedroidManager, _REDROID_STREAM_BOOT_ARG


def _manager(side_effect):
    mgr = RedroidManager()
    mgr._is_windows = False
    mgr._run_cmd = AsyncMock(side_effect=side_effect)
    return mgr


async def test_image_exists_true_when_images_q_returns_id():
    mgr = _manager(lambda cmd, **kw: "abc123\n")
    assert await mgr._image_exists("x:1") is True


async def test_image_exists_false_when_images_q_empty():
    mgr = _manager(lambda cmd, **kw: "")
    assert await mgr._image_exists("x:1") is False


async def test_ensure_image_noop_when_present():
    calls = []

    def fake(cmd, **kw):
        calls.append(cmd)
        return "abc123"  # images -q -> present

    mgr = _manager(fake)
    await mgr.ensure_image(REDROID_IMAGE)
    assert calls == [["docker", "images", "-q", REDROID_IMAGE]]


async def test_ensure_image_baked_missing_pulls_base_and_tags():
    calls = []

    def fake(cmd, **kw):
        calls.append(cmd)
        return ""  # images -q empty (missing); pull/tag succeed

    mgr = _manager(fake)
    await mgr.ensure_image(REDROID_IMAGE)
    assert ["docker", "pull", REDROID_BASE_IMAGE] in calls
    assert ["docker", "tag", REDROID_BASE_IMAGE, REDROID_IMAGE] in calls


async def test_ensure_image_other_missing_pulls_without_tag():
    calls = []

    def fake(cmd, **kw):
        calls.append(cmd)
        return ""  # missing, pull succeeds

    mgr = _manager(fake)
    await mgr.ensure_image("alpine:latest")
    assert ["docker", "pull", "alpine:latest"] in calls
    assert not any(c[1] == "tag" for c in calls)


async def test_ensure_image_other_missing_pull_failure_raises():
    def fake(cmd, **kw):
        if cmd[1] == "images":
            return ""  # missing
        if cmd[1] == "pull":
            raise DamruError("network down")
        return ""

    mgr = _manager(fake)
    with pytest.raises(DamruError):
        await mgr.ensure_image("alpine:latest")


def test_target_chrome_version_from_split_apk_dir(tmp_path):
    bundle = tmp_path / "148.0.7778.217"
    bundle.mkdir()
    (bundle / "base.apk").write_text("")

    assert RedroidManager()._target_chrome_version_from_apk_path(str(bundle)) == "148.0.7778.217"


def test_target_chrome_version_is_none_for_single_apk(tmp_path):
    apk = tmp_path / "chrome.apk"
    apk.write_text("")

    assert RedroidManager()._target_chrome_version_from_apk_path(str(apk)) is None


async def test_run_cmd_kills_timed_out_process(monkeypatch):
    class HangingProcess:
        returncode = None
        killed = False
        communicate_calls = 0

        async def communicate(self):
            self.communicate_calls += 1
            if not self.killed:
                await asyncio.sleep(60)
            self.returncode = -9
            return b"", b""

        def kill(self):
            self.killed = True
            self.returncode = -9

    process = HangingProcess()

    async def fake_create_subprocess_exec(*args, **kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    mgr = RedroidManager()
    mgr._is_windows = False

    with pytest.raises(DamruError, match="Command timed out"):
        await mgr._run_cmd(["docker", "ps"], timeout=0.01)

    assert process.killed is True
    assert process.communicate_calls == 2


async def test_start_container_enables_redroid_stream_uinput(monkeypatch):
    calls = []

    async def fake_run_cmd(cmd, **kw):
        calls.append(cmd)
        return ""

    mgr = RedroidManager()
    mgr._is_windows = False
    mgr._run_cmd = AsyncMock(side_effect=fake_run_cmd)
    mgr.ensure_image = AsyncMock()
    mgr._ensure_binderfs = AsyncMock()
    mgr._materialize_input_event_nodes_early = AsyncMock()
    mgr._seed_adb_authorized_keys_early = AsyncMock()
    mgr._wait_for_container_boot_internal = AsyncMock()
    mgr._wait_for_boot = AsyncMock()
    mgr._repair_docker_bridge_nat = AsyncMock()
    mgr._wait_for_package_service = AsyncMock()
    mgr._wait_for_touchscreen_input = AsyncMock()
    mgr._wait_for_android_dns_usable = AsyncMock(return_value=True)
    mgr._ensure_sensor_hal = AsyncMock(return_value=False)
    mgr._serial_for_container = AsyncMock(return_value="127.0.0.1:5600")

    assert await mgr.start_container(0) == "127.0.0.1:5600"

    docker_run = next(call for call in calls if call[:2] == ["docker", "run"])
    assert _REDROID_STREAM_BOOT_ARG in docker_run
    mgr._materialize_input_event_nodes_early.assert_awaited_once_with("damru-worker-0")
    mgr._wait_for_container_boot_internal.assert_awaited_once()
    mgr._seed_adb_authorized_keys_early.assert_awaited_once_with("damru-worker-0")
    mgr._wait_for_touchscreen_input.assert_awaited_once_with("127.0.0.1:5600")


async def test_materialize_input_event_nodes_early_creates_system_readable_nodes():
    calls = []

    async def fake_run_cmd(cmd, **kw):
        calls.append((cmd, kw))
        return ""

    mgr = RedroidManager()
    mgr._is_windows = False
    mgr._run_cmd = AsyncMock(side_effect=fake_run_cmd)

    await mgr._materialize_input_event_nodes_early("damru-worker-0", timeout=7)

    cmd, kwargs = calls[0]
    joined = " ".join(cmd)
    assert cmd[:3] == ["docker", "exec", "damru-worker-0"]
    assert "mkdir -p /dev/input" in joined
    assert "mknod" in joined
    assert "chown 0:1000" in joined
    assert "chmod 0660" in joined
    assert kwargs["timeout"] == 17
    assert kwargs["allow_failure"] is True


def test_host_adb_public_keys_reads_vendor_and_home(monkeypatch, tmp_path):
    vendor_key = tmp_path / "vendor_adbkey"
    vendor_pub = tmp_path / "vendor_adbkey.pub"
    vendor_pub.write_text("vendor-key host\nshared-key\n", encoding="utf-8")
    home = tmp_path / "home"
    home_pub = home / ".android" / "adbkey.pub"
    home_pub.parent.mkdir(parents=True)
    home_pub.write_text("shared-key\nhome-key\n", encoding="utf-8")

    monkeypatch.setenv("ADB_VENDOR_KEYS", str(vendor_key))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    assert RedroidManager._host_adb_public_keys() == [
        "vendor-key host",
        "shared-key",
        "home-key",
    ]


async def test_seed_adb_authorized_keys_early_writes_adb_keys(monkeypatch):
    calls = []

    async def fake_run_cmd(cmd, **kw):
        calls.append((cmd, kw))
        return ""

    mgr = RedroidManager()
    mgr._is_windows = False
    mgr._run_cmd = AsyncMock(side_effect=fake_run_cmd)
    monkeypatch.setattr(
        RedroidManager,
        "_host_adb_public_keys",
        classmethod(lambda cls: ["adb-public-key host"]),
    )

    await mgr._seed_adb_authorized_keys_early("damru-worker-0", timeout=8)

    cmd, kwargs = calls[0]
    joined = " ".join(cmd)
    payload = base64.b64encode(b"adb-public-key host\n").decode("ascii")
    assert cmd[:3] == ["docker", "exec", "damru-worker-0"]
    assert payload in joined
    assert "/data/misc/adb/adb_keys" in joined
    assert "setprop ctl.restart adbd" in joined
    assert kwargs["timeout"] == 8
    assert kwargs["allow_failure"] is True
