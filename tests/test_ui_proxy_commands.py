import subprocess
import types

import damru.cli as cli
from damru.proxy_runtime import android_proxy_host_from_route, proxy_bridge_upstream
from damru.ui.server import build_command


def _cp(code=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(["test"], code, stdout, stderr)


def test_ui_navigate_passes_proxy_to_cli():
    _, cmd, _, _ = build_command(
        "navigate",
        {
            "serial": "127.0.0.1:5600",
            "url": "https://browserleaks.com/ip",
            "proxy": "http://user:pass@proxy.example:10000",
        },
    )

    assert "stealth-open-url" in cmd
    assert "--proxy" in cmd
    assert cmd[cmd.index("--proxy") + 1] == "http://user:pass@proxy.example:10000"


def test_ui_random_profile_passes_proxy_to_cli():
    _, cmd, _, _ = build_command(
        "random-profile",
        {"serial": "127.0.0.1:5600", "proxy": "http://user:pass@proxy.example:10000"},
    )

    assert "random-profile" in cmd
    assert "--proxy" in cmd
    assert cmd[cmd.index("--proxy") + 1] == "http://user:pass@proxy.example:10000"


def test_com_br_url_hints_pt_br_locale():
    assert cli._locale_hint_for_url("https://www.example.com.br/") == "pt-BR"
    assert cli._locale_hint_for_url("https://www.example.com/") is None

def test_stealth_open_url_reuses_profile_by_default():
    parser = cli.build_parser()

    args = parser.parse_args(["stealth-open-url", "--url", "https://example.com"])
    assert args.cold_start is False
    assert args.timezone is None
    assert args.mode == "playwright"

    args = parser.parse_args(["stealth-open-url", "--url", "https://example.com", "--cold-start"])
    assert args.cold_start is True

    args = parser.parse_args([
        "stealth-open-url",
        "--url",
        "https://example.com",
        "--timezone",
        "Asia/Tokyo",
        "--device",
        "Samsung Galaxy S24",
        "--profile-tier",
        "all",
    ])
    assert args.timezone == "Asia/Tokyo"
    assert args.device == "Samsung Galaxy S24"
    assert args.profile_tier == "all"

    args = parser.parse_args([
        "stealth-open-url",
        "--url",
        "https://example.com",
        "--cold-start",
        "--reuse-profile",
    ])
    assert args.cold_start is False


def test_apply_android_proxy_writes_no_auth_host_port(monkeypatch):
    calls = []

    def fake_adb(serial, *args, timeout=30):
        calls.append((serial, args))
        return _cp(0)

    monkeypatch.setattr(cli, "_run_adb_text", fake_adb)

    applied = cli._apply_android_proxy("127.0.0.1:5600", proxy="http://proxy.example:10000")

    assert applied == "proxy.example:10000"
    assert ("127.0.0.1:5600", ("shell", "settings", "put", "global", "http_proxy", "proxy.example:10000")) in calls
    assert ("127.0.0.1:5600", ("shell", "settings", "put", "global", "global_http_proxy_host", "proxy.example")) in calls
    assert ("127.0.0.1:5600", ("shell", "settings", "put", "global", "global_http_proxy_port", "10000")) in calls


def test_apply_android_proxy_bridges_authenticated_proxy(monkeypatch):
    calls = []

    def fake_adb(serial, *args, timeout=30):
        calls.append((serial, args))
        return _cp(0)

    monkeypatch.setattr(cli, "_run_adb_text", fake_adb)
    monkeypatch.setattr(cli, "_ensure_proxy_bridge", lambda serial, upstream: "172.17.0.1:19000")

    applied = cli._apply_android_proxy("127.0.0.1:5600", proxy="http://user:pass@proxy.example:10000")

    assert applied == "172.17.0.1:19000"
    assert ("127.0.0.1:5600", ("shell", "settings", "put", "global", "http_proxy", "172.17.0.1:19000")) in calls


def test_socks_proxy_uses_bridge_without_port_guessing():
    upstream = proxy_bridge_upstream("socks5://user:pass@proxy.example:824")

    assert upstream == "socks5://user:pass@proxy.example:824"


def test_proxy_runtime_derives_docker_gateway_from_android_route():
    assert android_proxy_host_from_route("172.17.0.0/16 dev eth0 proto kernel scope link src 172.17.0.2") == "172.17.0.1"


def test_stealth_open_url_keeps_session_alive_through_native_open(monkeypatch):
    events = []

    class FakePage:
        url = "about:blank"

        async def goto(self, url, wait_until=None, timeout=None):
            events.append(("goto", url))
            self.url = url

        async def title(self):
            return "Damru"

    class FakeContext:
        def __init__(self):
            self.pages = [FakePage()]

        async def new_page(self):
            page = FakePage()
            self.pages.append(page)
            return page

        async def new_cdp_session(self, page):
            events.append(("cdp-session", page.url))

            class Session:
                async def send(self, *args, **kwargs):
                    events.append(("cdp-send", args[0] if args else None))

            return Session()

    class FakeDamru:
        def __init__(self, **kwargs):
            events.append(("init", kwargs.get("serial"), kwargs.get("locale"), kwargs.get("device")))
            device = types.SimpleNamespace(hardware_concurrency=8)
            self._profile = types.SimpleNamespace(locale="en-US", device=device)
            self._sync_ua_payload = {"userAgent": "UA"}
            self._spoofed_chrome_version = "148.0.7778.217"
            self._spoofed_android_version = 14
            self._context = FakeContext()

        async def __aenter__(self):
            events.append(("enter",))
            return self._context

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            events.append(("exit",))

        async def disconnect_cdp(self):
            events.append(("disconnect",))

        async def reconnect_cdp(self):
            events.append(("reconnect",))
            self._context = FakeContext()
            return self._context

        async def _apply_timezone_override(self):
            events.append(("tz",))

        async def _apply_locale_override(self, locale):
            events.append(("locale", locale))

        async def _apply_devtools_evasion(self):
            events.append(("devtools",))

        async def _apply_hardware_overrides(self, device):
            events.append(("hardware", device.hardware_concurrency))

        async def _apply_touch_emulation(self, device):
            events.append(("touch", device.hardware_concurrency))

        async def _apply_sensor_emulation(self):
            events.append(("sensor",))

        async def _apply_network_emulation(self):
            events.append(("network",))

        async def _apply_storage_quota_override(self, device):
            events.append(("storage", device.hardware_concurrency))

        async def _apply_ua_override(self, device, chrome_version=None, android_version=None):
            events.append(("ua", chrome_version, android_version))

        async def _arm_worker_core_override(self, cores):
            events.append(("workers", cores))

    def fake_run_adb_text(serial, *args, timeout=30):
        events.append(("adb", serial, args))
        return _cp(0, stdout="Starting: Intent")

    monkeypatch.setattr("damru.async_core.AsyncDamru", FakeDamru)
    monkeypatch.setattr(cli, "_run_adb_text", fake_run_adb_text)
    monkeypatch.setattr(cli, "_ensure_adb_connected", lambda serial: events.append(("ensure", serial)))
    monkeypatch.setattr(cli, "_repair_runtime_internet", lambda serial, quiet=True: events.append(("repair", serial)))

    args = cli.build_parser().parse_args([
        "stealth-open-url",
        "--serial",
        "wsl:127.0.0.1:5600",
        "--url",
        "https://example.com",
        "--mode",
        "cdp",
    ])

    assert cli._stealth_open_url(args) == 0
    assert ("disconnect",) not in events
    assert not any(e[0] == "reconnect" for e in events)
    for kind in ("hardware", "touch", "network", "storage", "tz", "ua", "workers"):
        assert any(e[0] == kind for e in events)
    assert not any(e[0] == "sensor" for e in events)


def test_stealth_open_url_reattach_mode_detaches_during_load(monkeypatch):
    events = []

    class FakePage:
        url = "https://example.com"

        async def goto(self, url, wait_until=None, timeout=None):
            events.append(("goto", url))

        async def title(self):
            return "Example"

    class FakeContext:
        pages = [FakePage()]

        async def new_page(self):
            return self.pages[0]

        async def new_cdp_session(self, page):
            class Session:
                async def send(self, *args, **kwargs):
                    pass
            return Session()

    class FakeDamru:
        def __init__(self, **kwargs):
            device = types.SimpleNamespace(hardware_concurrency=8)
            self._profile = types.SimpleNamespace(locale="en-US", device=device)
            self._context = FakeContext()

        async def __aenter__(self):
            events.append(("enter",))
            return self._context

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            events.append(("exit",))

        async def disconnect_cdp(self):
            events.append(("disconnect",))

        async def reconnect_cdp(self):
            events.append(("reconnect",))
            return self._context

        async def _apply_devtools_evasion(self): pass
        async def _apply_hardware_overrides(self, device): pass
        async def _apply_touch_emulation(self, device): pass
        async def _apply_sensor_emulation(self): pass
        async def _apply_network_emulation(self): pass
        async def _apply_storage_quota_override(self, device): pass
        async def _apply_timezone_override(self): pass
        async def _apply_ua_override(self, device, chrome_version=None, android_version=None): pass
        async def _arm_worker_core_override(self, cores): pass
        async def _apply_locale_override(self, locale): pass

    def fake_run_adb_text(serial, *args, timeout=30):
        events.append(("adb", args))
        return _cp(0, stdout="Starting: Intent")

    monkeypatch.setattr("damru.async_core.AsyncDamru", FakeDamru)
    monkeypatch.setattr(cli, "_run_adb_text", fake_run_adb_text)
    monkeypatch.setattr(cli, "_ensure_adb_connected", lambda serial: None)
    monkeypatch.setattr(cli, "_repair_runtime_internet", lambda serial, quiet=True: None)

    args = cli.build_parser().parse_args([
        "stealth-open-url",
        "--serial",
        "wsl:127.0.0.1:5600",
        "--url",
        "https://example.com",
        "--mode",
        "reattach",
    ])

    assert cli._stealth_open_url(args) == 0
    assert ("disconnect",) in events
    assert ("reconnect",) in events
    assert events.index(("disconnect",)) < next(i for i, e in enumerate(events) if e[0] == "adb")
    assert next(i for i, e in enumerate(events) if e[0] == "adb") < events.index(("reconnect",))
