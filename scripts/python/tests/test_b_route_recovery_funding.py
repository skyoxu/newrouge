"""Offline real-file funding tests; no model, network or native audit proof."""
from copy import deepcopy
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_recovery_funding as funding


def _concurrent_claim(namespace, parent_raw, start, results):
    start.wait(10)
    try:
        claim = funding.claim_comparison(namespace, parent_v3_raw=parent_raw)
    except (funding.FundingError, OSError):
        results.put('blocked')
    else:
        results.put(('winner', claim['claim_id']))


class RecoveryFundingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get('RECOVERY_FUNDING_TEST_TEMP'))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.namespace = self.root / 'comparison-v4'
        self.parent = b'{"retained_old_v3":"original"}'
        reference = lambda name: {'ref': 'logs/original/' + name, 'sha256': funding.raw_digest(name.encode())}
        self.inputs = {'old_permit': reference('permit.json'), 'old_request': reference('request.txt'),
                       'old_protocol': reference('protocol.jsonl'),
                       'extraction': {'prefix': 'logs/original/extract', 'manifest': {'output.json': reference('output.json')}},
                       'source': {'bytes_base64': 'U291cmNl', 'sha256': funding.raw_digest(b'Source')},
                       'current_identity': {'model': 'openai/gpt-6.1-sol', 'reasoning': 'high', 'tools': []},
                       'code_freeze': {'files': {'scripts/python/runtime.py': reference('runtime.py')}}}

    def prepare(self):
        return funding.prepare(self.namespace, parent_v3_raw=self.parent, inputs=self.inputs)

    def claim(self):
        self.prepare()
        return funding.claim_comparison(self.namespace, parent_v3_raw=self.parent)

    def test_prepare_complete_input_binding_and_parent_drift(self):
        intent = self.prepare()
        raw = (self.namespace / 'intent.json').read_bytes()
        self.assertEqual(54, intent['budget']['old_liabilities'])
        self.assertEqual(330, intent['budget']['comparison_seconds'])
        self.assertEqual(self.inputs, intent['inputs'])
        self.assertEqual(funding.digest(self.inputs), intent['input_digest'])
        self.assertEqual(intent, self.prepare())
        self.assertEqual('prepared', funding.inspect(self.namespace, parent_v3_raw=self.parent)['status'])
        with self.assertRaises(funding.FundingError):
            funding.inspect(self.namespace, parent_v3_raw=self.parent + b' ')
        mutated = deepcopy(self.inputs)
        mutated['code_freeze']['files']['extra.py'] = {'full': 'additional code membership'}
        with self.assertRaises(funding.FundingError):
            funding.prepare(self.namespace, parent_v3_raw=self.parent, inputs=mutated)
        self.assertEqual(raw, (self.namespace / 'intent.json').read_bytes())

    def test_strict_json_and_closed_input_objects(self):
        for mutate in ('unknown', 'non-finite', 'tuple', 'reference-extra'):
            with self.subTest(mutate=mutate):
                inputs = deepcopy(self.inputs)
                if mutate == 'unknown':
                    inputs['extra'] = {}
                elif mutate == 'non-finite':
                    inputs['source']['bad'] = float('nan')
                elif mutate == 'tuple':
                    inputs['current_identity']['tools'] = ('hidden',)
                else:
                    inputs['old_permit']['extra'] = 'not allowed'
                with self.assertRaises(funding.FundingError):
                    funding.prepare(self.namespace, parent_v3_raw=self.parent, inputs=inputs)
                self.assertFalse(self.namespace.exists())
        self.prepare()
        path = self.namespace / 'intent.json'
        original = path.read_bytes()
        path.write_bytes(b'{"schema_version":"duplicate","schema_version":"duplicate"}')
        with self.assertRaises(funding.FundingError):
            funding.inspect(self.namespace, parent_v3_raw=self.parent)
        self.assertNotEqual(original, path.read_bytes())

    def test_one_claim_is_charged_before_any_dispatch_and_never_reused(self):
        claim = self.claim()
        self.assertEqual(1, claim['logical_calls'])
        self.assertEqual(330, claim['reserved_seconds'])
        snapshot = funding.inspect(self.namespace, parent_v3_raw=self.parent)
        self.assertEqual('unknown', snapshot['status'])
        self.assertEqual(1, snapshot['logical_charged_or_unknown'])
        self.assertEqual(0, snapshot['released'])
        before = (self.namespace / 'claim.json').read_bytes()
        with self.assertRaises(funding.FundingError):
            funding.claim_comparison(self.namespace, parent_v3_raw=self.parent)
        self.assertEqual(before, (self.namespace / 'claim.json').read_bytes())

    def test_concurrent_real_processes_have_one_permanent_winner(self):
        self.prepare()
        context = multiprocessing.get_context('spawn')
        start, results = context.Event(), context.Queue()
        children = [context.Process(target=_concurrent_claim,
                    args=(str(self.namespace), self.parent, start, results)) for _ in range(2)]
        for child in children:
            child.start()
        start.set()
        observed = [results.get(timeout=20) for _ in children]
        for child in children:
            child.join(20)
            self.assertEqual(0, child.exitcode)
        self.assertEqual(1, sum(isinstance(row, tuple) and row[0] == 'winner' for row in observed))
        self.assertEqual(1, observed.count('blocked'))
        self.assertEqual(1, funding.inspect(self.namespace, parent_v3_raw=self.parent)['logical_charged_or_unknown'])
        results.close()
        results.join_thread()

    def test_partial_claim_and_host_loss_are_not_repaired_or_refunded(self):
        self.prepare()
        claim_path = self.namespace / 'claim.json'
        claim_path.write_bytes(b'{"partial":')
        before = claim_path.read_bytes()
        for action in (funding.inspect, funding.claim_comparison):
            with self.assertRaises(funding.FundingError):
                action(self.namespace, parent_v3_raw=self.parent)
        self.assertEqual(before, claim_path.read_bytes())

    def test_failure_after_claim_creation_leaves_permanent_unknown(self):
        self.prepare()
        with patch.object(funding, '_atomic_state', side_effect=OSError('simulated host loss')):
            with self.assertRaises(OSError):
                funding.claim_comparison(self.namespace, parent_v3_raw=self.parent)
        original = (self.namespace / 'claim.json').read_bytes()
        self.assertFalse((self.namespace / 'state.json').exists())
        with self.assertRaisesRegex(funding.FundingError, 'Claim consumed'):
            funding.inspect(self.namespace, parent_v3_raw=self.parent)
        with self.assertRaises(funding.FundingError):
            funding.claim_comparison(self.namespace, parent_v3_raw=self.parent)
        self.assertEqual(original, (self.namespace / 'claim.json').read_bytes())

    def test_each_terminal_outcome_retains_charge_and_rejects_claim_or_settle_retry(self):
        for outcome in ('success', 'blocked', 'unknown'):
            with self.subTest(outcome=outcome):
                namespace = self.root / ('terminal-' + outcome)
                funding.prepare(namespace, parent_v3_raw=self.parent, inputs=self.inputs)
                claim = funding.claim_comparison(namespace, parent_v3_raw=self.parent)
                wrong = {**claim, 'claim_id': '0' * 32}
                with self.assertRaises(funding.FundingError):
                    funding.settle_comparison(namespace, parent_v3_raw=self.parent, claim=wrong,
                                              outcome=outcome, evidence={})
                state = funding.settle_comparison(namespace, parent_v3_raw=self.parent, claim=claim,
                    outcome=outcome, evidence={'original_result': 'caller independently verified'})
                self.assertEqual(outcome, state['outcome'])
                self.assertTrue(state['settled'])
                self.assertEqual(0, state['released'])
                self.assertEqual(1, state['logical_charged_or_unknown'])
                self.assertEqual('settled', funding.inspect(namespace, parent_v3_raw=self.parent)['status'])
                with self.assertRaises(funding.FundingError):
                    funding.claim_comparison(namespace, parent_v3_raw=self.parent)
                with self.assertRaises(funding.FundingError):
                    funding.settle_comparison(namespace, parent_v3_raw=self.parent, claim=claim,
                                              outcome=outcome, evidence={})

    def test_partial_settlement_and_state_replace_fail_closed(self):
        claim = self.claim()
        original = (self.namespace / 'state.json').read_bytes()
        with patch.object(funding, '_atomic_state', side_effect=OSError('simulated interrupted replace')):
            with self.assertRaises(OSError):
                funding.settle_comparison(self.namespace, parent_v3_raw=self.parent, claim=claim,
                                          outcome='success', evidence={})
        self.assertTrue((self.namespace / 'settlement.json').exists())
        self.assertEqual(original, (self.namespace / 'state.json').read_bytes())
        with self.assertRaisesRegex(funding.FundingError, 'Partial or conflicting'):
            funding.inspect(self.namespace, parent_v3_raw=self.parent)
        with self.assertRaises(funding.FundingError):
            funding.claim_comparison(self.namespace, parent_v3_raw=self.parent)

    def test_atomic_state_replace_failure_retains_partial_artifact(self):
        self.prepare()
        with patch.object(funding.os, 'replace', side_effect=OSError('simulated replace failure')):
            with self.assertRaises(OSError):
                funding.claim_comparison(self.namespace, parent_v3_raw=self.parent)
        self.assertTrue((self.namespace / 'claim.json').exists())
        self.assertEqual(1, len(list(self.namespace.glob('.state-*.tmp'))))
        with self.assertRaisesRegex(funding.FundingError, 'partial namespace'):
            funding.inspect(self.namespace, parent_v3_raw=self.parent)

    def test_cap43_funds_full_mvg192_cap44_exhausts_without_lowering_caps(self):
        self.assertEqual(7, funding.mvg_funding(0, qualified=True)['topup'])
        allowed = funding.mvg_funding(43, qualified=True)
        self.assertEqual({'topup': 50, 'guard': 290, 'capability_ceiling': 96, 'mvg_ceiling': 192},
                         {key: allowed[key] for key in ('topup', 'guard', 'capability_ceiling', 'mvg_ceiling')})
        for count in (44, 96, 97, -1, True):
            with self.subTest(count=count), self.assertRaises(funding.FundingError):
                funding.mvg_funding(count, qualified=True)
        with self.assertRaises(funding.FundingError):
            funding.mvg_funding(0, qualified=False)

    def test_unsafe_names_hardlinks_and_reparse_points_are_rejected(self):
        for name in ('CON', 'NUL.json', 'bad:name', 'bad.', 'trailing ', '..'):
            with self.subTest(name=name), self.assertRaises(funding.FundingError):
                funding.prepare(self.root / name, parent_v3_raw=self.parent, inputs=self.inputs)
        self.prepare()
        intent_path = self.namespace / 'intent.json'
        alias = self.root / 'intent-hardlink.json'
        os.link(intent_path, alias)
        with self.assertRaisesRegex(funding.FundingError, 'Hardlinked'):
            funding.inspect(self.namespace, parent_v3_raw=self.parent)
        alias.unlink()
        real_lstat = Path.lstat

        def reparse_lstat(path):
            record = real_lstat(path)
            if path == intent_path:
                class ReparseRecord:
                    st_mode = record.st_mode
                    st_file_attributes = 0x400
                return ReparseRecord()
            return record

        with patch.object(Path, 'lstat', reparse_lstat):
            with self.assertRaisesRegex(funding.FundingError, 'Reparse'):
                funding.inspect(self.namespace, parent_v3_raw=self.parent)


if __name__ == '__main__':
    unittest.main(verbosity=2)
