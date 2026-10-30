# Test Report

- Unit tests: 81 passed
- Security tests: 4 passed
- Integration tests: 3 passed (previous run; requires a display)
- Total: 85 unit/security passed, 0 failed
- Offscreen smoke tests cover `ui/player_bar.PlayerBar` (render, state mirror, signals) and the song-only `ui/queue_panel.QueuePanel` (tracking, dedupe, page-queue override, empty-state note) without audio output.
