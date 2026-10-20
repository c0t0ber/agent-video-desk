---
name: script-desk
description: Script Desk — a local browser desk where a human and an AI agent co-edit a video script. The human highlights text and leaves notes (for the AI or to self, typed or dictated), edits by hand and presses Fix; the agent answers with concrete edits; the human takes or skips each edit and accepts an immutable version snapshot (v0, v1, …). Use when the user wants to review, rewrite or iterate on a video script, YouTube script, voice-over or long text together with you, says "fix", "I left notes on the script", "look at my notes", "accept the edits", or mentions _work/script/, script versions or a script desk — even if "Script Desk" is not named.
---

# Script Desk

A shared desk for a video script: the human works in the browser, you work through `cli.py`. Each side writes only its own file, so nobody overwrites the other.

`<skill>` below is the folder that contains this SKILL.md. Scripts live in `<skill>/scripts/` and need only Python 3.11+.

## Data

Everything lives in `<project>/_work/script/`:

| File | Who writes it | What it holds |
|---|---|---|
| `versions/vN.md` + `vN.meta.json` | server, on Accept | immutable snapshots |
| `user.json` | browser only | notes, hand-edited draft, Fix request, replies, take/skip decisions — **never edit or delete it** |
| `agent.json` | you, via `cli.py` | your notes, questions and the proposal for the current Fix |

The accepted version is also copied to a mirror file in the project (`script.md` by default, set once with `init --mirror`), unless someone edited that file outside the desk.

If `<project>/transcripts/*.json` exist (Whisper-format), the page shows them next to the script with playable audio of the same name. Voice notes (🎙) are transcribed by the sibling `ru-transcribe` skill (Russian speech; the first run downloads ~2.5 GB of models).

## Start

First version, once per project:

```bash
python3 <skill>/scripts/cli.py --project <video folder> init --from <draft.md> [--mirror script.md]
```

Run the server in the background:

```bash
python3 <skill>/scripts/server.py --project <video folder> [--port 8766]
```

Give the human http://127.0.0.1:8766. If the port is busy, the desk is probably already running: check with `lsof -i :8766` and do not start a second copy on the same project.

- **Claude Code:** run it with Bash in the background. Do not use the preview panel: on macOS it cannot read folders under `~/Documents`.
- **Codex:** the sandbox blocks binding a port and may block `~/Documents`. Ask to run outside the sandbox: `nohup python3 … > <project>/_work/script/server.log 2>&1 &`.

## Answering a Fix

The human presses **Fix** when they want your edits. How you notice:

- **With background watchers** (Claude Code Monitor): watch `python3 -u <skill>/scripts/cli.py --project P watch`. It prints one line per event: `FIX #N requested`, new notes, replies, accepted versions.
- **Without them** (Codex and others): run `cli.py --project P wait --timeout 1500` with a shell timeout above 1500 s. It exits 0 as soon as Fix is pressed and 2 on timeout. Or the human just says "fix" in chat.

Then:

1. `cli.py --project P read` — version, the human's hand edits as a diff, the Fix comment, every open note with its place in the text, replies to your questions.
2. `cli.py --project P text` — the whole working text, exactly as the human sees it.
3. Write a JSON file and submit it with `cli.py --project P propose edits.json`:
   ```json
   {"summary": "what you did, one line",
    "edits":   [{"note": "<note id or null>", "old": "exact piece of the working text", "new": "replacement", "why": "reason"}],
    "answers": [{"note": "<id>", "text": "reply to a note without an edit"}],
    "notes":   [{"quote": "piece of text", "text": "your note", "question": true}]}
   ```
   `old` must be an exact, unique piece of the working text, and edits must not overlap. `propose` checks all of this and tells you what does not apply.
4. The human takes or skips each edit and presses **Accept**. The server writes `v(N+1).md`.

To leave a single note or question without a Fix: `cli.py --project P note "quote" "text" [--question]`.

## Rules

- **Notes "to self" are not instructions.** Take them into account, do not act on them.
- **Keep the author's voice.** When the text comes from their own dictation, keep their phrases almost verbatim; remove only filler, repeats and false starts.
- **Move blocks with one edit over the whole text.** Before you do, check that none of their lines is lost: anything cut goes to a "Parked" section at the end instead of being deleted.
- **"The text changed after Fix"** from `propose` means the human edited by hand after pressing Fix. Re-read `text` and rebuild the edits.
