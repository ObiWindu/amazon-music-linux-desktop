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
