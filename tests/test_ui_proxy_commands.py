import subprocess

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
