import pytest

from damru.root import RootOps


class FakeADB:
    def __init__(self, iptables_output: str):
        self.iptables_output = iptables_output
        self.shell_calls = []
        self.root_calls = []

    async def shell(self, command, timeout=None, allow_failure=False):
        self.shell_calls.append(command)
        if "iptables -L OUTPUT" in command:
            return self.iptables_output
        if "iptables -C OUTPUT" in command:
            return "iptables: Bad rule (does a matching rule exist in that chain)."
        if command.startswith("stat -c"):
            return "u0_a123"
        return ""

    async def shell_root(self, command):
        self.root_calls.append(command)
        return ""


@pytest.mark.asyncio
async def test_webrtc_block_skips_when_android_iptables_filter_missing():
    adb = FakeADB(
        "iptables v1.8.7 (legacy): can't initialize iptables table `filter': "
        "Table does not exist"
    )
    root = RootOps(adb)

    await root.apply_webrtc_block()

    assert adb.root_calls == []


@pytest.mark.asyncio
async def test_webrtc_block_still_applies_owner_rule_when_available():
    adb = FakeADB("Chain OUTPUT (policy ACCEPT)")
    root = RootOps(adb)

    await root.apply_webrtc_block()

    assert any("--uid-owner 10123" in call for call in adb.root_calls)
