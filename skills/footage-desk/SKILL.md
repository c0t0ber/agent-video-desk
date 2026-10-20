---
name: footage-desk
description: Footage Desk — a local browser desk where a human and an AI agent pick video footage by words (a paper edit / text-based video editing). Clips play next to their word-level transcript; the human marks ranges take or skip, marks clips watched and leaves notes; the agent adds its own picks, notes and questions, then turns the selection into a cut list. Use when the user wants to review raw footage, select takes or sound bites, do a paper edit, cut a vlog or talking-head video by transcript, says "look at what I marked", "pick the rest", "build a rough cut from my takes", or mentions _work/review/, manifest.json or clip marks — even if "Footage Desk" is not named.
---

# Footage Desk

A shared desk for choosing footage by its words. The human works in the browser, you work through `cli.py`. Each side writes only its own file.

`<skill>` below is the folder that contains this SKILL.md. Scripts live in `<skill>/scripts/`: Python 3.11+ standard library, plus `ffmpeg`/`ffprobe` for building.

## Data

Everything lives in `<project>/_work/review/`:

| File | Who writes it | What it holds |
|---|---|---|
| `manifest.json` | `cli.py build` | clips, word timings, frames, proxy paths |
| `agent.json` | you, via `cli.py propose` | your `pick`s, `note`s and `question`s; the page reloads them within ~3 s |
| `user.json` | browser only | take / skip / watched / notes / replies to you — **never edit or delete it** |
| `proxy/`, `frames/` | `cli.py build` | small browser copies; safe to rebuild |

What the human's marks mean:

- **take** — goes into the cut, exactly these words; you only trim the edges to silence;
- **skip** — never;
- **watched, no mark** — seen and not picked; use only as glue if a scene needs it;
- **not watched** — your call.

## Build

```bash
python3 <skill>/scripts/cli.py --project <video folder> build [--src 'phone/*.mp4' --src 'GX*.MP4'] [--transcribe] [--title "Name"]
```

- By default every video in the project is used, except folders starting with `_` or `.`. Check the list in the output; narrow it with `--src` if renders or junk slipped in.
- Transcripts are looked up in `_work/tr/<name>.json`, `transcripts/<name>.json` and next to the video. Any Whisper / WhisperX JSON with `segments[].words[]` works, in any language. `--transcribe` creates missing ones with the `ru-transcribe` skill (Russian speech only, slow: run it in the background).
- Proxies are 540p H.264. HDR phone footage is tone-mapped on the GPU (VideoToolbox on macOS); if that fails, a plain libx264 proxy is made instead. Files are processed one at a time, and up-to-date proxies are not rebuilt.
- Clip time comes from the `creation_time` tag, else the file time. GoPro writes local time as UTC: if clocks look off, that is the camera.
- Rebuilding never touches `agent.json` or `user.json`. A clip id is its file name, so marks survive rebuilds.

## Start

```bash
python3 <skill>/scripts/server.py --project <video folder> [--port 8765]
```

Give the human http://127.0.0.1:8765; `?clip=<id>` opens a specific clip.

- **Claude Code:** run it with Bash in the background, not in the preview panel (on macOS it cannot read `~/Documents`).
- **Codex:** ask to run outside the sandbox: `nohup python3 … > <project>/_work/review/server.log 2>&1 &`.

## Work

1. `cli.py --project P text [clip …]` — transcript by phrase with timecodes; pick ranges from it.
2. `cli.py --project P read` — per clip: their take/skip marks with the words, clip notes, what happened to your marks (taken / rejected / seen, no answer / not seen) and their replies. `read --ranges` prints only the takes as `clip  a  b  # words`, ready for a cut list or EDL.
3. Write your marks to JSON and submit them with `cli.py --project P propose marks.json`:
   ```json
   {"clips": {"<clip id>": [{"a": 12.3, "b": 18.9, "kind": "pick", "note": "why it goes in", "id": "a1"}]}}
   ```
   Clips missing from the file keep their old marks; `--replace-all` replaces the whole layer. Keep mark `id`s stable between calls: the human's replies are attached to them.
4. Build the cut from their **take** ranges first. Your untouched picks stay; anything they marked **skip** is cut out of every range.
