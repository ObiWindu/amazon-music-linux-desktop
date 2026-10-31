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
    host = d._host_elf_arch() or "aarch64"
    cdm.write_bytes(_elf_bytes(183 if host == "aarch64" else 62) + b"\x00" * 64)
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
    old.write_bytes(_elf_bytes(183) + b"\x00" * 16)
    (old.parent / "manifest.json").write_text(json.dumps({"version": "4.10.2662.3"}))

    version_dir = home / ".config" / "Codex" / "WidevineCdm" / "4.10.3112.0"
    new = version_dir / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so"
    new.parent.mkdir(parents=True)
    new.write_bytes(_elf_bytes(183) + b"\x00" * 16)
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
    host = d._host_elf_arch() or "aarch64"
    cdm.write_bytes(_elf_bytes(183 if host == "aarch64" else 62) + b"\x00" * 64)
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
    cdm.write_bytes(_elf_bytes(183) + b"\x00" * 16)
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
    old.write_bytes(_elf_bytes(183) + b"\x00" * 16)
    (old.parent / "manifest.json").write_text(json.dumps({"version": "4.10.2662.3"}))

    version_dir = home / ".config" / "Codex" / "WidevineCdm" / "4.10.3112.0"
    new = version_dir / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so"
    new.parent.mkdir(parents=True)
    new.write_bytes(_elf_bytes(183) + b"\x00" * 16)
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

    # The stale non-native (linux_x64-on-ARM64) link is removed rather than
    # refreshed — writing the ARM64 binary under an x64 path would be a fake
    # architecture mapping. The native linux_arm64 link points at the newest
    # CDM instead.
    assert not old_link.exists() or not old_link.is_symlink()
    native_link = target / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so"
    assert native_link.resolve() == new.resolve()
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
    old.write_bytes(_elf_bytes(183) + b"\x00" * 16)
    (system_dir / "manifest.json").write_text(json.dumps({"version": "4.10.2662.3"}))

    version_dir = home / ".config" / "Codex" / "WidevineCdm" / "4.10.3112.0"
    new = version_dir / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so"
    new.parent.mkdir(parents=True)
    new.write_bytes(_elf_bytes(183) + b"\x00" * 16)
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
    new.write_bytes(_elf_bytes(183) + b"\x00" * 16)
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


def test_cdm_install_status_ready_not_initialized(tmp_path, monkeypatch):
    import amazon_music_desktop.browser.drm_diagnostics as d

    cdm = _make_cdm(tmp_path / "libwidevinecdm.so", "4.10.3112.0")
    monkeypatch.setattr(d.platform, "machine", lambda: "aarch64")
    # Filesystem validation passes, but this must never claim the CDM is
    # initialized — only the live MediaKeySession probe proves that.
    assert d.cdm_install_status(cdm) == "READY"
    assert d.cdm_install_status(tmp_path / "missing.so") == "NOT_INSTALLED"
    assert d.cdm_install_status(None) == "NOT_INSTALLED"


def test_cdm_inventory_skips_zero_size_placeholder(tmp_path, monkeypatch):
    d = _isolate_cdm_roots(tmp_path, monkeypatch)
    real = _make_cdm(tmp_path / "system" / "libwidevinecdm.so", "4.10.2662.3")
    stub = tmp_path / "system" / "WidevineCdm" / "_platform_specific" / "linux_x64" / "libwidevinecdm.so"
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_bytes(b"")  # distro placeholder, not a loadable CDM
    monkeypatch.setattr(d, "CDM_PATH", real)
    monkeypatch.setattr(d, "WIDEVINE_CDM_DIR", tmp_path / "system" / "WidevineCdm")
    monkeypatch.setattr(d, "BUNDLED_CDM_DIRS", ())

    inventory = d.cdm_inventory()
    assert all(e["path"] != str(stub) for e in inventory)
    assert any(e["path"] == str(real) for e in inventory)


def test_native_platform_dir_matches_host(monkeypatch):
    import amazon_music_desktop.browser.drm_diagnostics as d

    monkeypatch.setattr(d.platform, "machine", lambda: "aarch64")
    assert d._native_platform_dir() == "linux_arm64"
    monkeypatch.setattr(d.platform, "machine", lambda: "x86_64")
    assert d._native_platform_dir() == "linux_x64"


def test_ensure_widevine_user_dir_writes_native_only(tmp_path, monkeypatch):
    import amazon_music_desktop.browser.drm_diagnostics as d

    home = tmp_path / "home"
    version_dir = home / ".config" / "Codex" / "WidevineCdm" / "4.10.3112.0"
    new = version_dir / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so"
    new.parent.mkdir(parents=True)
    new.write_bytes(_elf_bytes(183) + b"\x00" * 16)
    (version_dir / "manifest.json").write_text(json.dumps({"version": "4.10.3112.0"}))

    monkeypatch.setattr(d, "CDM_PATH", tmp_path / "system" / "nope.so")
    monkeypatch.setattr(d, "WIDEVINE_CDM_DIR", tmp_path / "system" / "WidevineCdm")
    monkeypatch.setattr(d, "BUNDLED_CDM_DIRS", ())
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.setattr(d.platform, "machine", lambda: "aarch64")

    d.ensure_widevine_user_dir()

    for base in ("chromium", "google-chrome"):
        target = home / ".config" / base / "WidevineCdm"
        assert (target / "_platform_specific" / "linux_arm64" / "libwidevinecdm.so").is_symlink()
        # never write the host binary under the foreign arch path
        assert not (target / "_platform_specific" / "linux_x64" / "libwidevinecdm.so").exists()


def _isolated_no_cdm(tmp_path, monkeypatch, machine="aarch64"):
    import amazon_music_desktop.browser.drm_diagnostics as d

    monkeypatch.setattr(d.platform, "machine", lambda: machine)
    monkeypatch.setattr(d, "CDM_PATH", tmp_path / "none.so")
    monkeypatch.setattr(d, "WIDEVINE_CDM_DIR", tmp_path / "widevine")
    monkeypatch.setattr(d, "BUNDLED_CDM_DIRS", ())
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    return d


def test_explicit_cdm_wrong_arch_is_rejected(tmp_path, monkeypatch):
    d = _isolated_no_cdm(tmp_path, monkeypatch, machine="aarch64")
    wrong = tmp_path / "wrong.so"
    wrong.write_bytes(_elf_bytes(62) + b"\x00" * 16)  # x86_64 on an ARM64 host
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", f"--widevine-cdm-path={wrong}")
    assert d.find_usable_cdm() is None


def test_explicit_cdm_non_elf_is_rejected(tmp_path, monkeypatch):
    d = _isolated_no_cdm(tmp_path, monkeypatch, machine="aarch64")
    fake = tmp_path / "fake.so"
    fake.write_bytes(b"not a library" * 8)
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", f"--widevine-cdm-path={fake}")
    assert d.find_usable_cdm() is None


def test_explicit_cdm_empty_file_is_rejected(tmp_path, monkeypatch):
    d = _isolated_no_cdm(tmp_path, monkeypatch, machine="aarch64")
    empty = tmp_path / "empty.so"
    empty.write_bytes(b"")
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", f"--widevine-cdm-path={empty}")
    assert d.find_usable_cdm() is None


def test_discovery_rejects_malformed_binaries(tmp_path, monkeypatch):
    d = _isolated_no_cdm(tmp_path, monkeypatch, machine="aarch64")
    bad = tmp_path / "widevine" / "libwidevinecdm.so"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"definitely not an ELF library")
    (tmp_path / "widevine" / "manifest.json").write_text('{"version": "9.9.9.9"}')
    monkeypatch.setattr(d, "CDM_PATH", bad)
    # malformed file present but unusable: nothing is selected
    assert d.find_usable_cdm() is None
    assert d.check_library_presence(bad).ok is False


def test_check_library_presence_rejects_empty_file(tmp_path):
    from amazon_music_desktop.browser.drm_diagnostics import check_library_presence

    empty = tmp_path / "libwidevinecdm.so"
    empty.write_bytes(b"")
    result = check_library_presence(empty)
    assert result.ok is False
    assert "empty" in (result.error or "").lower()


def _write_maps(proc_root, pid, lines):
    proc_dir = proc_root / str(pid)
    proc_dir.mkdir(parents=True)
    (proc_dir / "maps").write_text("\n".join(lines) + "\n")


def test_loaded_cdm_paths_finds_mapped_cdm(tmp_path):
    from amazon_music_desktop.browser.drm_diagnostics import loaded_cdm_paths, observed_loaded_cdm

    proc = tmp_path / "proc"
    _write_maps(
        proc,
        1234,
        [
            "7f000000-7f100000 r--p 00000000 00:01 999 /usr/lib64/libfoo.so",
            "7f200000-7f300000 r-xp 00000000 00:01 1000 /opt/cdm/_platform_specific/linux_arm64/libwidevinecdm.so",
        ],
    )
    _write_maps(proc, 5678, ["7f000000-7f100000 r--p 00000000 00:01 999 /usr/lib64/libbar.so"])
    found = loaded_cdm_paths(proc)
    assert found == [
        {"pid": 1234, "path": "/opt/cdm/_platform_specific/linux_arm64/libwidevinecdm.so"}
    ]
    assert observed_loaded_cdm(proc) == [
        "/opt/cdm/_platform_specific/linux_arm64/libwidevinecdm.so"
    ]


def test_loaded_cdm_paths_empty_when_absent(tmp_path):
    from amazon_music_desktop.browser.drm_diagnostics import loaded_cdm_paths, observed_loaded_cdm

    assert loaded_cdm_paths(tmp_path / "no-such-proc") == []
    assert observed_loaded_cdm(tmp_path / "no-such-proc") == []
    proc = tmp_path / "proc"
    _write_maps(proc, 42, ["7f000000-7f100000 r--p 00000000 00:01 1 /usr/lib/libc.so"])
    assert loaded_cdm_paths(proc) == []


def test_loaded_cdm_paths_strips_deleted_marker(tmp_path):
    from amazon_music_desktop.browser.drm_diagnostics import observed_loaded_cdm

    proc = tmp_path / "proc"
    _write_maps(
        proc,
        99,
        ["7f200000-7f300000 r-xp 00000000 00:01 1000 /opt/old/libwidevinecdm.so (deleted)"],
    )
    assert observed_loaded_cdm(proc) == ["/opt/old/libwidevinecdm.so"]


def test_loaded_cdm_paths_tree_scope_limits_to_own_processes(tmp_path, monkeypatch):
    import amazon_music_desktop.browser.drm_diagnostics as d

    proc = tmp_path / "proc"
    for pid, ppid in ((100, 1), (101, 100), (200, 1)):
        pdir = proc / str(pid)
        pdir.mkdir(parents=True)
        (pdir / "stat").write_text(f"{pid} (fake) S {ppid} 0 0 0 0 0 0 0 0 0 0 0 0 0 0")
        if pid == 100:
            maps_line = "7f000000-7f100000 r--p 00000000 00:01 1 /usr/lib/libc.so"
        else:
            maps_line = (
                "7f200000-7f300000 r-xp 00000000 00:01 1000 "
                + ("/opt/app/libwidevinecdm.so" if pid == 101 else "/opt/other/libwidevinecdm.so")
            )
        (pdir / "maps").write_text(maps_line + "\n")
    monkeypatch.setattr(d.os, "getpid", lambda: 100)
    assert d.observed_loaded_cdm(proc, scope="tree") == ["/opt/app/libwidevinecdm.so"]
    assert sorted(d.observed_loaded_cdm(proc, scope="all")) == [
        "/opt/app/libwidevinecdm.so",
        "/opt/other/libwidevinecdm.so",
    ]


def test_loaded_cdm_paths_rejects_unknown_scope(tmp_path):
    import pytest

    from amazon_music_desktop.browser.drm_diagnostics import loaded_cdm_paths

    with pytest.raises(ValueError):
        loaded_cdm_paths(tmp_path, scope="everything")
