from pathlib import Path

from amazon_music_desktop.browser.drm_diagnostics import (
    _elf_arch,
    check_library_presence,
)


def test_elf_arch_real_cdm():
    p = Path("/var/lib/widevine/libwidevinecdm.so")
    if p.exists():
        assert _elf_arch(p) == "aarch64"


def test_check_library_presence():
    res = check_library_presence()
    # may pass or fail depending on environment; ensure structure
    assert hasattr(res, "ok")
    assert res.stage == "A_library_presence"
    assert isinstance(res.details, dict)


def test_missing_cdm(tmp_path):
    from amazon_music_desktop.browser.drm_diagnostics import check_library_presence
    res = check_library_presence(tmp_path / "nope.so")
    assert res.ok is False


def test_find_usable_cdm_missing(tmp_path, monkeypatch):
    import amazon_music_desktop.browser.drm_diagnostics as d
    monkeypatch.setattr(d, "CDM_PATH", tmp_path / "nope.so")
    monkeypatch.setattr(d, "WIDEVINE_CDM_DIR", tmp_path / "WidevineCdm")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert d.find_usable_cdm() is None


def test_build_widevine_flags(tmp_path):
    from amazon_music_desktop.browser.drm_diagnostics import build_widevine_flags
    cdm = tmp_path / "libwidevinecdm.so"
    assert build_widevine_flags(cdm, "") == f"--widevine-cdm-path={cdm}"
    assert "--widevine-cdm-path" in build_widevine_flags(cdm, "--foo=1")
    already = f"--widevine-cdm-path={cdm}"
    assert build_widevine_flags(cdm, already) == already
    assert build_widevine_flags(None, "--foo=1") == "--foo=1"


def test_configure_widevine_sets_env(tmp_path, monkeypatch):
    import os

    import amazon_music_desktop.browser.drm_diagnostics as d
    cdm = tmp_path / "libwidevinecdm.so"
    cdm.write_bytes(b"x" * 64)
    monkeypatch.setattr(d, "CDM_PATH", cdm)
    monkeypatch.setattr(d, "WIDEVINE_CDM_DIR", tmp_path / "WidevineCdm")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.delenv("QTWEBENGINE_CHROMIUM_FLAGS", raising=False)
    assert d.configure_widevine() == cdm
    assert f"--widevine-cdm-path={cdm}" in os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]


def test_find_usable_cdm_prefers_newest_user_component(tmp_path, monkeypatch):
    import json

    import amazon_music_desktop.browser.drm_diagnostics as d

    home = tmp_path / "home"
    old = tmp_path / "system" / "libwidevinecdm.so"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    (old.parent / "manifest.json").write_text(json.dumps({"version": "4.10.2662.3"}))

    version_dir = home / ".config" / "Codex" / "WidevineCdm" / "4.10.3112.0"
    new = version_dir / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so"
    new.parent.mkdir(parents=True)
    new.write_bytes(b"new")
    (version_dir / "manifest.json").write_text(json.dumps({"version": "4.10.3112.0"}))

    monkeypatch.setattr(d, "CDM_PATH", old)
    monkeypatch.setattr(d, "WIDEVINE_CDM_DIR", tmp_path / "system" / "WidevineCdm")
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.setattr(d.platform, "machine", lambda: "aarch64")

    assert d.find_usable_cdm() == new
    assert d.cdm_version() == "4.10.3112.0"


def test_ensure_widevine_user_dir_updates_old_system_link(tmp_path, monkeypatch):
    import json

    import amazon_music_desktop.browser.drm_diagnostics as d

    home = tmp_path / "home"
    old = tmp_path / "system" / "libwidevinecdm.so"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    (old.parent / "manifest.json").write_text(json.dumps({"version": "4.10.2662.3"}))

    version_dir = home / ".config" / "Codex" / "WidevineCdm" / "4.10.3112.0"
    new = version_dir / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so"
    new.parent.mkdir(parents=True)
    new.write_bytes(b"new")
    (version_dir / "manifest.json").write_text(json.dumps({"version": "4.10.3112.0"}))

    target = home / ".config" / "chromium" / "WidevineCdm"
    old_link = target / "_platform_specific" / "linux_x64" / "libwidevinecdm.so"
    old_link.parent.mkdir(parents=True)
    old_link.symlink_to(old)
    (target / "manifest.json").write_text(json.dumps({"version": "4.10.2662.3"}))

    monkeypatch.setattr(d, "CDM_PATH", old)
    monkeypatch.setattr(d, "WIDEVINE_CDM_DIR", tmp_path / "system" / "WidevineCdm")
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.setattr(d.platform, "machine", lambda: "aarch64")

    d.ensure_widevine_user_dir()

    assert old_link.resolve() == new.resolve()
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["version"] == "4.10.3112.0"
    assert any(p.get("arch") == "arm64" for p in manifest["platforms"])


def test_parse_cdm_session_result_ok():
    from amazon_music_desktop.browser.drm_diagnostics import parse_cdm_session_result
    r = parse_cdm_session_result({"ok": True, "keySystem": "com.widevine.alpha"})
    assert r.ok is True
    assert r.stage == "C_cdm_session"


def test_parse_cdm_session_result_fail():
    from amazon_music_desktop.browser.drm_diagnostics import parse_cdm_session_result
    r = parse_cdm_session_result({"ok": False, "error": "NotSupportedError: nope"})
    assert r.ok is False
    assert "NotSupportedError" in (r.error or "")
    assert parse_cdm_session_result(None).ok is False


def test_cdm_version(tmp_path):
    import json

    import amazon_music_desktop.browser.drm_diagnostics as d
    assert isinstance(d.cdm_version(), str)
    m = tmp_path / "manifest.json"
    m.write_text(json.dumps({"version": "4.10.2662.3"}))
    assert d.cdm_version(tmp_path / "libwidevinecdm.so") in ("4.10.2662.3", "unknown")


def test_cdm_session_probe_js_shape():
    from amazon_music_desktop.browser.drm_diagnostics import CDM_SESSION_PROBE_JS
    assert "createMediaKeys" in CDM_SESSION_PROBE_JS
    assert "createSession" in CDM_SESSION_PROBE_JS
    assert "com.widevine.alpha" in CDM_SESSION_PROBE_JS


def test_cdm_probe_state_missing():
    from amazon_music_desktop.browser.drm_diagnostics import cdm_probe_state
    for value in (None, "", "MISSING"):
        assert cdm_probe_state(value) == ("missing", None)


def test_cdm_probe_state_progress_and_final():
    import json

    from amazon_music_desktop.browser.drm_diagnostics import CDM_TEST_READ_JS, cdm_probe_state
    # QtWebEngine 6.11 delivers objects as ''; read-backs must stringify.
    assert "JSON.stringify" in CDM_TEST_READ_JS
    state, raw = cdm_probe_state(json.dumps({"ok": False, "error": "stage: creating MediaKeys..."}))
    assert state == "progress" and raw["error"].startswith("stage:")
    state, raw = cdm_probe_state(json.dumps({"ok": True, "keySystem": "com.widevine.alpha"}))
    assert state == "final" and raw["ok"] is True
    state, raw = cdm_probe_state(json.dumps({"ok": False, "error": "NotSupportedError: nope"}))
    assert state == "final"
    state, raw = cdm_probe_state({"ok": True, "keySystem": "com.widevine.alpha"})
    assert state == "final"
    state, raw = cdm_probe_state("garbage")
    assert state == "final" and raw == "garbage"


def test_detect_freeworld_checks_libavcodec_freeworld(monkeypatch):
    import amazon_music_desktop.browser.drm_diagnostics as d

    class FakeProc:
        def __init__(self, returncode):
            self.returncode = returncode

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeProc(0 if cmd == ["rpm", "-q", "libavcodec-freeworld"] else 1)

    monkeypatch.setattr(d.subprocess, "run", fake_run)
    assert d.detect_freeworld() is True
    assert calls == [["rpm", "-q", "libavcodec-freeworld"]]

    monkeypatch.setattr(d.subprocess, "run", lambda cmd, **kw: FakeProc(1))
    assert d.detect_freeworld() is False

    def boom(cmd, **kw):
        raise FileNotFoundError("rpm")

    monkeypatch.setattr(d.subprocess, "run", boom)
    assert d.detect_freeworld() is None
