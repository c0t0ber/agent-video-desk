"""Script Desk data: version snapshots, the author's layer (user.json) and the agent's layer (agent.json).

Shared by server.py (the browser side) and cli.py (the agent side).
Offsets in Python are code points; the browser also gets UTF-16 offsets (at16),
because JavaScript counts strings that way and emoji outside the BMP take two positions there.
"""
import hashlib, json, os, re, time


DEFAULT_MIRROR = 'script.md'


def write_json(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def read_text(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def read_json(path, default=None):
    """JSON from a file, or `default` when there is no file."""
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def sha1(text):
    return hashlib.sha1(text.encode()).hexdigest()


def cp_to_u16(text, i):
    return len(text[:i].encode('utf-16-le')) // 2


def u16_to_cp(text, i):
    n = 0
    for k, ch in enumerate(text):
        if n >= i:
            return k
        n += 2 if ord(ch) > 0xFFFF else 1
    return len(text)


def locate(text, old, hint=None):
    """Where `old` sits in `text`. With a hint, the nearest occurrence wins; without one it must be unique."""
    if not old:
        raise ValueError('empty old')
    if hint is not None and text[hint:hint + len(old)] == old:
        return hint
    hits = [m.start() for m in re.finditer(re.escape(old), text)]
    if not hits:
        raise ValueError(f'not found in the text: "{old[:80]}"')
    if hint is not None:
        return min(hits, key=lambda h: abs(h - hint))
    if len(hits) > 1:
        raise ValueError(f'found {len(hits)} times, quote a longer piece: "{old[:80]}"')
    return hits[0]


def apply_edits(text, edits):
    """Edits are {old, new, at?}; they must not overlap. Returns the new text."""
    placed = []
    for e in edits:
        at = locate(text, e['old'], e.get('at'))
        placed.append((at, at + len(e['old']), e['new']))
    placed.sort()
    for (_a1, b1, _), (a2, _b, _n) in zip(placed, placed[1:], strict=False):
        if a2 < b1:
            raise ValueError('edits overlap')
    out, pos = [], 0
    for a, b, new in placed:
        out.append(text[pos:a]); out.append(new); pos = b
    out.append(text[pos:])
    return ''.join(out)


class Store:
    def __init__(self, project):
        self.project = os.path.realpath(project)
        self.dir = os.path.join(self.project, '_work', 'script')
        self.vdir = os.path.join(self.dir, 'versions')
        self.user = os.path.join(self.dir, 'user.json')
        self.agent = os.path.join(self.dir, 'agent.json')
        self.backups = os.path.join(self.dir, 'backups')
        self.mirror_state = os.path.join(self.dir, 'mirror.json')
        # the accepted version is copied to <project>/<mirror file>; the name is fixed at `init --mirror`
        self.mirror = os.path.join(self.project, read_json(self.mirror_state, {}).get('file') or DEFAULT_MIRROR)

    # ── versions ──
    def versions(self):
        if not os.path.isdir(self.vdir):
            return []
        names = [f[:-3] for f in os.listdir(self.vdir) if re.fullmatch(r'v\d+\.md', f)]
        return sorted(names, key=lambda n: int(n[1:]))

    def latest(self):
        v = self.versions()
        return v[-1] if v else None

    def read_version(self, name):
        return read_text(os.path.join(self.vdir, name + '.md'))

    def read_meta(self, name):
        p = os.path.join(self.vdir, name + '.meta.json')
        return read_json(p, {})

    def versions_info(self):
        out = []
        for n in self.versions():
            m = self.read_meta(n)
            out.append({'name': n, 'made': m.get('made'), 'summary': m.get('summary', ''), 'by': m.get('by', '')})
        return out

    def write_version(self, text, meta):
        os.makedirs(self.vdir, exist_ok=True)
        last = self.latest()
        name = 'v%d' % (int(last[1:]) + 1 if last else 0)
        with open(os.path.join(self.vdir, name + '.md'), 'x', encoding='utf-8') as f:  # 'x': a snapshot is never overwritten
            f.write(text)
        write_json(os.path.join(self.vdir, name + '.meta.json'), {'name': name, 'made': time.strftime('%Y-%m-%d %H:%M:%S'), **meta})
        return name, self.write_mirror(text)

    def set_mirror(self, name):
        """Pick the mirror file name before the first version is written (init --mirror)."""
        if os.path.basename(name) != name or not name.endswith('.md'):
            raise ValueError(f'mirror must be a plain .md file name inside the project, got "{name}"')
        self.mirror = os.path.join(self.project, name)

    def write_mirror(self, text):
        """Copy the current version to the mirror file unless someone edited that file outside Script Desk."""
        state = read_json(self.mirror_state, {})
        if os.path.exists(self.mirror):
            have = sha1(read_text(self.mirror))
            if have != state.get('hash'):
                return f'{os.path.basename(self.mirror)} was edited outside Script Desk, left it as is'
        with open(self.mirror, 'w', encoding='utf-8') as f:
            f.write(text)
        write_json(self.mirror_state, {'file': os.path.basename(self.mirror), 'hash': sha1(text)})
        return None

    # ── layers ──
    def load_user(self):
        d = read_json(self.user, {})
        d.setdefault('version', 1)
        d.setdefault('base', self.latest())
        d.setdefault('draft', None)
        d.setdefault('notes', [])
        d.setdefault('replies', {})
        d.setdefault('fix', None)
        d.setdefault('decisions', {})
        return d

    def load_agent(self):
        d = read_json(self.agent, {})
        d.setdefault('notes', [])
        d.setdefault('proposal', None)
        return d

    def save_agent(self, d):
        os.makedirs(self.dir, exist_ok=True)
        write_json(self.agent, d)

    def working_text(self, user=None):
        """What the author is looking at: their hand edits on top of the latest version, or the version itself."""
        u = user or self.load_user()
        latest = self.latest()
        if u.get('draft') is not None and u.get('base') == latest:
            return u['draft']
        return self.read_version(latest)

    # ── accept ──
    def accept(self, take, proposal_id):
        u = self.load_user()
        c = self.load_agent()
        base = self.working_text(u)
        p = c.get('proposal')
        edits = []
        if take:
            if not p or p.get('id') != proposal_id:
                raise ValueError('this proposal is outdated, reload the page')
            if p.get('base_hash') != sha1(base):
                raise ValueError('the text changed after Fix, the AI edits would land in the wrong place')
            edits = [e for e in p['edits'] if e['id'] in take]
        text = apply_edits(base, edits) if edits else base
        latest = self.latest()
        if text == self.read_version(latest):
            raise ValueError('nothing to save: the text is the same as ' + latest)
        meta = {'from': latest, 'by': 'author + AI' if edits else 'author',
                'hand_edits': u.get('draft') is not None and u.get('base') == latest,
                'proposal': p.get('id') if p and edits else None,
                'summary': (p.get('summary') or '') if p and edits else 'hand edits',
                'taken': [e['id'] for e in edits],
                'skipped': [e['id'] for e in (p or {}).get('edits', []) if e['id'] not in take] if p and edits else []}
        name, warn = self.write_version(text, meta)
        return {'version': name, 'text': text, 'warning': warn}
