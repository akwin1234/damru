import json

import pytest

from damru.chrome import ChromeManager


class FakeADB:
    def __init__(self) -> None:
        self.shell_calls: list[str] = []
        self.root_calls: list[str] = []
        self.pushed: dict[str, str] = {}

    async def shell(self, command: str, *args, **kwargs) -> str:
        self.shell_calls.append(command)
        if command == "pm list packages":
            return "package:com.android.chrome\npackage:org.chromium.webview_shell\n"
        if "cat /data/data/org.chromium.webview_shell/app_webview/pref_store" in command:
            return json.dumps({"background_tracing": {"session_state": {"state": 0}}})
        if "stat -c '%U:%G' /data/data/org.chromium.webview_shell/app_webview/pref_store" in command:
            return "u0_a77:u0_a77"
        return ""

    async def shell_root(self, command: str, *args, **kwargs) -> str:
        self.root_calls.append(command)
        return ""

    async def push(self, local: str, remote: str) -> None:
        with open(local, encoding="utf-8") as handle:
            self.pushed[remote] = handle.read()


@pytest.mark.unit
async def test_webview_shell_uses_webview_command_line_and_pref_store() -> None:
    adb = FakeADB()
    browser = ChromeManager(adb, package="org.chromium.webview_shell")

    detected = await browser.detect_package()
    await browser.write_command_line(["--lang=pt-BR"])
    await browser.patch_preferences("pt-BR", "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7")

    assert detected == "org.chromium.webview_shell"
    assert any("/data/local/tmp/webview-command-line" in call for call in adb.root_calls)
    assert any('printf "%s" "webview ' in call for call in adb.root_calls)
    assert any("app_webview/pref_store" in call for call in adb.shell_calls)

    prefs = json.loads(adb.pushed["/data/local/tmp/damru_chrome_prefs.json"])
    assert prefs["intl"]["selected_languages"] == "pt-BR,pt,en-US,en"
    assert prefs["dns_prefetching"]["enabled"] is False
    assert prefs["net"]["network_prediction_options"] == 2
    assert prefs["webrtc"]["ip_handling_policy"] == "default_public_interface_only"
