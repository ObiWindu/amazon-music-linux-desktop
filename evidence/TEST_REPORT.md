# Test Report

- Unit tests: 214 passed (startup wiring order, playback_monitor incl. play-never-PLAYING, browser-claim vs position-confirmed PLAYING, progression/stall evidence (progress never PLAYING, frozen timeupdate stays BUFFERING, advancing timeupdate recovers STALLED, watchdog fed by movement only) and iframe-safe instrumentation, playback_diagnostics incl. VMP/license-stage evidence, timeline builder, transport strategy records, media-session corroboration without titles, navigation reset, mpris incl. http(s)-only artwork (Playing kept: MPRIS has no unconfirmed state, documented), drm_diagnostics incl. CDM inventory with eligibility flag, native + engine-lookup user-dir links, READY status, explicit-CDM and malformed-binary rejection, stale-flag replacement, manifest-gated selection (missing/malformed/versionless/arch-incompatible/empty-with-manifest rejected, bare engine-path library electable as last resort), engine-default-path discovery + status, loaded-CDM process-tree observation with tree scope, zero-size stub exclusion, probe exit-code contract 0/1/2/3)
- Security tests: 4 passed
- Integration tests: 28 passed, incl. live Amazon homepage load, first-run lifecycle (clean profile, 0700 dirs, engine lookup links, engine flag), verdict UNKNOWN/MATCH/MISMATCH, audio-output-gated-on-position, status-label confirming-vs-confirmed PLAYING, navigation reset, iframe instrumentation (offscreen)
- Total: 246 passed, 0 failed
- Headless EME probes (self-contained, no account): session probe exit 0 (`CDM SESSION OK`, verdict MATCH on 4.10.3112.0); license-exchange probe exit 0 (`LICENSE EXCHANGE OK`, keys usable vs UAT test server — proves CDM health, not Amazon acceptance). See PLAYBACK_FAILURE_TIMELINE.md entry 2026-11-03
- Device audio: PCM playback path verified (`pw-play` exit 0; null sink only in this session — audible check needs hardware)
- Static: ruff clean; mypy src --ignore-missing-imports clean
- All tests run without an Amazon account or DRM playback.
- Protected-playback verification still requires a real account; a passing
  CDM/session test does not count as playback (see PLAYBACK_FAILURE_TIMELINE.md).
