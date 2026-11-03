# DRM Report

- Stage A (library presence): PASS (aarch64, deps resolved; system CDM 4.10.2662.3)
- Stage B (EME/Widevine key system): PASS (com.widevine.alpha)
- Stage C (CDM init): **PASS as of 2026-11-03** — headless EME probe
  (`scripts/probe-cdm-session.py`, no flag) creates MediaKeys +
  MediaKeySession with the 4.10.3112.0 ARM64 build served from the engine's
  user-level lookup path; `/proc` maps confirm the helper processes hold
  exactly that binary (verdict MATCH). Full license exchange verified same
  day (`scripts/probe-cdm-license.py`): `generateRequest` → UAT test
  license server → `session.update` → keys `usable`, exit 0 — the CDM is
  fully capable; only Amazon's LD-device policy remains untested.
  (Regressed 2026-10-31 when only the flag mechanism was tested against
  the 0-byte distro stub; the earlier 2026-10-29 in-app success is
  consistent with a loadable component build, now reproduced headless.)
- Stage D (Amazon playback): PENDING (requires an Amazon account/subscription and audio output)

## License-stage status (the remaining blocker)

- Documented live failure (2026-10-29, CDM 4.10.2662.3): EME session created,
  `generateRequest()` OK, license POST to `music.amazon.fr/ZAZ/api/dmls/` →
  HTTP 400 `ForbiddenException`, `denialReason: VMP_VALIDATION_FAILED`
  ("UNVERIFIED request not eligible for LD content"); the page empties the
  media element and retries once. Full timeline:
  `evidence/PLAYBACK_FAILURE_TIMELINE.md`.
- CDM 4.10.3112.0 has NOT been verified against Amazon's license server;
  a passing CDM-session test does not count as license acceptance or
  playback. (It HAS completed full license exchanges with usable keys
  against the Widevine UAT test server — `scripts/probe-cdm-license.py`,
  2026-11-03 — which proves CDM health but says nothing about Amazon's
  LD-content device policy.)
- When a live run hits the rejection again, the app now classifies it from
  the page's console error: the playback pipeline marks
  `license_acquisition_attempted: FAILED` with failure code `LICENSE_FAILED`.
- If 4.10.3112.0 is also rejected, the blocker is Amazon's
  device-eligibility/attestation policy for this environment (ARM64 Asahi).
  That limitation is documented, not worked around.
