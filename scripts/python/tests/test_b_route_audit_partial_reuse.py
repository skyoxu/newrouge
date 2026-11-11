"""Synthetic protocol composition; the historical tool-transition seam is explicit.

Full request/protocol/execution/permit/schema/native proof validators stay live.
No real model or original server evidence is read or modified by these tests.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import _b_route_codec as codec
import _b_route_source_audit as audit
import _b_route_sources as sources
import _b_route_audit_recovery as recovery
from test_b_route_source_audit import SourceAuditTests


class PartialExtractionProofTests(unittest.TestCase):
    def test_partial_original_reuse_new_comparison_native_verify_and_tamper_rejection(self):
        fx = SourceAuditTests('test_v6_full_high_synthetic_protocol_execution_and_original_binding_replay')
        fx.setUp(); self.addCleanup(fx.doCleanups)
        fx.high_synthetic_protocol_roundtrip(audit.PRODUCER_SCHEMA_POLICY)
        olddir = next(p.parent for p in fx.root.rglob('report.json')
            if '/b-route-source-audit/' in p.as_posix() and p.parent.name == 'v5-protocol')
        prefix = olddir.relative_to(fx.root).as_posix()
        oldproof = fx.json(prefix+'/proof.json')
        account_ref = oldproof['accounted_ref']
        original = fx.json(prefix+'/input.json')
        old_identity = fx.json(prefix+'/identity.json')
        # Turn this private synthetic fixture into a genuinely incomplete audit.
        for rel in ['report.json','event.json','proof.json','comparison.json',
                    'steps/compare/execution.json','steps/compare/receipt.json',
                    'steps/compare/canonical-output.json','steps/compare/workspace/output.json']:
            path = olddir/rel
            self.assertTrue(path.resolve().is_relative_to(fx.root.resolve()))
            path.unlink()
        protocol = next((olddir/'steps/compare/workspace').glob('*.app-server.jsonl'))
        lines = protocol.read_bytes().splitlines(keepends=True)
        stop = next(i for i,line in enumerate(lines) if json.loads(line).get('message',{}).get('method') == 'turn/completed')
        protocol.write_bytes(b''.join(lines[:stop]))
        files = {p.relative_to(fx.root).as_posix():codec.raw_digest(p.read_bytes())
            for p in olddir.parent.rglob('*') if p.is_file()}
        retained = {p: (fx.root/p).read_bytes() for p in files}
        parent_ref='logs/ci/synthetic-parent.json'; fx.put(parent_ref,{'old_unknown':True,'charged':54})
        runner='logs/ci/synthetic-v4/runner/codex_isolated_model_runner.py'
        adapter=(fx.root/'protocol-runner.py').read_text(encoding='utf-8')
        adapter=adapter.replace('str(Path(__file__).with_name("b_route_protocol_child.py"))',
            repr(str(fx.root/'b_route_protocol_child.py')))
        fx.put(runner,adapter.encode('utf-8'))
        description=fx.json(prefix+'/runner.json')
        reference='logs/ci/synthetic-v4/reuse.json'
        def transition(old,new,*,runner_ref):
            # Only historical tool hash provenance is synthetic. The actual
            # native input/protocol/budget and phase identity digests are live.
            return {'synthetic_transition_seam':True,
                'old':codec.canonical_digest(old),'new':codec.canonical_digest(new),'runner':runner_ref}
        env={'CODEX_HOME':str(fx.root/'offline-metadata'),'NEWROGUE_CODEX_REASONING_EFFORT':'high',
            'NEWROGUE_B_ROUTE_FIXTURE_REASONING_EFFORT':'high'}
        with patch.dict(os.environ,env), patch.object(recovery,'coordinator_transition',side_effect=transition):
            current=audit.tool_identity(fx.root,fx.root/runner,'fixture/fixture-model','full-block',expected_reasoning_effort='high')
            value=audit.verify_step(sources.Observations(fx.root),prefix,{'name':'extract-000001'},
                audit.phase_input('extract',original,file=original['files'][0],citation_guidance='full-block'),old_identity)
            manifest={'schema_version':recovery.REUSE_SCHEMA,'original_prefix':prefix,'original_files':files,
                'parent_authority_ref':{'path':parent_ref,'raw_digest':codec.raw_digest((fx.root/parent_ref).read_bytes())},
                'old_unknown_refs':{'reservation':prefix+'/steps/compare/reservation.json',
                    'request':prefix+'/steps/compare/request.txt','protocol':protocol.relative_to(fx.root).as_posix()},
                'original_identity_digest':codec.canonical_digest(old_identity),
                'current_identity_digest':codec.canonical_digest(current),
                'source_input_digest':codec.canonical_digest(original),'extraction_digest':codec.canonical_digest(value),
                'runner_ref':runner,'phase_transition':transition(old_identity,current,runner_ref=runner)}
            fx.put(reference,manifest)
            code,report=fx.invoke('audit','compare-01',['--accounted',account_ref,'--runner',runner,
                '--expected-model','fixture/fixture-model','--completed-extraction-ref',reference,
                '--request-budget','1','--active-budget-seconds','330','--timeout-seconds','300',
                '--citation-guidance','full-block'],run='successor')
            self.assertEqual(1,code,report)  # Original omission remains a blocker.
            self.assertTrue(report['execution_complete'],report)
            self.assertFalse(report['planning_eligible'])
            self.assertEqual(['compare'],report['completed_steps'])
            self.assertEqual(1,report['runner_dispatch_count'])
            result=audit.verify_current_proof(sources.Observations(fx.root),report['output_ref']+'/report.json',scope_id='scope')
            self.assertEqual(value,result['extractions'][0])
            self.assertEqual(1,len(list((fx.root/report['output_ref']).parent.joinpath('reservations').glob('*.json'))))
            for path,raw in retained.items(): self.assertEqual(raw,(fx.root/path).read_bytes())
            expected=audit.phase_input('extract',original,file=original['files'][0],citation_guidance='full-block')
            for field in ['extraction_digest','current_identity_digest','source_input_digest','parent_authority_ref']:
                bad=deepcopy(manifest)
                if field=='parent_authority_ref': bad[field]['raw_digest']='sha256:'+'0'*64
                else: bad[field]='sha256:'+'0'*64
                fx.put(reference,bad)
                with self.subTest(field=field),self.assertRaises(ValueError):
                    recovery.verify_reuse_reference(sources.Observations(fx.root),reference,identity=current,
                        expected=expected,current_description=description,current_runner_ref=runner)
