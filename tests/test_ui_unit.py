from __future__ import annotations

from damru import cli
from damru.ui.jobs import Job
from damru.ui.redact import redact, redact_dict
from damru.ui.server import _clean_arg, profiles_payload


def test_redact_proxy_credentials():
    value = "socks5://user:secret@gw.example.com:824 password=hunter2 token=abc"
    redacted = redact(value)
    assert "secret" not in redacted
    assert "hunter2" not in redacted
    assert "token=***" in redacted
    assert "socks5://***:***@gw.example.com:824" in redacted


def test_redact_dict_nested_values():
    data = {"proxy": "http://u:p@example.com:8080", "nested": {"password": "password=abc"}}
    redacted = redact_dict(data)
    assert redacted["proxy"] == "http://***:***@example.com:8080"
    assert redacted["nested"] == {"password": "password=***"}


def test_job_redacts_command():
    job = Job(id="abc", name="probe", command=["damru", "--proxy", "socks5://u:p@example.com:1"])
    as_dict = job.as_dict()
    command = " ".join(as_dict["command"])
    assert "p@example" not in command
    assert "socks5://***:***@example.com:1" in command


def test_cli_parser_has_ui_command():
    parser = cli.build_parser()
    args = parser.parse_args(["ui", "--host", "127.0.0.1", "--port", "8765", "--no-open"])
    assert args.host == "127.0.0.1"
    assert args.port == 8765
    assert args.no_open is True
    assert callable(args.func)


def test_profiles_payload_contains_devices():
    payload = profiles_payload()
    profiles = payload["profiles"]
    assert profiles
    first = profiles[0]
    assert "screen_width" in first
    assert "hardware_concurrency" in first


def test_clean_arg_strips_shell_characters():
    cleaned = _clean_arg("wsl:127.0.0.1:5600; rm -rf / && echo nope")
    assert ";" not in cleaned
    assert "&&" not in cleaned


def test_cli_parser_has_worker_command():
    parser = cli.build_parser()
    args = parser.parse_args(["worker", "start", "--index", "2"])
    assert args.worker_command == "start"
    assert args.index == 2
    assert callable(args.func)
