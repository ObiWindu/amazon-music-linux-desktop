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
    monkeypatch.delenv("QTWEBENGINE_CHROMIUM_FLAGS", raising=False)
    assert d.configure_widevine() == cdm
    assert f"--widevine-cdm-path={cdm}" in os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]
