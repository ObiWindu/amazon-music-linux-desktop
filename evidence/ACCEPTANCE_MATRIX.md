# Acceptance Matrix

| ID | Criterion | Result | Evidence |
|---|---|---|---|
| AC-01 | Starts on Fedora AArch64 | Implemented/Verified | run-dev.sh launch |
| AC-02 | Dependencies detected | Verified | evidence/ENVIRONMENT.md |
| AC-03 | Main window renders | Verified | integration tests |
| AC-04 | Regional homepage loads | Implemented | go_home |
| AC-05 | Login via Amazon | Manual | N/A (requires account) |
| AC-06 | Session persistence | Implemented | persistent profile |
| AC-07 | Navigation controls | Verified | integration test |
| AC-08 | External navigation policy | Verified | security tests |
| AC-09 | Untrusted schemes rejected | Verified | security tests |
| AC-10 | Profile permissions | Verified | 0700 |
| AC-11 | Sensitive data absent from logs | Verified | redaction tests |
| AC-12 | Settings persist | Verified | unit tests |
| AC-13 | Missing CDM handled | Implemented | diagnostics |
| AC-14 | CDM arch/deps checked | Verified | diagnostics |
| AC-15 | EME detected | Verified | manual test |
| AC-16 | CDM init assessed | Verified | DRM_REPORT.md (MediaKeys/session OK; newest CDM selected) |
| AC-17 | Amazon protected playback | Unverified | requires account |
| AC-18 | Audio output | Unverified | requires account |
| AC-19 | Sustained playback | Unverified | requires account |
| AC-20 | Media keys/tray | Partial | tray implemented |
| AC-21 | Renderer failures handled | Implemented | main_window |
| AC-22 | Unit tests pass | Verified | 30 passed |
| AC-23 | Security tests pass | Verified | 4 passed |
| AC-24 | Lint/static pass | Verified | ruff+mypy |
| AC-25 | RPM builds AArch64 | Verified | rpm built |
| AC-26 | Installed RPM launches | Verified | staging install |
| AC-27 | Desktop launcher | Implemented | desktop entry |
| AC-28 | Upgrade preserves data | Not tested | N/A |
| AC-29 | Uninstall preserves profile | Implemented | no profile deletion |
| AC-30 | Documentation complete | Verified | docs/ |
| AC-31 | No stubs | Verified | source audit |
| AC-32 | Evidence complete | Verified | evidence/ |
