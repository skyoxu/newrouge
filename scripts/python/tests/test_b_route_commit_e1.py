"""Retained dependencies use real local storage and synthetic native eligibility."""
from copy import deepcopy
import shutil
import unittest
from unittest.mock import patch

import _b_route_adoption as adoption
import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_records as records
import _planning_apply_journal as journal
from _b_route_operation_scope import resource_scopes
from test_b_route_commit import CommitFixture
from test_b_route_records import MatrixFixture, CATALOG, encoded, logical


class RetainedDependencyCommitTests(CommitFixture, unittest.TestCase):
    def prepare_dependency(self, *, owner_revision=1, separate_receipts=False):
        self.fixture()
        request = self.relocate_proofs(deepcopy(self.fx.request))
        native, content = self.fx.cases['one']

        # Seed independently hashed formal Q/R bytes and an independent Q binding.
        seed = MatrixFixture()
        seed.models.clear()
        seed.current_plans.clear()
        q = seed.add_plan('q', 1)
        r = seed.add_plan('r', 1)
        seed.models[q]['definitions']['states'] = [{
            'id': 'q-state', 'requirement_ids': ['REQ-q'],
            'responsibility': 'Own the retained dependency state', 'uses': []}]
        qb = seed.add_binding('q', 7, task_id=11)
        proof = 'logs/proof/seed-admission.json'
        seed.artifacts[proof] = seed.artifacts.pop('evidence/admission.json')
        for model in seed.models.values():
            model['adoption_proof_refs'] = [seed.owned('planning_proof', proof)]
        files = seed.render()
        qref, qbref, rref = (seed.reference(name, files) for name in (q, qb, r))
        qscopes = resource_scopes(target_paths=[q, qb], plan_ids=['q'],
                                 task_ids=[11], state_ids=['q-state'])
        rscopes = resource_scopes(target_paths=[r], plan_ids=['r'])
        receipt_path = records.BASE + 'commits/operation-1.json'
        old_receipt = codec.strict_json_loads(files[receipt_path])
        proof_digest = codec.raw_digest(files[proof])
        old_receipt['authority'].append({'path': proof, 'before_digest': proof_digest,
                                         'after_digest': proof_digest})
        old_receipt['scopes'] = old_receipt['result']['scope_ids'] = sorted(set(qscopes) | set(rscopes))
        files[receipt_path] = encoded(old_receipt)
        old_receipt_ref = seed.reference(receipt_path, files)
        catalog = codec.strict_json_loads(files[CATALOG])
        catalog['scope_heads'] = [
            {'scope_id': scope, 'plan_refs': [ref], 'binding_refs': bindings,
             'receipt_ref': old_receipt_ref}
            for scopes, ref, bindings in ((qscopes, qref, [qbref]), (rscopes, rref, []))
            for scope in scopes]
        files[CATALOG] = encoded(catalog)
        if separate_receipts:
            for plan_id, scopes, refs, bindings in (('q', qscopes, [qref], [qbref]),
                                                    ('r', rscopes, [rref], [])):
                receipt = deepcopy(old_receipt)
                receipt['operation_id'] = 'operation-' + plan_id
                receipt['scopes'] = receipt['result']['scope_ids'] = list(scopes)
                receipt['plan_refs'], receipt['binding_refs'] = refs, bindings
                selected_paths = {row['path'] for row in refs + bindings}
                receipt['targets'] = [row for row in receipt['targets']
                    if row['path'] not in {q, qb, r} or row['path'] in selected_paths]
                receipt['result']['target_paths'] = [row['path'] for row in receipt['targets']]
                receipt['resolved_definitions'] = [row for row in receipt['resolved_definitions']
                    if row['plan_ref']['entity_id'] == plan_id]
                name = records.BASE + 'commits/' + receipt['operation_id'] + '.json'
                files[name] = encoded(receipt)
                reference = seed.reference(name, files)
                for head in catalog['scope_heads']:
                    if head['scope_id'] in scopes:
                        head['receipt_ref'] = reference
            files.pop(receipt_path)
            files[CATALOG] = encoded(catalog)
        joined = seed.join((11,))
        for name, document in (('master', joined.master), ('back', joined.back), ('gameplay', joined.gameplay)):
            files[adoption.TRIPLET[name]] = encoded(document)
        for name, raw in files.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        checked = records.validate_bundle({}, root=self.root, task_join=joined)
        self.assertTrue(checked.ok, checked.diagnostic)
        self.assertTrue(records.published_bundle(self.root, task_join=joined)['scope_ids'])
        observed = adoption.Snapshot(self.root)
        adoption._committed(observed)
        self.fx.protected_tasks = [{'task_id': 11, 'definition_digest': observed.tasks[11]}]

        use = logical('state', 'q-state', 'q', owner_revision)
        content['logical_references'] = [use]
        content['selected_dependencies'] = [qref]
        plan_template = request['material']['target_templates'][0]['after_payload']
        plan_template['logical_references'] = [deepcopy(use)]
        handoff = request['material']['handoff_ref']['path']
        native.artifacts[handoff] = encoded({'schema_version': 'synthetic.handoff.v1',
                                            'proposal': {'content': content}})
        (self.root / handoff).write_bytes(native.artifacts[handoff])
        digest = codec.raw_digest(native.artifacts[handoff])
        request['material']['handoff_ref']['raw_digest'] = digest
        plan_template['native_candidate_ref']['files'][0]['raw_digest'] = digest
        native.artifacts[q] = files[q]

        self.request = request
        self.fx.prepare(request)
        with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
            adoption.reserve(self.root, operation_id='OP-one')
        self.seed, self.seed_catalog = files, catalog
        self.q, self.qb, self.qref, self.qbref = q, qb, qref, qbref
        return journal.read_operation(self.root, operation_id='OP-one')

    def test_dependency_publish_retains_q_owner_and_independent_binding(self):
        envelope = self.prepare_dependency()
        frozen = envelope['frozen']
        before_heads = {row['scope_id']: row for row in self.seed_catalog['scope_heads']}
        selected = set(frozen['scope_ids'])
        qheads = {scope for scope, row in before_heads.items() if self.qref in row['plan_refs']}
        self.assertTrue(qheads <= selected)
        self.assertTrue(set(before_heads) - selected)
        self.assertNotIn(self.q, {row['path'] for row in frozen['targets']})
        self.assertNotIn(self.qb, {row['path'] for row in frozen['targets']})
        self.assertTrue(self.publish()['formal_adoption'])
        catalog = codec.strict_json_loads((self.root / CATALOG).read_bytes())
        heads = {row['scope_id']: row for row in catalog['scope_heads']}
        receipt_ref = heads[next(iter(selected))]['receipt_ref']
        self.assertTrue(all(heads[scope]['receipt_ref'] == receipt_ref for scope in selected))
        for scope, old in before_heads.items():
            if scope in qheads:
                self.assertEqual(old['plan_refs'], heads[scope]['plan_refs'])
                self.assertEqual(old['binding_refs'], heads[scope]['binding_refs'])
            elif scope not in selected:
                self.assertEqual(old, heads[scope])
        self.assertEqual(self.seed[self.q], (self.root / self.q).read_bytes())
        self.assertEqual(self.seed[self.qb], (self.root / self.qb).read_bytes())
        self.assertIn({'kind': 'state', 'definition_id': 'q-state', 'plan_ref': self.qref},
                      catalog['definition_owners'])
        receipt = codec.strict_json_loads((self.root / receipt_ref['path']).read_bytes())
        self.assertIn(self.qref, receipt['plan_refs'])
        self.assertIn(self.qbref, receipt['binding_refs'])
        task = next(row for row in catalog['task_index'] if row['task_id'] == 11)
        self.assertEqual([self.qref], task['plan_refs'])
        self.assertEqual([self.qbref], task['binding_refs'])
        intent = commit.validate_local(self.root, envelope)
        self.assertEqual(receipt, intent['receipt'])
        checked = records.validate_bundle({}, root=self.root, task_join=commit._task_join(self.root))
        self.assertTrue(checked.ok, checked.diagnostic)
        self.assertTrue(commit.read_committed(self.root, scope_ids=sorted(selected))['formal_adoption'])

    def test_missing_retained_q_still_rejects_before_target_write(self):
        envelope = self.prepare_dependency()
        (self.root / self.q).unlink()
        before = self.formal()
        with self.assertRaises(codec.CodecError):
            self.step('apply')
        self.assertEqual(before, self.formal())
        self.assertTrue(all(not (self.root / row['path']).exists() for row in envelope['frozen']['targets']))

    def test_dependency_publish_preserves_independent_prior_receipt_authority(self):
        envelope = self.prepare_dependency(separate_receipts=True)
        try:
            result = self.publish()
        except codec.CodecError as error:
            self.fail(str(error.diagnostic.to_dict()))
        self.assertTrue(result['formal_adoption'])
        self.assertTrue(commit.read_committed(self.root,
            scope_ids=envelope['frozen']['scope_ids'])['formal_adoption'])
        current = codec.strict_json_loads((self.root / CATALOG).read_bytes())
        p_ref = next(ref for head in current['scope_heads'] for ref in head['plan_refs']
                     if ref['entity_id'] not in ('q', 'r'))
        previous_raw = (self.root / p_ref['path']).read_bytes()
        previous = {'path': p_ref['path'], 'schema_version': adoption.PLAN,
                    'raw_digest': codec.raw_digest(previous_raw)}
        native, _ = self.fx.cases['one']
        native.artifacts[p_ref['path']] = previous_raw
        request = deepcopy(self.request)
        request['operation_id'] = 'OP-replan'
        request.pop('host_review_ref', None)
        alignment = request['material']['identity_alignment']
        alignment['plan'] = {'mode': 'reuse', 'plan_ref': previous}
        for family in ('requirements', 'flows'):
            for row in alignment[family]:
                row.update(mode='reuse', stable_id=envelope['frozen']['allocations'][family][row['candidate_id']],
                           evidence_ref=previous)
        flow = next(iter(envelope['frozen']['allocations']['flows'].values()))
        lineage = request['material']['target_templates'][0]['after_payload']['lineage']
        lineage.update(previous_plan_ref=p_ref, change_summary='Explicit unchanged semantic replan',
            identity_alignment=[{'kind': 'flow', 'previous_id': flow, 'current_id': flow,
                                 'rationale': alignment['flows'][0]['rationale']}])
        self.fx.prepare(request)
        with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
            adoption.reserve(self.root, operation_id='OP-replan')
        for stage in ('apply', 'verify', 'publish'):
            self.step(stage, 'OP-replan')
        current = codec.strict_json_loads((self.root / CATALOG).read_bytes())
        self.assertFalse(any(head['receipt_ref']['entity_id'] in ('OP-one', 'operation-q')
                             for head in current['scope_heads']))
        self.assertTrue(commit.read_committed(self.root)['formal_adoption'])

        # A clone retains formal certificate bytes but no local proof/operation logs.
        clone = self.root.with_name(self.root.name + '-clone')
        shutil.copytree(self.root, clone, ignore=shutil.ignore_patterns('logs'))
        formal_before = self.formal(clone)
        self.assertTrue(commit.read_committed(clone)['formal_adoption'])
        self.assertEqual(formal_before, self.formal(clone))

        required = clone / (records.BASE + 'commits/operation-q.json')
        original = required.read_bytes()
        other = codec.strict_json_loads(original)
        other['operation_id'] = 'operation-unbound'
        (clone / (records.BASE + 'commits/operation-unbound.json')).write_bytes(encoded(other))
        for damaged in (None, original + b'\n'):
            if damaged is None:
                required.unlink()
            else:
                required.write_bytes(damaged)
            with self.assertRaises(codec.CodecError):
                commit.read_committed(clone)
            required.write_bytes(original)
            self.assertTrue(commit.read_committed(clone)['formal_adoption'])

    def test_conflicting_dependency_owner_revision_still_rejects(self):
        envelope = self.prepare_dependency(owner_revision=2)
        before = self.formal()
        with self.assertRaises(codec.CodecError) as failure:
            self.step('apply')
        self.assertEqual(codec.ReasonCode.REVISION_MISMATCH, failure.exception.diagnostic.reason_code)
        self.assertEqual(before, self.formal())
        self.assertTrue(all(not (self.root / row['path']).exists() for row in envelope['frozen']['targets']))
