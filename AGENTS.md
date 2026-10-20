# AGENTS.md

Guidance for AI agents working **on** this repository. To **use** the desks, load the skill you need: `skills/<name>/SKILL.md`.

## Layout

```
.claude-plugin/        Claude Code plugin + marketplace manifests (plugin root = repo root)
.codex-plugin/         Codex plugin manifest
.agents/plugins/       Codex marketplace manifest
skills/script-desk/    SKILL.md + scripts/{server.py, cli.py, store.py, index.html}
skills/footage-desk/   SKILL.md + scripts/{server.py, cli.py, index.html}
skills/ru-transcribe/  SKILL.md + scripts/{transcribe.py, repeats.py, peek.py, compare.py} (uv inline deps)
examples/demo/         demo project used by the README and screenshots
tests/                 unittest suite: real servers, real ffmpeg on generated clips
```

## Contracts that must not break

- **Two layers, two writers.** `user.json` is written only by the browser; `agent.json` only by `cli.py`. Never make one side write the other's file.
- **Script versions are immutable.** `versions/vN.md` is opened with mode `x`; a new round is always a new file.
- **Edits are validated before the human sees them.** `cli.py propose` must reject non-unique or overlapping `old` strings.
- **Offsets:** Python uses code points; the browser gets UTF-16 offsets (`at16`, `len16`). Keep both in sync.
- **The server listens on 127.0.0.1 only** and serves `/media/` strictly inside the project folder.
- **Skills find each other by relative path** inside the plugin (`../../ru-transcribe/scripts/transcribe.py`).

## Conventions

- Python 3.11+, standard library only in `script-desk` and `footage-desk`. Heavy dependencies belong to `ru-transcribe` and are declared inline for `uv run`.
- Every external call (ffmpeg, ffprobe, uv) has a timeout and an error that says what was being done.
- No silent failures: log with context instead of `except: pass` / empty `catch`.
- UI strings go through the `STR` dictionary in each `index.html` (`en` and `ru`); CLI output is English.
- Keep the compact code style; `ruff check .` must pass.
- Update `CHANGELOG.md` (Keep a Changelog) and bump `version` in both `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json` for every release.

## Checks

```bash
python3 -m unittest discover -s tests -v
ruff check .
```
