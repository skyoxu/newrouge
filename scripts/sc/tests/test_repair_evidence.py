from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / 'scripts' / 'sc'))

import _repair_guidance
from _artifact_schema import validate_pipeline_repair_guide_payload


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')


def guide(root: Path, name: str, child: dict, *, snapshot: Path | None = None) -> dict:
    snapshot = snapshot or root / 'logs' / 'pipeline' / 'child-artifacts' / name
    write_json(snapshot / 'summary.json', child)
    script = {'sc-test': 'test.py', 'sc-acceptance-check': 'acceptance_check.py', 'sc-llm-review': 'llm_review.py'}[name]
    summary = {'status': 'fail', 'task_id': '7', 'run_id': 'run-7', 'steps': [{
        'name': name, 'status': 'fail', 'rc': 1, 'summary_file': str(snapshot / 'summary.json'),
        'cmd': ['py', '-3', f'scripts/sc/{script}', '--task-id', '7'],
    }]}
    with mock.patch.object(_repair_guidance, 'repo_root', return_value=root):
        payload = _repair_guidance.build_repair_guide(summary, task_id='7', out_dir=root / 'logs' / 'pipeline')
    validate_pipeline_repair_guide_payload(payload)
    return payload


class RepairEvidenceTests(unittest.TestCase):
    def test_failed_trx_exposes_test_source_and_quoted_narrow_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / 'logs' / 'unit' / 'day'
            artifacts.mkdir(parents=True)
            (artifacts / 'run_id.txt').write_text('run-7\n', encoding='utf-8')
            write_json(artifacts / 'summary.json', {'restore_rc': 0, 'test_rc': 1})
            (artifacts / 'tests.trx').write_text('''<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010">
<TestDefinitions><UnitTest id="u1"><TestMethod className="Game.Tests.RulesTests" name="RejectInvalid" /></UnitTest></TestDefinitions>
<Results><UnitTestResult testId="u1" testName="RejectInvalid" outcome="Failed"><Output><ErrorInfo><Message>Expected rejection.</Message><StackTrace>at Rules in C:\\work\\newrouge\\Game.Core\\Rules.cs:line 9
at Test in C:\\work\\newrouge\\Game.Core.Tests\\RulesTests.cs:line 19</StackTrace></ErrorInfo></Output></UnitTestResult>
<UnitTestResult testName="PassingTest" outcome="Passed" /></Results></TestRun>''', encoding='utf-8')
            payload = guide(root, 'sc-test', {'task_id': '7', 'run_id': 'run-7', 'steps': [{
                'name': 'unit', 'status': 'fail', 'artifacts_dir': str(artifacts),
                'cmd': ['py', '-3', 'scripts/python/run_dotnet.py', '--solution', 'Game With Space.sln'],
            }]})
            text = _repair_guidance.render_repair_guide_markdown(payload)
            self.assertIn('RejectInvalid', text)
            self.assertIn('Game.Core/Rules.cs', text)
            self.assertIn('Game.Core.Tests/RulesTests.cs', text)
            self.assertIn('Action:', text)
            self.assertIn('"Game With Space.sln"', text)
            self.assertIn('FullyQualifiedName=Game.Tests.RulesTests.RejectInvalid', text)
            self.assertNotIn('PassingTest', text)

    def test_acceptance_uses_snapshot_report_with_exact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = root / 'logs' / 'pipeline' / 'child-artifacts' / 'sc-acceptance-check'
            snapshot.mkdir(parents=True)
            live = root / 'logs' / 'ci' / 'day' / 'acceptance-refs.json'
            write_json(live, {'task_id': '99', 'errors': ['Wrong live report']})
            write_json(snapshot / 'acceptance-refs.json', {
                'task_id': '7', 'errors': ['tasks_back.json: acceptance[1]: referenced file not found on disk: Game.Core.Tests/MissingTests.cs'],
            })
            payload = guide(root, 'sc-acceptance-check', {'task_id': '7', 'run_id': 'run-7', 'steps': [{
                'name': 'acceptance-refs', 'status': 'fail',
                'cmd': ['py', '-3', 'scripts/python/validate_acceptance_refs.py', '--task-id', '7', '--out', str(live)],
            }]}, snapshot=snapshot)
            text = _repair_guidance.render_repair_guide_markdown(payload)
            self.assertIn('acceptance[1]', text)
            self.assertIn('Game.Core.Tests/MissingTests.cs', text)
            self.assertIn('.taskmaster/tasks/tasks_back.json', text)
            self.assertIn('validate_acceptance_refs.py', text)
            self.assertNotIn('Wrong live report', text)

    def test_llm_preserves_all_required_findings_and_their_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            findings = [{
                'finding_id': f'F{i}', 'severity': 'P1', 'claim': f'Incorrect behavior {i}',
                'required_action': f'Repair rule {i}', 'verification': f'Rerun test {i}',
                'evidence': [f'Game.Core/Rule{i}.cs:12'], 'authority_refs': ['docs/adr/ADR-0001.md'],
                'disposition': {'action': 'fix'},
            } for i in range(6)]
            findings.append({'finding_id': 'DEFERRED', 'severity': 'P2', 'claim': 'Later', 'disposition': {'action': 'defer'}})
            payload = guide(root, 'sc-llm-review', {'task_id': '7', 'run_id': 'run-7', 'steps': [{
                'name': 'code-reviewer', 'details': {'review_contract': {'findings': findings}},
            }]})
            text = _repair_guidance.render_repair_guide_markdown(payload)
            for i in range(6):
                self.assertIn(f'Repair rule {i}', text)
                self.assertIn(f'Game.Core/Rule{i}.cs', text)
            self.assertNotIn('DEFERRED', text)

    def test_mismatched_child_identity_retains_existing_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = guide(root, 'sc-acceptance-check', {'task_id': '99', 'run_id': 'run-7', 'steps': [{
                'name': 'contracts', 'status': 'fail', 'details': {'errors': ['Unrelated contract failure']},
            }]})
            text = _repair_guidance.render_repair_guide_markdown(payload)
            self.assertIn('acceptance-rerun', text)
            self.assertNotIn('Unrelated contract failure', text)

    def test_stale_unit_artifacts_are_not_reported_as_current_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / 'logs' / 'unit' / 'day'
            artifacts.mkdir(parents=True)
            (artifacts / 'run_id.txt').write_text('other-run', encoding='utf-8')
            (artifacts / 'tests.trx').write_text('<TestRun><UnitTestResult testName="StaleTest" outcome="Failed" /></TestRun>', encoding='utf-8')
            payload = guide(root, 'sc-test', {'task_id': '7', 'run_id': 'run-7', 'steps': [{
                'name': 'unit', 'status': 'fail', 'artifacts_dir': str(artifacts),
            }]})
            self.assertNotIn('StaleTest', _repair_guidance.render_repair_guide_markdown(payload))

    def test_restore_failure_does_not_relabel_retained_trx_as_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / 'logs' / 'unit' / 'day'
            artifacts.mkdir(parents=True)
            (artifacts / 'run_id.txt').write_text('run-7', encoding='utf-8')
            write_json(artifacts / 'summary.json', {'restore_rc': 1})
            (artifacts / 'tests.trx').write_text('<TestRun><UnitTestResult testName="RetainedTest" outcome="Failed" /></TestRun>', encoding='utf-8')
            payload = guide(root, 'sc-test', {'task_id': '7', 'run_id': 'run-7', 'steps': [{
                'name': 'unit', 'status': 'fail', 'artifacts_dir': str(artifacts),
            }]})
            self.assertNotIn('RetainedTest', _repair_guidance.render_repair_guide_markdown(payload))

    def test_advisory_model_review_expands_findings_without_changing_producer_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = root / 'logs' / 'pipeline' / 'child-artifacts' / 'sc-llm-review'
            write_json(snapshot / 'summary.json', {'task_id': '7', 'run_id': 'run-7', 'steps': [{
                'name': 'code-reviewer', 'details': {'review_contract': {'findings': [{
                    'finding_id': 'F1', 'severity': 'P1', 'claim': 'Incomplete recovery',
                    'required_action': 'Repair bound recovery', 'evidence': ['scripts/python/resume_task.py:1'],
                }]}},
            }]})
            summary = {'status': 'ok', 'run_id': 'run-7', 'steps': [{
                'name': 'sc-llm-review', 'status': 'ok', 'summary_file': str(snapshot / 'summary.json'),
                'cmd': ['py', '-3', 'scripts/sc/llm_review.py', '--task-id', '7'],
            }]}
            with mock.patch.object(_repair_guidance, 'repo_root', return_value=root):
                payload = _repair_guidance.build_repair_guide(summary, task_id='7', out_dir=root / 'logs' / 'pipeline', marathon_state={
                    'agent_review': {'review_verdict': 'needs-fix', 'recommended_action': 'resume', 'owner_steps': ['sc-llm-review']},
                })
            validate_pipeline_repair_guide_payload(payload)
            self.assertEqual('ok', summary['status'])
            self.assertEqual('ok', payload['summary_status'])
            self.assertIn('Repair bound recovery', _repair_guidance.render_repair_guide_markdown(payload))

    def test_corrupt_child_summary_keeps_the_original_recovery_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'logs' / 'summary.json'
            path.parent.mkdir(parents=True)
            path.write_text('{invalid', encoding='utf-8')
            with mock.patch.object(_repair_guidance, 'repo_root', return_value=root):
                payload = _repair_guidance.build_repair_guide({'status': 'fail', 'run_id': 'run-7', 'steps': [{
                    'name': 'sc-test', 'status': 'fail', 'summary_file': str(path),
                }]}, task_id='7', out_dir=root / 'logs')
            validate_pipeline_repair_guide_payload(payload)
            self.assertIn('--task-id 7 --resume', _repair_guidance.render_repair_guide_markdown(payload))

    def test_review_keeps_structured_verification_and_mandatory_severity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = guide(root, 'sc-llm-review', {'task_id': '7', 'run_id': 'run-7', 'steps': [{
                'name': 'code-reviewer', 'details': {'review_contract': {'findings': [{
                    'finding_id': 'F0', 'severity': 'p0', 'claim': 'Lost state',
                    'required_action': 'Preserve checkpoint', 'verification': ['Run recovery test'],
                    'disposition': {'action': 'defer'},
                }]}},
            }]})
            text = _repair_guidance.render_repair_guide_markdown(payload)
            self.assertIn('P0 finding: F0', text)
            self.assertIn('Run recovery test', text)

    def test_different_run_does_not_supply_current_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = guide(root, 'sc-acceptance-check', {'task_id': '7', 'run_id': 'other-run', 'steps': [{
                'name': 'contracts', 'status': 'fail', 'details': {'errors': ['Different run evidence']},
            }]})
            self.assertNotIn('Different run evidence', _repair_guidance.render_repair_guide_markdown(payload))


if __name__ == '__main__':
    unittest.main()
