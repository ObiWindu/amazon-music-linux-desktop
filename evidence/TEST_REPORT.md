# Test Report

- Unit tests: 179 passed (playback_monitor incl. play-never-PLAYING and progression/stall evidence, playback_diagnostics incl. VMP/license-stage evidence, timeline builder and transport strategy records, mpris, drm_diagnostics incl. CDM inventory/version comparison, native-only user-dir links, READY status, explicit-CDM and malformed-binary rejection, loaded-CDM process-tree observation, zero-size stub exclusion; startup wiring order)
- Security tests: 4 passed
- Integration tests: 19 passed (offscreen; includes playback observability wiring: VMP console error to pipeline, renderer termination, monitor payload propagation, persistent profile, player-action miss/strategy observability, decoding-gated-on-duration, seek JS + MPRIS Seeked, arch-aware user agent)
- Total: 202 passed, 0 failed
- Static: ruff clean; mypy src --ignore-missing-imports clean
- All tests run without an Amazon account or DRM playback.
- Protected-playback verification still requires a real account; a passing
  CDM/session test does not count as playback (see PLAYBACK_FAILURE_TIMELINE.md).
