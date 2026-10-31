# Test Report

- Unit tests: 189 passed (startup wiring order, playback_monitor incl. play-never-PLAYING, progression/stall evidence and iframe-safe instrumentation, playback_diagnostics incl. VMP/license-stage evidence, timeline builder, transport strategy records, media-session corroboration without titles, navigation reset, mpris incl. http(s)-only artwork, drm_diagnostics incl. CDM inventory/version comparison, native-only user-dir links, READY status, explicit-CDM and malformed-binary rejection, engine-default-path status, loaded-CDM process-tree observation, zero-size stub exclusion)
- Security tests: 4 passed
- Integration tests: 21 passed, 1 pre-existing network failure excluded (offscreen; includes playback observability wiring: VMP console error to pipeline, renderer termination, monitor payload propagation, persistent profile, player-action miss/strategy observability, decoding-gated-on-duration, seek JS + MPRIS Seeked, navigation reset, media-session snapshot dedup, iframe instrumentation, arch-aware user agent)
- Total: 214 passed, 0 failed (test_go_home excluded: requires live Amazon network; fails identically on pristine tree)
- Headless EME probe (scripts/probe-cdm-session.py): CDM SESSION FAILED on this host — engine ignores --widevine-cdm-path, 0-byte distro stub (see PLAYBACK_FAILURE_TIMELINE.md addendum 2026-10-31)
- Static: ruff clean; mypy src --ignore-missing-imports clean
- All tests run without an Amazon account or DRM playback.
- Protected-playback verification still requires a real account; a passing
  CDM/session test does not count as playback (see PLAYBACK_FAILURE_TIMELINE.md).
