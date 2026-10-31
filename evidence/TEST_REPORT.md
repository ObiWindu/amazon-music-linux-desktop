# Test Report

- Unit tests: 158 passed (playback_monitor, playback_diagnostics incl. VMP/license-stage evidence and timeline builder, mpris, drm_diagnostics incl. CDM inventory/version comparison)
- Security tests: 4 passed
- Integration tests: 13 passed (offscreen; includes playback observability wiring: VMP console error to pipeline, renderer termination, monitor payload propagation, persistent profile, player-action miss observability)
- Total: 175 passed, 0 failed
- Static: ruff clean; mypy src --ignore-missing-imports clean
- All tests run without an Amazon account or DRM playback.
- Protected-playback verification still requires a real account; a passing
  CDM/session test does not count as playback (see PLAYBACK_FAILURE_TIMELINE.md).
