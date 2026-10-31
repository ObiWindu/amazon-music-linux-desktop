import json
import struct
from pathlib import Path

import pytest

from amazon_music_desktop.browser.drm_diagnostics import (
    _elf_arch,
    check_library_presence,
)


@pytest.fixture(autouse=True)
def _clear_qt_flags(monkeypatch):
    monkeypatch.delenv("QTWEBENGINE_CHROMIUM_FLAGS", raising=False)


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
    monkeypatch.setattr(d, "BUNDLED_CDM_DIRS", ())
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
    monkeypatch.setattr(d, "BUNDLED_CDM_DIRS", ())
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
    monkeypatch.setattr(d, "BUNDLED_CDM_DIRS", ())
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.setattr(d.platform, "machine", lambda: "aarch64")

    assert d.find_usable_cdm() == new
    assert d.cdm_version() == "4.10.3112.0"


def test_find_usable_cdm_honors_explicit_flag(tmp_path, monkeypatch):
    import amazon_music_desktop.browser.drm_diagnostics as d

    cdm = tmp_path / "libwidevinecdm.so"
    cdm.write_bytes(b"x" * 64)
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", f"--widevine-cdm-path={cdm}")
    monkeypatch.setattr(d, "CDM_PATH", tmp_path / "nope.so")
    monkeypatch.setattr(d, "WIDEVINE_CDM_DIR", tmp_path / "WidevineCdm")
    monkeypatch.setattr(d, "BUNDLED_CDM_DIRS", ())
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    assert d.find_usable_cdm() == cdm


def test_find_usable_cdm_in_bundled_rpm_dir(tmp_path, monkeypatch):
    import json

    import amazon_music_desktop.browser.drm_diagnostics as d

    bundled = tmp_path / "usr" / "lib64" / "amazon-music-desktop" / "WidevineCdm"
    cdm = bundled / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so"
    cdm.parent.mkdir(parents=True)
    cdm.write_bytes(b"bundled")
    (bundled / "manifest.json").write_text(json.dumps({"version": "4.10.3112.0"}))

    monkeypatch.setattr(d, "CDM_PATH", tmp_path / "nope.so")
    monkeypatch.setattr(d, "WIDEVINE_CDM_DIR", tmp_path / "system" / "WidevineCdm")
    monkeypatch.setattr(d, "BUNDLED_CDM_DIRS", (bundled,))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    monkeypatch.setattr(d.platform, "machine", lambda: "aarch64")

    assert d.find_usable_cdm() == cdm
    assert d.cdm_version(cdm) == "4.10.3112.0"


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
    monkeypatch.setattr(d, "BUNDLED_CDM_DIRS", ())
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.setattr(d.platform, "machine", lambda: "aarch64")

    d.ensure_widevine_user_dir()

    assert old_link.resolve() == new.resolve()
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["version"] == "4.10.3112.0"
    assert any(p.get("arch") == "arm64" for p in manifest["platforms"])


def test_ensure_widevine_user_dir_updates_system_widevinecdm_link(tmp_path, monkeypatch):
    import json

    import amazon_music_desktop.browser.drm_diagnostics as d

    home = tmp_path / "home"
    system_dir = tmp_path / "system" / "WidevineCdm"
    old = system_dir / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    (system_dir / "manifest.json").write_text(json.dumps({"version": "4.10.2662.3"}))

    version_dir = home / ".config" / "Codex" / "WidevineCdm" / "4.10.3112.0"
    new = version_dir / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so"
    new.parent.mkdir(parents=True)
    new.write_bytes(b"new")
    (version_dir / "manifest.json").write_text(json.dumps({"version": "4.10.3112.0"}))

    target = home / ".config" / "chromium" / "WidevineCdm"
    link = target / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so"
    link.parent.mkdir(parents=True)
    link.symlink_to(old)
    (target / "manifest.json").write_text(json.dumps({"version": "4.10.2662.3"}))

    monkeypatch.setattr(d, "CDM_PATH", tmp_path / "system" / "libwidevinecdm.so")
    monkeypatch.setattr(d, "WIDEVINE_CDM_DIR", system_dir)
    monkeypatch.setattr(d, "BUNDLED_CDM_DIRS", ())
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.setattr(d.platform, "machine", lambda: "aarch64")

    d.ensure_widevine_user_dir()

    assert link.resolve() == new.resolve()
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["version"] == "4.10.3112.0"


def test_ensure_widevine_user_dir_keeps_custom_link(tmp_path, monkeypatch):
    import json

    import amazon_music_desktop.browser.drm_diagnostics as d

    home = tmp_path / "home"
    version_dir = home / ".config" / "Codex" / "WidevineCdm" / "4.10.3112.0"
    new = version_dir / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so"
    new.parent.mkdir(parents=True)
    new.write_bytes(b"new")
    (version_dir / "manifest.json").write_text(json.dumps({"version": "4.10.3112.0"}))

    custom = tmp_path / "custom" / "libwidevinecdm.so"
    custom.parent.mkdir(parents=True)
    custom.write_bytes(b"custom")

    target = home / ".config" / "chromium" / "WidevineCdm"
    link = target / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so"
    link.parent.mkdir(parents=True)
    link.symlink_to(custom)

    monkeypatch.setattr(d, "CDM_PATH", tmp_path / "system" / "nope.so")
    monkeypatch.setattr(d, "WIDEVINE_CDM_DIR", tmp_path / "system" / "WidevineCdm")
    monkeypatch.setattr(d, "BUNDLED_CDM_DIRS", ())
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.setattr(d.platform, "machine", lambda: "aarch64")

    d.ensure_widevine_user_dir()

    assert link.resolve() == custom.resolve()


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


# --- CDM inventory and version comparison (spec 4.4) -------------------------


def _elf_bytes(machine: int) -> bytes:
    # minimal ELF: magic + 64-bit LE class/data + e_machine at offset 18
    return b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 10 + struct.pack("<H", machine)


def _make_cdm(path: Path, version: str | None, machine: int = 183) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_elf_bytes(machine) + b"\x00" * 16)
    if version is not None:
        path.parent.joinpath("manifest.json").write_text(json.dumps({"version": version}))
    return path


def _isolate_cdm_roots(tmp_path, monkeypatch, machine: str = "aarch64"):
    import amazon_music_desktop.browser.drm_diagnostics as d

    monkeypatch.setattr(d.platform, "machine", lambda: machine)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    return d


def test_cdm_inventory_lists_and_marks_selected(tmp_path, monkeypatch):
    d = _isolate_cdm_roots(tmp_path, monkeypatch)
    old = _make_cdm(tmp_path / "system" / "libwidevinecdm.so", "4.10.2662.3")
    new = _make_cdm(
        tmp_path / "home" / ".config" / "chromium" / "WidevineCdm" / "4.10.3112.0"
        / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so",
        "4.10.3112.0",
    )
    monkeypatch.setattr(d, "CDM_PATH", old)
    monkeypatch.setattr(d, "WIDEVINE_CDM_DIR", tmp_path / "widevine")
    monkeypatch.setattr(d, "BUNDLED_CDM_DIRS", ())

    inventory = d.cdm_inventory()
    by_path = {e["path"]: e for e in inventory}
    assert len(inventory) == 2
    assert by_path[str(new)]["selected"] is True
    assert by_path[str(new)]["version"] == "4.10.3112.0"
    assert by_path[str(old)]["selected"] is False
    assert by_path[str(old)]["version"] == "4.10.2662.3"
    assert all(e["arch_match"] is True for e in by_path.values())
    assert all(e["manifest_valid"] for e in by_path.values())


def test_cdm_inventory_flags_arch_mismatch(tmp_path, monkeypatch):
    d = _isolate_cdm_roots(tmp_path, monkeypatch, machine="x86_64")
    wrong = _make_cdm(tmp_path / "system" / "libwidevinecdm.so", None, machine=183)
    monkeypatch.setattr(d, "CDM_PATH", wrong)
    monkeypatch.setattr(d, "WIDEVINE_CDM_DIR", tmp_path / "widevine")
    monkeypatch.setattr(d, "BUNDLED_CDM_DIRS", ())

    inventory = d.cdm_inventory()
    assert inventory[0]["arch_match"] is False
    assert inventory[0]["selected"] is False  # never selected on this host


def test_cdm_version_comparison_distinguishes_system_and_selected(tmp_path, monkeypatch):
    d = _isolate_cdm_roots(tmp_path, monkeypatch)
    old = _make_cdm(tmp_path / "system" / "libwidevinecdm.so", "4.10.2662.3")
    new = _make_cdm(
        tmp_path / "home" / ".config" / "chromium" / "WidevineCdm" / "4.10.3112.0"
        / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so",
        "4.10.3112.0",
    )
    monkeypatch.setattr(d, "CDM_PATH", old)
    monkeypatch.setattr(d, "WIDEVINE_CDM_DIR", tmp_path / "widevine")
    monkeypatch.setattr(d, "BUNDLED_CDM_DIRS", ())

    comparison = d.cdm_version_comparison()
    assert comparison["system_cdm"]["version"] == "4.10.2662.3"
    assert comparison["selected_cdm"]["version"] == "4.10.3112.0"
    assert comparison["selected_cdm"]["path"] == str(new)
    assert comparison["flag_passed"] == f"--widevine-cdm-path={new}"
    # the actually loaded CDM is not observable through public APIs
    assert "not directly observable" in comparison["qt_webengine_loaded"]


def test_cdm_version_comparison_without_any_cdm(tmp_path, monkeypatch):
    d = _isolate_cdm_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(d, "CDM_PATH", tmp_path / "none.so")
    monkeypatch.setattr(d, "WIDEVINE_CDM_DIR", tmp_path / "widevine")
    monkeypatch.setattr(d, "BUNDLED_CDM_DIRS", ())

    comparison = d.cdm_version_comparison()
    assert comparison["system_cdm"]["present"] is False
    assert comparison["selected_cdm"]["path"] is None
    assert comparison["flag_passed"] is None
    assert comparison["candidates"] == []
