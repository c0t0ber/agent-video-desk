# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.2] - 2026-10-20

### Changed

- Demo clips are no longer committed as binaries; `examples/demo/make_clips.py` generates them with ffmpeg and the system text-to-speech (`say` on macOS, `espeak-ng` on Linux).
- Script Desk: the Russian keyboard-layout map is named `RU_LAYOUT`, so security scanners don't mistake it for a key.

## [0.1.1] - 2026-10-20

### Added

- Animated demo of the Script Desk loop and a social preview image in `docs/images/`.
- Plugin icon (`assets/icon.png`), used as the Codex composer icon and logo.
- `SECURITY.md`: what runs locally, what goes online, how to report a vulnerability.

### Changed

- GitHub Actions are pinned to commit SHAs.
- README states which part downloads dependencies and models, and from where.

### Fixed

- Script Desk: the top bar no longer wraps onto a second line at common laptop widths.

## [0.1.0] - 2026-10-20

### Added

- Script Desk: browser desk for co-editing a video script with an agent — notes for AI / to self, dictation, hand edits, Fix, inline take/skip of proposed edits, immutable version snapshots, mirror file (`init --mirror`).
- Script Desk CLI for agents: `init`, `read`, `text`, `propose`, `note`, `watch` (background watchers) and `wait` (agents without them).
- Footage Desk: browser desk for picking footage by word-level transcript — take/skip marks on words, watched ranges, clip notes, agent picks, notes and questions with replies.
- Footage Desk CLI: `build` (proxies with HDR tone mapping and libx264 fallback, frame strips, manifest from any Whisper-format JSON), `text`, `read`, `read --ranges`, `propose`.
- ru-transcribe: verbatim Russian transcription (GigaAM-v3 CTC) with WhisperX word alignment; `repeats.py`, `peek.py`, `compare.py` for retakes and dirty cuts.
- English UI with a built-in Russian translation (`?lang=ru`).
- Plugin manifests and marketplaces for Claude Code and Codex; `npx skills` compatible layout.
- Demo project, screenshots, CI on Linux and macOS.

[Unreleased]: https://github.com/c0t0ber/agent-video-desk/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/c0t0ber/agent-video-desk/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/c0t0ber/agent-video-desk/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/c0t0ber/agent-video-desk/releases/tag/v0.1.0
