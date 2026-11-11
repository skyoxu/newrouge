"""Offline transition boundaries; synthetic orchestration is not native proof."""
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_execution_transition as transition


class ExecutionTransitionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get('EXECUTION_TRANSITION_TEST_TEMP'))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git('init', '-q')
        self.write('.gitattributes', b'*.py text eol=lf\n*.schema.json text eol=crlf\n')
        self.write('scripts/python/_b_route_planning_runtime.py', b'VALUE = 1\n')
        self.write('scripts/python/_mvg_capability_append.py', b'UNCHANGED = True\n')
        self.write('scripts/python/tests/test_ignored.py', b'TEST = True\n')
        self.write('docs/example.schema.json', b'{"original":true}\n')
        self.commit('Frozen source')
        self.commit_id = self.git('rev-parse', 'HEAD').decode().strip()

    def git(self, *arguments):
        return subprocess.check_output(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@localhost',
                                        '-C', str(self.root), *arguments], stderr=subprocess.PIPE)

    def write(self, name, raw):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    def commit(self, message):
        self.git('add', '-A')
        self.git('commit', '-qm', message)

    def test_explicit_crlf_checkout_is_bound_with_original_raw_digest(self):
        schema = self.write('docs/example.schema.json', b'{"original":true}\r\n')
        manifest = transition._source_manifest(self.root, self.commit_id)
        self.assertEqual('explicit-git-attribute-crlf', manifest['docs/example.schema.json']['checkout_conversion'])
        self.assertEqual(transition.codec.raw_digest(schema.read_bytes()), manifest['docs/example.schema.json']['raw_digest'])
        self.assertNotIn('scripts/python/tests/test_ignored.py', manifest)
        self.write('docs/example.schema.json', b'{"original":true}\n\r\n')
        with self.assertRaisesRegex(transition.TransitionError, 'uncommitted_source'):
            transition._source_manifest(self.root, self.commit_id)

    def test_docs_only_head_advance_is_allowed_but_new_tracked_production_is_not(self):
        before = transition._source_manifest(self.root, self.commit_id)
        self.write('docs/evidence.md', b'Observed result\n')
        self.commit('Evidence only')
        self.assertEqual(before, transition._source_manifest(self.root, self.commit_id))
        self.write('scripts/python/unexpected.py', b'NEW = True\n')
        self.commit('Unexpected production addition')
        with self.assertRaisesRegex(transition.TransitionError, 'production_membership_changed'):
            transition._source_manifest(self.root, self.commit_id)

    def test_uncommitted_and_untracked_source_drift_are_rejected(self):
        runtime = self.root / 'scripts/python/_b_route_planning_runtime.py'
        old = runtime.read_bytes()
        runtime.write_bytes(b'VALUE = 2\n')
        with self.assertRaisesRegex(transition.TransitionError, 'uncommitted_source'):
            transition._source_manifest(self.root, self.commit_id)
        runtime.write_bytes(old)
        self.write('scripts/python/untracked.py', b'UNTRACKED = True\n')
        with self.assertRaisesRegex(transition.TransitionError, 'untracked_production'):
            transition._source_manifest(self.root, self.commit_id)

    def test_allowlist_requires_new_transition_and_rejects_unlisted_source(self):
        original = {'scripts/python/_mvg_capability_append.py': {'identity': 'old'},
                    'scripts/python/_b_route_planning_runtime.py': {'identity': 'old'},
                    'scripts/python/_b_route_codec.py': {'identity': 'old'}}
        current = {**original, 'scripts/python/_b_route_execution_transition.py': {'identity': 'new'},
                   'scripts/python/_b_route_review_recovery.py': {'identity': 'new'}}
        self.assertEqual(2, len(transition._allowed_delta(original, current)))
        current['scripts/python/_mvg_capability_append.py'] = {'identity': 'changed'}
        # Membership permits the bounded append owner; its semantic restrictions
        # are separately enforced by the mandatory source/semantic guards.
        self.assertEqual(sorted(('scripts/python/_b_route_execution_transition.py',
                                 'scripts/python/_b_route_review_recovery.py',
                                 'scripts/python/_mvg_capability_append.py')),
                         transition._allowed_delta(original, current))
        forbidden = {**current, 'scripts/python/_b_route_codec.py': {'identity': 'changed'}}
        with self.assertRaisesRegex(transition.TransitionError, 'outside_allowlist'):
            transition._allowed_delta(original, forbidden)
        without_transition = {key: value for key, value in current.items()
                              if key != 'scripts/python/_b_route_execution_transition.py'}
        with self.assertRaisesRegex(transition.TransitionError, 'new_module_not_committed'):
            transition._allowed_delta(original, without_transition)
        existing_transition = {**original, 'scripts/python/_b_route_execution_transition.py': {'identity': 'old'}}
        with self.assertRaisesRegex(transition.TransitionError, 'new_module_not_committed'):
            transition._allowed_delta(existing_transition, current)
        removed = {key: value for key, value in current.items()
                   if key != 'scripts/python/_mvg_capability_append.py'}
        with self.assertRaisesRegex(transition.TransitionError, 'source_removal_forbidden'):
            transition._allowed_delta(original, removed)

    def test_canonical_review_and_generation_owner_edits_are_rejected(self):
        current = self.root / 'current'
        path = current / 'scripts/python/_b_route_planning_runtime.py'
        path.parent.mkdir(parents=True)
        names = ('review_schema', 'review_issues', 'obligations', 'machine', 'qualified_sources',
                 'generation_schema', 'generation_schemas', 'generation_target')
        text = '\n\n'.join('def ' + name + '():\n    return "original"' for name in names) + '\n'
        self.write('scripts/python/_b_route_planning_runtime.py', text.encode())
        path.write_text(text, encoding='utf-8')
        self.assertEqual(set(names), set(transition._semantic_unchanged(self.root, current)))
        path.write_text(text.replace('def review_issues():\n    return "original"',
                                     'def review_issues():\n    return "weakened"'), encoding='utf-8')
        with self.assertRaisesRegex(transition.TransitionError, 'canonical_semantics_changed'):
            transition._semantic_unchanged(self.root, current)

    def test_legacy_view_is_explicit_and_keeps_original_identity(self):
        desc = {'rules': {'original': True}, 'prepared_ref': 'logs/old/prepared.json'}
        state = {'schema_version': transition.CURRENT_RUN_SCHEMA, 'planning_runtime': desc,
                 'runtime_identity': transition.codec.canonical_digest(desc),
                 'b_route_execution_transition': {'original_run_schema': transition.ORIGINAL_RUN_SCHEMA}}
        before = deepcopy(state)
        view = transition._legacy_view(state)
        self.assertEqual(transition.ORIGINAL_RUN_SCHEMA, view['schema_version'])
        self.assertNotIn('b_route_execution_transition', view)
        self.assertEqual(state['runtime_identity'], view['runtime_identity'])
        self.assertEqual(state['planning_runtime'], view['planning_runtime'])
        self.assertEqual(before, state)

    def test_no_cached_load_and_tamper_rejection_before_native_subprocess(self):
        # Only the public orchestration contract is synthetic here. Root must
        # separately run the unchanged real r5 native verifier with actual proof.
        prepared_ref = 'logs/ci/transition-fixture/prepared.json'
        prepared_raw = b'{"original":"complete native result supplied by isolated fixture"}\n'
        self.write(prepared_ref, prepared_raw)
        frozen = transition.codec.strict_json_loads(prepared_raw)
        body = {key: {} for key in transition._FIELDS if key != 'transition_digest'}
        body.update(schema_version=transition.SCHEMA, original_commit=transition.ORIGINAL_COMMIT,
                    original_run_schema=transition.ORIGINAL_RUN_SCHEMA,
                    original_source_root='original', current_commit='1' * 40,
                    artifact_root=str(self.root), prepared_ref=prepared_ref,
                    prepared_raw_digest=transition.codec.raw_digest(prepared_raw),
                    frozen_sha256=transition.codec.canonical_digest(frozen))
        record = {**body, 'transition_digest': transition.codec.canonical_digest(body)}
        state = {'schema_version': transition.CURRENT_RUN_SCHEMA, 'b_route_execution_transition': record}
        with patch.object(transition, '_collect', return_value=(body, frozen)) as collect:
            self.assertEqual(frozen, transition.load_prepared(self.root, state))
            self.assertEqual(frozen, transition.load_prepared(self.root, state))
            self.assertEqual(2, collect.call_count)
        mutated = deepcopy(state)
        mutated['b_route_execution_transition']['current_commit'] = '2' * 40
        with patch.object(transition, '_collect') as collect:
            with self.assertRaisesRegex(transition.TransitionError, 'digest_changed'):
                transition.load_prepared(self.root, mutated)
            collect.assert_not_called()
        with self.assertRaisesRegex(transition.TransitionError, 'explicit_v2'):
            transition.load_prepared(self.root, {**state, 'schema_version': transition.ORIGINAL_RUN_SCHEMA})

    def test_unsafe_references_rejected_before_reads(self):
        for name in ('../outside.json', '/outside.json', 'logs\\old.json', 'logs/auth.json', 'sessions/prepared.json'):
            with self.subTest(name=name), self.assertRaises(transition.TransitionError):
                transition._path(self.root, name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
