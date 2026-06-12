"""Unit tests for RedroidManager image management.

The subprocess boundary (_run_cmd) is stubbed so these run without Docker.
Behaviour under test: which docker commands ensure_image / _image_exists
issue, and when. _is_windows is forced False so _docker_cmd is
deterministic regardless of the host running the tests.
"""
import asyncio
from unittest.mock import AsyncMock

import pytest

from damru.async_core import DamruError
from damru.config import REDROID_BASE_IMAGE, REDROID_IMAGE
from damru.docker import RedroidManager


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
