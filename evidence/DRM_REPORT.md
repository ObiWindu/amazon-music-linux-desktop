# DRM Report

- Stage A (library presence): PASS (aarch64, deps resolved; system CDM 4.10.2662.3)
- Stage B (EME/Widevine key system): PASS (com.widevine.alpha)
- Stage C (CDM init): PASS (MediaKeys + MediaKeySession create OK; newer component CDM 4.10.3112.0 is selected over the 2022 system build)
- Stage D (Amazon playback): PENDING (requires an Amazon account/subscription and audio output; older 4.10.2662.3 fails VMP_VALIDATION_FAILED, newer CDM needs host verification)
