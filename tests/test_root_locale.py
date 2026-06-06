import pytest

from damru.root import RootOps


class FakeADB:
    def __init__(self) -> None:
        self.root_commands: list[str] = []
        self.shell_commands: list[str] = []

    async def shell_root(self, command: str, *args, **kwargs) -> str:
        self.root_commands.append(command)
        return ""

    async def shell(self, command: str, *args, **kwargs) -> str:
        self.shell_commands.append(command)
        return ""


@pytest.mark.unit
async def test_apply_locale_sets_legacy_language_country_props() -> None:
    adb = FakeADB()
    root = RootOps(adb)  # type: ignore[arg-type]

    await root.apply_locale("pt-BR")

    assert 'setprop persist.sys.locale "pt-BR"' in adb.root_commands
    assert 'setprop persist.sys.language "pt"' in adb.root_commands
    assert 'setprop persist.sys.country "BR"' in adb.root_commands
    assert "settings put system system_locales pt-BR" in adb.shell_commands
