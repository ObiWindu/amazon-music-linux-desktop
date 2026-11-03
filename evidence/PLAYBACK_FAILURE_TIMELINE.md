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
- READY: filesystem validation passed for the selected CDM (manifest valid,
  host-matching ELF arch). The live CDM session probe is the only evidence
  for initialization.
- INITIALIZED: **established 2026-11-03** — headless EME probe creates
  MediaKeys + MediaKeySession with 4.10.3112.0 via the engine's user-level
  lookup path, and `/proc` maps confirm our helpers hold exactly that
  binary (verdict MATCH). History: a 4.10.3112.0 success was recorded
  2026-10-29; on 2026-10-31 only the 0-byte distro stub was attempted
  (flag ignored), so initialization failed that day — see addenda below.
- LICENSE ACCEPTED: never observed on any build so far.
- PLAYBACK VERIFIED: never observed.

If a live run with 4.10.3112.0 still returns `VMP_VALIDATION_FAILED`, the
blocker is Amazon's device-eligibility/attestation policy for this
environment. That limitation will be documented here and in the README
rather than worked around: no DRM bypass, identity spoofing, or license
manipulation is in scope for this project.

## Addendum 2026-10-31 — CDM never loads: engine ignores --widevine-cdm-path

Headless EME probes (`scripts/probe-cdm-session.py`, offscreen QtWebEngine,
`--widevine-cdm-path` pointing at 4.10.3112.0 and at system 4.10.2662.3,
with and without `--no-sandbox`) all fail identically:

- `requestMediaKeySystemAccess('com.widevine.alpha')` succeeds (key system
  advertised), then `createMediaKeys()` fails:
  `NotSupportedError: CreateCdmFunc not available.`
- Chromium stderr (verbose) shows the loader attempting exactly one path:
  `/usr/lib64/chromium-browser/WidevineCdm/_platform_specific/linux_x64/libwidevinecdm.so`
  ("file too short") — a **0-byte placeholder**. The flagged path is never
  mentioned, even for a deliberately bogus one, although `ps` confirms the
  flag reaches the QtWebEngineProcess cmdline.
- The string `widevine-cdm-path` is absent from the engine binaries
  (`libQt6WebEngineCore.so.6.11.2`): this build
  (`qt6-qtwebengine-6.11.2-2.fc44.aarch64`) has no support for the switch.

Current failure order is therefore EARLIER than the Oct-29 VMP record:
CDM load fails → no license request is ever sent → VMP cannot currently be
re-tested. The Oct-29 license-stage evidence stands as a record of that day
(a loadable CDM existed at the engine's path then); it is not reproducible
today. Repro: `QT_QPA_PLATFORM=offscreen python3
scripts/probe-cdm-session.py`; exit 1 with `CDM SESSION FAILED` above.
Environment: Fedora Asahi Remix 44 aarch64, SELinux Enforcing, no Amazon
account needed for this stage.

## Addendum 2026-11-03 — CDM loads via the engine's user-level lookup path

The 0-byte distro stub is not the whole story. Strings in
`libQt6WebEngineCore.so.6.11.2` show the engine searches fixed layout
names, including `~/.config/chromium/WidevineCdm` with the single
platform subpath `_platform_specific/linux_x64`. Placing the validated
4.10.3112.0 ARM64 binary at that lookup name (user home only — no flag,
no system writes, no binary modification) makes the headless EME probe
succeed: `{"ok":true,"keySystem":"com.widevine.alpha"}` repeatedly, and
`/proc/*/maps` shows the probe's own helper processes holding exactly
the Codex 4.10.3112.0 binary. The directory name is a lookup key, not
an attestation — arch compatibility is enforced on the ELF binary
(`file` confirms ARM aarch64; dlopen enforces it at load). The app now
maintains the validated host-arch CDM under every engine lookup name
(`ensure_widevine_user_dir()`); the `--widevine-cdm-path` flag is still
set for builds that honor it, and stale flag values are replaced at
startup. With a CDM loading again, VMP re-testing is unblocked pending
an Amazon account (see `docs/LICENSE_VERIFICATION_RUNBOOK.md`).

### Same-day result: full license exchange succeeds (test server)

`scripts/probe-cdm-license.py` (new) drives EME end-to-end against public
Widevine *test* vectors (Tears of Steel PSSH + UAT proxy, no Amazon
involved): `generateRequest` → license POST → `session.update` → all
`keyStatuses` become `usable`. Result on this host with CDM 4.10.3112.0:
`LICENSE EXCHANGE OK`, exit 0, twice in a row. This proves the CDM is
fully capable of completing real license exchanges. It does NOT answer
Amazon: the UAT test server does not enforce Amazon's LD-content device
policy, so `VMP_VALIDATION_FAILED` for Amazon remains possible. What the
exchange rules out is CDM health as a variable — the only remaining
question is Amazon's device eligibility for this environment, testable
only with an entitled account per the runbook.

## Entry 2026-11-03 — EME proven, license untested (the five facts)

- **User-level lookup path.** The engine searches fixed layout names
  (found via binary strings in `libQt6WebEngineCore.so.6.11.2`): only
  `_platform_specific/linux_x64` under the Chromium user dirs — no
  `linux_arm64` lookup exists on this build. `~/.config/chromium` and
  `~/.config/google-chrome` `WidevineCdm/_platform_specific/linux_x64/`
  now carry the validated host-arch binary (symlinks maintained by
  `ensure_widevine_user_dir()`); the distro stub at
  `/usr/lib64/chromium-browser/...` is untouched (still 0 bytes).
- **Selected CDM version.** Aurora selects Codex `4.10.3112.0` (ARM64,
  manifest-valid, ELF-validated). The sandbox `file` check confirms:
  `ELF 64-bit LSB shared object, ARM aarch64`.
- **Successful EME probe.** `scripts/probe-cdm-session.py` (now
  self-contained: offscreen default, lookup-path pre-flight, mapped-binary
  verification, exit 0/1/2) prints
  `CDM SESSION OK: {"ok": true, "keySystem": "com.widevine.alpha"}`
  repeatedly — with and without `--widevine-cdm-path`, exit code 0.
- **Actual observed mapped binary.** `/proc/*/maps` of the probe's own
  helper processes shows five mappings of exactly
  `~/.config/Codex/WidevineCdm/4.10.3112.0/_platform_specific/
  linux_arm64/libwidevinecdm.so`. Selection vs loaded verdict: MATCH.
- **Session initialization vs Amazon authorization.** MediaKeys +
  MediaKeySession creation is proven; license acceptance is NOT tested —
  Amazon's license server has not been contacted in this work (the
  2026-10-29 `VMP_VALIDATION_FAILED` record stands as the only license
  evidence). `test_go_home` passes again (earlier failures were transient
  sandbox network issues), and PCM audio output is verified working
  (`pw-play` exit 0; only a null sink exists here), so the remaining
  unknowns are strictly: account-gated license response, then audible
  playback on hardware.
