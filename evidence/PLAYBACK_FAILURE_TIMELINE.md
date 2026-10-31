# Playback Failure Timeline — song selection ends at 0:00

Failure: selecting a song starts nothing audible; the player resets to 0:00.
Primary environment: Fedora Asahi Remix 44, aarch64 (the development host).

## Reproduction instructions

1. Launch the app (`scripts/run-dev.sh`) on a host with the persistent profile
   (`~/.local/share/amazon-music-desktop`) signed in to Amazon Music.
2. Select any song.
3. Open **Diagnostics**: the playback pipeline shows the per-stage statuses and
   the timeline; the log records console errors (redacted).
4. A license rejection appears as a console error containing
   `VMP_VALIDATION_FAILED`; the pipeline marks
   `license_acquisition_attempted: FAILED` with failure code `LICENSE_FAILED`.

## Timeline of one song-selection attempt

From the instrumented live run of 2026-10-29 (docs/TROUBLESHOOTING.md), with
the then-selected CDM 4.10.2662.3:

| # | Stage | Result | Evidence |
|---|---|---|---|
| 1 | Song selected | SUCCESS | queue panel `on_track` (page title/media session) |
| 2 | Playback action initiated | SUCCESS | page player transport responded |
| 3 | Media element activated | SUCCESS | `play`/`playing` events, media element has `currentSrc` |
| 4 | Encrypted media encountered | SUCCESS | `encrypted` event |
| 5 | EME key-system negotiation | SUCCESS | `com.widevine.alpha` accepted |
| 6 | MediaKeys creation | SUCCESS | `createMediaKeys()` OK |
| 7 | MediaKeySession creation | SUCCESS | `createSession()` OK, `generateRequest()` OK |
| 8 | License request initiated | SUCCESS | POST to `music.amazon.fr/ZAZ/api/dmls/` observed |
| 9 | License server response | **FAILED** | HTTP 400 `ForbiddenException`, `denialReason: VMP_VALIDATION_FAILED`, message: `UNVERIFIED request not eligible for LD content` |
| 10 | Media keys usable | **UNKNOWN** | never authorized (stage 9 failed) |
| 11 | Decoder starts | **FAILED** | page empties the media element and retries once; playback resets to 0:00 |
| 12 | Audio output | **NOT REACHED** | no audio observed |

The failure reproduces deterministically with CDM 4.10.2662.3 (the 2022
system build).

## Root-cause assessment

- The rejection is server-side at license acquisition, not an EME/CDM
  initialization failure: stages 4-7 succeed before the HTTP 400.
- `VMP_VALIDATION_FAILED` is Amazon validating the Widevine Verified Media
  Path (device attestation bound into the license request). The message says
  the request is "UNVERIFIED ... not eligible for LD content".
- Whether CDM 4.10.3112.0 (the component-updated build the app now prefers)
  passes this check is **not yet verified**: no licensed playback test has
  been run against the license server with that build. Initialization alone
  (MediaKeys + session) is documented as passing with 4.10.3112.0.
- An ARM64-specific factor cannot be ruled out: VMP attestation covers the
  CDM build and its execution environment, and the only tested host is
  ARM64. An x86_64 comparison run is part of the manual test matrix.
- The error is associated with the expected playback request (it arrives on
  the license endpoint immediately after `generateRequest()` for selected
  content), and content quality/entitlement variation has not been excluded.

## Honest status (do not advertise beyond this)

- DETECTED: CDM discovery and architecture validation (system 4.10.2662.3,
  component 4.10.3112.0).
- INITIALIZED: CDM 4.10.3112.0 (MediaKeySession creation verified live).
- LICENSE ACCEPTED: never observed on any build so far.
- PLAYBACK VERIFIED: never observed.

If a live run with 4.10.3112.0 still returns `VMP_VALIDATION_FAILED`, the
blocker is Amazon's device-eligibility/attestation policy for this
environment. That limitation will be documented here and in the README
rather than worked around: no DRM bypass, identity spoofing, or license
manipulation is in scope for this project.
