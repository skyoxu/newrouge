"""Thin CLI contract checks; only the adoption service boundary is synthetic."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch
import uuid

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SCRIPTS), str(SCRIPTS.parent / 'sc')]
sys.dont_write_bytecode = True

import b_route_adoption as cli
import _b_route_codec as codec
import dev_cli


def service():
    fake = ModuleType('_b_route_adoption')
    for stage in ('prepare', 'reserve', 'inspect', 'prepare_review', 'complete_review'):
        setattr(fake, stage, Mock(return_value={'operation_id': 'OP-1',
            'scope_ids': ['flow:fixture'], 'state': 'prepared', **cli.FLAGS}))
    return fake


def captured(function, *args):
    output = io.StringIO()
    with redirect_stdout(output):
        code = function(*args)
    return code, json.loads(output.getvalue())


class AdoptionCliTests(unittest.TestCase):
    def test_review_stages_use_same_owner_through_both_entries(self):
        fake = service()
        with patch.dict(sys.modules, {'_b_route_adoption': fake}):
            for stage, method in (('review-prepare', 'prepare_review'), ('review-complete', 'complete_review')):
                arguments = ['--root', '.', '--operation-id', 'OP-1', '--stage', stage]
                expected = {'operation_id': 'OP-1'}
                if stage == 'review-prepare':
                    arguments += ['--request', 'fixture/request.json']
                    expected['request_ref'] = 'fixture/request.json'
                for entry, prefix in ((cli.main, []), (dev_cli.main, ['b-route-adoption'])):
                    code, value = captured(entry, prefix + arguments)
                    self.assertEqual(0, code)
                    self.assertTrue(all(value[key] is False for key in cli.FLAGS))
                    getattr(fake, method).assert_called_with(Path('.').absolute(), **expected)

    def test_direct_and_dev_main_dispatch_same_service_for_each_stage(self):
        fake = service()
        with patch.dict(sys.modules, {'_b_route_adoption': fake}):
            for stage in ('prepare', 'reserve', 'inspect'):
                arguments = ['--root', '.', '--operation-id', 'OP-1', '--stage', stage]
                if stage == 'prepare':
                    arguments += ['--request', 'fixture/request.json']
                direct = captured(cli.main, arguments)
                routed = captured(dev_cli.main, ['b-route-adoption', *arguments])
                self.assertEqual(direct, routed)
                self.assertEqual(0, direct[0])
                expected = {'operation_id': 'OP-1'}
                if stage == 'prepare':
                    expected['request_ref'] = 'fixture/request.json'
                getattr(fake, stage).assert_called_with(Path('.').absolute(), **expected)
        self.assertEqual([2, 2, 2], [getattr(fake, stage).call_count
                                   for stage in ('prepare', 'reserve', 'inspect')])

    def test_dev_build_parser_dispatch_is_not_limited_to_main_script(self):
        fake = service()
        parser = dev_cli.build_parser()
        args = parser.parse_args(['b-route-adoption', '--stage', 'inspect',
                                  '--operation-id', 'OP-1'])
        with patch.dict(sys.modules, {'_b_route_adoption': fake}):
            code, value = captured(args.func, args)
        self.assertEqual(0, code)
        self.assertEqual('prepared', value['state'])
        fake.inspect.assert_called_once_with(Path('.').absolute(), operation_id='OP-1')

    def test_invalid_arguments_are_json_and_never_call_service(self):
        fake = service()
        bad = [[], ['--stage', 'apply', '--operation-id', 'OP-1'],
               ['--stage', 'review-prepare', '--operation-id', 'OP-1'],
               ['--stage', 'review-complete', '--operation-id', 'OP-1', '--request', 'other.json'],
               ['--stage', 'prepare', '--operation-id', 'OP-1'],
               ['--stage', 'reserve', '--operation-id', 'OP-1', '--request', 'other.json'],
               ['--stage', 'inspect', '--operation-id', 'OP-1', '--request', 'other.json'],
               ['--stage', 'inspect', '--operation-id', ' padded '],
               ['--stage', 'inspect', '--operation-id', '\ud800']]
        with patch.dict(sys.modules, {'_b_route_adoption': fake}):
            for arguments in bad:
                with self.subTest(arguments=arguments):
                    for entry, prefix in ((cli.main, []), (dev_cli.main, ['b-route-adoption'])):
                        code, value = captured(entry, prefix + arguments)
                        self.assertEqual(2, code)
                        self.assertEqual('blocked', value['status'])
                        self.assertEqual(1, len(value['diagnostics']))
                        self.assertEqual(set(codec.Diagnostic(codec.ReasonCode.OK).to_dict()),
                                         set(value['diagnostics'][0]))
        self.assertTrue(all(getattr(fake, stage).call_count == 0
                            for stage in ('prepare', 'reserve', 'inspect')))

    def test_original_service_diagnostic_and_resume_location_survive(self):
        fake = service()
        diagnostic = codec.Diagnostic(codec.ReasonCode.PENDING, codec.Stage.BUNDLE,
            expected='resolved operation', actual='fixture pending',
            resume_ref='logs/ci/b-route-operations/fixture/operation.json')
        fake.reserve.side_effect = codec.CodecError(diagnostic)
        with patch.dict(sys.modules, {'_b_route_adoption': fake}):
            code, value = captured(cli.main, ['--stage', 'reserve', '--operation-id', 'OP-1'])
        expected = diagnostic.to_dict()
        expected['entity_id'] = 'OP-1'
        self.assertEqual(2, code)
        self.assertEqual([expected], value['diagnostics'])
        self.assertTrue(all(value[name] is False for name in cli.FLAGS))

    def test_invalid_or_authorizing_service_output_fails_closed(self):
        fake = service()
        for result in ([1], {'formal_adoption': True}, {'readiness': 1}, {'value': float('nan')}):
            with self.subTest(result=result):
                fake.inspect.return_value = result
                with patch.dict(sys.modules, {'_b_route_adoption': fake}):
                    code, value = captured(cli.main, ['--stage', 'inspect', '--operation-id', 'OP-1'])
                self.assertEqual(2, code)
                self.assertTrue(all(value[name] is False for name in cli.FLAGS))

    def test_fresh_actual_cli_inspect_has_no_filesystem_or_bytecode_side_effect(self):
        home = SCRIPTS.parents[1] / 'logs/ci/2026-11-06/adoption-cli-fixtures'
        home.mkdir(parents=True, exist_ok=True)
        case = home / ('case-' + uuid.uuid4().hex[:8])
        case.mkdir()
        root = case / 'empty-project'
        root.mkdir()
        for name in ('dev_cli.py', 'b_route_adoption.py', '_b_route_codec.py', '_planning_skill_common.py'):
            shutil.copyfile(SCRIPTS / name, case / name)
        (case / '_b_route_adoption.py').write_bytes(b'''"""Synthetic service; no project state or qualification."""
def inspect(root, *, operation_id):
    return {"operation_id":operation_id,"scope_ids":[],"state":"prepared",
            "formal_adoption":False,"readiness":False,"runtime_verified":False}
def prepare(*args, **kwargs):
    raise AssertionError("inspect only")
def reserve(*args, **kwargs):
    raise AssertionError("inspect only")
''')
        before = {p.relative_to(case).as_posix(): p.read_bytes()
                  for p in case.rglob('*') if p.is_file()}
        environment = {'SystemRoot': os.environ.get('SystemRoot', r'C:\Windows'),
                       'TEMP': str(case), 'TMP': str(case), 'PYTHONNOUSERSITE': '1'}
        results = []
        for name in ('b_route_adoption.py', 'dev_cli.py'):
            command = [sys.executable, '-S', str(case / name)]
            if name == 'dev_cli.py':
                command.append('b-route-adoption')
            command += ['--root', str(root), '--stage', 'inspect', '--operation-id', 'OP-1']
            completed = subprocess.run(command, cwd=case, env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', timeout=15)
            self.assertEqual(0, completed.returncode, completed.stderr)
            results.append(json.loads(completed.stdout))
            self.assertEqual(before, {p.relative_to(case).as_posix(): p.read_bytes()
                                     for p in case.rglob('*') if p.is_file()})
            self.assertFalse(list(case.rglob('__pycache__')))
        self.assertEqual(results[0], results[1])
        self.assertEqual([], list(root.iterdir()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
