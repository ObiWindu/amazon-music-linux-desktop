"""Exit-code contract tests for scripts/probe-cdm-session.py.

0 = session created and selected CDM mapping verified (MATCH).
1 = CDM initialization failed.
2 = no compatible CDM discovered.
3 = session created but the mapped CDM could not be verified
    (nothing mapped, unreadable /proc, or a different binary).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_probe():
    path = Path(__file__).resolve().parents[2] / "scripts" / "probe-cdm-session.py"
    spec = importlib.util.spec_from_file_location("probe_cdm_session", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verify_mapped_match_is_zero(monkeypatch):
    probe = _load_probe()
    monkeypatch.setattr(
        probe, "loaded_cdm_paths", lambda scope="tree": [{"pid": 1, "path": "/a/libwidevinecdm.so"}]
    )
    assert probe.verify_mapped("/a/libwidevinecdm.so") == 0


def test_verify_mapped_missing_is_three_not_zero(monkeypatch):
    probe = _load_probe()
    monkeypatch.setattr(probe, "loaded_cdm_paths", lambda scope="tree": [])
    assert probe.verify_mapped("/a/libwidevinecdm.so") == 3


def test_verify_mapped_unreadable_proc_is_three(monkeypatch):
    probe = _load_probe()

    def boom(scope="tree"):
        raise OSError("no proc")

    monkeypatch.setattr(probe, "loaded_cdm_paths", boom)
    assert probe.verify_mapped("/a/libwidevinecdm.so") == 3


def test_verify_mapped_different_binary_is_three(monkeypatch):
    probe = _load_probe()
    monkeypatch.setattr(
        probe, "loaded_cdm_paths", lambda scope="tree": [{"pid": 1, "path": "/b/other.so"}]
    )
    assert probe.verify_mapped("/a/libwidevinecdm.so") == 3
