---
name: ru-transcribe
description: Verbatim Russian speech-to-text for video editing — exact words including repeats, retakes and false starts (GigaAM-v3 CTC) plus accurate per-word timestamps (WhisperX forced alignment), Whisper-compatible JSON, TXT and SRT. Use whenever Russian audio or video needs a transcript, word-level timecodes, subtitles, finding retakes and dirty cuts, a paper edit, aligning captions or animation to words, or checking an edited voice track against the script — even when the user says "run it through Whisper", "transcribe", "timecode it", "find where they said it", "find the retakes". Prefer it over plain Whisper for Russian; use Whisper for other languages.
---

# Verbatim Russian transcription for editing

`<skill>` below is the folder that contains this SKILL.md.

## Why not just Whisper

Whisper is a language model, so it tidies speech up. For editing that breaks two things:

- **It drops repeats and false starts.** A phrase said twice is written once. The retake stays in the audio but not in the text, the cut leaves a scrap behind, and checking the cut with the same Whisper does not see it either.
- **Word boundaries drift.** Pauses get absorbed into neighbouring words, so a cut on its timestamps lands mid-word.

So this skill combines:

1. **Text — GigaAM-v3 CTC.** Writes exactly what was said: repeats included, no punctuation, numbers as words. More accurate than Whisper on Russian.
2. **Word timing — WhisperX forced alignment** (wav2vec2, Russian model): fits the finished text to the audio to within tens of milliseconds. A word that fails to align keeps GigaAM's own timestamp.

## Run

```bash
uv run <skill>/scripts/transcribe.py <recording> [--out DIR] [--pretty] [--no-align]
```

- `<recording>` — anything ffmpeg reads: wav, mp3, m4a, mp4, mov.
- `--out` — output folder (default: next to the recording).
- `--pretty` — add a readable version with punctuation and digits (GigaAM-v3 e2e) for on-screen subtitles. Do not cut by it: it smooths out false starts.
- `--no-align` — skip WhisperX and keep GigaAM timestamps: faster, coarser.

Dependencies install themselves through `uv` (inline script metadata). The first run downloads about 2.5 GB of models. Requires `ffmpeg`. CPU works; long recordings are split at pauses into chunks of up to 18 s automatically.

## Output

Three files named after the recording:

- `<name>.json` — the main one, Whisper-compatible, so anything that reads Whisper JSON reads it:
  ```json
  {"segments": [{"id": 0, "start": 79.1, "end": 83.7, "text": "…",
                 "words": [{"word": "…", "start": 79.1, "end": 79.32}]}]}
  ```
  With `--pretty`, each segment also has `text_pretty`.
- `<name>.txt` — `[mm:ss.s] segment text`, for reading and spotting retakes.
- `<name>.srt` — subtitles per segment.

## Cutting retakes with it

1. **Find repeats.** The same phrase two or three times in a row is a retake; usually the last clean one is kept.
   ```bash
   uv run <skill>/scripts/repeats.py <name>.json
   ```
   It lists both immediate repeats and restarts a few words later. Some hits are deliberate repetition; judge by meaning.
2. **Cut by words from the `.json`.** A range starts at the first word's `start` and ends at the last word's `end`. Move the boundary into the quietest spot nearby rather than cutting exactly on the timestamp. Extend the end to the first silence after the word: soft endings ring longer than their timestamp, and cutting on it clips them.
3. **If a cut catches something extra,** look at the stretch:
   ```bash
   uv run <skill>/scripts/peek.py <recording> <name>.json 293.8 296.2
   ```
   It prints loudness per 50 ms with the words, so you can see where a word really ends and where the pause is.
4. **Check the result with the same tool.** Transcribe the edited voice track and compare it with the script word by word:
   ```bash
   uv run <skill>/scripts/compare.py <script .md or .txt> <name>.json
   ```
   It prints the timecode, the script line and what differs: missing in audio, extra in audio, said differently. A clipped word, a scrap of another take or a lost word means a dirty cut. `repeats.py` alone is not enough for this check, and Whisper is useless here: it smooths away exactly the scraps you are looking for.

   Use `compare.py` before editing too: it shows where the speaker skipped or changed the script.

## Notes

- **Numbers are words** in the main text; digits appear only in `text_pretty`. When searching for a phrase, treat "20" and its spelled-out form as the same.
- **No punctuation, lower case** in the main text. Fine for cutting; use `--pretty` for subtitles.
- **Silence is skipped.** If a stretch is missing from the transcript, it was below the threshold; check it with `peek.py`.
- **Russian only.** The alignment model is Russian. For other languages use Whisper + WhisperX with that language's alignment model; Footage Desk reads that JSON as is.
- **Tip for the speaker:** after a slip, pause for two seconds and repeat the whole phrase. Retakes then split at pauses almost by themselves.
