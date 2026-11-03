#!/usr/bin/env python3
"""Headless full Widevine license exchange (diagnostic, no Amazon account).

Drives EME end-to-end against public Widevine *test* vectors (Tears of
Steel + UAT proxy): requestMediaKeySystemAccess -> createMediaKeys ->
generateRequest -> license POST -> session.update -> keyStatuses.
Proves the CDM can complete a real license exchange (keys usable),
which the session-creation probe alone does not.

Exit codes: 0 keys usable; 1 exchange failed; 2 no usable CDM; 3 no network.
"""

from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from amazon_music_desktop.browser.drm_diagnostics import (
    cdm_version,
    ensure_widevine_user_dir,
    find_usable_cdm,
)

PSSH_B64 = (
    "AAAARHBzc2gAAAAA7e+LqXnWSs6jyCfc1R0h7QAAACQIARIB"
    "NRoNd2lkZXZpbmVfdGVzdCIKMjAxNV90ZWFycyoCU0Q="
)
LICENSE_URL = "https://proxy.uat.widevine.com/proxy"

LICENSE_JS = (
    "window.__amdLicTest = {ok: false, error: 'probe started, no result yet'};"
    "(async () => {"
    "try {"
    "var psshB64 = __PSSH__;"
    "var raw = Uint8Array.from(atob(psshB64), function (c) { return c.charCodeAt(0); });"
    "window.__amdLicTest = {ok: false, error: 'stage: requesting key system...'};"
    "var access = await navigator.requestMediaKeySystemAccess("
    "'com.widevine.alpha', [{"
    "initDataTypes: ['cenc'],"
    "audioCapabilities: [{contentType: 'audio/mp4; codecs=\"mp4a.40.2\"'}],"
    "videoCapabilities: [{contentType: 'video/mp4; codecs=\"avc1.42E01E\"'}]"
    "}]);"
    "window.__amdLicTest = {ok: false, error: 'stage: creating MediaKeys...'};"
    "var keys = await access.createMediaKeys();"
    "var session = keys.createSession();"
    "if (!session) throw new Error('createSession returned null');"
    "var updated = new Promise(function (resolve, reject) {"
    "session.addEventListener('message', async function (ev) {"
    "try {"
    "window.__amdLicTest = {ok: false, error: 'stage: requesting license...'};"
    "var resp = await fetch(__LICURL__, {method: 'POST', body: ev.message});"
    "if (!resp.ok) throw new Error('license server HTTP ' + resp.status);"
    "var buf = await resp.arrayBuffer();"
    "window.__amdLicTest = {ok: false, error: 'stage: updating session...'};"
    "await session.update(buf);"
    "resolve('updated');"
    "} catch (e) { reject(e); }"
    "});"
    "session.addEventListener('message', function () {}, false);"
    "});"
    "var keyOk = new Promise(function (resolve) {"
    "session.addEventListener('keystatuseschange', function () {"
    "var states = [];"
    "session.keyStatuses.forEach(function (s, id) { states.push(s); });"
    "window.__amdLicTest = {ok: false, error: 'stage: keys ' + states.join(',')};"
    "if (states.length && states.every(function (s) { return s === 'usable'; })) resolve(states);"
    "});"
    "});"
    "window.__amdLicTest = {ok: false, error: 'stage: generating request...'};"
    "await session.generateRequest('cenc', raw);"
    "await Promise.race([Promise.all([updated, keyOk]),"
    "new Promise(function (_, rej) { setTimeout(function () { rej(new Error('license timeout')); }, 20000); })]);"
    "window.__amdLicTest = {ok: true, keySystem: access.keySystem};"
    "} catch (e) { window.__amdLicTest = {ok: false, error: (e && e.name ? e.name + ': ' : '') + (e && e.message ? e.message : e)}; }"
    "})();"
    "'started';"
)
LIC_READ_JS = "(JSON.stringify(window.__amdLicTest) || 'MISSING')"


def main() -> int:
    ensure_widevine_user_dir()
    cdm = find_usable_cdm()
    print(f"selected CDM: {cdm} (version {cdm_version(cdm)})", flush=True)
    if cdm is None:
        print("no usable CDM found", flush=True)
        return 2
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    if "--widevine-cdm-path" not in flags:
        flags = f"{flags} --widevine-cdm-path={cdm}".strip()
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags

    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    js = LICENSE_JS.replace("__PSSH__", json.dumps(PSSH_B64)).replace(
        "__LICURL__", json.dumps(LICENSE_URL)
    )
    app = QApplication([])
    view = QWebEngineView()
    state: dict = {"polls": 0, "code": 1}

    def finish(code: int, message: str) -> None:
        print(message, flush=True)
        state["code"] = code
        app.exit(code)

    def poll() -> None:
        state["polls"] += 1
        view.page().runJavaScript(LIC_READ_JS, on_read)

    def on_read(result: object) -> None:
        raw = result if isinstance(result, str) else ""
        if raw in ("", "MISSING", None):
            if state["polls"] >= 25:
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
            finish(0, f"LICENSE EXCHANGE OK: {json.dumps(data)}")
        elif isinstance(data, dict) and str(data.get("error", "")).startswith("stage:"):
            if state["polls"] >= 25:
                finish(1, f"TIMEOUT in flight: {data.get('error')}")
            else:
                QTimer.singleShot(1000, poll)
        else:
            error = data.get("error", data) if isinstance(data, dict) else data
            finish(1, f"LICENSE EXCHANGE FAILED: {error}")

    view.loadFinished.connect(lambda _ok: view.page().runJavaScript(js, lambda _r: QTimer.singleShot(1500, poll)))
    view.setHtml("<html><body>license probe</body></html>", QUrl("https://music.amazon.fr/"))
    QTimer.singleShot(45000, lambda: finish(1, "TIMEOUT: page never loaded"))
    app.exec()
    return state["code"]


if __name__ == "__main__":
    raise SystemExit(main())
