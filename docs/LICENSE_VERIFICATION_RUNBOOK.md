# License Verification Runbook — CDM 4.10.3112.0

Purpose: determine, with reproducible evidence, whether Amazon's license
server accepts the component-updated Widevine build
(`~/.config/*/WidevineCdm/4.10.3112.0/...`, ARM64) that the app now selects —
or whether it answers `VMP_VALIDATION_FAILED` as it did for 4.10.2662.3.

A passing CDM session test is **not** license acceptance and **not**
playback. Only this runbook's license-stage evidence counts.

## Preconditions

- Fedora Asahi Remix (ARM64) with a graphical session and working audio
  (PipeWire/PulseAudio).
- Legitimate Amazon Music account with an entitlement that can play protected
  content (e.g. an active subscription for HD/Ultra HD tracks used in test).
- App built from the current tree; launch with `./scripts/run-dev.sh`.
- Close other Chromium/Electron apps if possible: the "Observed mapped CDM"
  scan is tree-scoped to our app, but a quiet system keeps the log readable.

## Procedure

1. Launch the app and sign in through Amazon's own login flow.
2. Open **Diagnostics → Run diagnostics**. Confirm:
   - `CDM in use` points at the `4.10.3112.0` build,
   - `CDM install status: READY`,
   - `CDM manifest validity: valid`,
   - `Observed mapped CDM (live process): none visible` (expected before
     first EME use).
3. Click **Test CDM session**. Expected: `[C_cdm_session] OK` with
   `keySystem: com.widevine.alpha`. This proves the CDM instantiates.
4. Re-run diagnostics. Expected now: `Observed mapped CDM` lists the
   `4.10.3112.0` path with `(matches selected CDM)`. Record whether it does.
5. Select any subscribed track and press play. Watch for up to 60 seconds.
6. Open **Diagnostics** again and copy the report
   (**Copy report**, or Settings → Playback diagnostics → Copy).
   The report is redacted by construction: it never contains cookies,
   authorization headers, tokens, account identifiers, license bodies, or
   keys. Verify no such material is present before sharing.

## What to record

| Field | Value |
|---|---|
| Qt / Chromium | from `=== Browser ===` |
| CDM version in use | from `CDM version:` |
| Observed mapped CDM | `matches selected CDM`? or path seen |
| Pipeline `license_acquisition_attempted` | VERIFIED / FAILED / UNKNOWN |
| Console error text (redacted) | e.g. `denialReason: VMP_VALIDATION_FAILED` |
| Failure code | e.g. `LICENSE_FAILED` |
| Audible playback | yes / no, duration heard |
| Amazon region | fr / us / uk / de |
| Track entitlement | subscription tier used |

## Interpreting the result

- **License accepted**: sustained audible playback with monitor state
  `PLAYING` and advancing position, and the pipeline's
  `media_decoding_started` / `audio_output_started` stages VERIFIED.
  (The collector marks `license_acquisition_attempted` FAILED only on
  console-error evidence and leaves it UNKNOWN otherwise, so acceptance is
  established by the downstream playback evidence, not by that stage
  flipping to VERIFIED.) Update the timeline doc with the new evidence
  (browser version, CDM version, region, track tier).
- **HTTP 400 `VMP_VALIDATION_FAILED` again**: the blocker is Amazon's
  device-eligibility/attestation policy for this environment, also for
  4.10.3112.0. Record it in `evidence/PLAYBACK_FAILURE_TIMELINE.md` and the
  README status ladder. Do **not** attempt to bypass, spoof, or patch around
  it — that is out of scope.
- **`Observed mapped CDM` shows a different path than selected**: the engine
  loaded another build (e.g. a distro default). Record both paths, the flag
  from `flag_passed`, and re-check `QTWEBENGINE_CHROMIUM_FLAGS` for an
  explicit override.

## Forbidden

No DRM bypass, no device-identity or attestation spoofing, no license
request/response manipulation, no Widevine binary patching, no credential
interception, no attempt to defeat Amazon's authorization policy. If the
environment is rejected, document it.
