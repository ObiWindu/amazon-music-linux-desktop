"""Diagnostics dialog."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout

from ..browser.drm_diagnostics import (
    CDM_PATH,
    browser_info,
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
        from PySide6.QtCore import QTimer

        from ..browser.drm_diagnostics import CDM_SESSION_PROBE_JS

        window = self.parent()
        page = getattr(getattr(window, "view", None), "page", lambda: None)()
        if page is None:
            self.text.setPlainText("No browser page available for CDM test.")
            return
        self.text.setPlainText("Testing CDM session (creates MediaKeys + session)...")
        # QtWebEngine does not resolve returned Promises to Python, so the
        # probe stores its result on window and we read it back after a delay.
        try:
            page.runJavaScript(CDM_SESSION_PROBE_JS, self._on_probe_started)
        except Exception as exc:
            self.text.setPlainText(f"CDM session test failed to start: {exc}")
            return
        QTimer.singleShot(6000, self._fetch_cdm_session_result)

    def _on_probe_started(self, result) -> None:
        if result != "started":
            log.warning("CDM probe evaluate returned unexpected: %r", result)

    def _fetch_cdm_session_result(self) -> None:
        window = self.parent()
        page = getattr(getattr(window, "view", None), "page", lambda: None)()
        if page is None:
            return
        try:
            page.runJavaScript("window.__amdCdmTest", self._on_cdm_session_result)
        except Exception as exc:
            self.text.setPlainText(f"CDM session test failed to read back: {exc}")

    def _on_cdm_session_result(self, result) -> None:
        if result is None:
            raw = "None (probe script never ran: evaluation blocked or failed)"
        elif not isinstance(result, dict):
            raw = f"unexpected raw value: {result!r}"
        else:
            raw = None
        current = self.text.toPlainText()
        extra = f"\n\n=== Widevine Stage C (live) ===\n{raw}" if raw else (
            "\n\n=== Widevine Stage C (live) ===\n" + format_stage(parse_cdm_session_result(result))
        )
        self.text.setPlainText(current + extra)

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
        lines.append(f"freeworld WebEngine (proprietary codecs): {freeworld}")
        lines.append("note: AAC/MP3 decode verified working in this WebEngine build;")
        lines.append("use 'Test CDM session' to check whether the CDM itself loads.")
        self.text.setPlainText("\n".join(lines))
