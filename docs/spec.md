# MASTER ENGINEERING SPECIFICATION — AMAZON MUSIC DESKTOP FOR FEDORA ASAHI REMIX

**Project codename:** Aurora Music Desktop  
**Application name:** Amazon Music Desktop  
**Target platform:** Fedora Asahi Remix on Apple Silicon  
**Target architecture:** Linux ARM64 / AArch64  
**Primary language:** Python 3  
**Desktop framework:** PySide6 + Qt 6  
**Browser engine:** Qt WebEngine / Chromium  
**DRM technology:** Legitimately obtained Google Widevine CDM  
**Development approach:** Autonomous, evidence-driven implementation and testing  
**Delivery standard:** Production-quality, installable, maintainable Linux desktop application

---

# 1. ROLE AND MISSION

You are an autonomous senior Linux desktop engineer, Python architect, Qt specialist, Chromium/WebEngine integration engineer, application security engineer, QA engineer, release engineer, and technical writer.

Your task is to design, implement, test, harden, package, document, and deliver a complete Linux desktop application for Amazon Music.

The application must provide a polished, standalone desktop experience for Amazon Music while using Amazon's own website and authentication flow. It must use an embedded browser engine capable of supporting Widevine DRM when the CDM and browser versions are compatible.

The application is intended to run natively on Apple Silicon Linux through Fedora Asahi Remix, not through a virtual machine, x86 emulation, Windows compatibility layer, or remote desktop.

## 1.1 Existing environment and confirmed baseline

The target development machine has the following confirmed characteristics:

- Fedora Asahi Remix, Fedora 44.
- ARM64 / AArch64 architecture.
- `python3-pyside6-6.11.2-1.fc44.aarch64`.
- `qt6-qtwebengine-6.11.2-2.fc44.aarch64`.
- PySide6 WebEngine Python bindings import successfully.
- Qt WebEngine reports Chromium 140.0.0.0.
- Widevine CDM exists at `/var/lib/widevine/libwidevinecdm.so`.
- The CDM is an ELF 64-bit AArch64 shared object.
- The CDM's dependencies examined with `ldd` resolved without reported missing libraries.
- A JavaScript EME diagnostic returned `com.widevine.alpha` from `navigator.requestMediaKeySystemAccess()`.

These facts are the starting baseline, not proof that end-to-end DRM playback works.

**Important:** Detection of the Encrypted Media Extensions API or acceptance of a Widevine key-system request does not prove that the actual CDM loads, obtains valid licenses, or successfully decrypts and plays Amazon Music content. Establish these separately.

Do not waste time reinstalling dependencies already confirmed to be installed. Verify their actual capabilities and versions instead.

## 1.2 Mission objectives

Deliver an application that:

1. Runs natively on the target AArch64 Linux system.
2. Presents Amazon Music in a dedicated desktop window.
3. Uses Amazon's legitimate website and authentication mechanisms.
4. Supports persistent sessions without implementing a separate password system.
5. Supports Widevine playback where technically and contractually supported.
6. Provides reliable desktop integration, keyboard controls, media keys where available, and application lifecycle management.
7. Protects the user's login session and local browser data.
8. Handles failures clearly without crashing or silently corrupting user data.
9. Is reproducibly buildable and installable.
10. Includes automated tests, manual verification procedures, diagnostics, packaging, and documentation.
11. Has no placeholder implementations presented as finished features.
12. Has evidence for every acceptance criterion.

This is a desktop wrapper around Amazon Music, not an attempt to recreate Amazon's streaming backend, reverse-engineer its private APIs, or implement an independent DRM system.

---

# 2. AUTONOMOUS EXECUTION RULES

These rules are mandatory and take precedence over convenience.

## 2.1 Do not stop at the first working prototype

Continue through the entire engineering lifecycle:

1. Inspect the environment.
2. Establish the baseline.
3. Investigate the relevant technical constraints.
4. Design the architecture.
5. Implement the application.
6. Build and run it.
7. Test every feature.
8. Diagnose and fix failures.
9. Perform security and regression testing.
10. Package and install the application.
11. Verify the installed application.
12. Produce evidence and documentation.
13. Perform a final acceptance audit.

A successful import, a rendered window, a loaded webpage, or a successful EME API call is not completion.

Do not finish after writing source code. Do not finish after the first successful launch. Do not finish after merely producing an RPM.

## 2.2 Inspect before modifying

Before making changes:

- Inspect the current project directory.
- Inspect all existing source files and project configuration.
- Inspect Git status if the project is under version control.
- Determine whether the user already has an implementation that must be preserved.
- Record the installed Fedora, Python, Qt, PySide6, Chromium, and Widevine versions.
- Record the relevant package names and installation paths.
- Determine whether the application is running in a graphical desktop session.
- Identify the available display server and audio system.
- Determine which testing, packaging, and diagnostic tools are installed.

Do not overwrite existing user work without inspecting it and making an appropriate backup or Git checkpoint.

## 2.3 Research uncertain technical behavior

When an API, command-line flag, package, DRM mechanism, or compatibility requirement is uncertain:

1. Consult official documentation first.
2. Inspect the installed library and package metadata.
3. Check the actual executable's supported options where applicable.
4. Reproduce the behavior with a minimal test.
5. Record the result.
6. Select an implementation based on verified evidence.

Use official Qt, Fedora, Python, Chromium, and relevant Asahi documentation where applicable.

Do not invent API methods, package names, supported CDM flags, or browser capabilities.

Do not assume that a command-line flag accepted by one Chromium distribution is supported by Qt WebEngine.

Do not silently fall back to a different implementation that has not been tested.

## 2.4 No false completion claims

Never state that a feature is complete because its code exists.

For every requirement, distinguish between:

- Implemented.
- Automated tests passed.
- Manually verified.
- Verified on the target hardware.
- Blocked by an external dependency.
- Not applicable.
- Failed.
- Not tested.

A test that was not executed must not be reported as passing.

A mocked test must not be reported as proof of real Amazon authentication or DRM playback.

A successful browser initialization must not be reported as proof of successful playback.

## 2.5 Completion condition

The task is complete only when all applicable, locally testable acceptance criteria pass and the deliverables are verified.

If a requirement depends on Amazon's servers, a valid subscription, an externally issued DRM license, account eligibility, unavailable hardware, or a third-party service:

- Implement all controllable parts.
- Test the integration using the strongest legitimate method available.
- Record the external dependency.
- Provide reproducible instructions for completing the remaining test.
- Report the limitation honestly.
- Continue completing every other requirement.

Never manufacture evidence, bypass DRM, or claim 100% success when external validation remains unperformed.

---

# 3. PRODUCT DEFINITION

## 3.1 Intended experience

The application should behave like a dedicated desktop music application rather than a generic browser window.

The user should be able to:

- Launch Amazon Music from the desktop application menu.
- Sign in directly through Amazon.
- Remain signed in between launches when Amazon's session policy allows.
- Browse and play music using Amazon's supported website.
- Use normal browser navigation when necessary.
- Control playback through the website.
- Use desktop media controls when technically feasible.
- Minimize the application to the system tray if supported.
- Restore the application without losing the current session.
- Exit cleanly without corrupting persistent data.
- Update the application without unnecessarily deleting login state.

The application must not require users to paste credentials into a separate login form.

## 3.2 Supported service regions

The initial release should support configurable Amazon Music regional URLs.

At minimum, allow a configurable starting URL and provide sensible defaults for common regions, including:

- France: `https://music.amazon.fr/`
- United States: `https://music.amazon.com/`
- United Kingdom: `https://music.amazon.co.uk/`
- Germany: `https://music.amazon.de/`

Additional regions may be supported where their domains are verified.

The application must not hardcode a US-only URL throughout the implementation.

The selected region must persist across launches.

If Amazon redirects the user to a legitimate regional domain, the application should preserve the session and navigation when safe.

---

# 4. TECHNICAL ARCHITECTURE

## 4.1 Primary stack

Use:

- Python 3.
- PySide6.
- Qt 6 Widgets.
- Qt WebEngine.
- Qt WebEngine Core.
- Qt WebEngine Widgets.
- Qt Network where necessary.
- Python standard library for basic configuration, logging, and file operations.
- pytest and pytest-qt for automated testing where compatible.
- Ruff for linting and formatting.
- mypy or an equivalent static type checker where practical.
- RPM tooling and Fedora-native packaging tools for distribution.

Use the installed system packages where possible.

Avoid unnecessary dependencies, especially dependencies that are difficult to obtain on AArch64.

Do not replace the working Qt stack without a concrete technical reason.

## 4.2 Proposed source architecture

Organize the code into small modules with explicit responsibilities.

Suggested layout:

    amazon-music-desktop/
    ├── pyproject.toml
    ├── README.md
    ├── LICENSE
    ├── CHANGELOG.md
    ├── CONTRIBUTING.md
    ├── .gitignore
    ├── src/
    │   └── amazon_music_desktop/
    │       ├── __init__.py
    │       ├── __main__.py
    │       ├── app.py
    │       ├── main_window.py
    │       ├── browser/
    │       │   ├── __init__.py
    │       │   ├── profile.py
    │       │   ├── page.py
    │       │   ├── navigation.py
    │       │   ├── drm_diagnostics.py
    │       │   └── download_policy.py
    │       ├── services/
    │       │   ├── __init__.py
    │       │   ├── configuration.py
    │       │   ├── logging_service.py
    │       │   ├── health_check.py
    │       │   └── desktop_integration.py
    │       ├── ui/
    │       │   ├── __init__.py
    │       │   ├── toolbar.py
    │       │   ├── settings_dialog.py
    │       │   ├── diagnostics_dialog.py
    │       │   └── about_dialog.py
    │       └── resources/
    │           ├── icons/
    │           └── styles/
    ├── tests/
    │   ├── unit/
    │   ├── integration/
    │   ├── security/
    │   ├── packaging/
    │   └── fixtures/
    ├── packaging/
    │   ├── rpm/
    │   ├── desktop/
    │   └── icons/
    ├── scripts/
    │   ├── run-dev.sh
    │   ├── run-tests.sh
    │   └── verify-install.sh
    ├── docs/
    │   ├── ARCHITECTURE.md
    │   ├── SECURITY.md
    │   ├── DRM_COMPATIBILITY.md
    │   ├── TESTING.md
    │   ├── INSTALLATION.md
    │   └── TROUBLESHOOTING.md
    └── evidence/
        ├── test-results/
        ├── compatibility/
        └── release/

Adapt this layout when justified, but preserve separation of concerns.

Avoid a monolithic `app.py` containing every feature.

## 4.3 Architecture boundaries

Separate these responsibilities:

- Application startup and shutdown.
- Main window and presentation.
- WebEngine initialization.
- Browser profile and persistent storage.
- Navigation policy.
- Amazon domain policy.
- Download handling.
- DRM diagnostics.
- Settings and configuration.
- Desktop integration.
- Logging and support diagnostics.
- Packaging and release validation.

The UI must not directly manipulate configuration files throughout the codebase.

The browser policy must not depend on fragile assumptions about the current window title.

Use clear interfaces and type annotations for nontrivial methods.

---

# 5. BROWSER ENGINE AND WIDEVINE INTEGRATION

This is the project's highest-risk technical area and must be addressed early.

## 5.1 Existing Widevine installation

The current CDM is located at:

    /var/lib/widevine/libwidevinecdm.so

It is an AArch64 ELF shared object, approximately 10 MB in size.

Its inspected dependencies included:

- `libdl.so.2`
- `libpthread.so.0`
- `libnspr4.so`
- `libm.so.6`
- `libc.so.6`

The previous `ldd` output did not report missing dependencies.

The installed Qt WebEngine reports:

    QtWebEngine/6.11.2 Chrome/140.0.0.0

A diagnostic browser successfully recognized the `com.widevine.alpha` key system.

These facts establish the initial test environment, not a guarantee of full compatibility.

## 5.2 Investigate actual CDM loading

The implementation must determine how the installed Qt WebEngine build discovers, loads, and initializes a Widevine CDM.

Do not assume that either `--widevine-path` or `--widevine-cdm-path` is a valid or sufficient solution.

Investigate:

1. Official Qt WebEngine DRM documentation for the installed version.
2. The actual Qt WebEngine Chromium version.
3. The supported CDM discovery mechanism.
4. Whether the system build contains the relevant proprietary-code integration.
5. Whether the CDM ABI matches the Chromium build.
6. Whether the CDM is accepted by the engine's component-loading logic.
7. Whether the CDM can be initialized.
8. Whether a legitimate Widevine license request succeeds for supported content.
9. Whether protected playback produces audible output.

Use supported integration methods. Do not patch DRM checks, bypass license validation, modify protected media, or attempt to defeat content protection.

## 5.3 Required DRM diagnostic stages

Implement separate checks for the following stages.

**Stage A — Library presence**

- Verify the configured CDM path.
- Verify that the file exists.
- Verify that it is readable by the application user.
- Check the ELF architecture.
- Inspect shared-library dependencies.
- Report actionable errors.

**Stage B — Browser capability**

- Detect whether Encrypted Media Extensions are available.
- Query `com.widevine.alpha`.
- Use a realistic, nonempty media capability configuration.
- Distinguish `NotSupportedError`, `SecurityError`, and other failures.
- Report the browser version and the tested capabilities.

**Stage C — CDM initialization**

- Check actual browser and CDM initialization diagnostics.
- Distinguish a registered key system from a functioning CDM.
- Report component-loading and ABI errors where observable.
- Do not expose license tokens or sensitive headers in logs.

**Stage D — License and playback**

- Use Amazon's actual website and its legitimate playback process.
- Confirm whether a valid account and subscription are required.
- Test a legitimately available track.
- Determine whether a DRM license was successfully obtained without logging its contents.
- Confirm that playback starts.
- Confirm that audio is audible.
- Check for playback errors and unexpected termination.

Do not claim that Stage D passed solely because Stage B passed.

## 5.4 DRM fallback strategy

If Qt WebEngine cannot load the installed CDM:

1. Record the exact error and relevant versions.
2. Verify the CDM path and architecture.
3. Check the Qt package's supported features.
4. Check the official integration documentation.
5. Reproduce the problem in a minimal application.
6. Determine whether a supported configuration or compatible system package solves it.
7. Evaluate a different embedded browser engine only if necessary.
8. Preserve the native desktop application interface if the engine must change.

Any alternative engine must be evaluated for:

- AArch64 compatibility.
- Fedora 44 support.
- Widevine compatibility.
- Security updates.
- Licensing.
- Package availability.
- Persistence.
- Amazon authentication.
- Accessibility.
- Audio output.
- Reproducibility.

Do not download arbitrary proprietary CDM binaries or claim compatibility without evidence.

---

# 6. APPLICATION USER INTERFACE

## 6.1 Main window

Build a polished native Qt window with:

- Application icon.
- Appropriate window title.
- Minimum practical window dimensions.
- Responsive resizing.
- A browser content area.
- Navigation toolbar.
- Loading indicator.
- Error display.
- Optional status bar.
- Keyboard-accessible controls.
- Native application menus.

The design should feel like a desktop music player, not a generic testing utility.

Avoid adding fake playback controls that do not operate the actual player.

## 6.2 Navigation toolbar

Provide:

- Back.
- Forward.
- Reload.
- Home.
- Loading progress.
- Stop-loading behavior.
- Optional current-page information.
- An accessible settings entry.
- A diagnostics entry.

Navigation buttons must reflect their actual enabled state.

The loading indicator must be driven by actual browser loading signals.

Prevent repeated navigation events from producing unstable UI state.

## 6.3 Home behavior

The Home action must return to the user's configured Amazon Music regional URL.

The application should preserve the browser profile and session.

It must not delete cookies or reset the account when returning home.

## 6.4 Loading and network failures

Handle:

- DNS failures.
- Network disconnections.
- TLS certificate errors.
- Timeouts.
- Amazon service errors.
- Renderer termination.
- Unexpected browser process exit.
- Failed resource loads.

Display a useful recovery message without replacing Amazon's normal login or playback UI unnecessarily.

Provide retry and reload actions where appropriate.

Do not automatically disable certificate verification when a connection fails.

## 6.5 Appearance

Support a clean, modern interface that follows the desktop's general appearance where practical.

Implement:

- High-DPI scaling.
- Keyboard focus indicators.
- Accessible labels.
- Appropriate spacing.
- Readable status messages.
- Correct icon scaling.
- A dark appearance option if reliable and useful.
- Consistent window and dialog styling.

Do not inject CSS into Amazon's website merely to force a theme unless the behavior is explicitly configurable, tested, and does not interfere with the service.

---

# 7. AMAZON AUTHENTICATION AND SESSION MANAGEMENT

## 7.1 Authentication model

Amazon handles authentication through its own website.

The application must not implement its own Amazon password form.

It must not ask the user to provide:

- Amazon passwords.
- One-time authentication codes.
- Session cookies.
- Authentication tokens.
- License tokens.
- Browser storage exports.

Do not scrape authentication data from Amazon's pages.

Do not intercept password submissions.

Do not capture, export, or transmit cookies.

## 7.2 Persistent browser profile

Use a dedicated Qt WebEngine profile and persistent storage.

Store profile data under an application-specific directory within the user's home directory, using the appropriate XDG location.

For example:

    ~/.local/share/amazon-music-desktop/

Keep cache data and durable session storage separate where the API permits.

Set restrictive directory permissions, normally `0700`, and ensure files created by the application are not readable by unrelated local users.

Verify the actual permissions on disk rather than assuming the operating system applied them.

Do not run the application as root.

Do not store browser cookies in application configuration files.

Do not log cookies, authorization headers, or session contents.

## 7.3 Session behavior

Test:

- First launch.
- Login through Amazon.
- Closing and reopening the application.
- Session persistence.
- Expired session handling.
- Amazon logout.
- Clearing site data.
- Switching the configured regional homepage.
- Updating the application without deleting the profile.

Session persistence remains subject to Amazon's policies and expiration behavior.

The app must never attempt to defeat Amazon's account security or session expiration mechanisms.

## 7.4 Clear site data

Provide a clearly labeled option to clear Amazon site data.

Explain that it may sign the user out.

The operation must require confirmation.

Do not delete unrelated browser profiles or system-wide browser data.

---

# 8. NAVIGATION AND ORIGIN SECURITY

The application must not be an unrestricted general-purpose browser unless that behavior is explicitly part of the product design.

At the same time, an overly restrictive host allowlist must not break legitimate authentication redirects.

## 8.1 Navigation policy

Implement a centralized navigation policy.

Classify navigation requests into:

- Trusted Amazon pages.
- Verified Amazon authentication endpoints.
- Other required service origins established through testing.
- External links.
- Untrusted schemes.
- Downloads.
- Pop-ups and new-window requests.

Allow HTTPS by default only for the explicitly permitted origins and necessary verified authentication flows.

Do not blindly trust every subdomain merely because its name ends with `amazon.com`.

Use correct hostname parsing, canonicalization, and boundary checks.

For example, a hostname such as `amazon.com.attacker.example` must never be treated as an Amazon hostname.

## 8.2 Authentication redirects

Authentication may involve legitimate service domains that are not simple variations of the homepage domain.

Discover these through the actual login flow and authoritative documentation.

Add only the minimum required origins.

Do not weaken navigation security to make login work without investigating the redirect.

Document why each additional origin is required.

## 8.3 External links

When a user clicks an external link:

- Open it in the system's regular browser, or
- Display an explicit, accessible confirmation.

Do not silently navigate the embedded session to arbitrary websites.

Prevent external pages from accessing the application's privileged UI or internal interfaces.

## 8.4 Dangerous URL schemes

Explicitly evaluate handling of:

- `javascript:`
- `data:`
- `file:`
- `ftp:`
- `intent:`
- Custom URL schemes.
- Local filesystem URLs.

Do not allow untrusted web content to navigate to local files or execute arbitrary commands.

Permit a non-HTTPS scheme only when there is a documented, narrowly scoped requirement.

## 8.5 Pop-ups and new windows

Handle `createWindow()` and related WebEngine behavior explicitly.

Prevent unexpected pop-ups from creating uncontrolled windows.

Support legitimate authentication or service windows if required.

Every new window must inherit the appropriate security policy and must not gain broader privileges than the main page.

---

# 9. DOWNLOADS AND FILE ACCESS

Define an explicit download policy.

For each download:

- Validate the destination.
- Show the filename and destination.
- Require user confirmation when appropriate.
- Avoid overwriting files silently.
- Prevent directory traversal.
- Handle interrupted downloads.
- Report failures.
- Avoid opening downloaded files automatically.

Do not allow arbitrary Amazon webpage content to write files outside the permitted destination.

Do not grant unnecessary filesystem access.

If downloads are not needed for the initial release, disable them and document the limitation rather than providing an insecure partial implementation.

---

# 10. MEDIA CONTROLS AND DESKTOP INTEGRATION

## 10.1 Playback controls

Amazon's website is responsible for actual playback.

Do not recreate or intercept Amazon's private playback APIs.

Where possible, support the website's actual media session and browser media integration.

Evaluate Qt WebEngine support for Media Session APIs and the capabilities available on the installed Linux stack.

## 10.2 Keyboard shortcuts

Implement application-level shortcuts that do not conflict with Amazon's controls.

At minimum:

- Reload.
- Back.
- Forward.
- Home.
- Toggle application visibility if a tray is implemented.
- Open settings.
- Open diagnostics.
- Quit.

Playback shortcuts must operate the actual page or supported media session. Do not advertise nonfunctional controls.

## 10.3 Media keys

Investigate Linux desktop media-key integration.

Use supported desktop interfaces, such as MPRIS over D-Bus, where appropriate.

Do not assume Qt WebEngine automatically exposes every Media Session action to MPRIS.

If an MPRIS implementation is needed, use an established library compatible with the target environment or implement the protocol carefully.

Support, where technically feasible:

- Play.
- Pause.
- Play/pause toggle.
- Next.
- Previous.
- Playback status.
- Current track metadata when legitimately exposed.
- Player identity.
- Desktop media-key routing.

Only expose actions that can actually be implemented reliably.

Do not fabricate track metadata.

Test behavior under the target desktop environment.

## 10.4 System tray

Implement an optional system tray icon with:

- Show/hide.
- Restore.
- Open Amazon Music.
- Settings.
- Diagnostics.
- Quit.

Detect whether a usable tray is available.

If no tray exists, the app must remain fully usable.

Do not hide the application permanently when the tray is unavailable.

## 10.5 Application shutdown

On quit:

- Stop timers and background tasks.
- Save configuration.
- Allow browser storage to flush.
- Release Qt resources cleanly.
- Avoid unnecessary profile deletion.
- Avoid orphaned subprocesses.
- Log unexpected shutdown errors without logging sensitive session data.

---

# 11. SETTINGS AND CONFIGURATION

Implement a validated configuration system.

Suggested settings:

- Amazon Music region.
- Homepage URL.
- Window dimensions.
- Last window position where appropriate.
- Theme preference.
- System tray preference.
- Minimize-to-tray preference.
- Media-key integration preference.
- Download behavior.
- Diagnostics verbosity.
- Optional developer diagnostics.

Use a standard user configuration location, such as:

    ~/.config/amazon-music-desktop/

Do not store passwords, cookies, access tokens, or DRM license data in the settings file.

Validate all settings on load.

If configuration is corrupt:

1. Preserve a diagnostic copy when safe.
2. Log a sanitized explanation.
3. Load safe defaults.
4. Allow the user to recover.
5. Never delete persistent browser data as an automatic recovery measure.

Configuration changes must take effect when expected and be covered by tests.

---

# 12. DIAGNOSTICS AND LOGGING

Provide a diagnostics interface that helps the user troubleshoot without exposing secrets.

## 12.1 System information

Report:

- Application version.
- Python version.
- Fedora release.
- Machine architecture.
- PySide6 version.
- Qt version.
- Qt WebEngine version.
- Chromium user-agent version.
- Configured Amazon region.
- Whether the configured CDM path exists.
- CDM architecture.
- Whether its dependencies resolve.
- EME API availability.
- Widevine key-system detection result.
- Relevant browser initialization errors, where observable.
- Audio subsystem availability where testable.
- Network reachability checks that do not require credentials.

## 12.2 Logging

Use Python's logging system with rotating log files.

Logs should include:

- Timestamp.
- Severity.
- Application component.
- Diagnostic event.
- Relevant non-sensitive error details.

Redact:

- Passwords.
- Cookies.
- Session identifiers.
- Authorization headers.
- Access tokens.
- License request and response bodies.
- Personal account information.
- Sensitive URL query parameters.

Avoid logging complete navigation URLs when they may contain sensitive query parameters.

Never enable unrestricted network tracing by default.

## 12.3 Support bundle

Provide an optional support bundle containing sanitized diagnostics.

The bundle must exclude:

- Browser cookies.
- Browser profile databases.
- Local storage contents.
- Authentication state.
- Passwords.
- Private keys.
- License contents.
- Personal account information.
- Arbitrary downloaded files.

Show the user what categories of data will be included before exporting the bundle.

Test the redaction rules.

---

# 13. SECURITY REQUIREMENTS

Security is a core feature, not a final cosmetic pass.

## 13.1 Threat model

Consider:

- Malicious external links.
- Malicious web content.
- Cross-origin navigation.
- Compromised third-party resources.
- Local users attempting to read the profile.
- Accidental diagnostic leakage.
- Malicious downloads.
- Corrupted configuration.
- Renderer crashes.
- Stale or incompatible browser components.
- Untrusted installation scripts.
- Malicious update packages.

## 13.2 Required controls

- Do not run as root.
- Do not disable TLS certificate validation.
- Do not disable Chromium sandboxing merely to make the application start.
- Do not allow untrusted content to access local files.
- Do not expose privileged Python objects to webpage JavaScript.
- Do not use `QWebChannel` for this application unless an essential, narrowly scoped requirement is demonstrated.
- If a bridge is required, expose only minimal safe operations and verify the origin on every call.
- Do not execute arbitrary shell commands derived from webpage content.
- Do not accept arbitrary command-line input as a CDM path without validation.
- Use restrictive permissions for configuration and profile data.
- Avoid unnecessary network services.
- Keep the application updated with compatible security fixes.
- Do not bundle a CDM without explicit licensing authorization.
- Do not bypass Widevine security checks or content protection.

## 13.3 Chromium flags

Treat all Chromium command-line flags as security-sensitive.

Inspect the installed Qt WebEngine documentation and actual implementation before setting flags.

Do not disable:

- The Chromium sandbox.
- TLS validation.
- Site isolation.
- Web security.
- Origin restrictions.

Do not add random flags copied from unrelated Chromium distributions.

Use only flags whose behavior is verified for the installed version.

Document each non-default flag and its necessity.

## 13.4 Security review

Create `docs/SECURITY.md` documenting:

- Threat model.
- Browser profile storage.
- Authentication boundaries.
- Navigation policy.
- Download policy.
- DRM integration.
- Logging and redaction.
- Update mechanism.
- Known limitations.
- Reporting process for security issues.

Perform a final security review before declaring the release complete.

---

# 14. WIDEVINE AND AMAZON PLAYBACK ACCEPTANCE

The application must distinguish between browser capability and real playback.

## 14.1 Required DRM evidence

Collect evidence for these distinct claims:

| Check | Required evidence |
|---|---|
| CDM exists | File metadata and verified path |
| Correct architecture | `file` output or equivalent ELF inspection |
| Dependencies resolve | Dependency check without unresolved libraries |
| EME is available | Actual JavaScript diagnostic result |
| Widevine key system is exposed | Successful key-system access request |
| CDM is initialized | Browser or CDM diagnostic evidence, where available |
| Amazon authentication works | Successful sign-in through Amazon's own flow |
| Protected content is accepted | Actual supported playback attempt |
| Playback starts | Observed player state and audible output |
| Playback remains stable | Sustained playback test with no relevant errors |

Do not infer a passing result for one row from another row.

## 14.2 Legitimate testing

Use only an account the user is authorized to use.

Respect subscription requirements, regional restrictions, licensing conditions, and Amazon's service policies.

Do not:

- Forge DRM licenses.
- Bypass authentication.
- Extract or export license secrets.
- Patch Widevine to ignore verification.
- Disable content protection.
- Intercept and decrypt protected media.
- Implement unauthorized streaming endpoints.
- Circumvent playback restrictions.

If a supported track is unavailable because of account or service restrictions, record the blocker and use a legitimate alternative test where available.

## 14.3 Playback acceptance

For the release candidate, perform an actual end-to-end playback test:

1. Start the installed application.
2. Open Amazon Music.
3. Sign in if required.
4. Select a legitimately available track.
5. Start playback.
6. Confirm audible audio.
7. Allow playback to continue for at least 15 minutes.
8. Test pause and resume.
9. Test navigation while playback is active.
10. Test minimize and restore.
11. Test application shutdown and restart.
12. Confirm the session behaves as expected.
13. Review logs for relevant errors.

Where the service offers a test that can be completed without a subscription, use it only if it exercises the same relevant protected playback path.

If actual playback cannot be tested, the release must be marked **DRM integration unverified**, not fully DRM-validated.

---

# 15. AUTOMATED TESTING

Create a meaningful automated test suite.

## 15.1 Unit tests

Test:

- Configuration defaults.
- Configuration validation.
- Invalid configuration recovery.
- Region selection.
- URL normalization.
- Hostname boundary checks.
- Navigation policy decisions.
- Scheme rejection.
- Download destination validation.
- File permission setup.
- Log redaction.
- Support bundle sanitization.
- CDM path validation.
- Architecture detection.
- Dependency diagnostics parsing.
- Application shutdown logic.

Unit tests must be deterministic and must not require a real Amazon account.

## 15.2 Integration tests

Test:

- Main window initialization.
- WebEngine profile creation.
- Persistent storage configuration.
- Navigation controls.
- URL loading.
- Loading indicators.
- Error display.
- Settings persistence.
- Regional homepage changes.
- External-link policy.
- Pop-up policy.
- Download confirmation.
- Crash handling.
- Diagnostics generation.

Use test fixtures or a controlled local HTTP server for generic browser behavior.

Do not use production Amazon endpoints for every unit or integration test.

## 15.3 Security tests

Test:

- Malicious hostname suffixes.
- Unicode and malformed hostnames.
- URL user-information fields.
- Unexpected URL schemes.
- External navigation.
- Local file access attempts.
- Path traversal.
- Dangerous download names.
- Log redaction.
- Support bundle contents.
- Profile directory permissions.
- Corrupt configuration.
- Untrusted pop-up requests.

## 15.4 GUI tests

Use pytest-qt where compatible with the installed Qt version.

Test:

- Window creation.
- Toolbar actions.
- Settings dialogs.
- Confirmation dialogs.
- Keyboard shortcuts.
- Error handling.
- Quit behavior.
- Tray behavior where the environment supports it.

Do not silently skip tests because a display server is missing. Record the reason and run the remaining headless-compatible tests.

## 15.5 DRM tests

Automate the checks that can be tested without real protected playback:

- CDM path validation.
- ELF architecture inspection.
- EME capability diagnostics.
- Widevine key-system detection.
- Error classification.
- Diagnostic output formatting.

Keep account-based Amazon playback tests separate from ordinary CI.

Do not claim automated DRM integration coverage for behavior that was only manually inspected.

---

# 16. RELIABILITY AND PERFORMANCE

## 16.1 Startup

The app should:

- Launch without unnecessary blocking operations on the UI thread.
- Display a responsive window promptly.
- Avoid unnecessary network requests before showing the interface.
- Handle a slow or unavailable network.
- Avoid blocking shutdown while waiting indefinitely for the website.

Measure startup time and report the observed result.

## 16.2 Memory and CPU

Measure resource usage after:

- Startup.
- Login.
- Idle browsing.
- Music playback.
- Long-running playback.
- Multiple navigation operations.
- Minimize and restore.

Establish realistic thresholds based on the actual embedded Chromium footprint.

Do not invent arbitrary memory guarantees.

Investigate significant growth over a sustained test.

## 16.3 Long-running stability

Run an extended stability test where feasible.

Check for:

- Renderer crashes.
- Repeated reloads.
- Resource leaks.
- Broken audio after suspend/resume.
- Profile corruption.
- Unresponsive UI.
- Uncontrolled subprocess growth.

Document any limitations related to the desktop session, audio server, or Qt WebEngine.

## 16.4 Error recovery

Provide predictable behavior for:

- Network interruption.
- Invalid configuration.
- Missing CDM.
- Incompatible CDM.
- Missing Qt WebEngine runtime.
- Browser process termination.
- Invalid downloads.
- Read-only profile directory.
- Full disk.
- Failed package installation.

Never respond to an error by automatically deleting the user's profile.

---

# 17. FEDORA PACKAGING AND INSTALLATION

The release must be suitable for Fedora Asahi Remix on ARM64.

## 17.1 Development execution

Provide a reliable command to run the application from the source tree.

Support the system-installed PySide6 and Qt WebEngine packages.

Do not require users to install unrelated x86-64 dependencies.

## 17.2 Desktop integration

Install the appropriate desktop entry under:

    /usr/share/applications/

Install icons under a standard hicolor icon directory.

Use a proper application identifier.

The launcher must invoke the installed application reliably.

Do not hardcode the developer's home directory into the installed launcher.

Ensure the app works when launched from the desktop menu, not only from a terminal.

## 17.3 RPM package

Create a Fedora RPM package where the build environment permits.

The package must:

- Declare appropriate architecture constraints.
- Declare runtime dependencies.
- Install source or packaged Python modules in a standard location.
- Install desktop entries and icons.
- Include the application license and documentation.
- Avoid overwriting user data.
- Avoid bundling proprietary Widevine components without authorization.
- Avoid running arbitrary network downloads during package installation.
- Avoid requiring root privileges to play music.
- Preserve the user's profile across application updates.

Use a reproducible build configuration where practical.

Build for AArch64 and verify the architecture metadata.

## 17.4 Installation and removal

Document and test:

- Fresh installation.
- Upgrade.
- Launch.
- Desktop-menu integration.
- Uninstallation.
- Reinstallation.
- Profile preservation.
- Removal without accidental destruction of user data.

Package removal must not delete the user's session profile by default.

## 17.5 Alternative packaging

If RPM packaging cannot be completed, provide a documented source-installation method and explain the precise blocker.

Do not claim that a Flatpak, AppImage, or other package is ready unless it has actually been built and tested on the target architecture.

---

# 18. DOCUMENTATION

Produce the following complete documentation.

## README.md

Include:

- Project overview.
- Features.
- Architecture.
- Requirements.
- Fedora installation instructions.
- Development setup.
- Launch instructions.
- Testing.
- Packaging.
- Security model.
- Widevine limitations.
- Troubleshooting.
- Known limitations.

## INSTALLATION.md

Include:

- Supported Fedora and architecture.
- Required packages.
- RPM installation.
- Source installation.
- Desktop launcher setup.
- Upgrade procedure.
- Uninstallation.
- Profile backup and recovery.

## DRM_COMPATIBILITY.md

Include:

- Qt WebEngine version.
- Chromium version.
- CDM path and architecture.
- CDM dependency results.
- Supported configuration mechanism.
- EME test result.
- CDM initialization result.
- Amazon playback result.
- Known limitations.
- Reproduction instructions.

## SECURITY.md

Document the security model and sensitive-data handling.

## TESTING.md

Document:

- Test environment.
- Test commands.
- Automated test coverage.
- Manual test procedures.
- DRM acceptance procedure.
- Packaging checks.
- Expected evidence.

## TROUBLESHOOTING.md

Cover:

- Missing WebEngine bindings.
- Missing CDM.
- Incompatible CDM.
- Unsupported key system.
- Login loops.
- Audio failures.
- Network errors.
- Renderer crashes.
- Profile permission errors.
- Desktop launcher failures.

All commands must be checked against the actual implementation and target Fedora release.

---

# 19. BUILD AND RELEASE AUTOMATION

Provide scripts or documented commands for:

- Environment inspection.
- Linting.
- Type checking.
- Unit tests.
- Integration tests.
- Security tests.
- GUI tests.
- Package building.
- RPM metadata validation.
- Installation validation.
- Evidence collection.

A single documented verification command should run all locally executable release checks.

It should return a nonzero exit status if any required check fails.

Do not make the verification script report success merely because a test dependency is unavailable.

If a test cannot run, classify it explicitly.

Avoid embedding credentials or private data in scripts.

Ensure scripts work from the project root regardless of the caller's current directory.

---

# 20. CONTINUOUS QUALITY CONTROL

Use a test-driven or verification-driven development workflow.

For each significant feature:

1. Write or identify the acceptance criterion.
2. Implement the feature.
3. Run its relevant tests.
4. Inspect the actual output.
5. Fix failures.
6. Run regression tests.
7. Record the result.

After a substantial refactor, rerun all affected tests.

Before release, rerun the full verification suite.

Review source code for:

- Dead code.
- Duplicate implementations.
- Inconsistent error handling.
- Unsafe defaults.
- Unused dependencies.
- Hardcoded development paths.
- Placeholder methods.
- Unreachable code.
- Misleading UI.
- Incomplete documentation.
- Undocumented Chromium flags.

Do not leave a required feature implemented as a TODO, stub, placeholder, or permanently disabled button.

If a feature is not technically feasible, remove misleading UI, document the limitation, and record the evidence.

---

# 21. MANDATORY ACCEPTANCE CRITERIA

The following table defines the release gate.

| ID | Acceptance criterion | Required evidence |
|---|---|---|
| AC-01 | Application starts on Fedora AArch64 | Successful launch log and architecture record |
| AC-02 | Correct Python and Qt dependencies are detected | Dependency report |
| AC-03 | Main window renders and remains responsive | GUI test and manual verification |
| AC-04 | Amazon Music regional homepage loads | Recorded browser navigation result |
| AC-05 | Login occurs directly through Amazon | Manual authentication verification |
| AC-06 | Session persistence behaves correctly | Close/reopen test |
| AC-07 | Navigation controls work | Automated GUI or integration test |
| AC-08 | External navigation follows the security policy | Security test results |
| AC-09 | Untrusted schemes are rejected | Automated security tests |
| AC-10 | Profile permissions are restrictive | Filesystem permission checks |
| AC-11 | Sensitive data is absent from logs | Redaction tests |
| AC-12 | Settings persist correctly | Configuration tests |
| AC-13 | Missing CDM is handled gracefully | Negative diagnostic test |
| AC-14 | CDM architecture and dependencies are checked | Diagnostic report |
| AC-15 | EME capability is detected accurately | Browser diagnostic result |
| AC-16 | CDM initialization is independently assessed | Runtime evidence where observable |
| AC-17 | Actual Amazon protected playback is tested | Manual end-to-end evidence |
| AC-18 | Audio output is verified | Manual playback confirmation |
| AC-19 | Playback survives a sustained test | Recorded stability result |
| AC-20 | Media keys and tray work if claimed supported | Desktop integration tests |
| AC-21 | Renderer failures are handled safely | Failure-injection test where feasible |
| AC-22 | All mandatory unit tests pass | Test report |
| AC-23 | All mandatory security tests pass | Security test report |
| AC-24 | Lint and static checks pass | Tool output |
| AC-25 | RPM builds for AArch64 | Successful package build |
| AC-26 | Installed RPM launches correctly | Fresh-install verification |
| AC-27 | Desktop launcher works | Manual desktop test |
| AC-28 | Upgrade preserves user data | Upgrade test |
| AC-29 | Uninstallation preserves user profile by default | Removal test |
| AC-30 | Documentation is complete and accurate | Documentation audit |
| AC-31 | No mandatory features remain as stubs | Source audit |
| AC-32 | Release evidence is complete | Evidence manifest and audit |

For any criterion that cannot be tested in the available environment, explain why and provide a reproducible procedure.

A release must not be described as fully validated while AC-17 or AC-18 remains unverified.

---

# 22. EVIDENCE-BASED COMPLETION PROTOCOL

The agent must maintain an evidence ledger from the beginning of development.

Create:

    evidence/ACCEPTANCE_MATRIX.md
    evidence/TEST_REPORT.md
    evidence/ENVIRONMENT.md
    evidence/DRM_REPORT.md
    evidence/SECURITY_REPORT.md
    evidence/RELEASE_REPORT.md

## 22.1 Acceptance matrix

For every acceptance criterion, record:

- Criterion ID.
- Requirement.
- Implementation location.
- Test procedure.
- Test result.
- Evidence filename or reference.
- Date and environment.
- Outstanding issue, if any.

## 22.2 Evidence collection

Use actual outputs from tools and tests.

Where useful, collect:

- Command output.
- Test runner reports.
- Package build logs.
- RPM metadata.
- File permission checks.
- Screenshots of the actual running application.
- Actual Amazon playback verification notes.
- Sanitized diagnostic logs.
- Build hashes.
- Git revision.
- Dependency inventory.

Do not fabricate screenshots or alter evidence to hide a failure.

Do not include passwords, cookies, license data, or private account details in evidence.

## 22.3 Final verification command

Provide one documented command, for example:

    ./scripts/verify-release.sh

The actual script must:

1. Validate the environment.
2. Run linting.
3. Run static checks.
4. Run unit tests.
5. Run applicable integration tests.
6. Run security tests.
7. Validate configuration and resources.
8. Validate package metadata.
9. Build the package where supported.
10. Verify that mandatory test stages have executed.
11. Produce a machine-readable report.
12. Return a failure exit code if a mandatory check fails or has not been executed.

A passing local test suite does not replace the actual Amazon DRM playback test.

## 22.4 Independent final audit

Before declaring completion, perform a separate audit against the acceptance matrix.

Search for:

- TODO.
- FIXME.
- Placeholder.
- NotImplementedError.
- Empty handlers.
- `pass` in required implementations.
- Fake playback state.
- Mocked production functionality.
- Disabled controls.
- Hardcoded development paths.
- Unverified Chromium flags.
- Missing error handling.
- Undocumented limitations.
- Incomplete tests.

Investigate every finding. Some occurrences may be legitimate, but no required feature may remain incomplete without explicit disclosure.

Rerun the release verification command after the final code change.

Record the final Git revision and package hash.

---

# 23. DEFINITION OF DONE

The project is complete only when all of the following are true:

1. The source tree is complete and organized.
2. The application runs on the target Fedora AArch64 system.
3. The UI is usable and responsive.
4. Authentication is handled by Amazon.
5. Browser profile storage is persistent and appropriately protected.
6. Navigation and downloads follow the documented security policy.
7. Widevine integration has been investigated and implemented using a verified mechanism.
8. Actual protected playback has been tested where the account and service permit it.
9. All mandatory automated tests pass.
10. Security checks pass.
11. The RPM builds successfully, or a documented, verified alternative installation is provided.
12. The installed application works from the desktop launcher.
13. Upgrade and removal behavior have been tested.
14. Documentation matches the actual implementation.
15. No mandatory feature is represented by a placeholder.
16. The acceptance matrix contains real evidence.
17. The final verification command succeeds.
18. The final audit finds no unresolved mandatory implementation defects.
19. All external blockers and unverified claims are disclosed.
20. The final report identifies the delivered files and their actual locations.

Do not use the phrase "100% complete" unless every applicable acceptance criterion has passed and the evidence supports the statement.

If external DRM or Amazon service behavior cannot be verified, state exactly which criteria remain unverified rather than concealing them.

---

# 24. REQUIRED FINAL DELIVERY

When the project is complete, deliver:

1. Complete source code.
2. A buildable project configuration.
3. Automated tests.
4. Fedora installation scripts.
5. RPM package for AArch64 where the environment permits.
6. Desktop launcher and icons.
7. Complete documentation.
8. Acceptance matrix.
9. Test reports.
10. DRM compatibility report.
11. Security report.
12. Release verification script.
13. Build and package hashes.
14. Clear installation and launch commands.
15. Known limitations and any outstanding external verification steps.

If file creation is supported, create the deliverables in the working directory and provide the exact paths to the generated artifacts.

Do not merely paste a handful of source files into a final response and call the application complete.

---

# 25. EXECUTION ORDER

Follow this sequence unless verified evidence justifies a change.

**Phase 1 — Environment and baseline**

Inspect the target system, confirm versions, verify the project directory, and record the baseline.

**Phase 2 — DRM feasibility**

Establish how the installed Qt WebEngine build loads Widevine. Reproduce the actual CDM initialization path and test legitimate playback as early as possible.

**Phase 3 — Architecture and security**

Define the application structure, profile lifecycle, navigation policy, error handling, and logging rules.

**Phase 4 — Core application**

Implement startup, the main window, navigation, regional settings, persistent profile, and lifecycle handling.

**Phase 5 — Security and diagnostics**

Implement origin policy, safe downloads, diagnostics, logging redaction, configuration validation, and support-bundle sanitization.

**Phase 6 — Desktop integration**

Implement the desktop launcher, icons, keyboard shortcuts, optional tray behavior, and media-key integration where supported.

**Phase 7 — Automated testing**

Write and execute unit, integration, GUI, and security tests. Fix failures and rerun regressions.

**Phase 8 — Packaging**

Build the AArch64 RPM, install it on the target system, launch it through the desktop entry, and test upgrade and removal behavior.

**Phase 9 — End-to-end validation**

Test real Amazon authentication and playback, including sustained audio output, session persistence, and error handling.

**Phase 10 — Evidence and final audit**

Run the release verification command, inspect all evidence, complete the acceptance matrix, and produce the final report.

If a phase reveals a blocker, resolve it before depending on that phase's functionality. Continue with independent work where possible, but never represent a blocked prerequisite as satisfied.

---

# FINAL INSTRUCTION TO THE CODING AGENT

You are responsible for delivering a functioning, verifiable application, not merely proposing an implementation.

Work autonomously. Inspect the actual environment. Use the installed software. Verify APIs against real documentation. Write the code. Execute it. Test it. Read the output. Diagnose errors. Fix defects. Repeat until the applicable acceptance criteria pass.

Do not stop because the code compiles, the tests initially pass, the window opens, or the Widevine key system is detected.

Do not invent successful test results. Do not bypass DRM. Do not weaken browser security to hide integration problems. Do not delete the user's existing data. Do not ask the user to perform work that you can safely and legitimately complete yourself.

When a test requires the user's Amazon credentials, an interactive desktop session, a paid subscription, or another capability unavailable to you, prepare the test and request only the minimum necessary user action. Never request credentials in chat or collect them in the application.

If a problem can be solved through code, configuration, dependency inspection, documentation, or testing, investigate and solve it. If a genuine external blocker remains, document it precisely and complete everything else.

**The goal is the strongest defensible completion standard: every applicable requirement implemented, every locally testable requirement verified, every claimed result supported by evidence, every defect resolved, and every unavoidable limitation explicitly disclosed.**

Begin with Phase 1 and continue through Phase 10. Do not declare the project finished until the final acceptance audit is complete.
