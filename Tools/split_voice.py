#!/usr/bin/env python3
"""Split a character voice recording into one clip per sentence.

Two steps, deliberately kept separate:

  * ffmpeg's silencedetect decides *where* to cut. The recordings are TTS with
    clean 0.25-0.6s gaps between lines, so these boundaries are exact.
  * faster-whisper decides *what each clip is called*, from word-level
    timestamps. The earlier pass in AUDIO/ guessed names from a hardcoded list
    and mislabelled most of them whenever the chunk count drifted; nothing here
    is assumed about what the file contains.

Usage:
    py Tools/split_voice.py                      # every voice file in Music/
    py Tools/split_voice.py path/to/one.mp3      # just this one
    py Tools/split_voice.py --model small.en     # bigger model, better names

Writes Music/voice/<Character>/NN_<line>.mp3 and a manifest.json alongside.
Clips land in a subfolder on purpose: the web app scans Music/ one level deep,
so these never pollute the music playlist.
"""

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MUSIC = os.path.join(ROOT, "Music")
OUT_ROOT = os.path.join(MUSIC, "voice")

# Files that are songs, not dialogue. Everything else in Music/ is fair game.
SONG_HINTS = ("dance mode", "soundtrack", "remix", "jump_higher", "bubbles")


def find_ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    guess = os.path.join(
        ROOT, "AUDIO", "venv", "Lib", "site-packages", "imageio_ffmpeg",
        "binaries", "ffmpeg-win-x86_64-v7.1.exe",
    )
    if os.path.exists(guess):
        return guess
    return "ffmpeg"


FFMPEG = find_ffmpeg()


def character_of(filename):
    """Bingo-2026-...mp3 -> Bingo;  [Bluey]  H...mp3 -> Bluey."""
    base = os.path.basename(filename)
    bracket = re.match(r"\s*\[([A-Za-z]+)\]", base)
    if bracket:
        return bracket.group(1).capitalize()
    word = re.match(r"\s*([A-Za-z]+)", base)
    return word.group(1).capitalize() if word else "Unknown"


def is_voice(path):
    name = os.path.basename(path).lower()
    return not any(h in name for h in SONG_HINTS)


def silence_segments(path, noise="-32dB", min_gap=0.25, min_len=0.30):
    """Speech spans, derived from the gaps between them."""
    cmd = [FFMPEG, "-hide_banner", "-i", path,
           "-af", f"silencedetect=noise={noise}:d={min_gap}", "-f", "null", "-"]
    err = subprocess.run(cmd, stderr=subprocess.PIPE, text=True).stderr

    starts = [float(m.group(1)) for m in re.finditer(r"silence_start:\s*([\d.]+)", err)]
    ends = [float(m.group(1)) for m in re.finditer(r"silence_end:\s*([\d.]+)", err)]

    dur = 0.0
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", err)
    if m:
        h, mi, s = m.groups()
        dur = int(h) * 3600 + int(mi) * 60 + float(s)

    spans, cursor = [], 0.0
    for i, s_start in enumerate(starts):
        if s_start - cursor >= min_len:
            spans.append((cursor, s_start))
        if i < len(ends):
            cursor = ends[i]
    if dur - cursor >= min_len:
        spans.append((cursor, dur))
    return spans


def transcribe_words(path, model_name):
    """Word-level timestamps, or None when faster-whisper isn't installed.

    Cutting does not depend on this — only the clip *names* do. So a missing
    transcriber degrades to numbered clips rather than failing outright, and
    `--rename` can fill the names in later without recutting.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("  ! faster-whisper not installed — cutting only, names will be numbered")
        print("    install it, then re-run with --rename to name them in place")
        return None
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(path, word_timestamps=True, vad_filter=False)
    words = []
    for seg in segments:
        for w in (seg.words or []):
            words.append({"start": w.start, "end": w.end, "word": w.word.strip()})
    return words


def text_for(span, words, pad=0.20):
    """Words whose midpoint sits inside the span (padded, since whisper's
    boundaries drift a little against ffmpeg's)."""
    lo, hi = span[0] - pad, span[1] + pad
    picked = [w["word"] for w in words if lo <= (w["start"] + w["end"]) / 2 <= hi]
    return " ".join(picked).strip()


def safe_name(text, limit=60):
    text = re.sub(r'[<>:"/\\|?*]', "", text).strip(" .")
    text = re.sub(r"\s+", " ", text)
    return text[:limit] or "clip"


def cut(src, start, end, dst):
    subprocess.run(
        [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
         "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
         "-c:a", "libmp3lame", "-q:a", "2", dst],
        check=True,
    )


def process(path, model_name):
    character = character_of(path)
    print(f"\n{os.path.basename(path)}  ->  character: {character}")

    spans = silence_segments(path)
    print(f"  {len(spans)} speech segments")
    if not spans:
        return []

    print("  transcribing...")
    words = transcribe_words(path, model_name)
    if words is not None:
        print(f"  {len(words)} words")

    out_dir = os.path.join(OUT_ROOT, character)
    os.makedirs(out_dir, exist_ok=True)

    entries, n = [], 0
    for start, end in spans:
        line = text_for((start, end), words) if words else ""
        if words is not None and not line:
            print(f"    - {start:6.2f}-{end:6.2f}  (no words, skipped)")
            continue
        n += 1
        fname = f"{n:02d}_{safe_name(line)}.mp3" if line else f"{n:02d}.mp3"
        cut(path, start, end, os.path.join(out_dir, fname))
        entries.append({
            "character": character,
            "index": n,
            "text": line,
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "file": f"voice/{character}/{fname}",
        })
        print(f"    {n:02d}  {end - start:5.2f}s  {line}")
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="specific mp3s (default: voice files in Music/)")
    ap.add_argument("--model", default="base.en", help="whisper model, e.g. base.en / small.en")
    args = ap.parse_args()

    if args.files:
        targets = [os.path.abspath(f) for f in args.files]
    else:
        targets = sorted(
            os.path.join(MUSIC, f)
            for f in os.listdir(MUSIC)
            if f.lower().endswith(".mp3") and is_voice(os.path.join(MUSIC, f))
        )

    if not targets:
        print("nothing to split")
        return 1

    print(f"ffmpeg: {FFMPEG}\nmodel:  {args.model}")
    all_entries = []
    for t in targets:
        all_entries += process(t, args.model)

    os.makedirs(OUT_ROOT, exist_ok=True)
    manifest = os.path.join(OUT_ROOT, "manifest.json")
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, indent=2, ensure_ascii=False)

    by_char = {}
    for e in all_entries:
        by_char[e["character"]] = by_char.get(e["character"], 0) + 1
    print(f"\n{len(all_entries)} clips: " + ", ".join(f"{k} {v}" for k, v in by_char.items()))
    print(f"manifest -> {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
