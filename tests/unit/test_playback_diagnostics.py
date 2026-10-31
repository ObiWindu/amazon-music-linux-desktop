"""Unit tests for playback pipeline diagnostics and report redaction."""

from __future__ import annotations

from amazon_music_desktop.browser.playback_diagnostics import (
    PLAYBACK_PIPELINE_STAGES,
    DiagnosticStatus,
    FailureCode,
    PlaybackDiagnostics,
    PlaybackPipeline,
    classify_failure,
)


def test_pipeline_defaults_are_unknown():
    pipeline = PlaybackPipeline()
    assert pipeline.stage_names() == list(PLAYBACK_PIPELINE_STAGES)
    assert len(pipeline.stages()) == 10
    assert set(pipeline.summary().values()) == {"UNKNOWN"}


def test_mark_verify_and_fail():
    pipeline = PlaybackPipeline()
    stage = pipeline.verify("amazon_music_page_loaded")
    assert stage.status == DiagnosticStatus.VERIFIED
    assert stage.timestamp is not None
    stage = pipeline.fail("track_selection_initiated", error="no track")
    assert stage.status == DiagnosticStatus.FAILED
    assert stage.error == "no track"


def test_mark_unknown_stage_and_invalid_status():
    pipeline = PlaybackPipeline()
    stage = pipeline.mark("unlisted_stage", "VERIFIED")
    assert stage.name == "unlisted_stage"
    assert pipeline.get("unlisted_stage") is stage
    assert pipeline.mark("unlisted_stage", "bogus").status == DiagnosticStatus.UNKNOWN


def test_track_selection_marks_media_request_not_applicable():
    diagnostics = PlaybackDiagnostics()
    diagnostics.note_track_selected()
    summary = diagnostics.pipeline.summary()
    assert summary["track_selection_initiated"] == "VERIFIED"
    assert summary["media_request_initiated"] == "NOT_APPLICABLE"
    # EME stages stay UNKNOWN: no evidence yet
    assert summary["eme_key_system_negotiation_attempted"] == "UNKNOWN"
    assert summary["cdm_initialization_attempted"] == "UNKNOWN"


def test_page_loaded_verified_and_failed():
    diagnostics = PlaybackDiagnostics()
    diagnostics.note_page_loaded(ok=True)
    assert diagnostics.pipeline.summary()["amazon_music_page_loaded"] == "VERIFIED"
    diagnostics.note_page_loaded(url="https://music.example/session?token=abc", ok=False)
    assert diagnostics.pipeline.summary()["amazon_music_page_loaded"] == "FAILED"
    kinds = [e.kind for e in diagnostics.events]
    assert "load_error" in kinds
    # the session token never reaches the stored event
    assert "token=abc" not in diagnostics.to_report()


def test_encrypted_and_decoding_stages_verified():
    diagnostics = PlaybackDiagnostics()
    diagnostics.note_encrypted_media(timestamp=10.0)
    diagnostics.note_media_decoding(timestamp=11.0)
    diagnostics.note_audio_output(timestamp=12.0)
    summary = diagnostics.pipeline.summary()
    assert summary["encrypted_media_detected"] == "VERIFIED"
    assert summary["media_decoding_started"] == "VERIFIED"
    assert summary["audio_output_started"] == "VERIFIED"
    assert diagnostics.pipeline.get("encrypted_media_detected").timestamp == 10.0


def test_cdm_session_failure_marks_stage_and_code():
    diagnostics = PlaybackDiagnostics()
    diagnostics.note_cdm_session(False, error="CDM session test failed: rejected")
    summary = diagnostics.pipeline.summary()
    assert summary["cdm_initialization_attempted"] == "FAILED"
    assert diagnostics.failure_code == FailureCode.DRM_INIT_FAILED
    assert any(e.kind == "cdm_error" for e in diagnostics.events)


def test_cdm_session_success_marks_stage_verified():
    diagnostics = PlaybackDiagnostics()
    diagnostics.note_cdm_session(True)
    assert diagnostics.pipeline.summary()["cdm_initialization_attempted"] == "VERIFIED"


def test_decrypt_stage_never_verified_without_evidence():
    diagnostics = PlaybackDiagnostics()
    # nothing happened at all: no stage may claim success, and
    # media_request_initiated is only marked N/A once selection is verified
    assert set(diagnostics.pipeline.summary().values()) == {"UNKNOWN"}
    diagnostics.note_track_selected()
    summary = diagnostics.pipeline.summary()
    assert summary["media_request_initiated"] == "NOT_APPLICABLE"


def test_classify_failure_codes():
    cases = {
        "no compatible CDM discovered": FailureCode.DRM_NOT_FOUND,
        "CDM not found under /var/lib/widevine": FailureCode.DRM_NOT_FOUND,
        "architecture mismatch: CDM is x86_64, host is aarch64": FailureCode.DRM_ARCH_MISMATCH,
        "manifest.json invalid": FailureCode.DRM_MANIFEST_INVALID,
        "manifest malformed": FailureCode.DRM_MANIFEST_INVALID,
        "CDM init failed": FailureCode.DRM_INIT_FAILED,
        "widevine session setup failed": FailureCode.DRM_INIT_FAILED,
        "EME unsupported by this build": FailureCode.EME_UNSUPPORTED,
        "denialReason: VMP_VALIDATION_FAILED": FailureCode.LICENSE_FAILED,
        "license request returned 400 ForbiddenException": FailureCode.LICENSE_FAILED,
        "decoder failure": FailureCode.MEDIA_DECODE_FAILED,
        "unsupported codec": FailureCode.MEDIA_DECODE_FAILED,
        "media stalled for 12s": FailureCode.MEDIA_STALLED,
        "audio output device unavailable": FailureCode.AUDIO_OUTPUT_FAILED,
    }
    for message, expected in cases.items():
        assert classify_failure(message) == expected, message


def test_classify_failure_requires_evidence():
    # never guess: without evidence the failure is unclassified
    assert classify_failure("") == FailureCode.UNKNOWN_PLAYBACK_ERROR
    assert classify_failure(None) == FailureCode.UNKNOWN_PLAYBACK_ERROR
    assert classify_failure("something odd happened") == FailureCode.UNKNOWN_PLAYBACK_ERROR


def test_classify_failure_accepts_direct_code():
    assert classify_failure("DRM_ARCH_MISMATCH") == FailureCode.DRM_ARCH_MISMATCH
    assert classify_failure("boom", code="MEDIA_STALLED") == FailureCode.MEDIA_STALLED


def test_record_console_error_redacts_and_sanitizes():
    diagnostics = PlaybackDiagnostics()
    diagnostics.record_console_error(
        "request failed: Set-Cookie: session=abc123",
        source="https://music.amazon.com/path?token=secret&x=1",
        line=42,
    )
    event = diagnostics.events[0]
    assert "abc123" not in event.message
    assert "REDACTED" in event.message
    assert event.details["source"] == "https://music.amazon.com/path"
    assert event.details["line"] == 42


def test_record_renderer_termination():
    diagnostics = PlaybackDiagnostics()
    diagnostics.record_renderer_termination("Crashed", 11)
    assert diagnostics.last_error == "render process terminated: status=Crashed code=11"
    assert diagnostics.events[0].details == {"status": "Crashed", "code": 11}


def test_record_media_error_classifies_decode_failure():
    diagnostics = PlaybackDiagnostics()
    diagnostics.record_media_error("media decoder failure")
    assert diagnostics.failure_code == FailureCode.MEDIA_DECODE_FAILED


def test_report_is_structured_and_redacted():
    diagnostics = PlaybackDiagnostics()
    diagnostics.note_page_loaded(ok=True)
    diagnostics.note_track_selected()
    diagnostics.note_encrypted_media(timestamp=1.0)
    diagnostics.record_console_error("Authorization: Bearer abc.def.ghi", line=3)
    diagnostics.classify("license failed")

    report = diagnostics.to_report()
    assert "=== Playback Diagnostics ===" in report
    assert "=== Pipeline ===" in report
    assert "Track selection initiated: VERIFIED" in report
    assert "Failure code: LICENSE_FAILED" in report
    # redaction: token and account material never appear
    assert "Bearer" not in report
    assert "abc.def.ghi" not in report

    # every export path returns the same redacted report
    assert diagnostics.export_report() == report
    assert diagnostics.redacted_report() == report


def test_events_capped():
    diagnostics = PlaybackDiagnostics()
    for i in range(600):
        diagnostics.record_console_error(f"noise {i}")
    assert len(diagnostics.events) == 500


def test_set_failure_code_invalid_falls_back_to_unknown():
    diagnostics = PlaybackDiagnostics()
    diagnostics.set_failure_code("NOT_A_CODE")
    assert diagnostics.failure_code == FailureCode.UNKNOWN_PLAYBACK_ERROR
    diagnostics.set_failure_code(None)
    assert diagnostics.failure_code is None
