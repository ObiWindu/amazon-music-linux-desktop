# Test Report

- Unit tests: 208 passed (startup wiring order, playback_monitor incl. play-never-PLAYING, progression/stall evidence (progress never PLAYING, frozen timeupdate stays BUFFERING, advancing timeupdate recovers STALLED, watchdog fed by movement only) and iframe-safe instrumentation, playback_diagnostics incl. VMP/license-stage evidence, timeline builder, transport strategy records, media-session corroboration without titles, navigation reset, mpris incl. http(s)-only artwork, drm_diagnostics incl. CDM inventory with eligibility flag, native + engine-lookup user-dir links, READY status, explicit-CDM and malformed-binary rejection, stale-flag replacement, manifest-gated selection (missing/malformed/versionless/arch-incompatible/empty-with-manifest rejected, bare engine-path library electable as last resort), engine-default-path discovery + status, loaded-CDM process-tree observation with tree scope, zero-size stub exclusion)
- Security tests: 4 passed
- Integration tests: 27 passed, incl. live Amazon homepage load, first-run lifecycle (0700 profile dirs, engine lookup links, engine flag), verdict UNKNOWN/MATCH/MISMATCH, audio-output-gated-on-position, navigation reset, iframe instrumentation (offscreen; QtWebEngine loads https://music.amazon.fr/ OK)
- Total: 239 passed, 0 failed
- Headless EME probe (scripts/probe-cdm-session.py, self-contained): CDM SESSION OK with 4.10.3112.0 via the engine's user-level lookup path; /proc maps confirm helpers hold that binary (verdict MATCH). License stage untested — needs an Amazon account (see PLAYBACK_FAILURE_TIMELINE.md entry 2026-11-03)
- Device audio: PCM playback path verified (`pw-play` exit 0; null sink only in this session — audible check needs hardware)
- Static: ruff clean; mypy src --ignore-missing-imports clean
- All tests run without an Amazon account or DRM playback.
- Protected-playback verification still requires a real account; a passing
  CDM/session test does not count as playback (see PLAYBACK_FAILURE_TIMELINE.md).
