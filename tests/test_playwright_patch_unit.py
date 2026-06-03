from damru.playwright_patch import (
    _ENV_MARKER,
    _PATCH_MARKER,
    _VALID_CONTEXT_SNIPPET,
    _VALID_RUNTIME_SNIPPET,
    _patch_text,
)


def test_patch_text_emits_valid_runtime_condition():
    source = '''
const promises = [
  this._client.send("Runtime.enable", {}),
];
this._page.frameManager.frameCommittedNewDocumentNavigation(framePayload.id, framePayload.url + (framePayload.urlFragment || ""), framePayload.name || "", framePayload.loaderId, initial);
const frame = contextPayload.auxData ? this._page.frameManager.frame(contextPayload.auxData.frameId) : null;
'''

    patched = _patch_text(source)

    assert _PATCH_MARKER in patched
    assert _VALID_RUNTIME_SNIPPET in patched
    assert _VALID_CONTEXT_SNIPPET in patched
    assert f"process.env.{_ENV_MARKER}  this" not in patched
    assert "contextPayload.auxData  this._page" not in patched


def test_patch_text_repairs_broken_marker_patch():
    broken = f'''
(process.env.{_ENV_MARKER}  this._client.send("Runtime.enable", {{}}).then(() => {{ /* {_PATCH_MARKER} */ }}));
const frame = contextPayload.auxData  this._page.frameManager.frame(contextPayload.auxData.frameId) : null;
'''

    repaired = _patch_text(broken)

    assert _VALID_RUNTIME_SNIPPET in repaired
    assert _VALID_CONTEXT_SNIPPET in repaired
    assert f"process.env.{_ENV_MARKER}  this" not in repaired
    assert "contextPayload.auxData  this._page" not in repaired
