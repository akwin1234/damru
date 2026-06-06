from damru.devices import get_device
import damru.proxy as proxy_mod
from damru.profiles import build_profile
from damru.proxy import make_sticky_proxy_url, resolve_locale_for_geo, resolve_proxy_geo


def test_profile_geo_uses_android_http_proxy(monkeypatch):
    seen = []

    def fake_geo(proxy):
        seen.append(proxy)
        return {
            "timezone": "America/Denver",
            "locale": "en-US",
            "country_code": "US",
            "ip": "",
        }

    monkeypatch.setattr("damru.profiles.resolve_proxy_geo", fake_geo)

    profile = build_profile(
        get_device("pixel_8_pro"),
        proxy="socks5://user:pass@proxy.example:824",
        http_proxy="172.17.0.1:18888",
    )

    assert seen == ["172.17.0.1:18888"]
    assert profile.timezone == "America/Denver"
    assert profile.locale == "en-US"
    assert profile.android_http_proxy == "172.17.0.1:18888"


def test_explicit_timezone_still_overrides_proxy_geo(monkeypatch):
    def fake_geo(proxy):
        return {
            "timezone": "America/Denver",
            "locale": "en-US",
            "country_code": "US",
            "ip": "",
        }

    monkeypatch.setattr("damru.profiles.resolve_proxy_geo", fake_geo)

    profile = build_profile(
        get_device("pixel_8_pro"),
        proxy="socks5://user:pass@proxy.example:824",
        http_proxy="172.17.0.1:18888",
        timezone="America/New_York",
    )

    assert profile.timezone == "America/New_York"
    assert profile.locale == "en-US"


def test_proxy_geo_keeps_authenticated_proxy_url(monkeypatch):
    seen = []

    def fake_geo(proxy):
        seen.append(proxy)
        return {
            "timezone": "Asia/Manila",
            "locale": "en-PH",
            "country_code": "PH",
            "ip": "",
        }

    monkeypatch.setattr("damru.profiles.resolve_proxy_geo", fake_geo)

    profile = build_profile(
        get_device("pixel_8_pro"),
        proxy="http://user:pass@proxy.example:10000",
    )

    assert seen == ["http://user:pass@proxy.example:10000"]
    assert profile.timezone == "Asia/Manila"
    assert profile.locale == "en-PH"
    assert profile.android_http_proxy == "proxy.example:10000"

def test_profile_can_use_pre_resolved_android_bridge(monkeypatch):
    seen = []

    def fake_geo(proxy):
        seen.append(proxy)
        return {
            "timezone": "Pacific/Honolulu",
            "locale": "en-US",
            "country_code": "US",
            "ip": "",
        }

    monkeypatch.setattr("damru.profiles.resolve_proxy_geo", fake_geo)

    profile = build_profile(
        get_device("pixel_8_pro"),
        proxy="http://user:pass@proxy.example:823",
        android_proxy="172.17.0.1:18993",
    )

    assert seen == ["http://user:pass@proxy.example:823"]
    assert profile.timezone == "Pacific/Honolulu"
    assert profile.android_http_proxy == "172.17.0.1:18993"

def test_geo_locale_uses_real_country_variants(monkeypatch):
    monkeypatch.setattr("damru.proxy.random.choice", lambda values: values[1] if len(values) > 1 else values[0])

    assert resolve_locale_for_geo("Asia/Kolkata", "IN") == "hi-IN"
    assert resolve_locale_for_geo("Asia/Manila", "PH") == "fil-PH"
    assert resolve_locale_for_geo("America/New_York", "US") == "en-US"
    assert resolve_locale_for_geo("Europe/Paris", "XX") == "fr-FR"

def test_country_locale_map_covers_iso_and_cldr_alpha2():
    iso_and_cldr_alpha2 = {
        "AC", "CP", "CQ", "DG", "EA", "IC", "TA", "ZZ",
        "AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AQ", "AR", "AS", "AT", "AU", "AW", "AX", "AZ",
        "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI", "BJ", "BL", "BM", "BN", "BO", "BQ", "BR", "BS",
        "BT", "BV", "BW", "BY", "BZ", "CA", "CC", "CD", "CF", "CG", "CH", "CI", "CK", "CL", "CM", "CN",
        "CO", "CR", "CU", "CV", "CW", "CX", "CY", "CZ", "DE", "DJ", "DK", "DM", "DO", "DZ", "EC", "EE",
        "EG", "EH", "ER", "ES", "ET", "FI", "FJ", "FK", "FM", "FO", "FR", "GA", "GB", "GD", "GE", "GF",
        "GG", "GH", "GI", "GL", "GM", "GN", "GP", "GQ", "GR", "GS", "GT", "GU", "GW", "GY", "HK", "HM",
        "HN", "HR", "HT", "HU", "ID", "IE", "IL", "IM", "IN", "IO", "IQ", "IR", "IS", "IT", "JE", "JM",
        "JO", "JP", "KE", "KG", "KH", "KI", "KM", "KN", "KP", "KR", "KW", "KY", "KZ", "LA", "LB", "LC",
        "LI", "LK", "LR", "LS", "LT", "LU", "LV", "LY", "MA", "MC", "MD", "ME", "MF", "MG", "MH", "MK",
        "ML", "MM", "MN", "MO", "MP", "MQ", "MR", "MS", "MT", "MU", "MV", "MW", "MX", "MY", "MZ", "NA",
        "NC", "NE", "NF", "NG", "NI", "NL", "NO", "NP", "NR", "NU", "NZ", "OM", "PA", "PE", "PF", "PG",
        "PH", "PK", "PL", "PM", "PN", "PR", "PS", "PT", "PW", "PY", "QA", "RE", "RO", "RS", "RU", "RW",
        "SA", "SB", "SC", "SD", "SE", "SG", "SH", "SI", "SJ", "SK", "SL", "SM", "SN", "SO", "SR", "SS",
        "ST", "SV", "SX", "SY", "SZ", "TC", "TD", "TF", "TG", "TH", "TJ", "TK", "TL", "TM", "TN", "TO",
        "TR", "TT", "TV", "TW", "TZ", "UA", "UG", "UM", "US", "UY", "UZ", "VA", "VC", "VE", "VG", "VI",
        "VN", "VU", "WF", "WS", "YE", "YT", "ZA", "ZM", "ZW",
    }

    missing = iso_and_cldr_alpha2 - set(proxy_mod._COUNTRY_LOCALE_VARIANTS)
    assert missing == set()


def test_proxy_geo_does_not_use_stale_cache_by_default(monkeypatch):
    proxy_mod._geo_cache["http://proxy.example:18888"] = {
        "timezone": "America/New_York",
        "locale": "en-US",
        "country_code": "US",
        "ip": "",
    }

    class FakeResponse:
        def json(self):
            return {
                "timezone": "America/Denver",
                "country_code": "US",
                "ip": "",
            }

    class FakeRequests:
        @staticmethod
        def get(*args, **kwargs):
            return FakeResponse()

    monkeypatch.setitem(__import__("sys").modules, "requests", FakeRequests)

    geo = resolve_proxy_geo("http://proxy.example:18888", retries=1)

    assert geo["timezone"] == "America/Denver"


def test_dataimpulse_proxy_gets_sticky_session(monkeypatch):
    monkeypatch.setattr("damru.proxy.secrets.token_hex", lambda n: "abc12345")

    proxy = "socks5://user:pass@proxy.dataimpulse.com:824"
    sticky = make_sticky_proxy_url(proxy)

    assert sticky == "socks5://user;sessid.damruabc12345;sessttl.30:pass@proxy.dataimpulse.com:824"


def test_dataimpulse_sticky_session_is_not_process_cached(monkeypatch):
    tokens = iter(["aaa11111", "bbb22222"])
    monkeypatch.setattr("damru.proxy.secrets.token_hex", lambda n: next(tokens))

    proxy = "http://user:pass@proxy.dataimpulse.com:823"

    first = make_sticky_proxy_url(proxy)
    second = make_sticky_proxy_url(proxy)

    assert ";sessid.damruaaa11111;" in first
    assert ";sessid.damrubbb22222;" in second
    assert first != second

def test_non_dataimpulse_proxy_is_not_changed():
    proxy = "socks5://user:pass@proxy.example:824"
    assert make_sticky_proxy_url(proxy) == proxy
