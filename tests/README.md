# Test Suite

Damru tests are split into fast unit tests and live environment probes.

## Fast Tests

Default pytest runs the unit-safe suite and skips Docker, ADB, Redroid, GPU, network, and live website probes.

```bash
python -m pytest -q
```

## Live Probes

Run these only on a prepared Ubuntu/WSL Redroid host:

```bash
python -m pytest --run-damru-probes -q
```

Useful focused checks:

```bash
python -m pytest tests/test_images_unit.py tests/test_root_webrtc.py -q
python -m damru check-env --viewer
python -m damru fix-wsl
```

Manual probe scripts can still be run directly with `python tests/<script>.py` when you intentionally want a live browser/device check.

## Privacy

Never commit proxy credentials, local usernames, IP addresses, private screenshots, or account data in test fixtures or proof outputs.
