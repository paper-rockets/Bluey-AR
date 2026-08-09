#!/usr/bin/env python3
"""Rename the cut clips after what is actually said.

Transcripts come from Whisper (Tools/transcribe.html runs it in the browser).
Whisper is solid on ordinary English but mangles the show's vocabulary --
"Wackadoo!" comes back as "What could you do?" -- so each line is fuzzy-matched
against the canonical phrase list before naming. Anything below the confidence
threshold keeps its raw transcript rather than being forced onto a wrong phrase;
a bad guess is worse than a slightly scruffy name.

    py Tools/name_clips.py transcripts.json
"""

import json
import os
import re
import sys
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICE = os.path.join(ROOT, "Music", "voice")
THRESHOLD = 0.72

CANON = [
    "Hi Charlie!", "Hi Avery!", "Hello Charlie.", "Hello Avery.", "Hooray!",
    "For real life?!", "Oh, biscuits!", "Cheese and crackers!", "Wackadoo!",
    "Triffic!", "Gotta be done!", "How very dare you!", "Let's play a game!",
    "Keepy Uppy!", "Dance mode!", "Catch it, Charlie!", "Over here, Avery!",
    "Are you ready, Charlie?", "Are you ready, Avery?", "Come on, let's go!",
    "Come on!", "Let's go!", "Quick, hide!", "Run!", "Jump!",
    "Shake it, Charlie!", "Spin around, Avery!", "Freeze!", "Wiggle your tail!",
    "Jump up high!", "Keep dancing!", "Faster, Charlie!", "Slower, Avery!",
    "Don't stop the music!", "Musical statues!", "Bum shuffle!",
    "Tickle crabs!", "Let's boogie!", "One, two, three, jump!",
    "Awesome dancing, Charlie!", "Awesome dancing, Avery!",
    "Wow, look at Avery go!", "One.", "Two.", "Three!",
]


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def best_match(text):
    t = norm(text)
    if not t:
        return None, 0.0
    best, score = None, 0.0
    for phrase in CANON:
        r = SequenceMatcher(None, t, norm(phrase)).ratio()
        if r > score:
            best, score = phrase, r
    return best, score


def safe(text, limit=60):
    text = re.sub(r'[<>:"/\\|?*]', "", text).strip(" .")
    return re.sub(r"\s+", " ", text)[:limit] or "clip"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    with open(sys.argv[1], encoding="utf-8") as f:
        rows = json.load(f)

    out, corrected, kept = [], 0, 0
    for r in rows:
        raw = (r.get("text") or "").strip()
        phrase, score = best_match(raw)
        if phrase and score >= THRESHOLD:
            label, source = phrase, f"canon {score:.2f}"
            if norm(phrase) != norm(raw):
                corrected += 1
        else:
            label, source = raw, f"raw   {score:.2f}"
            kept += 1

        char = r["character"]
        old = os.path.join(VOICE, char, os.path.basename(r["file"]))
        new_name = f"{r['index']:02d}_{safe(label)}.mp3"
        new = os.path.join(VOICE, char, new_name)

        if os.path.exists(old):
            if old != new:
                if os.path.exists(new):
                    os.remove(new)
                os.rename(old, new)
        else:
            print(f"  ! missing {old}")

        flag = "" if score >= THRESHOLD else "   <-- check"
        print(f"  {char:6} {r['index']:02d}  [{source}]  {raw!r} -> {label!r}{flag}")

        e = dict(r)
        e.update({"text": label, "raw": raw, "confidence": round(score, 3),
                  "file": f"voice/{char}/{new_name}"})
        out.append(e)

    with open(os.path.join(VOICE, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"\n{len(out)} clips | {corrected} corrected to canonical | {kept} kept raw (below {THRESHOLD})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
