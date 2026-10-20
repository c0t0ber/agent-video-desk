# /// script
# requires-python = ">=3.11"
# ///
"""Find repeats in a transcript: a word or phrase said twice in a row, or restarted a couple of words later.

    uv run repeats.py <transcript.json>

On a raw recording these are retakes, candidates for cutting. On an edited voice track they are dirty cuts.
Some hits are ordinary speech (deliberate repetition for emphasis): judge by meaning.
"""
import json, sys

T = json.load(open(sys.argv[1]))
W = [(w["word"].strip().lower(), w["start"]) for s in T["segments"] for w in s.get("words", [])]
ws = [w for w, _ in W]
shown = set()
for n in (5, 4, 3, 2, 1):          # length of the repeated piece
    for gap in range(0, 5 if n > 1 else 1):   # how many words between the two attempts
        for i in range(len(ws) - 2 * n - gap + 1):
            j = i + n + gap
            if ws[i:i + n] != ws[j:j + n] or any(k in shown for k in range(i, j + n)):
                continue
            if n == 1 and len(ws[i]) < 4:   # one- to three-letter doubled words are almost always noise
                continue
            shown.update(range(i, j + n))
            t = W[i][1]
            kind = "in a row" if gap == 0 else f"{gap} words apart"
            print(f"{int(t // 60)}:{t % 60:04.1f}  ×{n} {kind}:  …{' '.join(ws[max(0, i - 3):j + n + 3])}…")
if not shown:
    print("no repeats found")
