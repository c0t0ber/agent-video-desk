#!/usr/bin/env python3
"""Script Desk — a shared desk for a video script (the author + an AI agent).

  python3 <script-desk skill>/scripts/server.py --project <video folder> [--port 8766]
  → http://127.0.0.1:8766

In the project folder, under _work/script/:
  versions/vN.md   script snapshots, never changed once written (the server writes them on "Accept")
  user.json        the author's layer: notes (for AI / to self), hand edits, Fix request, replies  (written by the browser only)
  agent.json       the agent's layer: notes, questions, proposed edits for a Fix  (written by the agent only, via cli.py)
The server writes a new version when the author accepts: draft + taken edits → v(N+1).md.
The current version is copied to the mirror file (script.md by default) unless it was edited outside Script Desk.
Listens on 127.0.0.1 only. No dependencies beyond the standard library.
"""
import argparse, glob, json, mimetypes, os, re, shutil, subprocess, sys, time
import socketserver
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument('--project', required=True)
ap.add_argument('--port', type=int, default=8766)
args = ap.parse_args()
S = store.Store(args.project)
if not S.versions():
    sys.exit(f'no versions in {S.dir} — first run: python3 {os.path.join(HERE, "cli.py")} --project {args.project} init --from <script.md>')
TYPES = {'.wav': 'audio/wav', '.m4a': 'audio/mp4', '.mp3': 'audio/mpeg', '.webm': 'audio/webm', '.mp4': 'audio/mp4', '.json': 'application/json'}
# voice notes are transcribed by the sibling ru-transcribe skill shipped in the same plugin
TRANSCRIBE = os.path.realpath(os.path.join(HERE, '..', '..', 'ru-transcribe', 'scripts', 'transcribe.py'))
VOICE_TIMEOUT = 600  # s; the first run downloads ~2.5 GB of models, after that a one-minute note takes seconds
UV = shutil.which('uv') or os.path.expanduser('~/.local/bin/uv')


def log(msg):
    sys.stderr.write('%s %s\n' % (time.strftime('%H:%M:%S'), msg))
    sys.stderr.flush()


def read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def mtime(p):
    return os.path.getmtime(p) if os.path.exists(p) else 0


def save_user(raw):
    data = json.loads(raw)  # refuse anything that is not JSON
    if not isinstance(data, dict) or not isinstance(data.get('notes'), list):
        raise ValueError('bad shape')
    os.makedirs(S.backups, exist_ok=True)
    if os.path.exists(S.user):  # a dated copy at most every 5 minutes — notes by hand are expensive to lose
        last = max([mtime(os.path.join(S.backups, f)) for f in os.listdir(S.backups)] or [0])
        if time.time() - last > 300:
            shutil.copy2(S.user, os.path.join(S.backups, time.strftime('user-%Y%m%d-%H%M%S.json')))
    store.write_json(S.user, data)


def transcript():
    """The project's recordings: transcripts/<stem>.json + an audio file with the same stem."""
    out = []
    for js in sorted(glob.glob(os.path.join(S.project, 'transcripts', '*.json'))):
        stem = os.path.splitext(os.path.basename(js))[0]
        audio = None
        for d in (S.project, os.path.join(S.project, 'transcripts')):
            for ext in ('.wav', '.m4a', '.mp3'):
                if os.path.exists(os.path.join(d, stem + ext)):
                    audio = os.path.relpath(os.path.join(d, stem + ext), S.project)
                    break
            if audio:
                break
        segs = store.read_json(js, {}).get('segments', [])
        out.append({'name': stem, 'audio': audio,
                    'segments': [{'start': s['start'], 'end': s['end'], 'text': s.get('text_pretty') or s['text']} for s in segs]})
    return out


def voice(raw, ctype):
    """A spoken note: keep the recording, return its text (GigaAM, with punctuation)."""
    vdir = os.path.join(S.dir, 'voice')
    os.makedirs(vdir, exist_ok=True)
    ext = '.mp4' if 'mp4' in ctype else '.ogg' if 'ogg' in ctype else '.webm'
    name = time.strftime('voice-%Y%m%d-%H%M%S') + ext
    path = os.path.join(vdir, name)
    with open(path, 'wb') as f:
        f.write(raw)
    if not os.path.exists(TRANSCRIBE):
        raise RuntimeError(f'{TRANSCRIBE} is missing — the plugin is not installed completely')
    log(f'voice: {name}, {len(raw) // 1024} KB → transcribing')
    try:
        r = subprocess.run([UV, 'run', TRANSCRIBE, path, '--out', vdir, '--no-align', '--pretty'], capture_output=True, text=True, timeout=VOICE_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f'transcribing {name} took longer than {VOICE_TIMEOUT} s; the recording is kept at {path}') from None
    js = os.path.splitext(path)[0] + '.json'
    if r.returncode != 0 or not os.path.exists(js):
        raise RuntimeError(f'transcribing {name} failed (exit {r.returncode}): ' + (r.stderr or r.stdout)[-300:])
    segs = store.read_json(js, {}).get('segments', [])
    text = ' '.join((s.get('text_pretty') or s['text']).strip() for s in segs).strip()
    return {'text': text, 'audio': os.path.relpath(path, S.project)}


class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *a):
        if not self.path.startswith(('/media/', '/api/poll')):
            sys.stderr.write('%s %s\n' % (time.strftime('%H:%M:%S'), fmt % a))

    def send_bytes(self, body, ctype, code=200):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj, code=200):
        self.send_bytes(json.dumps(obj, ensure_ascii=False).encode(), 'application/json; charset=utf-8', code)

    def send_file(self, path):
        size = os.path.getsize(path)
        ctype = TYPES.get(os.path.splitext(path)[1].lower()) or mimetypes.guess_type(path)[0] or 'application/octet-stream'
        start, end = 0, size - 1
        rng = re.match(r'bytes=(\d*)-(\d*)', self.headers.get('Range', ''))
        if rng and (rng.group(1) or rng.group(2)):  # audio seeking needs byte ranges
            if rng.group(1):
                start = int(rng.group(1)); end = min(int(rng.group(2)), size - 1) if rng.group(2) else size - 1
            else:
                start = max(0, size - int(rng.group(2)))
            if start > end or start >= size:
                self.send_response(416); self.send_header('Content-Range', f'bytes */{size}'); self.send_header('Content-Length', '0'); self.end_headers(); return
            self.send_response(206)
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        else:
            self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Cache-Control', 'max-age=3600')
        self.end_headers()
        try:
            with open(path, 'rb') as f:
                f.seek(start); left = end - start + 1
                while left > 0:
                    chunk = f.read(min(262144, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk); left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the player dropped the request while seeking

    def body(self):
        return self.rfile.read(int(self.headers.get('Content-Length', 0)))

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path in ('/', '/index.html'):
            return self.send_bytes(read_bytes(os.path.join(HERE, 'index.html')), 'text/html; charset=utf-8')
        if path == '/api/project':
            return self.send_json({'name': os.path.basename(S.project), 'mirror': os.path.basename(S.mirror), 'versions': S.versions_info(), 'transcripts': transcript()})
        if path.startswith('/api/version/'):
            name = path[len('/api/version/'):]
            if name in S.versions():
                return self.send_json({'name': name, 'text': S.read_version(name), 'meta': S.read_meta(name)})
        if path == '/api/agent':
            return self.send_json({'mtime': mtime(S.agent), 'data': S.load_agent()})
        if path == '/api/user':
            return self.send_json({'mtime': mtime(S.user), 'data': S.load_user()})
        if path == '/api/poll':
            return self.send_json({'agent': mtime(S.agent), 'user': mtime(S.user), 'versions': S.versions()})
        if path.startswith('/media/'):
            full = os.path.realpath(os.path.join(S.project, path[len('/media/'):]))
            if full.startswith(S.project + os.sep) and os.path.isfile(full):
                return self.send_file(full)
        self.send_json({'error': 'not found'}, 404)

    def do_PUT(self):
        if urlparse(self.path).path != '/api/user':
            return self.send_json({'error': 'not found'}, 404)
        try:
            save_user(self.body())
        except Exception as e:
            log(f'PUT /api/user rejected: {e!r}')
            return self.send_json({'error': str(e)}, 400)
        self.send_json({'ok': True, 'mtime': mtime(S.user)})

    def do_POST(self):
        if urlparse(self.path).path == '/api/voice':
            try:
                return self.send_json(voice(self.body(), self.headers.get('Content-Type', '')))
            except Exception as e:
                log(f'POST /api/voice failed: {e}')
                return self.send_json({'error': str(e)}, 500)
        if urlparse(self.path).path != '/api/accept':
            return self.send_json({'error': 'not found'}, 404)
        try:
            req = json.loads(self.body())
            res = S.accept(req.get('take') or [], req.get('proposal'))
        except Exception as e:
            log(f'POST /api/accept rejected: {e}')
            return self.send_json({'error': str(e)}, 400)
        log(f'accepted version {res["version"]}' + (f' ({res["warning"]})' if res.get('warning') else ''))
        self.send_json({'ok': True, **res})


class LocalServer(ThreadingHTTPServer):
    """HTTPServer.server_bind calls socket.getfqdn(), a reverse DNS lookup that can hang for a long time on macOS.
    The desk only ever listens on 127.0.0.1, so the name is not needed."""

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


if __name__ == '__main__':
    srv = LocalServer(('127.0.0.1', args.port), H)
    print(f'Script Desk: http://127.0.0.1:{args.port}   project: {S.project}', flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
