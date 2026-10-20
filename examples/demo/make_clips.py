#!/usr/bin/env python3
"""Build the three demo clips for examples/demo (they are not shipped as binaries).

  python3 examples/demo/make_clips.py

Each clip is a moving colour gradient with a synthetic voice reading one line. The voice comes from
macOS `say` (the transcripts in transcripts/ were made from it), or `espeak-ng` / `espeak` on Linux;
without any of them the clips are silent. Word timings in transcripts/ match the macOS voice; with
another voice they are approximate, which is fine for trying the desks.

Needs ffmpeg. Writes clips/ride_01.mp4 … ride_03.mp4 next to this file and skips clips that already exist.
"""
import os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'clips')
TIMEOUT = 120  # s per external call; each clip is under 10 s long
CLIPS = [  # name, spoken line, gradient colours, creation time (the desk sorts and groups clips by it)
    ('ride_01', "So the plan for today is simple. Ride to the lighthouse, eat something, and come back before dark. "
                "That's it. That's the whole plan.", '0x1e3a5f:c1=0x4a90c2', '2026-10-18T01:11:00Z'),
    ('ride_02', "Okay, this climb. This climb is way worse than it looked on the map. I'm pushing the bike now. "
                "I'm honestly thinking about turning back.", '0x5a3d1f:c1=0xc28a4a', '2026-10-18T02:12:00Z'),
    ('ride_03', "We made it. The wind up here is crazy, I can barely stand. But look at this view. "
                "Every metre of pushing was worth it.", '0x1f4d3a:c1=0x6ac29a', '2026-10-18T03:13:00Z'),
]


def run(cmd, what):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        sys.exit(f'{what}: took longer than {TIMEOUT} s')
    if r.returncode != 0:
        sys.exit(f'{what}: exit {r.returncode}: {(r.stderr or r.stdout).strip()[-400:]}')


def speak(text, path):
    """Synthesize `text` to an audio file; return its path, or None when no TTS engine is installed."""
    if shutil.which('say'):
        run(['say', '-v', 'Samantha', '-r', '170', '-o', path + '.aiff', text], 'say')
        return path + '.aiff'
    for engine in ('espeak-ng', 'espeak'):
        if shutil.which(engine):
            run([engine, '-v', 'en-us', '-s', '165', '-w', path + '.wav', text], engine)
            return path + '.wav'
    return None


def main():
    if not shutil.which('ffmpeg'):
        sys.exit('ffmpeg is required: https://ffmpeg.org/download.html')
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, line, colours, created in CLIPS:
            dst = os.path.join(OUT, name + '.mp4')
            if os.path.exists(dst):
                print(f'{name}: exists, skipped')
                continue
            audio = speak(line, os.path.join(tmp, name))
            video = ['-f', 'lavfi', '-i', f'gradients=s=960x540:c0={colours}:speed=0.015:rate=24']
            if audio:
                cmd = ['ffmpeg', '-y', '-v', 'error', *video, '-i', audio, '-shortest', '-c:a', 'aac', '-b:a', '96k']
            else:
                print(f'{name}: no say/espeak found, making a silent clip')
                cmd = ['ffmpeg', '-y', '-v', 'error', *video, '-t', '8']
            run(cmd + ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '30', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                       '-metadata', f'creation_time={created}', dst], f'ffmpeg {name}')
            print(f'{name}: {dst}')


if __name__ == '__main__':
    main()
