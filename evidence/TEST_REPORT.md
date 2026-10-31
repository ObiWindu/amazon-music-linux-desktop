# Test Report

- Unit tests: 148 passed (includes new playback_monitor, playback_diagnostics, mpris suites)
- Security tests: 4 passed
- Integration tests: 6 passed (offscreen)
- Total: 158 passed, 0 failed
- Static: ruff clean; mypy src --ignore-missing-imports clean
- New coverage: playback state transitions, media event processing, browser
  payload replay (dedup), stall detection, failure classification, diagnostic
  report redaction (including Bearer-token ordering), MPRIS status/metadata
  sync and transport forwarding, CDM architecture-aware validation and
  manifest/install-status classification.
- All tests run without an Amazon account or DRM playback; protected playback
  verification still requires a real account (see DRM_REPORT.md).
