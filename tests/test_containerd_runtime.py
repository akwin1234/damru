from __future__ import annotations


def test_redroid_runtime_name_containerd(monkeypatch):
    from damru import config
    from damru import runtime

    monkeypatch.setattr(config, "REDROID_RUNTIME", "containerd", raising=False)
    assert runtime.redroid_runtime_name() == "containerd"


def test_redroid_runtime_name_default_docker(monkeypatch):
    from damru import config
    from damru import runtime

    monkeypatch.setattr(config, "REDROID_RUNTIME", "docker", raising=False)
    assert runtime.redroid_runtime_name() == "docker"


def test_create_redroid_manager_selects_containerd(monkeypatch):
    from damru import config
    from damru import runtime

    monkeypatch.setattr(config, "REDROID_RUNTIME", "containerd", raising=False)
    mgr = runtime.create_redroid_manager()
    assert mgr.__class__.__name__ == "ContainerdRedroidManager"
