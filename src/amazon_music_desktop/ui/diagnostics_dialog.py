"""Diagnostics dialog."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout

from ..browser.drm_diagnostics import (
    CDM_PATH,
    CDM_SESSION_PROBE_JS,
    CDM_TEST_READ_JS,
    browser_info,
    cdm_probe_state,
    cdm_version,
    detect_freeworld,
    find_usable_cdm,
    format_stage,
    parse_cdm_session_result,
    run_stage_a,
)
from ..services.health_check import collect_health
from ..services.logging_service import get_logger

log = get_logger("diagnostics")


class DiagnosticsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Diagnostics")
        self.resize(720, 520)
        layout = QVBoxLayout(self)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)
        btns = QHBoxLayout()
        run_btn = QPushButton("Run diagnostics")
        run_btn.clicked.connect(self.run)
        cdm_btn = QPushButton("Test CDM session")
        cdm_btn.setToolTip("Create a Widevine MediaKeySession: proves the CDM loads")
        cdm_btn.clicked.connect(self.test_cdm_session)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(run_btn)
        btns.addWidget(cdm_btn)
        btns.addWidget(close_btn)
        layout.addLayout(btns)
        self.run()

    def test_cdm_session(self) -> None:
        page = self._browser_page()
        if page is None:
            self.text.setPlainText("No browser page available for CDM test.")
            return
        self._cdm_page = page
        self._cdm_attempts = 0
        self._cdm_restarts = 0
        self.text.setPlainText(
            "Testing CDM session (creates MediaKeys + session)...\n"
            "the result appears within a few seconds."
        )
        # QtWebEngine does not resolve returned Promises to Python, so the
        # probe stores its result on window and we poll it back. The page
        # can reload while we wait (the SPA re-navigates during boot and
        # periodically), which wipes the marker - hence polling + one restart.
        try:
            page.runJavaScript(CDM_SESSION_PROBE_JS, self._on_probe_started)
        except Exception as exc:
            self.text.setPlainText(f"CDM session test failed to start: {exc}")
            return
        from PySide6.QtCore import QTimer

        QTimer.singleShot(1500, self._cdm_poll)

    def _browser_page(self):
        window = self.parent()
        return getattr(getattr(window, "view", None), "page", lambda: None)()

    def _on_probe_started(self, result) -> None:
        if result != "started":
            log.warning("CDM probe evaluate returned unexpected: %r", result)
            self._cdm_note(f"probe evaluate returned {result!r} (page may still be loading)")

    def _cdm_poll(self) -> None:
        if not self.isVisible():
            return
        page = self._cdm_page
        if page is None:
            return
        self._cdm_attempts += 1
        try:
            page.runJavaScript(CDM_TEST_READ_JS, self._cdm_on_poll)
        except Exception as exc:
            self._cdm_finish(f"CDM session test failed to read back: {exc}")

    def _cdm_on_poll(self, result) -> None:
        from PySide6.QtCore import QTimer

        if not self.isVisible():
            return
        state, raw = cdm_probe_state(result)
        if state == "missing":
            if self._cdm_restarts == 0:
                # The marker vanished: the document we probed was replaced.
                # Re-run the probe on the current document, keep polling.
                self._cdm_restarts += 1
                try:
                    self._cdm_page.runJavaScript(CDM_SESSION_PROBE_JS, self._on_probe_started)
                except Exception as exc:
                    self._cdm_finish(f"CDM session probe restart failed: {exc}")
                    return
            if self._cdm_attempts >= 8:
                self._cdm_finish(
                    "probe marker never appeared on the page\n"
                    "(the page kept reloading during the test, or JavaScript\n"
                    "evaluation was blocked). Retry once the page is loaded and idle."
                )
                return
        elif state == "progress":
            stage = str(raw.get("error", "")) if isinstance(raw, dict) else str(raw)
            if self._cdm_attempts >= 8:
                self._cdm_finish(f"probe did not finish (hung at: {stage})")
                return
            self._cdm_note(f"in progress: {stage}")
        else:
            if isinstance(raw, dict):
                self._cdm_finish(format_stage(parse_cdm_session_result(raw)))
            else:
                self._cdm_finish(f"unexpected raw value: {raw!r}")
            return
        QTimer.singleShot(1500, self._cdm_poll)

    def _cdm_finish(self, message: str) -> None:
        current = self.text.toPlainText()
        self.text.setPlainText(
            current
            + "\n\n=== Widevine Stage C (live) ===\n"
            + message
            + "\n\nnote: a successful CDM session does not imply protected playback;"
            "\nAmazon's license service currently rejects this CDM server-side"
            " (VMP_VALIDATION_FAILED)."
        )

    def _cdm_note(self, message: str) -> None:
        current = self.text.toPlainText()
        self.text.setPlainText(current + f"\n{message}")

    def run(self) -> None:
        lines = []
        lines.append("=== System ===")
        for k, v in collect_health().items():
            lines.append(f"{k}: {v}")
        lines.append("")
        lines.append("=== Browser ===")
        for k, v in browser_info().items():
            lines.append(f"{k}: {v}")
        lines.append("")
        lines.append("=== Widevine Stage A ===")
        lines.append(format_stage(run_stage_a()))
        lines.append("")
        lines.append(f"CDM path: {CDM_PATH}")
        lines.append(f"CDM in use: {find_usable_cdm()}")
        lines.append(f"CDM version: {cdm_version()}")
        freeworld = detect_freeworld()
        lines.append(f"libavcodec-freeworld (Fedora freeworld codec library): {freeworld}")
        lines.append("note: AAC/MP3 decode verified working in this WebEngine build;")
        lines.append("use 'Test CDM session' to check whether the CDM itself loads.")
        self.text.setPlainText("\n".join(lines))
