import json, os, shutil, subprocess, tempfile, unittest

from helpers import FOOTAGE_DESK, Server, run

SCRIPT = os.path.join(FOOTAGE_DESK, 'cli.py')


def make_video(path, seconds, size='320x180'):
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc=size={size}:rate=25:duration={seconds}',
                    '-f', 'lavfi', '-i', f'sine=frequency=440:duration={seconds}', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-shortest', path], check=True, timeout=60)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'needs ffmpeg')
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        p = cls.project = cls.tmp.name
        os.makedirs(os.path.join(p, 'phone'))
        os.makedirs(os.path.join(p, 'transcripts'))
        os.makedirs(os.path.join(p, '_export'))
        make_video(os.path.join(p, 'clip1.mp4'), 3)
        make_video(os.path.join(p, 'phone', 'vert.mov'), 2, size='180x320')
        make_video(os.path.join(p, '_export', 'render.mp4'), 1)  # service folder, not footage
        with open(os.path.join(p, 'transcripts', 'clip1.json'), 'w', encoding='utf-8') as f:
            json.dump({'segments': [{'start': 0.2, 'end': 1.6, 'text': 'привет это тест',
                                     'words': [{'word': 'привет', 'start': 0.2, 'end': 0.6}, {'word': 'это', 'start': 0.7, 'end': 0.9},
                                               {'word': 'тест', 'start': 1.0, 'end': 1.6}]}]}, f, ensure_ascii=False)
        cls.build = run(SCRIPT, '--project', p, 'build', '--frames-every', '1', '--title', 'Тест', timeout=300)
        with open(os.path.join(p, '_work', 'review', 'manifest.json'), encoding='utf-8') as f:
            cls.manifest = json.load(f)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def clip(self, cid):
        return next(c for c in self.manifest['clips'] if c['id'] == cid)

    def propose(self, spec, *extra):
        path = os.path.join(self.project, 'p.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(spec, f, ensure_ascii=False)
        return run(SCRIPT, '--project', self.project, 'propose', path, *extra)

    def test_build_collects_material(self):
        self.assertEqual(self.build.returncode, 0, self.build.stdout + self.build.stderr)
        self.assertEqual(self.manifest['title'], 'Тест')
        self.assertEqual(sorted(c['id'] for c in self.manifest['clips']), ['clip1', 'vert'])
        c = self.clip('clip1')
        self.assertEqual([w[0] for w in c['words']], ['привет', 'это', 'тест'])
        self.assertEqual(c['segs'], [0])
        self.assertAlmostEqual(c['dur'], 3, delta=0.2)
        self.assertGreaterEqual(len(c['frames']), 3)
        self.assertTrue(os.path.exists(os.path.join(self.project, c['video'][len('/media/'):])))
        self.assertIn('(vertical)', self.clip('vert')['label'])
        self.assertIn('no transcript (1)', self.build.stdout)

    def test_rebuild_keeps_layers(self):
        user = os.path.join(self.project, '_work', 'review', 'user.json')
        with open(user, 'w', encoding='utf-8') as f:
            json.dump({'clips': {}}, f)
        r = run(SCRIPT, '--project', self.project, 'build', '--frames-every', '1', timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn('proxy clip1', r.stdout)  # proxy is up to date
        with open(user, encoding='utf-8') as f:
            self.assertEqual(json.load(f), {'clips': {}})

    def test_propose_validates(self):
        r = self.propose({'clips': {'clip1': [{'a': 0.1, 'b': 9, 'kind': 'pick'}], 'nope': []}})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('outside the clip', r.stderr)
        self.assertIn('nope: no such clip', r.stderr)

    def test_propose_read_and_ranges(self):
        r = self.propose({'clips': {'clip1': [{'a': 0.1, 'b': 1.7, 'note': 'вступление'}, {'a': 2, 'b': 2.5, 'kind': 'question', 'note': '?'}]}})
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.project, '_work', 'review', 'agent.json'), encoding='utf-8') as f:
            layer = json.load(f)
        self.assertEqual([i['id'] for i in layer['clips']['clip1']], ['a1', 'a2'])
        with open(os.path.join(self.project, '_work', 'review', 'user.json'), 'w', encoding='utf-8') as f:
            json.dump({'clips': {'clip1': {'marks': [{'kind': 'take', 'a': 0.1, 'b': 1.7, 'note': 'да'}], 'watched': [[0, 3]]}},
                       'replies': {'clip1/a2': 'нет'}}, f, ensure_ascii=False)
        out = run(SCRIPT, '--project', self.project, 'read').stdout
        self.assertIn('TAKE', out)
        self.assertIn('привет это тест', out)
        self.assertIn('REPLY: нет', out)
        self.assertRegex(out, r'a1\s+pick\s+taken')
        ranges = run(SCRIPT, '--project', self.project, 'read', '--ranges').stdout
        self.assertTrue(ranges.startswith('clip1\t0.10\t1.70\t# привет это тест'), ranges)

    def test_text(self):
        out = run(SCRIPT, '--project', self.project, 'text', 'clip1').stdout
        self.assertIn('0.20–   1.60  привет это тест', out)

    def test_server_serves_agent_layer(self):
        with Server(os.path.join(FOOTAGE_DESK, 'server.py'), self.project) as srv:
            self.assertIn('agent', srv.get('/api/poll'))
            self.assertIn('clips', srv.get('/api/agent')['data'])


if __name__ == '__main__':
    unittest.main()
