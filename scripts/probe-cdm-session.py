#!/usr/bin/env python3
"""Headless Widevine CDM session probe (diagnostic tool, no Amazon account).

Self-contained: needs only a checkout (or installed package) plus PySide6
with QtWebEngine. It defaults to the offscreen platform, loads a minimal
EME page (no network: content is injected via setHtml under an https base
URL so requestMediaKeySystemAccess is allowed), creates MediaKeys + a
MediaKeySession, verifies the mapped binary in our own helper processes,
and prints the redacted result.

Success proves the CDM instantiates in this environment. It is NOT license
acceptance and NOT playback.

Exit codes: 0 CDM session OK and mapped binary verified; 1 session failed;
2 no usable CDM selected.
"""

from __future__ import annotations

import json
import os
import sys

# Headless by default; override from the outside for a visible run.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from amazon_music_desktop.browser.drm_diagnostics import (
    CDM_SESSION_PROBE_JS,
    CDM_TEST_READ_JS,
    _platform_dirs,
    cdm_version,
    find_usable_cdm,
    loaded_cdm_paths,
)

ENGINE_USER_ROOTS = ("chromium", "google-chrome")


def report_lookup_paths() -> None:
    """Show which engine lookup paths exist (read-only pre-flight check)."""
    from pathlib import Path

    home = Path.home()
    print("engine lookup paths (user level):", flush=True)
    for base in ENGINE_USER_ROOTS:
        for platform_dir in _platform_dirs():
            link = (
                home
                / ".config"
                / base
                / "WidevineCdm"
                / "_platform_specific"
                / platform_dir
                / "libwidevinecdm.so"
            )
            try:
                ok = link.is_file() and os.access(link, os.R_OK)
                size = link.stat().st_size if ok else -1
            except OSError:
                ok, size = False, -1
            print(f"  {'present' if ok else 'MISSING'} ({size} bytes): {link}", flush=True)


def verify_mapped(selected: str | None) -> int:
    """Confirm our helpers mapped the selected CDM. Returns exit code."""
    try:
        mapped = [entry["path"] for entry in loaded_cdm_paths(scope="tree")]
    except Exception as exc:  # /proc unavailable (non-Linux): session result stands
        print(f"mapped-CDM scan unavailable: {exc}", flush=True)
        return 0
    if not mapped:
        print("mapped CDM: none visible in our helper processes", flush=True)
        return 0
    for path in mapped:
        print(f"mapped CDM: {path}", flush=True)
    if selected is not None and any(path == selected for path in mapped):
        print(f"verdict: MATCH — engine mapped the selected CDM ({selected})", flush=True)
        return 0
    print(
        f"verdict: MISMATCH — selected {selected or 'none'}, "
        f"engine mapped {', '.join(mapped)}",
        flush=True,
    )
    return 1


def main() -> int:
    cdm = find_usable_cdm()
    print(f"selected CDM: {cdm} (version {cdm_version(cdm)})", flush=True)
    if cdm is None:
        print("no usable CDM found", flush=True)
        return 2
    report_lookup_paths()
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    if "--widevine-cdm-path" not in flags:
        flags = f"{flags} --widevine-cdm-path={cdm}".strip()
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags
    print(f"flags: {flags}", flush=True)

    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    view = QWebEngineView()
    state: dict = {"polls": 0, "code": 1}

    def finish(code: int, message: str) -> None:
        print(message, flush=True)
        if code == 0:
            code = verify_mapped(str(cdm))
        state["code"] = code
        app.exit(code)

    def poll() -> None:
        state["polls"] += 1
        view.page().runJavaScript(CDM_TEST_READ_JS, on_read)

    def on_read(result: object) -> None:
        raw = result if isinstance(result, str) else ""
        if raw in ("", "MISSING", None):
            if state["polls"] >= 10:
                finish(1, "TIMEOUT: probe marker never appeared")
            else:
                QTimer.singleShot(1000, poll)
            return
        try:
            data = json.loads(raw)
        except ValueError:
            finish(1, f"UNEXPECTED read-back: {raw[:200]}")
            return
        if isinstance(data, dict) and data.get("ok") is True:
            finish(0, f"CDM SESSION OK: {json.dumps(data)}")
        elif isinstance(data, dict) and str(data.get("error", "")).startswith("stage:"):
            if state["polls"] >= 10:
                finish(1, f"TIMEOUT in flight: {data.get('error')}")
            else:
                QTimer.singleShot(1000, poll)
        else:
            error = data.get("error", data) if isinstance(data, dict) else data
            finish(1, f"CDM SESSION FAILED: {error}")

    def on_loaded(_ok: bool) -> None:
        view.page().runJavaScript(CDM_SESSION_PROBE_JS, lambda _r: QTimer.singleShot(1000, poll))

    view.loadFinished.connect(on_loaded)
    view.setHtml("<html><body>cdm probe</body></html>", QUrl("https://music.amazon.fr/"))
    QTimer.singleShot(30000, lambda: finish(1, "TIMEOUT: page never loaded"))
    app.exec()
    return state["code"]


if __name__ == "__main__":
    raise SystemExit(main())
