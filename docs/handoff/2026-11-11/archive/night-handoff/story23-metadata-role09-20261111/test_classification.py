"""Original-AST dispatch differentials and actual descriptor-close checks."""
import ast
import errno
import ntpath
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest

TASK = Path(__file__).resolve().parents[2]
SOURCE = TASK / 'r59'
BASE = TASK / 'night-handoff/story27-r52-public-review-prepare-host-followup02/review_prepare_host.draft.py'
VARIANT = Path(__file__).with_name('review_prepare_host.classification.py')


def method(path, name, namespace):
    tree = ast.parse(path.read_bytes(), filename=str(path))
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1:
        raise AssertionError((name, len(nodes)))
    nodes[0].decorator_list = []
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), 'exec'), namespace)
    return namespace[name]


class Denied(RuntimeError):
    pass


def require(ok, reason):
    if not ok:
        raise Denied(reason)


class Loader:
    pass


tree = ast.parse(BASE.read_bytes())
assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'SECRETS' for t in n.targets))
secrets = ast.literal_eval(assignment.value)


def namespace():
    result = dict(Path=Path, SOURCE=SOURCE, TARGET=TASK / 'nx', REQUEST='unit-request',
                  os=os, ntpath=ntpath, sys=sys, SECRETS=secrets, require=require, Loader=Loader)
    method(BASE, 'key', result)
    return result


class Guard:
    def __init__(self):
        self._filename_classifications = {}
        self.codec_fds = {}
        self.codec_fd_events = []

    def deny(self, why, value):
        raise Denied((why, value))


def frame(filename, name='ordinary', globals_=None, locals_=None, code=None):
    return types.SimpleNamespace(f_code=code or types.SimpleNamespace(co_filename=str(filename), co_name=name),
        f_globals=globals_, f_locals=locals_ or {}, f_back=None)


def outcome(role, guard, f, event='call'):
    try:
        role(guard, f, event, None)
        return ('allowed',)
    except Denied as error:
        return ('denied', error.args)


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.old_ns, self.new_ns = namespace(), namespace()
        self.old = method(BASE, 'role', self.old_ns)
        self.new = method(VARIANT, 'role', self.new_ns)
        self.old_guard, self.new_guard = Guard(), Guard()

    def compare(self, f, event='call'):
        old = outcome(self.old, self.old_guard, f, event)
        self.assertEqual(old, outcome(self.new, self.new_guard, f, event))
        return old

    def test_cold_hit_outside_prefix_source_change_and_full_table_fallback(self):
        for root in (SOURCE, SOURCE.parent / 'r59-other', TASK / 'outside'):
            f = frame(root / 'ordinary.py')
            self.assertEqual(('allowed',), self.compare(f))
            self.assertEqual(('allowed',), self.compare(f))
        # Classification is paired with SOURCE, never transferred to another root.
        f = frame(SOURCE / 'ordinary.py', 'run_native')
        self.assertEqual('denied', self.compare(f)[0])
        self.old_ns['SOURCE'] = self.new_ns['SOURCE'] = TASK / 'different-source'
        self.assertEqual(('allowed',), self.compare(f))
        self.old_ns['SOURCE'] = self.new_ns['SOURCE'] = SOURCE
        for index in range(260):
            f = frame(SOURCE / ('ordinary' + str(index) + '.py'))
            self.assertEqual(('allowed',), self.compare(f))
        self.assertEqual(256, len(self.new_guard._filename_classifications))
        # An uncached new path still executes original classification and refusal.
        self.assertEqual('denied', self.compare(frame(SOURCE / 'last.py', 'produce_proof'))[0])
        self.assertEqual(256, len(self.new_guard._filename_classifications))

    def test_invalid_and_sensitive_filenames_keep_original_repeated_refusal(self):
        for filename in ('', 'relative.py', str(SOURCE / 'sessions/source.py'),
                         str(SOURCE / '.codex/auth.json'), 'C:\\bad\x00name.py'):
            f = frame(filename)
            with self.subTest(filename=filename):
                self.assertEqual('denied', self.compare(f)[0])
                self.assertEqual('denied', self.compare(f)[0])
                self.assertNotIn((filename, SOURCE), self.new_guard._filename_classifications)
        self.assertEqual(('allowed',), self.compare(frame('<frozen collections>')))
        self.assertEqual(('allowed',), self.compare(frame('', 'ordinary'), 'return'))

    def test_hot_filename_never_reuses_dynamic_model_native_or_owner_authority(self):
        for filename, names in [('_codex_app_server.py', ['run_request']),
                                ('_llm_backend.py', ['chat', 'call_llm']),
                                ('ordinary.py', ['run_native', 'produce_proof', 'run_candidate'])]:
            path = SOURCE / 'scripts/python' / filename
            self.assertEqual(('allowed',), self.compare(frame(path)))
            for name in names:
                self.assertEqual('denied', self.compare(frame(path, name))[0])
        path = SOURCE / 'scripts/python/_b_route_adoption.py'
        self.assertEqual(('allowed',), self.compare(frame(path)))
        owner = types.ModuleType('_b_route_adoption')
        exec(compile('def original():\n    pass\n', str(path), 'exec'), owner.__dict__)
        owner.__loader__ = Loader()
        owner.prepare_review = types.SimpleNamespace(__wrapped__=owner.original)
        previous = sys.modules.get('_b_route_adoption')
        sys.modules['_b_route_adoption'] = owner
        try:
            # Compile the actual checked name, then vary globals and operation locals.
            exec(compile('def prepare_review():\n    pass\n', str(path), 'exec'), owner.__dict__)
            function = owner.prepare_review
            owner.prepare_review = types.SimpleNamespace(__wrapped__=function)
            for globals_, locals_ in [({}, {}), (owner.__dict__,
                    {'root': TASK / 'nx', 'operation_id': 'wrong-operation', 'request_ref': 'unit-request'})]:
                f = frame(path, code=function.__code__, globals_=globals_, locals_=locals_)
                self.assertEqual('denied', self.compare(f)[0])
        finally:
            if previous is None:
                del sys.modules['_b_route_adoption']
            else:
                sys.modules['_b_route_adoption'] = previous

    def test_task_forbidden_predicate_still_delegates_calls_and_denies(self):
        old_h = types.SimpleNamespace(Guard=types.SimpleNamespace(role=self.old))
        new_h = types.SimpleNamespace(Guard=types.SimpleNamespace(role=self.new))
        old = method(TASK / 'night-handoff/story23-metadata-role08-20261111/metadata_host.Root-only.py',
                     'role', dict(Path=Path, SOURCE=SOURCE, H=old_h))
        new = method(Path(__file__).with_name('metadata_host.Root-only.py'),
                     'role', dict(Path=Path, SOURCE=SOURCE, H=new_h))
        for filename, name in [('_b_route_segmented_funding.py', 'ordinary'),
                               ('_b_route_segmented_journal.py', 'ordinary'),
                               ('_b_route_inventory.py', 'git'), ('ordinary.py', 'prepare_run'),
                               ('_codex_app_server.py', 'run_request'), ('ordinary.py', 'run_native')]:
            f = frame(SOURCE / 'scripts/python' / filename, name)
            self.assertEqual(('denied', outcome(old, self.old_guard, f)[1]), outcome(new, self.new_guard, f))

    def test_original_returned_wrapper_checks_actual_closed_and_live_descriptors(self):
        for closed in (False, True):
            g = Guard()
            g.role = types.MethodType(self.new, g)
            f = frame(SOURCE / 'scripts/python/_b_route_codec.py', 'read_json')
            fd, path = tempfile.mkstemp(prefix='role09-', dir=Path(__file__).parent)
            try:
                g.codec_fds[fd] = {'frame': f, 'path': path, 'fdopen_admitted': True}
                returned = method(VARIANT, 'returned', dict(guard=g, os=os, errno=errno, require=require))
                if closed:
                    os.close(fd)
                    fd = None
                    returned(f, 'return', None)
                    self.assertEqual({}, g.codec_fds)
                    self.assertIs(g.codec_fd_events[-1]['actual_closed'], True)
                    self.assertEqual(errno.EBADF, g.codec_fd_events[-1]['fstat_error']['errno'])
                else:
                    with self.assertRaises(Denied):
                        returned(f, 'return', None)
                    self.assertIn(fd, g.codec_fds)
                    self.assertIs(g.codec_fd_events[-1]['actual_closed'], False)
            finally:
                if fd is not None:
                    os.close(fd)
                os.unlink(path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
