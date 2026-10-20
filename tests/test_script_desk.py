import json, os, sys, tempfile, unittest

from helpers import SCRIPT_DESK, Server, run

sys.path.insert(0, SCRIPT_DESK)
import store  # noqa: E402

SCRIPT = os.path.join(SCRIPT_DESK, 'cli.py')
TEXT = '# Ролик\n\nПервая мысль про агента.\nВторая мысль 🙂 про деньги.\n'


class StoreEdits(unittest.TestCase):
    def test_apply_edits_in_any_order(self):
        out = store.apply_edits('раз два три', [{'old': 'три', 'new': '3'}, {'old': 'раз', 'new': '1'}])
        self.assertEqual(out, '1 два 3')

    def test_overlap_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'overlap'):
            store.apply_edits('раз два три', [{'old': 'раз два', 'new': 'x'}, {'old': 'два три', 'new': 'y'}])

    def test_ambiguous_old_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'found 2 times'):
            store.locate('да да', 'да')

    def test_utf16_offsets_count_emoji_twice(self):
        self.assertEqual(store.cp_to_u16('🙂x', 1), 2)
        self.assertEqual(store.u16_to_cp('🙂x', 2), 1)


class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = self.tmp.name
        src = os.path.join(self.project, 'draft.md')
        with open(src, 'w', encoding='utf-8') as f:
            f.write(TEXT)
        r = run(SCRIPT, '--project', self.project, 'init', '--from', src)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.S = store.Store(self.project)

    def tearDown(self):
        self.tmp.cleanup()

    def press_fix(self):
        user = {'notes': [{'id': 'n1', 'for': 'ai', 'quote': 'про деньги', 'text': 'конкретнее', 'start': TEXT.index('про деньги') + 1}],
                'fix': {'n': 1, 'at': '2026-10-19 12:00', 'comment': 'поехали'}}
        store.write_json(self.S.user, user)

    def propose(self, spec):
        path = os.path.join(self.project, 'p.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(spec, f, ensure_ascii=False)
        return run(SCRIPT, '--project', self.project, 'propose', path)

    def test_init_writes_v0_and_mirror(self):
        self.assertEqual(self.S.versions(), ['v0'])
        with open(os.path.join(self.project, 'script.md'), encoding='utf-8') as f:
            self.assertEqual(f.read(), TEXT)

    def test_wait_times_out_without_fix(self):
        r = run(SCRIPT, '--project', self.project, 'wait', '--timeout', '0.3', '--every', '0.1')
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_fix_propose_accept(self):
        self.press_fix()
        r = run(SCRIPT, '--project', self.project, 'wait', '--timeout', '5', '--every', '0.1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('FIX #1', r.stdout)
        self.assertIn('конкретнее', run(SCRIPT, '--project', self.project, 'read').stdout)

        r = self.propose({'summary': 'деньги', 'edits': [{'note': 'n1', 'old': 'про деньги', 'new': 'про 35 евро', 'why': 'конкретнее'}]})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.project, '_work', 'script', 'agent.json')))
        self.assertFalse(os.path.exists(os.path.join(self.project, '_work', 'script', 'claude.json')))
        # answered fix is no longer waiting
        self.assertEqual(run(SCRIPT, '--project', self.project, 'wait', '--timeout', '0.2', '--every', '0.1').returncode, 2)

        prop = self.S.load_agent()['proposal']
        res = self.S.accept(['e1'], prop['id'])
        self.assertEqual(res['version'], 'v1')
        self.assertIn('про 35 евро', self.S.read_version('v1'))
        self.assertEqual(self.S.read_meta('v1')['by'], 'author + AI')

    def test_propose_refuses_bad_edits(self):
        self.press_fix()
        r = self.propose({'edits': [{'note': 'n1', 'old': 'мысль', 'new': 'x'}]})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('found 2 times', r.stderr)
        r = self.propose({'edits': [{'note': 'nope', 'old': 'агента', 'new': 'x'}]})
        self.assertIn('no note nope', r.stderr)

    def test_server_serves_agent_layer(self):
        with Server(os.path.join(SCRIPT_DESK, 'server.py'), self.project) as srv:
            self.assertIn('agent', srv.get('/api/poll'))
            self.assertEqual(srv.get('/api/agent')['data']['notes'], [])
            self.assertEqual(srv.get('/api/project')['versions'][0]['name'], 'v0')


if __name__ == '__main__':
    unittest.main()
