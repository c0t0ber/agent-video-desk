#!/usr/bin/env python3
"""Footage Desk — a shared desk for picking footage by words (the author + an AI agent).

  python3 <footage-desk skill>/scripts/server.py --project <video folder> [--port 8765]
  → http://127.0.0.1:8765

In the project folder, under _work/review/:
  manifest.json  clips, word timings, frames               (built by cli.py build)
  agent.json     the agent's layer: picks, notes, questions (written by the agent only, via cli.py propose)
  user.json      the author's layer: take / skip / watched / notes  (written by the browser only)
Layers live in separate files so nobody overwrites the other side. The page picks up agent.json changes by itself.
Listens on 127.0.0.1 only. No dependencies beyond the standard library.
"""
import argparse, json, mimetypes, os, re, shutil, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument('--project', required=True)
ap.add_argument('--port', type=int, default=8765)
args = ap.parse_args()
PROJECT = os.path.realpath(args.project)
REVIEW = os.path.join(PROJECT, '_work', 'review')
USER = os.path.join(REVIEW, 'user.json')
AGENT = os.path.join(REVIEW, 'agent.json')
BACKUPS = os.path.join(REVIEW, 'backups')
if not os.path.exists(os.path.join(REVIEW, 'manifest.json')):
    sys.exit(f'no {REVIEW}/manifest.json — first run: python3 {os.path.join(HERE, "cli.py")} --project {args.project} build')
TYPES = {'.lrv': 'video/mp4', '.mp4': 'video/mp4', '.mov': 'video/quicktime', '.jpg': 'image/jpeg', '.png': 'image/png', '.json': 'application/json'}


def log(msg):
    sys.stderr.write('%s %s\n' % (time.strftime('%H:%M:%S'), msg))
    sys.stderr.flush()


def read_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def mtime(p):
    return os.path.getmtime(p) if os.path.exists(p) else 0


def save_user(raw):
    data = json.loads(raw)  # refuse anything that is not JSON
    if not isinstance(data, dict) or not isinstance(data.get('clips'), dict):
        raise ValueError('bad shape')
    os.makedirs(BACKUPS, exist_ok=True)
    if os.path.exists(USER):  # a dated copy at most every 5 minutes — marking by hand is expensive to lose
        last = max([mtime(os.path.join(BACKUPS, f)) for f in os.listdir(BACKUPS)] or [0])
        if time.time() - last > 300:
            shutil.copy2(USER, os.path.join(BACKUPS, time.strftime('user-%Y%m%d-%H%M%S.json')))
    tmp = USER + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, USER)


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
        if rng and (rng.group(1) or rng.group(2)):  # video seeking needs byte ranges
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

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path in ('/', '/index.html'):
            return self.send_bytes(read_bytes(os.path.join(HERE, 'index.html')), 'text/html; charset=utf-8')
        if path == '/api/project':
            return self.send_bytes(read_bytes(os.path.join(REVIEW, 'manifest.json')), 'application/json; charset=utf-8')
        if path == '/api/agent':
            data = read_json(AGENT, {'clips': {}})
            return self.send_json({'mtime': mtime(AGENT), 'data': data})
        if path == '/api/user':
            data = read_json(USER, {'version': 1, 'clips': {}})
            return self.send_json({'mtime': mtime(USER), 'data': data})
        if path == '/api/poll':
            return self.send_json({'agent': mtime(AGENT), 'user': mtime(USER)})
        if path.startswith('/media/'):
            full = os.path.realpath(os.path.join(PROJECT, path[len('/media/'):]))
            if full.startswith(PROJECT + os.sep) and os.path.isfile(full):
                return self.send_file(full)
        self.send_json({'error': 'not found'}, 404)

    def do_PUT(self):
        if urlparse(self.path).path != '/api/user':
            return self.send_json({'error': 'not found'}, 404)
        try:
            save_user(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        except Exception as e:
            log(f'PUT /api/user rejected: {e!r}')
            return self.send_json({'error': str(e)}, 400)
        self.send_json({'ok': True, 'mtime': mtime(USER)})


if __name__ == '__main__':
    srv = ThreadingHTTPServer(('127.0.0.1', args.port), H)
    print(f'Footage Desk: http://127.0.0.1:{args.port}   project: {PROJECT}', flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
