# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy"]
# ///
"""Peek into a stretch of a recording: loudness per 50 ms plus transcript words. Use it to find the exact cut point.

    uv run peek.py <recording> <transcript.json> <from second> <to second>

Each line: time, loudness in dB, a bar, and the words starting in that window. Silence (below −50 dB) has an empty bar.
"""
import json, subprocess, sys

import numpy as np

audio, tr, a, b = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
pcm = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(a), "-to", str(b), "-i", audio, "-ac", "1", "-ar", "16000",
                      "-f", "s16le", "-"], capture_output=True, check=True).stdout
x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
hop = 800
n = len(x) // hop
db = 20 * np.log10(np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1)) + 1e-9)
words = [(w["start"], w["word"].strip()) for s in json.load(open(tr))["segments"] for w in s.get("words", [])
         if a - 1 <= w["start"] <= b]
for i in range(n):
    t = a + i * 0.05
    here = " ".join(f"[{w}]" for s, w in words if t <= s < t + 0.05)
    print(f"{t:8.2f} {db[i]:6.1f} {'█' * max(0, int((db[i] + 66) / 2)):<26} {here}")
