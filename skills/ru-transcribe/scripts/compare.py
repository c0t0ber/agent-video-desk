# /// script
# requires-python = ">=3.11"
# dependencies = ["num2words"]
# ///
"""Compare a transcript with the intended text word by word: what is missing, what is extra, what was said differently.

    uv run compare.py <text: .md or .txt> <transcript.json>

On an edited voice track this finds dirty cuts that repeats.py cannot see:
a clipped word ending, a lost word, a leftover scrap of another take.
On a clean recording it shows where the speaker went off script.

Headings, notes in square brackets (`[diagram: …]`), label lines (`**Label:** …`) and checklists
are dropped from the text. Digits are read as words; word endings are not compared,
because the transcript often gets them wrong while the meaning is the same.
"""
import difflib, json, re, sys

from num2words import num2words


def script_words(path):
    out = []
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for no, raw in enumerate(lines, 1):
        s = raw.strip()
        if (not s or s.startswith("#") or s.startswith("---") or re.match(r"^[-*] \[.\]", s)
                or re.match(r"^\*\*[^*]*:\*\*", s) or re.fullmatch(r"\*[^*]+\*", s)):
            continue
        s = re.sub(r"`[^`]*`", " ", s)        # notes in backticks
        s = re.sub(r"\[[^\]]*\]", " ", s)     # notes in square brackets
        for w in re.findall(r"[0-9]+|[a-zA-Zа-яА-ЯёЁ]+", s):
            if w.isdigit():
                out += [(p, no) for p in num2words(int(w), lang="ru").split()]
            else:
                out.append((w.lower().replace("ё", "е"), no))
    return out


def key(w):
    """A word without its ending, so inflected forms of the same word compare equal."""
    return w[:max(4, len(w) - 2)] if len(w) > 5 else w


text, tr = sys.argv[1], sys.argv[2]
S = script_words(text)
V = [(w["word"].strip().lower().replace("ё", "е"), w["start"])
     for s in json.load(open(tr))["segments"] for w in s.get("words", []) if w["word"].strip()]
a, b = [w for w, _ in S], [w for w, _ in V]
found = 0
for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [key(w) for w in a], [key(w) for w in b], autojunk=False).get_opcodes():
    if tag == "equal" or "".join(a[i1:i2]) == "".join(b[j1:j2]):   # a word split or joined differently is not a difference
        continue
    found += 1
    t = V[min(j1, len(V) - 1)][1]
    line = S[min(i1, len(S) - 1)][1]
    kind = {"delete": "missing in audio", "insert": "extra in audio", "replace": "different"}[tag]
    print(f"{int(t // 60)}:{t % 60:04.1f}  line {line:<4} {kind:<16} "
          f"…{' '.join(b[max(0, j1 - 3):j1])} [{' '.join(a[i1:i2]) or '—'} → {' '.join(b[j1:j2]) or '—'}] {' '.join(b[j2:j2 + 3])}…")
print(f"\ntext has {len(a)} words, audio {len(b)}, differences {found}" if found else "no differences")
