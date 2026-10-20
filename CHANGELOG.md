# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/c0t0ber/agent-video-desk/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/c0t0ber/agent-video-desk/releases/tag/v0.1.0
