"""Playback pipeline diagnostics for Amazon Music Desktop.

Tracks the observable stages of protected playback (remediation spec 4.1) and
classifies failures into standardized error codes (spec 4.3). A stage is only
ever marked VERIFIED on direct evidence: a successful stage is never inferred
from CDM presence or from a later stage having succeeded.

Reports are structured, timestamped, and redacted through
``services.logging_service``: license traffic, credentials, account
identifiers, and personal listening information never enter this module's
output.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..services.logging_service import redact_text, sanitize_url

# Pipeline stages from the remediation specification. Stages that public
# browser APIs cannot observe stay UNKNOWN; media_request_initiated is
# NOT_APPLICABLE (no public API reports it) and is marked when track
# selection is verified.
PLAYBACK_PIPELINE_STAGES: tuple[str, ...] = (
    "amazon_music_page_loaded",
    "track_selection_initiated",
    "media_request_initiated",
    "encrypted_media_detected",
    "eme_key_system_negotiation_attempted",
    "cdm_initialization_attempted",
    "license_acquisition_attempted",
    "decryption_key_availability_established",
    "media_decoding_started",
    "audio_output_started",
)

PLAYBACK_PIPELINE_LABELS: dict[str, str] = {
    "amazon_music_page_loaded": "Amazon Music page loaded",
    "track_selection_initiated": "Track selection initiated",
    "media_request_initiated": "Media request initiated",
    "encrypted_media_detected": "Encrypted media detected",
    "eme_key_system_negotiation_attempted": "EME key-system negotiation attempted",
    "cdm_initialization_attempted": "CDM initialization attempted",
    "license_acquisition_attempted": "License acquisition attempted",
    "decryption_key_availability_established": "Decryption/key availability established",
    "media_decoding_started": "Media decoding started",
    "audio_output_started": "Audio output started",
}


class DiagnosticStatus(str, Enum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


PipelineStatus = DiagnosticStatus


class FailureCode(str, Enum):
    DRM_NOT_FOUND = "DRM_NOT_FOUND"
    DRM_ARCH_MISMATCH = "DRM_ARCH_MISMATCH"
    DRM_MANIFEST_INVALID = "DRM_MANIFEST_INVALID"
    DRM_INIT_FAILED = "DRM_INIT_FAILED"
    EME_UNSUPPORTED = "EME_UNSUPPORTED"
    LICENSE_FAILED = "LICENSE_FAILED"
    MEDIA_DECODE_FAILED = "MEDIA_DECODE_FAILED"
    MEDIA_STALLED = "MEDIA_STALLED"
    AUDIO_OUTPUT_FAILED = "AUDIO_OUTPUT_FAILED"
    UNKNOWN_PLAYBACK_ERROR = "UNKNOWN_PLAYBACK_ERROR"


PlaybackErrorCode = FailureCode

# Console-message markers that constitute direct evidence that a license
# request was attempted and rejected — e.g. Amazon's documented HTTP 400
# `denialReason: VMP_VALIDATION_FAILED`. Only the error text is captured
# (redacted); license bodies, headers, and keys are never stored.
LICENSE_FAILURE_MARKERS: tuple[str, ...] = (
    "vmp_validation_failed",
    "vmp validation failed",
    "denialreason",
    "license request failed",
    "license request rejected",
    "license denied",
)


def looks_like_license_failure(message: str) -> bool:
    """True when a console error is direct evidence of license rejection."""
    low = str(message or "").lower()
    return any(marker in low for marker in LICENSE_FAILURE_MARKERS)


@dataclass
class PipelineStage:
    name: str
    label: str = ""
    status: DiagnosticStatus = DiagnosticStatus.UNKNOWN
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    timestamp: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.name,
            "label": self.label or PLAYBACK_PIPELINE_LABELS.get(self.name, self.name),
            "status": self.status.value,
            "details": dict(self.details),
            "error": redact_text(self.error) if self.error else None,
            "timestamp": self.timestamp,
        }


@dataclass
class DiagnosticEvent:
    kind: str
    message: str
    timestamp: float = field(default_factory=time.time)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "message": redact_text(self.message),
            "timestamp": self.timestamp,
            "details": {
                k: (redact_text(v) if isinstance(v, str) else v)
                for k, v in self.details.items()
            },
        }


class PlaybackPipeline:
    """Mutable model of the observable playback pipeline stages."""

    def __init__(self, stages: tuple[str, ...] | list[str] | None = None) -> None:
        names = stages if stages is not None else PLAYBACK_PIPELINE_STAGES
        self._stages: dict[str, PipelineStage] = {
            name: PipelineStage(name=name, label=PLAYBACK_PIPELINE_LABELS.get(name, name))
            for name in names
        }

    def stages(self) -> list[PipelineStage]:
        return list(self._stages.values())

    def stage_names(self) -> list[str]:
        return list(self._stages.keys())

    def get(self, name: str) -> PipelineStage | None:
        return self._stages.get(name)

    def mark(
        self,
        stage: str,
        status: DiagnosticStatus | str,
        *,
        details: dict[str, Any] | None = None,
        error: str | None = None,
        timestamp: float | None = None,
    ) -> PipelineStage:
        if stage not in self._stages:
            self._stages[stage] = PipelineStage(
                name=stage, label=PLAYBACK_PIPELINE_LABELS.get(stage, stage)
            )
        st = self._stages[stage]
        if isinstance(status, DiagnosticStatus):
            st.status = status
        else:
            try:
                st.status = DiagnosticStatus(str(status).upper())
            except ValueError:
                st.status = DiagnosticStatus.UNKNOWN
        if details:
            st.details.update(details)
        if error is not None:
            st.error = redact_text(str(error))
        st.timestamp = time.time() if timestamp is None else float(timestamp)
        return st

    def verify(self, stage: str, **kwargs: Any) -> PipelineStage:
        return self.mark(stage, DiagnosticStatus.VERIFIED, **kwargs)

    def fail(self, stage: str, **kwargs: Any) -> PipelineStage:
        return self.mark(stage, DiagnosticStatus.FAILED, **kwargs)

    def reset(self) -> None:
        for stage in self._stages.values():
            stage.status = DiagnosticStatus.UNKNOWN
            stage.details = {}
            stage.error = None
            stage.timestamp = None

    def to_dict(self) -> dict[str, Any]:
        return {name: stage.to_dict() for name, stage in self._stages.items()}

    def summary(self) -> dict[str, str]:
        return {name: stage.status.value for name, stage in self._stages.items()}


class PlaybackDiagnostics:
    """Collects structured, redacted playback and browser diagnostics."""

    def __init__(self, pipeline: PlaybackPipeline | None = None) -> None:
        self.pipeline = pipeline if pipeline is not None else PlaybackPipeline()
        self.events: list[DiagnosticEvent] = []
        self._last_error: str | None = None
        self._failure_code: FailureCode | None = None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def failure_code(self) -> FailureCode | None:
        return self._failure_code

    def _record(self, kind: str, message: str, details: dict[str, Any] | None) -> DiagnosticEvent:
        # Redact at capture time: the stored event never holds credentials or
        # license traffic, even if a future caller reads raw events.
        event = DiagnosticEvent(
            kind=kind,
            message=redact_text(str(message)),
            details={
                k: (redact_text(str(v)) if isinstance(v, str) else v)
                for k, v in (details or {}).items()
            },
        )
        self.events.append(event)
        if len(self.events) > 500:
            self.events = self.events[-500:]
        self._last_error = redact_text(event.message)
        return event

    # --- browser-side evidence -------------------------------------------

    def record_console_error(
        self, message: str, source: str | None = None, line: int | None = None
    ) -> DiagnosticEvent:
        event = self._record(
            "console_error",
            message,
            {"source": sanitize_url(source) if source else None, "line": line},
        )
        if looks_like_license_failure(message):
            # Direct evidence from the page: a license operation was attempted
            # and rejected. This is the only way this stage becomes FAILED.
            self.pipeline.mark(
                "license_acquisition_attempted",
                DiagnosticStatus.FAILED,
                error=event.message,
            )
            self._failure_code = FailureCode.LICENSE_FAILED
        return event

    def record_load_error(
        self, url: str | None = None, error: str | None = None
    ) -> DiagnosticEvent:
        return self._record(
            "load_error",
            error or "page load failed",
            {"url": sanitize_url(url) if url else None},
        )

    def record_renderer_termination(
        self, status: Any = None, code: Any = None
    ) -> DiagnosticEvent:
        return self._record(
            "renderer_terminated",
            f"render process terminated: status={status} code={code}",
            {"status": status, "code": code},
        )

    def record_media_error(self, message: str, **details: Any) -> DiagnosticEvent:
        self.classify(message, **details)
        return self._record("media_error", message, details)

    def record_player_action_missed(self, action: str) -> DiagnosticEvent:
        """A transport action found no target on the page: observable, and
        never a false success — the UI only updates from the page probe."""
        return self._record(
            "player_action_missed",
            f"transport action had no target on the page: {action}",
            {"action": action},
        )

    def record_player_action(self, action: str, outcome: str) -> DiagnosticEvent:
        """Record how a transport action was dispatched on the page.

        ``outcome`` is the verbatim strategy token returned by the page
        snippet (``play``/``pause`` for the media-element toggle,
        ``sel:<label>`` for a selector click, ``geom:<x>:<label>`` for the
        geometry fallback, ``seek``/``vol:..`` for seek/volume). An empty
        outcome is recorded as a miss. Success here means the click was
        *dispatched* — playback state still comes only from the monitor.
        """
        if not outcome:
            return self.record_player_action_missed(action)
        return self._record(
            "player_action",
            f"transport action dispatched on the page: {action} ({outcome[:60]})",
            {"action": action, "strategy": outcome[:80]},
        )

    # --- pipeline stage evidence -----------------------------------------

    def note_page_loaded(self, url: str | None = None, ok: bool = True) -> None:
        if ok:
            self.pipeline.verify(
                "amazon_music_page_loaded", details={"url": sanitize_url(url) if url else None}
            )
        else:
            self.pipeline.fail("amazon_music_page_loaded", error="page load failed")
            self.record_load_error(url)

    def note_track_selected(self) -> None:
        # Media request initiation is not observable through public APIs; the
        # remaining EME stages stay UNKNOWN until real evidence arrives.
        self.pipeline.verify("track_selection_initiated")
        self.pipeline.mark(
            "media_request_initiated",
            DiagnosticStatus.NOT_APPLICABLE,
            details={"reason": "not observable via public browser APIs"},
        )

    def note_encrypted_media(self, timestamp: float | None = None) -> None:
        self.pipeline.verify("encrypted_media_detected", timestamp=timestamp)

    def note_media_decoding(self, timestamp: float | None = None) -> None:
        self.pipeline.verify("media_decoding_started", timestamp=timestamp)

    def note_audio_output(self, timestamp: float | None = None) -> None:
        self.pipeline.verify("audio_output_started", timestamp=timestamp)

    def note_cdm_session(self, ok: bool, error: str | None = None) -> None:
        stage = "cdm_initialization_attempted"
        if ok:
            self.pipeline.verify(stage)
        else:
            self.pipeline.fail(stage, error=error or "CDM session test failed")
            self.set_failure_code(
                classify_failure(error or "cdm init failed", cdm=True)
            )
            self.record_cdm_error(error or "CDM session test failed")

    def record_cdm_error(self, message: str, **details: Any) -> DiagnosticEvent:
        return self._record("cdm_error", message, details)

    def mark_stage(
        self, stage: str, status: DiagnosticStatus | str, **kwargs: Any
    ) -> PipelineStage:
        return self.pipeline.mark(stage, status, **kwargs)

    # --- failure classification ------------------------------------------

    def classify(self, message: str = "", **evidence: Any) -> FailureCode:
        code = classify_failure(message, **evidence)
        self._failure_code = code
        self._last_error = redact_text(str(message)) if message else self._last_error
        return code

    def set_failure_code(self, code: FailureCode | str | None) -> None:
        if code is None:
            self._failure_code = None
            return
        if isinstance(code, FailureCode):
            self._failure_code = code
            return
        try:
            self._failure_code = FailureCode(str(code))
        except ValueError:
            self._failure_code = FailureCode.UNKNOWN_PLAYBACK_ERROR

    # --- reporting ---------------------------------------------------------

    def build_timeline(self) -> list[dict[str, Any]]:
        """Ordered per-stage timeline for one playback attempt (Phase 1).

        Stages without evidence report UNKNOWN; NOT_APPLICABLE stages were
        never observable through public browser APIs in the first place.
        """
        timeline: list[dict[str, Any]] = []
        for stage in self.pipeline.stages():
            entry = stage.to_dict()
            entry["observed"] = stage.status in (
                DiagnosticStatus.VERIFIED,
                DiagnosticStatus.FAILED,
            )
            timeline.append(entry)
        return timeline

    def timeline_report(self) -> str:
        lines = ["Playback attempt timeline:"]
        for entry in self.build_timeline():
            stamp = f"{entry['timestamp']:.3f}" if entry["timestamp"] else "-"
            lines.append(f"[{stamp}] {entry['label']}: {entry['status']}")
            if entry["error"]:
                lines.append(f"    error: {entry['error']}")
        return "\n".join(lines)

    def to_report(self) -> str:
        lines: list[str] = []
        lines.append("=== Playback Diagnostics ===")
        lines.append(
            f"Last error: {redact_text(self._last_error) if self._last_error else 'none'}"
        )
        lines.append(
            f"Failure code: {self._failure_code.value if self._failure_code else 'none'}"
        )
        lines.append("")
        lines.append("=== Pipeline ===")
        for stage in self.pipeline.stages():
            lines.append(f"{stage.to_dict()['label']}: {stage.status.value}")
            if stage.error:
                lines.append(f"  error: {stage.error}")
            for k, v in stage.details.items():
                lines.append(
                    f"  {k}: {redact_text(str(v)) if isinstance(v, str) else v}"
                )
        lines.append("")
        lines.append("=== Events ===")
        for event in self.events[-50:]:
            d = event.to_dict()
            lines.append(f"{d['timestamp']:.3f} {d['kind']}: {d['message']}")
        return "\n".join(lines)

    # Names kept for callers that treat the collector as a report source.
    def export_report(self) -> str:
        return self.to_report()

    def redacted_report(self) -> str:
        return self.to_report()


def classify_failure(message: Any = "", **evidence: Any) -> FailureCode:
    """Classify a failure from available evidence; never guess without any."""
    parts = [str(message or "")]
    parts.extend(f"{k}={v}" for k, v in evidence.items())
    low = " ".join(parts).lower()
    if "drm_not_found" in low or "no compatible cdm" in low or "cdm not found" in low or "no usable" in low:
        return FailureCode.DRM_NOT_FOUND
    if "arch" in low and ("mismatch" in low or "incompatible" in low):
        return FailureCode.DRM_ARCH_MISMATCH
    if "manifest" in low and ("invalid" in low or "malformed" in low):
        return FailureCode.DRM_MANIFEST_INVALID
    if ("cdm" in low or "widevine" in low or "mediakeys" in low) and (
        "init" in low or "session" in low
    ):
        return FailureCode.DRM_INIT_FAILED
    if "eme" in low and ("unsupported" in low or "not supported" in low):
        return FailureCode.EME_UNSUPPORTED
    if "vmp" in low or "license" in low or "denialreason" in low:
        return FailureCode.LICENSE_FAILED
    if "decode" in low or "decoder" in low or "codec" in low:
        return FailureCode.MEDIA_DECODE_FAILED
    if "stall" in low:
        return FailureCode.MEDIA_STALLED
    if "audio" in low and ("output" in low or "device" in low):
        return FailureCode.AUDIO_OUTPUT_FAILED
    for code in FailureCode:
        if code.value in low:
            return code
    return FailureCode.UNKNOWN_PLAYBACK_ERROR
