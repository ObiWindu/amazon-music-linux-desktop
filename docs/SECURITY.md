# Security

## Threat model
Malicious links, malicious web content, cross-origin navigation, local users reading profile, diagnostic leakage, malicious downloads, corrupt config, renderer crashes.

## Controls
- Dedicated profile directory with 0700 permissions.
- Navigation policy with hostname boundary checks.
- Dangerous schemes blocked (javascript, data, file, ftp, intent).
- External links opened in system browser.
- Downloads require confirmation and destination validation.
- Logs redact passwords, cookies, tokens, licenses.
- No QWebChannel bridge.
- No credential capture.

## Known limitations
- Widevine CDM is system-provided; app does not bundle it.
