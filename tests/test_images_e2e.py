"""End-to-end test for ensure_image's auto-pull/tag fallback.

Performs a REAL base-image pull and tag against the host's Docker — no
mocks. It is heavy (downloads the redroid base image) and targets the
redroid host (WSL2 on Windows / native Linux), so it is opt-in and skipped
unless DAMRU_E2E=1:

    DAMRU_E2E=1 python -m pytest tests/test_images_e2e.py

On Windows the RedroidManager routes docker through the configured WSL2
distro automatically, so this exercises the true first-run code path.
"""
import os

import pytest

from damru.config import REDROID_BASE_IMAGE, REDROID_IMAGE
from damru.docker import RedroidManager

pytestmark = pytest.mark.skipif(
    os.environ.get("DAMRU_E2E") != "1",
    reason="opt-in: set DAMRU_E2E=1 to run (heavy: pulls the redroid base image)",
)


async def test_ensure_image_pulls_and_tags_baked_from_base():
    mgr = RedroidManager()

    # Remove the baked tag so ensure_image must fall back to base + tag.
    await mgr._run_cmd(
        mgr._docker_cmd("rmi", "-f", REDROID_IMAGE),
        timeout=60, allow_failure=True,
    )
    assert await mgr._image_exists(REDROID_IMAGE) is False

    await mgr.ensure_image(REDROID_IMAGE)

    # Both the pulled base and the tagged launch image should now exist.
    assert await mgr._image_exists(REDROID_BASE_IMAGE) is True
    assert await mgr._image_exists(REDROID_IMAGE) is True
