"""Shared bits for the tests: paths to the scripts, running them, a throwaway local server."""
import json, os, socket, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, 'skills')
SCRIPT_DESK = os.path.join(SKILLS, 'script-desk', 'scripts')
FOOTAGE_DESK = os.path.join(SKILLS, 'footage-desk', 'scripts')


def run(script, *args, timeout=60):
    return subprocess.run([sys.executable, script, *map(str, args)], capture_output=True, text=True, timeout=timeout)


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Server:
    """Start server.py on a free port, wait until it answers, stop it on exit."""

    def __init__(self, script, project):
        self.port = free_port()
        self.proc = subprocess.Popen([sys.executable, script, '--project', project, '--port', str(self.port)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def get(self, path):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}{path}', timeout=5) as r:
            return json.loads(r.read())

    def __enter__(self):
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError('server died on start: ' + self.proc.stderr.read())
            try:
                with socket.create_connection(('127.0.0.1', self.port), timeout=0.5):
                    return self
            except OSError:
                time.sleep(0.1)
        raise RuntimeError('server did not come up within 10 s')

    def __exit__(self, *exc):
        self.proc.terminate()
        self.proc.wait(timeout=5)
        self.proc.stdout.close()
        self.proc.stderr.close()
