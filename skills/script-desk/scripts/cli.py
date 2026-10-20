#!/usr/bin/env python3
"""Script Desk — the agent's side (Claude Code, Codex or any agent that can run shell commands).

  cli.py --project P init --from FILE.md [--mirror script.md]   first version v0 from an existing file
  cli.py --project P read                    current state: version, hand edits, Fix request, notes, replies
  cli.py --project P text                    the whole working text (exactly what the author sees)
  cli.py --project P propose FILE.json       propose edits for the Fix → agent.json
  cli.py --project P note "quote" "text" [--question]   leave a note or a question on the text
  cli.py --project P watch                   event stream for a background watcher (Monitor in Claude Code)
  cli.py --project P wait [--timeout 1800]   block until Fix is pressed, then exit (agents without background watchers)

FILE.json for propose:
  {"summary": "what you did, one line",
   "edits":   [{"note": "<note id or null>", "old": "exact piece of the text", "new": "replacement", "why": "reason"}],
   "answers": [{"note": "<id>", "text": "reply to a note without an edit"}],
   "notes":   [{"quote": "piece of the text", "text": "your note", "question": true}]}
`old` is searched in the working text; if it occurs more than once, quote a longer piece. Edits must not overlap.
"""
import argparse, difflib, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store  # noqa: E402
from store import apply_edits, cp_to_u16, locate, sha1, u16_to_cp  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('--project', required=True, help='project folder (the video)')
sub = ap.add_subparsers(dest='cmd', required=True)
p = sub.add_parser('init'); p.add_argument('--from', dest='src', required=True)
p.add_argument('--mirror', default=store.DEFAULT_MIRROR, help='file in the project that always holds the accepted version')
sub.add_parser('read')
sub.add_parser('text')
p = sub.add_parser('propose'); p.add_argument('file')
p = sub.add_parser('note'); p.add_argument('quote'); p.add_argument('text'); p.add_argument('--question', action='store_true')
p = sub.add_parser('watch'); p.add_argument('--every', type=float, default=1.0); p.add_argument('--quiet-for', type=float, default=20.0)
p = sub.add_parser('wait'); p.add_argument('--every', type=float, default=1.0); p.add_argument('--timeout', type=float, default=1800.0)
args = ap.parse_args()
S = store.Store(args.project)
CLI = os.path.abspath(__file__)


def ctx(text, a, b, pad=60):
    pre = text[max(0, a - pad):a].replace('\n', ' ⏎ ')
    post = text[b:b + pad].replace('\n', ' ⏎ ')
    return f'…{pre}[[{text[a:b]}]]{post}…'


def anchor(text, n):
    """Find a browser note in the text: by its UTF-16 offset first, then by the quote."""
    q = n.get('quote') or ''
    hint = u16_to_cp(text, n['start']) if isinstance(n.get('start'), int) else None
    try:
        a = locate(text, q, hint)
        return a, a + len(q)
    except ValueError:
        return None


def cmd_init():
    if S.versions():
        sys.exit(f'versions already exist: {", ".join(S.versions())}')
    try:
        S.set_mirror(args.mirror)
    except ValueError as err:
        sys.exit(str(err))
    text = store.read_text(args.src)
    name, warn = S.write_version(text, {'from': None, 'by': 'import', 'summary': 'from ' + os.path.basename(args.src)})
    print(f'{name} ← {args.src}; accepted versions are mirrored to {os.path.relpath(S.mirror)}' + (f'  ({warn})' if warn else ''))


def cmd_read():
    u, c = S.load_user(), S.load_agent()
    latest = S.latest()
    text = S.working_text(u)
    print(f'version: {latest}   all: {", ".join(S.versions())}')
    if u.get('draft') is not None and u.get('base') == latest:
        base = S.read_version(latest)
        diff = list(difflib.unified_diff(base.splitlines(), text.splitlines(), latest, 'hand edits', lineterm='', n=1))
        print(f'\n── author\'s hand edits on top of {latest} ──')
        print('\n'.join(diff[2:]) if diff else '(the draft is the same as the version)')
    f = u.get('fix')
    p = c.get('proposal')
    if f:
        done = p and p.get('fix') == f.get('n')
        print(f'\n── Fix #{f.get("n")} requested {f.get("at")}: ' + ('proposal already sent' if done else 'WAITING FOR A PROPOSAL') + ' ──')
        if f.get('comment'):
            print('comment on the Fix:', f['comment'])
    open_notes = [n for n in u['notes'] if not n.get('done')]
    for kind, title in (('ai', 'notes for AI'), ('me', 'author\'s notes to self (do not act on them, only take them into account)')):
        ns = [n for n in open_notes if n.get('for') == kind]
        print(f'\n── {title}: {len(ns)} ──')
        for n in ns:
            where = anchor(text, n) if n.get('quote') else None
            lost = f'(location lost, quote: "{(n.get("quote") or "")[:80]}")'
            loc = '(general note on the whole script)' if not n.get('quote') else ctx(text, *where) if where else lost
            print(f'[{n["id"]}] {n.get("text", "").strip()}\n      {loc}')
    mine = [n for n in c['notes'] if not n.get('done')]
    if mine:
        print(f'\n── your notes and questions: {len(mine)} ──')
        for n in mine:
            rep = u['replies'].get(n['id'])
            closed = ' (closed by the author)' if n['id'] in u.get('closed', []) else ''
            print(f'[{n["id"]}] {n["text"]}{closed}' + (f'\n      author\'s reply: {rep}' if rep else ''))
    if p and u.get('decisions'):
        print('\n── decisions on the current proposal ──')
        for e in p['edits']:
            d = u['decisions'].get(e['id'])
            if d:
                print(f'{e["id"]}: {"take" if d == "take" else "skip"} — {e["why"]}')


def cmd_text():
    sys.stdout.write(S.working_text())


def cmd_propose():
    u, c = S.load_user(), S.load_agent()
    text = S.working_text(u)
    spec = store.read_json(args.file)
    if not isinstance(spec, dict):
        sys.exit(f'{args.file}: expected a JSON object with "edits", "answers", "notes"')
    note_ids = {n['id'] for n in u['notes']}
    edits = []
    for i, e in enumerate(spec.get('edits', []), 1):
        if e.get('note') and e['note'] not in note_ids:
            sys.exit(f'edit {i}: no note {e["note"]}')
        try:
            at = locate(text, e['old'])
        except (ValueError, KeyError) as err:
            sys.exit(f'edit {i}: {err}')
        edits.append({'id': f'e{i}', 'note': e.get('note'), 'old': e['old'], 'new': e['new'], 'why': e.get('why', ''),
                      'at': at, 'at16': cp_to_u16(text, at), 'len16': cp_to_u16(e['old'], len(e['old']))})
    try:
        result = apply_edits(text, edits)  # proves the whole set applies cleanly before the author sees it
    except ValueError as err:
        sys.exit(f'edits do not apply: {err}')
    for a in spec.get('answers', []):
        if a.get('note') not in note_ids:
            sys.exit(f'answer: no note {a.get("note")}')
    for n in spec.get('notes', []):
        try:
            add_note(c, text, n['quote'], n['text'], n.get('question', False))
        except ValueError as err:
            sys.exit(f'note: {err}')
    fix = u.get('fix') or {}
    c['proposal'] = {'id': 'p%d-%s' % (fix.get('n', 0), time.strftime('%H%M%S')), 'fix': fix.get('n'), 'base': S.latest(),
                     'base_hash': sha1(text), 'made': time.strftime('%Y-%m-%d %H:%M:%S'), 'summary': spec.get('summary', ''),
                     'edits': edits, 'answers': spec.get('answers', [])}
    S.save_agent(c)
    print(f'proposal {c["proposal"]["id"]}: {len(edits)} edits, {len(spec.get("answers", []))} answers; '
          f'words {len(text.split())} → {len(result.split())}')


def add_note(c, text, quote, body, question):
    a = locate(text, quote)
    n = {'id': 'c%d' % (int(time.time() * 1000) % 10**10 + len(c['notes'])), 'quote': quote, 'start': cp_to_u16(text, a),
         'text': body, 'kind': 'question' if question else 'note', 'ver': S.latest(), 'made': time.strftime('%Y-%m-%d %H:%M:%S')}
    c['notes'].append(n)
    return n


def cmd_note():
    c = S.load_agent()
    try:
        n = add_note(c, S.working_text(), args.quote, args.text, args.question)
    except ValueError as err:
        sys.exit(str(err))
    S.save_agent(c)
    print('note', n['id'])


def cmd_watch():
    """One stdout line per thing worth waking the agent for. Fix requests go out at once, the rest after a quiet spell."""
    def snap():
        u = S.load_user()
        return {'fix': (u.get('fix') or {}).get('n'), 'fix_comment': (u.get('fix') or {}).get('comment'),
                'notes': {n['id']: (n.get('text'), n.get('for'), bool(n.get('done'))) for n in u['notes']},
                'replies': dict(u.get('replies', {})), 'draft': sha1(u['draft']) if u.get('draft') is not None else None,
                'versions': S.versions()}
    read_cmd = f'python3 {CLI} --project {os.path.relpath(S.project)} read'
    prev = snap()
    pending, last_change = [], 0.0
    print(f'watching {S.dir}', flush=True)
    fix = fix_waiting()
    if fix:  # pressed while nobody was watching
        print(f'FIX #{fix["n"]} waiting since {fix.get("at")} — {read_cmd}', flush=True)
    while True:
        time.sleep(args.every)
        try:
            cur = snap()
        except (json.JSONDecodeError, OSError):
            continue  # caught the file mid-write
        if cur['fix'] != prev['fix'] and cur['fix']:
            print(f'FIX #{cur["fix"]} requested' + (f': {cur["fix_comment"]}' if cur['fix_comment'] else '') + f' — {read_cmd}', flush=True)
        new = [k for k in cur['notes'] if k not in prev['notes']]
        changed = [k for k in cur['notes'] if k in prev['notes'] and cur['notes'][k] != prev['notes'][k]]
        replies = [k for k in cur['replies'] if cur['replies'][k] != prev['replies'].get(k)]
        if new: pending.append(f'new notes: {len(new)}')
        if changed: pending.append(f'changed notes: {len(changed)}')
        if replies: pending.append(f'replies to your questions: {len(replies)}')
        if cur['draft'] != prev['draft']: pending.append('hand edits in the text')
        if cur['versions'] != prev['versions']:
            print(f'accepted version {cur["versions"][-1]}', flush=True)
        if cur != prev:
            last_change = time.time()
        if pending and time.time() - last_change > args.quiet_for:
            print('; '.join(dict.fromkeys(pending)), flush=True)
            pending = []
        prev = cur


def fix_waiting():
    """The Fix the author asked for that nobody answered yet, or None."""
    fix, prop = S.load_user().get('fix') or {}, S.load_agent().get('proposal') or {}
    if fix.get('n') and not fix.get('accepted') and prop.get('fix') != fix['n']:
        return fix
    return None


def cmd_wait():
    """Block until a Fix is waiting, then exit 0; exit 2 on timeout. Run it with a shell timeout above --timeout."""
    deadline = time.time() + args.timeout
    print(f'waiting for Fix in {S.dir} (up to {args.timeout:.0f} s)', flush=True)
    while True:
        try:
            fix = fix_waiting()
        except (json.JSONDecodeError, OSError) as err:  # caught a file mid-write
            print(f'could not read the layers ({err}), retrying', file=sys.stderr, flush=True)
            fix = None
        if fix:
            print(f'FIX #{fix["n"]} requested {fix.get("at")}' + (f': {fix["comment"]}' if fix.get('comment') else '') +
                  f' — python3 {CLI} --project {os.path.relpath(S.project)} read', flush=True)
            return
        if time.time() > deadline:
            print(f'no Fix within {args.timeout:.0f} s — run wait again if the author is still editing', flush=True)
            sys.exit(2)
        time.sleep(args.every)


{'init': cmd_init, 'read': cmd_read, 'text': cmd_text, 'propose': cmd_propose, 'note': cmd_note, 'watch': cmd_watch,
 'wait': cmd_wait}[args.cmd]()
