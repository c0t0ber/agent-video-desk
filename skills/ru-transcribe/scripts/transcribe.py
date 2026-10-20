# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = [
#   "torch",
#   "torchaudio",
#   "numpy",
#   "whisperx",
#   "gigaam @ git+https://github.com/salute-developers/GigaAM.git",
# ]
# ///
"""Verbatim Russian speech transcription with accurate word timestamps.

    uv run transcribe.py <recording: wav/mp3/m4a/mp4…> [--out DIR] [--pretty] [--no-align]

Text: GigaAM-v3 CTC writes exactly what was said, with repeats and false starts (Whisper smooths them away).
Word timing: WhisperX forced alignment (wav2vec2, ru); a word that fails to align keeps the GigaAM timestamp.
Long recordings are split at pauses: GigaAM takes segments up to ~25 s.

Output next to the recording (or in --out):
  <name>.json — segments[].words[] {word, start, end}, Whisper-compatible
  <name>.txt  — [mm:ss.s] segment text
  <name>.srt  — subtitles per segment (with --pretty: punctuation and digits)
"""
import argparse, json, os, subprocess, sys, tempfile, time, wave

import numpy as np

SR = 16000


def decode(path):
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(pcm, np.int16).astype(np.float32) / 32768


def split_by_pauses(x, max_len=18.0, min_len=3.0):
    """Chunks up to max_len seconds, cut in the middle of the longest pause; pure silence is skipped."""
    hop = SR // 100
    n = len(x) // hop
    db = 20 * np.log10(np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1)) + 1e-9)
    noise, speech = np.percentile(db, 10), np.percentile(db, 90)
    thr = min(noise + 10, speech - 12)
    quiet = db < thr
    # pauses of 0.2 s or longer: (middle, length) in hundredths of a second
    pauses, i = [], 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            if j - i >= 20:
                pauses.append(((i + j) // 2, j - i))
            i = j
        else:
            i += 1
    chunks, start = [], 0
    while start < n:
        if n - start <= max_len * 100:
            end = n
        else:
            lo, hi = start + int(min_len * 100), start + int(max_len * 100)
            cand = [(length, mid) for mid, length in pauses if lo <= mid <= hi]
            end = max(cand)[1] if cand else lo + int(np.argmin(db[lo:hi]))  # no pause: cut at the quietest point
        loud = np.nonzero(~quiet[start:end])[0]
        if len(loud):  # trim silence at the edges, keeping a small margin
            a = max(start, start + loud[0] - 15)
            b = min(end, start + loud[-1] + 25)
            chunks.append((a / 100, b / 100))
        start = end
    return chunks


def write_wav(path, x):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def ts(t, srt=False):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",") if srt else f"{int(t // 60):02d}:{t % 60:04.1f}"


def main():
    ap = argparse.ArgumentParser(description="Verbatim Russian speech transcription with accurate word timestamps")
    ap.add_argument("audio")
    ap.add_argument("--out", help="output folder (default: next to the recording)")
    ap.add_argument("--pretty", action="store_true", help="also add readable text with punctuation and digits (for subtitles)")
    ap.add_argument("--no-align", action="store_true", help="skip WhisperX alignment, keep GigaAM timestamps")
    ap.add_argument("--max-chunk", type=float, default=18.0)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    t0 = time.time()
    out_dir = args.out or os.path.dirname(os.path.abspath(args.audio))
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, os.path.splitext(os.path.basename(args.audio))[0])

    x = decode(args.audio)
    chunks = split_by_pauses(x, args.max_chunk)
    print(f"recording {len(x) / SR / 60:.1f} min → {len(chunks)} chunks", file=sys.stderr)

    import gigaam
    ctc = gigaam.load_model("v3_ctc")
    pretty = gigaam.load_model("v3_e2e_rnnt") if args.pretty else None

    segments = []
    with tempfile.TemporaryDirectory() as tmp:
        for k, (a, b) in enumerate(chunks):
            path = os.path.join(tmp, "c.wav")
            write_wav(path, x[int(a * SR):int(b * SR)])
            r = ctc.transcribe(path, word_timestamps=True)
            if not r.text.strip():
                continue
            seg = {"start": round(a, 3), "end": round(b, 3), "text": r.text.strip(),
                   "words": [{"word": w.text, "start": round(a + w.start, 3), "end": round(a + w.end, 3)} for w in r.words]}
            if pretty:
                seg["text_pretty"] = str(pretty.transcribe(path)).strip()
            segments.append(seg)
            print(f"\rtext: {k + 1}/{len(chunks)}", end="", file=sys.stderr)
    print(file=sys.stderr)

    if not args.no_align:
        import whisperx
        model, meta = whisperx.load_align_model(language_code="ru", device=args.device)
        fixed = 0
        for k, s in enumerate(segments):
            res = whisperx.align([{"start": s["start"], "end": s["end"], "text": s["text"]}], model, meta, x, args.device,
                                 return_char_alignments=False)
            aw = [w for seg in res["segments"] for w in seg.get("words", [])]
            if len(aw) == len(s["words"]):
                for w, g in zip(aw, s["words"], strict=True):
                    if "start" in w and "end" in w:
                        g["start"], g["end"] = round(float(w["start"]), 3), round(float(w["end"]), 3)
                        fixed += 1
            print(f"\raligning: {k + 1}/{len(segments)}", end="", file=sys.stderr)
        print(f"\naligned words: {fixed}", file=sys.stderr)

    for i, s in enumerate(segments):
        s["id"] = i
        if s["words"]:
            s["start"], s["end"] = s["words"][0]["start"], s["words"][-1]["end"]

    engine = "gigaam-v3_ctc" + ("" if args.no_align else "+whisperx-align")
    json.dump({"language": "ru", "engine": engine, "segments": segments}, open(base + ".json", "w"), ensure_ascii=False, indent=1)
    with open(base + ".txt", "w") as f:
        for s in segments:
            f.write(f"[{ts(s['start'])}] {s.get('text_pretty') or s['text']}\n")
    with open(base + ".srt", "w") as f:
        for i, s in enumerate(segments, 1):
            f.write(f"{i}\n{ts(s['start'], True)} --> {ts(s['end'], True)}\n{s.get('text_pretty') or s['text']}\n\n")
    nw = sum(len(s["words"]) for s in segments)
    print(f"done in {time.time() - t0:.0f} s: {len(segments)} segments, {nw} words → {base}.json / .txt / .srt")


if __name__ == "__main__":
    main()
