#!/usr/bin/env python3
"""Footage Desk — the agent's side: build the material, read the author's marks, write your own.

  cli.py --project P build [--src GLOB …] [--transcribe] [--frames-every 5] [--title T]
        project videos → proxies, frames, words → _work/review/manifest.json
  cli.py --project P text [CLIP …]       clip transcripts with timecodes, to pick ranges from
  cli.py --project P read [--ranges]     the author's marks: take / skip / watched, replies to your marks
  cli.py --project P propose FILE.json   your marks → _work/review/agent.json

FILE.json for propose (clips missing from the file stay as they were; --replace-all replaces the whole layer):
  {"clips": {"<clip id>": [{"a": 12.3, "b": 18.9, "kind": "pick", "note": "why it goes in", "id": "optional"}]}}
  kind: pick — goes into the cut, note — a remark, question — a question to the author.

What the author's marks mean:
  take                → goes into the cut, exactly these words (the agent only trims edges to silence)
  skip                → never
  watched, no mark    → seen and not picked: use only as glue if a scene needs it
  not watched         → the agent decides

Standard library + ffmpeg/ffprobe only. Transcripts are Whisper-format JSON (segments[].words[] {word, start, end});
--transcribe produces them for Russian speech with the ru-transcribe skill from this plugin (via uv).
"""
import argparse, datetime as dt, glob, json, os, re, shutil, subprocess, sys, time
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
TRANSCRIBE = os.path.realpath(os.path.join(HERE, '..', '..', 'ru-transcribe', 'scripts', 'transcribe.py'))
VIDEO_EXT = {'.mp4', '.mov', '.m4v', '.mkv', '.avi', '.mts', '.webm'}
PROXY_SHORT = 540        # short side of the proxy, px: enough to review in a browser, small on disk
PROBE_TIMEOUT = 60       # s per ffprobe call
HDR_TRANSFERS = {'smpte2084', 'arib-std-b67'}  # PQ and HLG: phones record these; without tone mapping proxies look washed out
KINDS = {'pick', 'note', 'question'}

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('--project', required=True, help='project folder (the video)')
sub = ap.add_subparsers(dest='cmd', required=True)
p = sub.add_parser('build')
p.add_argument('--src', action='append', default=[], help='glob relative to the project; default: every video except folders starting with _ or .')
p.add_argument('--transcribe', action='store_true', help='transcribe clips that have no transcript (ru-transcribe, Russian speech, slow)')
p.add_argument('--frames-every', type=float, default=5.0, help='one frame every N seconds, shown for parts without speech')
p.add_argument('--title', help='page title; default: the folder name')
p = sub.add_parser('text'); p.add_argument('clips', nargs='*')
p = sub.add_parser('read'); p.add_argument('--ranges', action='store_true', help='only "take" ranges, one line each')
p = sub.add_parser('propose'); p.add_argument('file'); p.add_argument('--replace-all', action='store_true')
args = ap.parse_args()

PROJECT = os.path.realpath(args.project)
REVIEW = os.path.join(PROJECT, '_work', 'review')
MANIFEST = os.path.join(REVIEW, 'manifest.json')
AGENT = os.path.join(REVIEW, 'agent.json')
USER = os.path.join(REVIEW, 'user.json')


def span(sec):
    """Human length: seconds under a minute, minutes above."""
    return f'{sec:.0f} s' if sec < 60 else f'{sec / 60:.1f} min'


def log(msg):
    print(time.strftime('%H:%M:%S'), msg, flush=True)


def write_json(path, data, compact=False):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        else:
            json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def need_manifest():
    if not os.path.exists(MANIFEST):
        sys.exit(f'no {MANIFEST} — first run: python3 {os.path.abspath(__file__)} --project {args.project} build')
    return load_json(MANIFEST, None)


# ── build ──

def run(cmd, timeout, what):
    """Run a tool; on failure say what we were doing and show the tail of its stderr."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f'{what}: took longer than {timeout:.0f} s') from None
    if r.returncode != 0:
        raise RuntimeError(f'{what}: exit {r.returncode}: {(r.stderr or r.stdout).strip()[-400:]}')
    return r.stdout


def probe(path):
    out = run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', path], PROBE_TIMEOUT, f'ffprobe {path}')
    d = json.loads(out)
    v = next((s for s in d.get('streams', []) if s.get('codec_type') == 'video'), None)
    if not v:
        raise RuntimeError(f'{path} has no video stream')
    rot = str(v.get('tags', {}).get('rotate', ''))
    for sd in v.get('side_data_list', []):
        if 'rotation' in sd:
            rot = str(int(sd['rotation']))
    w, h = int(v['width']), int(v['height'])
    return {'w': w, 'h': h, 'portrait': (h > w) != (rot.lstrip('-') in ('90', '270')),
            'hdr': v.get('color_transfer') in HDR_TRANSFERS, 'dur': float(d['format'].get('duration') or v.get('duration') or 0),
            'created': d['format'].get('tags', {}).get('creation_time')}


def find_sources():
    if args.src:
        files = [f for pat in args.src for f in glob.glob(os.path.join(PROJECT, pat), recursive=True)]
    else:
        files = []
        for root, dirs, names in os.walk(PROJECT):
            dirs[:] = sorted(d for d in dirs if not d.startswith(('_', '.')))  # _work, _export… are service folders, not footage
            files += [os.path.join(root, n) for n in names if not n.startswith('.')]
    files = sorted({os.path.realpath(f) for f in files if os.path.splitext(f)[1].lower() in VIDEO_EXT and os.path.isfile(f)})
    stems = {}
    for f in files:
        stems.setdefault(os.path.splitext(os.path.basename(f))[0], []).append(f)
    out = []
    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]
        rel = os.path.relpath(f, PROJECT)
        cid = stem if len(stems[stem]) == 1 else os.path.splitext(rel)[0].replace(os.sep, '__')  # same file name in different folders
        out.append((re.sub(r'[^\w.-]', '_', cid), f))
    return out


def transcript_path(cid, src):
    stem = os.path.splitext(os.path.basename(src))[0]
    for cand in (os.path.join(PROJECT, '_work', 'tr', stem + '.json'), os.path.join(PROJECT, 'transcripts', stem + '.json'),
                 os.path.splitext(src)[0] + '.json'):
        if os.path.exists(cand):
            return cand
    return None


def transcribe(src, dur):
    out = os.path.join(PROJECT, '_work', 'tr')
    os.makedirs(out, exist_ok=True)
    uv = shutil.which('uv')
    if not uv:
        raise RuntimeError('uv is not installed — the transcriber installs its dependencies through it')
    timeout = 900 + dur * 3  # the first run downloads models; after that CPU transcription is well under real time
    run([uv, 'run', TRANSCRIBE, src, '--out', out], timeout, f'transcribing {os.path.basename(src)}')
    return os.path.join(out, os.path.splitext(os.path.basename(src))[0] + '.json')


def words_of(path):
    """→ ([[word, start, end], …], [index of the first word of every phrase])"""
    if not path:
        return [], []
    d = load_json(path, {})
    if d.get('junk'):  # transcript flagged as junk: no usable speech
        return [], []
    W, segs = [], []
    for s in d.get('segments', []):
        ws = [w for w in s.get('words', []) if w.get('word', '').strip() and 'start' in w and 'end' in w]
        if ws:
            segs.append(len(W))
            W += [[w['word'].strip(), round(w['start'], 2), round(w['end'], 2)] for w in ws]
    return W, segs


def make_proxy(src, dst, info):
    """Small H.264 for the browser. Hardware encoder first, libx264 if it is not there; HDR is tone-mapped on the GPU."""
    long_side = PROXY_SHORT * 16 // 9
    common = ['-ac', '2', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart']
    sw_scale = f'scale={PROXY_SHORT}:-2' if info['portrait'] else f'scale=-2:{PROXY_SHORT}'
    attempts = []
    if info['hdr']:
        ow, oh = (PROXY_SHORT, long_side) if info['portrait'] else (long_side, PROXY_SHORT)
        attempts.append(('videotoolbox HDR→SDR', ['-init_hw_device', 'videotoolbox=vt', '-filter_hw_device', 'vt', '-i', src, '-vf',
                         f'format=p010le,hwupload,scale_vt=w={ow}:h={oh}:color_matrix=bt709:color_primaries=bt709:color_transfer=bt709,'
                         'hwdownload,format=p010le,format=yuv420p,fps=30', '-color_primaries', 'bt709', '-color_trc', 'bt709',
                         '-colorspace', 'bt709', '-c:v', 'h264_videotoolbox', '-b:v', '2500k', '-g', '30']))
    attempts.append(('videotoolbox', ['-i', src, '-vf', f'{sw_scale},fps=30,format=yuv420p', '-c:v', 'h264_videotoolbox', '-b:v', '2500k', '-g', '30']))
    attempts.append(('libx264', ['-i', src, '-vf', f'{sw_scale},fps=30,format=yuv420p', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '26', '-g', '30']))
    timeout = 300 + info['dur'] * 2
    errors = []
    for name, a in attempts:
        try:
            run(['ffmpeg', '-y', '-v', 'error'] + a + common + [dst + '.tmp.mp4'], timeout, f'proxy {os.path.basename(src)} ({name})')
            os.replace(dst + '.tmp.mp4', dst)
            if errors:
                log(f'  proxy built with {name}; earlier attempts: {"; ".join(errors)}')
            return
        except RuntimeError as e:
            errors.append(str(e))
    raise RuntimeError(' | '.join(errors))


def make_frames(cid, proxy, every):
    """A frame every N seconds in frames/<id>/, named <N>_<k>.jpg: frame k shows second (k-1)*N."""
    fdir = os.path.join(REVIEW, 'frames', cid)
    os.makedirs(fdir, exist_ok=True)
    n = f'{every:g}'
    have = sorted(glob.glob(os.path.join(fdir, f'{n}_*.jpg')))
    if not have or os.path.getmtime(have[0]) < os.path.getmtime(proxy):
        for f in glob.glob(os.path.join(fdir, '*.jpg')):  # other step or stale proxy
            os.remove(f)
        run(['ffmpeg', '-y', '-v', 'error', '-i', proxy, '-vf', f'fps=1/{every},scale=-2:180', '-q:v', '5',
             os.path.join(fdir, f'{n}_%04d.jpg')], 600, f'frames {cid}')
        have = sorted(glob.glob(os.path.join(fdir, f'{n}_*.jpg')))
    out = []
    for f in have:
        k = int(os.path.splitext(f)[0].rsplit('_', 1)[1])
        out.append([round((k - 1) * every, 2), '/media/' + quote(os.path.relpath(f, PROJECT))])
    return out


def started(info, src):
    """Wall-clock start: the container's creation_time, else the file's mtime minus its length."""
    if info['created']:
        try:
            return dt.datetime.fromisoformat(info['created'].replace('Z', '+00:00')).timestamp(), 'tag'
        except ValueError:
            log(f'  could not parse creation_time "{info["created"]}", using the file time')
    return os.path.getmtime(src) - info['dur'], 'file'


def cmd_build():
    sources = find_sources()
    if not sources:
        sys.exit(f'no videos found in {PROJECT} ({", ".join(sorted(VIDEO_EXT))}); pass --src')
    os.makedirs(os.path.join(REVIEW, 'proxy'), exist_ok=True)
    log(f'footage: {len(sources)} files in {PROJECT}')
    clips, failed, no_words = [], [], []
    for i, (cid, src) in enumerate(sources, 1):
        rel = os.path.relpath(src, PROJECT)
        try:
            info = probe(src)
            proxy = os.path.join(REVIEW, 'proxy', cid + '.mp4')
            if not os.path.exists(proxy) or os.path.getmtime(proxy) < os.path.getmtime(src):
                log(f'[{i}/{len(sources)}] proxy {rel} ({info["dur"]:.0f} s{", HDR" if info["hdr"] else ""})')
                make_proxy(src, proxy, info)
            tr = transcript_path(cid, src)
            if not tr and args.transcribe:
                log(f'[{i}/{len(sources)}] transcribing {rel}')
                tr = transcribe(src, info['dur'])
            W, segs = words_of(tr)
            if not tr:
                no_words.append(rel)
            start, clock_from = started(info, src)
            t = dt.datetime.fromtimestamp(start).astimezone()
            folder = os.path.dirname(rel)
            clips.append({'id': cid, 'kind': 'video', 'src': rel, 'clock_from': clock_from,
                          'label': (folder + ' · ' if folder else '') + os.path.splitext(os.path.basename(src))[0] + (' (vertical)' if info['portrait'] else ''),
                          'start': start, 'dur': round(probe(proxy)['dur'], 2), 'video': '/media/' + quote(os.path.relpath(proxy, PROJECT)),
                          'words': W, 'segs': segs, 'frames': make_frames(cid, proxy, args.frames_every),
                          'day': t.strftime('%d.%m'), 'clock': t.strftime('%H:%M')})
        except (RuntimeError, OSError, ValueError, KeyError) as e:
            log(f'[{i}/{len(sources)}] SKIPPED {rel}: {e}')
            failed.append(rel)
    clips.sort(key=lambda c: c['start'])
    write_json(MANIFEST, {'title': args.title or os.path.basename(PROJECT), 'clips': clips}, compact=True)
    if not os.path.exists(AGENT):
        write_json(AGENT, {'clips': {}})
    tot = sum(c['dur'] for c in clips)
    log(f'done: {len(clips)} clips, {span(tot)}, {sum(len(c["words"]) for c in clips)} words → {MANIFEST}')
    if no_words:
        log(f'no transcript ({len(no_words)}): {", ".join(no_words[:8])}{" …" if len(no_words) > 8 else ""} — '
            'looked in _work/tr/, transcripts/ and next to the file; to transcribe: build --transcribe')
    if failed:
        log(f'failed ({len(failed)}): {", ".join(failed)}')
        sys.exit(1)


# ── reading ──

def words(c, a, b):
    return ' '.join(w[0] for w in c['words'] if w[1] >= a - 0.15 and w[1] < b) or '(no speech)'


def cov(rs, a, b):
    return sum(max(0, min(b, r[1]) - max(a, r[0])) for r in rs)


def cmd_text():
    clips = need_manifest()['clips']
    want = set(args.clips)
    unknown = want - {c['id'] for c in clips}
    if unknown:
        sys.exit(f'no such clips: {", ".join(sorted(unknown))}')
    for c in clips:
        if want and c['id'] not in want:
            continue
        print(f'\n== {c["id"]} · {c["day"]} {c["clock"]} · {c["dur"]:.0f} s · {c["label"]}')
        if not c['words']:
            print('   (no speech)')
        bounds = c['segs'] + [len(c['words'])]
        for s, e in zip(bounds, bounds[1:], strict=False):
            ws = c['words'][s:e]
            if ws:
                print(f'   {ws[0][1]:7.2f}–{ws[-1][2]:7.2f}  {" ".join(w[0] for w in ws)}')


def cmd_read():
    man = need_manifest()
    ai = load_json(AGENT, {'clips': {}})['clips']
    if not os.path.exists(USER):
        sys.exit('no user.json yet — nothing has been marked in Footage Desk')
    U = load_json(USER, {})
    tot_take = tot_seen = tot = 0
    for c in man['clips']:
        u = U.get('clips', {}).get(c['id'], {})
        marks, watched = u.get('marks', []), u.get('watched', [])
        seen = cov(watched, 0, c['dur']); tot_seen += seen; tot += c['dur']
        if args.ranges:
            for m in marks:
                if m['kind'] == 'take':
                    print(f'{c["id"]}\t{m["a"]:.2f}\t{m["b"]:.2f}\t# {words(c, m["a"], m["b"])[:90]}' + (f'  ← {m["note"]}' if m.get('note') else ''))
            continue
        replies = {k.split('/', 1)[1]: v for k, v in U.get('replies', {}).items() if k.startswith(c['id'] + '/')}
        if not marks and not watched and not u.get('note') and not replies:
            continue
        print(f'\n== {c["day"]} {c["clock"]} {c["id"]} ({c["label"]}, {c["dur"]:.0f} s) — watched {seen / max(c["dur"], 0.01) * 100:.0f}%')
        if u.get('note'):
            print(f'   CLIP NOTE: {u["note"]}')
        for m in marks:
            tot_take += (m['b'] - m['a']) if m['kind'] == 'take' else 0
            mark = 'TAKE' if m['kind'] == 'take' else 'SKIP'
            print(f'   {mark} {m["a"]:7.2f}–{m["b"]:7.2f}  {words(c, m["a"], m["b"])[:110]}' + (f'   ← {m["note"]}' if m.get('note') else ''))
        for it in ai.get(c['id'], []):
            d = max(it['b'] - it['a'], 0.01)
            t = sum(max(0, min(it['b'], m['b']) - max(it['a'], m['a'])) for m in marks if m['kind'] == 'take')
            k = sum(max(0, min(it['b'], m['b']) - max(it['a'], m['a'])) for m in marks if m['kind'] == 'skip')
            st = 'taken' if t >= d * .8 else 'rejected' if k >= d * .8 else ('seen, no answer' if cov(watched, it['a'], it['b']) >= d * .6 else 'not seen')
            rep = replies.get(it['id'])
            print(f'   agent {it["id"]:10} {it.get("kind", "pick"):8} {st}' + (f'   REPLY: {rep}' if rep else ''))
    if not args.ranges:
        print(f'\nTotal: take {span(tot_take)}, watched {tot_seen / max(tot, 0.01) * 100:.0f}% of {span(tot)}. '
              f'Updated: {U.get("updated", "?")}')


# ── agent layer ──

def cmd_propose():
    man = {c['id']: c for c in need_manifest()['clips']}
    spec = load_json(args.file, None)
    if not isinstance(spec, dict) or not isinstance(spec.get('clips'), dict):
        sys.exit(f'{args.file}: expected an object {{"clips": {{"<id>": [ … ]}}}}')
    layer = {'clips': {}} if args.replace_all else load_json(AGENT, {'clips': {}})
    replies = load_json(USER, {}).get('replies', {})
    errors, n = [], 0
    for cid, items in spec['clips'].items():
        c = man.get(cid)
        if not c:
            errors.append(f'{cid}: no such clip')
            continue
        out, ids = [], set()
        for i, it in enumerate(items, 1):
            where = f'{cid}[{i}]'
            try:
                a, b = float(it['a']), float(it['b'])
            except (KeyError, TypeError, ValueError):
                errors.append(f'{where}: a and b must be numbers'); continue
            kind = it.get('kind', 'pick')
            if kind not in KINDS:
                errors.append(f'{where}: kind "{kind}", allowed: {", ".join(sorted(KINDS))}'); continue
            if not (0 <= a < b <= c['dur'] + 0.5):
                errors.append(f'{where}: {a}–{b} is outside the clip 0–{c["dur"]}'); continue
            iid = str(it.get('id') or '')
            if not iid or iid in ids:
                iid = next(f'a{k}' for k in range(1, 10**6) if f'a{k}' not in ids)
            ids.add(iid)
            out.append({'id': iid, 'a': round(a, 2), 'b': round(b, 2), 'kind': kind, 'note': str(it.get('note', ''))})
        dropped = [old['id'] for old in layer['clips'].get(cid, []) if old['id'] not in ids and f'{cid}/{old["id"]}' in replies]
        if dropped:
            log(f'  {cid}: the author replied to {", ".join(dropped)}, which are not in the new set — those replies lose their mark')
        layer['clips'][cid] = sorted(out, key=lambda x: x['a'])
        n += len(out)
    if errors:
        sys.exit('agent.json not written:\n  ' + '\n  '.join(errors))
    if args.replace_all:
        gone = [k for k in replies if k.split('/', 1)[0] not in spec['clips']]
        if gone:
            log(f'  --replace-all: the author\'s replies lost their marks: {", ".join(gone[:10])}')
    write_json(AGENT, layer)
    log(f'agent.json: {n} marks in {len(spec["clips"])} clips; {sum(len(v) for v in layer["clips"].values())} in the layer')


{'build': cmd_build, 'text': cmd_text, 'read': cmd_read, 'propose': cmd_propose}[args.cmd]()
