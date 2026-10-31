# DRM Report

- Stage A (library presence): PASS (aarch64, deps resolved; system CDM 4.10.2662.3)
- Stage B (EME/Widevine key system): PASS (com.widevine.alpha)
- Stage C (CDM init): **FAIL as of 2026-10-31** — headless probes with the
  flag pointed at 4.10.3112.0 and at system 4.10.2662.3 (with and without
  `--no-sandbox`) all end in `NotSupportedError: CreateCdmFunc not
  available`. The engine ignores `--widevine-cdm-path` on this build and
  attempts only the 0-byte distro stub (see timeline addendum). The
  2026-10-29 in-app session success with 4.10.3112.0 does not reproduce.
- Stage D (Amazon playback): PENDING (requires an Amazon account/subscription and audio output)

## License-stage status (the remaining blocker)

- Documented live failure (2026-10-29, CDM 4.10.2662.3): EME session created,
  `generateRequest()` OK, license POST to `music.amazon.fr/ZAZ/api/dmls/` →
  HTTP 400 `ForbiddenException`, `denialReason: VMP_VALIDATION_FAILED`
  ("UNVERIFIED request not eligible for LD content"); the page empties the
  media element and retries once. Full timeline:
  `evidence/PLAYBACK_FAILURE_TIMELINE.md`.
- CDM 4.10.3112.0 has NOT been verified against the license server; a passing
  CDM-session test does not count as license acceptance or playback.
- When a live run hits the rejection again, the app now classifies it from
  the page's console error: the playback pipeline marks
  `license_acquisition_attempted: FAILED` with failure code `LICENSE_FAILED`.
- If 4.10.3112.0 is also rejected, the blocker is Amazon's
  device-eligibility/attestation policy for this environment (ARM64 Asahi).
  That limitation is documented, not worked around.
