#!/usr/bin/env python3
"""Headless Widevine CDM session probe (diagnostic tool, no Amazon account).

Sets --widevine-cdm-path to the app's selected CDM *before* QtWebEngine
initializes, loads a minimal EME page (no network: content is injected via
setHtml under an https base URL so requestMediaKeySystemAccess is allowed),
creates MediaKeys + a MediaKeySession, and prints the redacted result.

Success proves the CDM instantiates in this environment. It is NOT license
acceptance and NOT playback. Exit code 0 on CDM session success, 1 otherwise.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from amazon_music_desktop.browser.drm_diagnostics import (
    CDM_SESSION_PROBE_JS,
    CDM_TEST_READ_JS,
    cdm_version,
    find_usable_cdm,
)


def main() -> int:
    cdm = find_usable_cdm()
    print(f"selected CDM: {cdm} (version {cdm_version(cdm)})", flush=True)
    if cdm is None:
        print("no usable CDM found", flush=True)
        return 1
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
    state: dict = {"polls": 0}

    def finish(code: int, message: str) -> None:
        print(message, flush=True)
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
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
