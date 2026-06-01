"""Integration test for _image_exists against a real local Docker.

Skipped unless a working `docker` CLI + daemon are present. Pulls a tiny
public image (hello-world) and asserts _image_exists flips False -> True.
Does not touch any redroid image or container.

Run on a box with Docker (e.g. native Linux, or macOS/Windows with Docker
Desktop):

    python -m pytest tests/test_images_integration.py
"""
import shutil
import subprocess

import pytest

from damru.docker import RedroidManager

TINY_IMAGE = "hello-world:latest"


def _docker_ok() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        r = subprocess.run(
            ["docker", "info", "--format", "{{.OSType}}"],
            capture_output=True, timeout=15,
        )
        return r.returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_ok(), reason="docker CLI + daemon not available"
)


def _manager():
    mgr = RedroidManager()
    mgr._is_windows = False  # talk to host docker directly
    return mgr


async def test_image_exists_flips_after_pull():
    mgr = _manager()
    # Clean slate so the False assertion is meaningful.
    await mgr._run_cmd(
        ["docker", "rmi", "-f", TINY_IMAGE], timeout=30, allow_failure=True
    )
    assert await mgr._image_exists(TINY_IMAGE) is False

    await mgr._run_cmd(["docker", "pull", TINY_IMAGE], timeout=120)
    assert await mgr._image_exists(TINY_IMAGE) is True
