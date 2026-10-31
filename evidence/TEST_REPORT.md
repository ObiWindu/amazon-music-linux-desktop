# Test Report

- Unit tests: 205 passed (startup wiring order, playback_monitor incl. play-never-PLAYING, progression/stall evidence (progress never PLAYING, frozen timeupdate stays BUFFERING, advancing timeupdate recovers STALLED) and iframe-safe instrumentation, playback_diagnostics incl. VMP/license-stage evidence, timeline builder, transport strategy records, media-session corroboration without titles, navigation reset, mpris incl. http(s)-only artwork, drm_diagnostics incl. CDM inventory with eligibility flag, native-only user-dir links, READY status, explicit-CDM and malformed-binary rejection, manifest-gated selection (missing/malformed/versionless/arch-incompatible/empty-with-manifest rejected, bare engine-path library electable as last resort), engine-default-path discovery + status, loaded-CDM process-tree observation with tree scope, zero-size stub exclusion)
- Security tests: 4 passed
- Integration tests: 22 passed, 1 pre-existing network failure excluded (offscreen; includes playback observability wiring, verdict UNKNOWN/MATCH/MISMATCH section labels, navigation reset, media-session snapshot dedup, iframe instrumentation, plus all prior coverage)
- Total: 231 passed, 0 failed (test_go_home excluded: requires live Amazon network; fails identically on pristine tree)
- Headless EME probe (scripts/probe-cdm-session.py): CDM SESSION FAILED on this host — engine ignores --widevine-cdm-path, 0-byte distro stub (see PLAYBACK_FAILURE_TIMELINE.md addendum 2026-10-31)
- Static: ruff clean; mypy src --ignore-missing-imports clean
- All tests run without an Amazon account or DRM playback.
- Protected-playback verification still requires a real account; a passing
  CDM/session test does not count as playback (see PLAYBACK_FAILURE_TIMELINE.md).
