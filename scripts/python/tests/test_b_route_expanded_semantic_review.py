"""Root-only offline view/schema tests. Neutral data never qualifies origin/model."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import _b_route_adoption_projection as projection
import _b_route_adoption_review as review
import _b_route_adoption_semantic_view as view
import _b_route_codec as codec
import _b_route_qualified_origin as origin
import _b_route_schema_resources as resources
class _NeutralCandidateData:
    SCHEMA = 'newrouge.b-route-planning-candidate.v1'
    PARTS = {'domain_rules', 'csharp_adapter', 'binding', 'scene'}

# Fixture literals only; never a product owner, candidate qualification or module.
candidate = _NeutralCandidateData

def use(fid='FLOW', owner='proposal-owner'):
    return {'kind': 'flow', 'definition_id': fid, 'proposed_owner_key': owner}

def point(node, flow='FLOW'):
    return {'flow_id': flow, 'node_id': node}

class ExpandedSemanticReviewTests(unittest.TestCase):
    def setUp(self):
        # Pure local data seam: inline original flow/envelope/use/point data builders.
        # No inherited setUp/prepare, tokenizer, disk fixture or origin qualification.
        class NeutralContent:
            def flow(self, fid='FLOW'):
                owner = use(fid)
                nodes = [{'id': name, 'responsibility': 'Keep exact  \r\n', 'owner': deepcopy(owner), 'command_uses': [], 'state_uses': []} for name in ('entry', 'act', 'success', 'optional')]
                edges = [{'id': 'edge' + str(i), 'from': point(a, fid), 'to': point(b, fid), 'condition': 'Declared condition', 'responsibility': 'Flow owner', 'owner': deepcopy(owner)} for i, (a, b) in enumerate((('entry', 'act'), ('act', 'success'), ('success', 'entry')))]
                boundaries = [{'id': name, 'kind': name, 'node': point(name, fid), 'condition': 'Declared boundary', 'required': True, 'rationale': 'Source obligation'} for name in ('entry', 'success')]
                obligation = {'applicability': 'not_applicable', 'rationale': 'Source describes pure logical rule.', 'responsibilities': [], 'owner': deepcopy(owner)}
                return {'id': fid, 'proposed_owner_key': 'proposal-owner', 'requirement_ids': [self.proposal['proposal_id']], 'capability_ids': ['proposal:capability-main', 'CAP-EXISTING'], 'source_block_ids': ['B1'], 'entry_condition': 'Enter when requested', 'branches': [{'kind': k, 'applicability': 'not_applicable', 'rationale': 'No such source obligation', 'boundary_ids': []} for k in ('failure', 'cancel', 'return')], 'handoffs': [], 'state_owners': [], 'parts': [{'kind': k, 'applicability': 'applicable' if k == 'domain_rules' else 'not_applicable', 'rationale': 'Source-backed logical applicability', 'responsibilities': ['Keep rule'] if k == 'domain_rules' else []} for k in sorted(candidate.PARTS)], 'observable_result': 'Visible rule result', 'verification_targets': ['Observe result'], 'ui': {**deepcopy(obligation), 'inputs': [], 'feedback': [], 'scene_entry': [], 'scene_return': []}, 'human_verification': deepcopy(obligation), 'graph': {'nodes': nodes, 'edges': edges, 'boundaries': boundaries, 'loops': [{'id': 'retry', 'anchors': [point('act', fid)], 'exit_boundary_ids': ['success'], 'description': 'Successful boundary allows reentry', 'exit_condition': 'Success observed'}]}}
            def envelope(self):
                rid = self.proposal['proposal_id']
                verification = {'requirement_id': rid, 'disposition': 'flow', 'flow_id': 'FLOW', 'rationale': 'Observable result', 'sink_id': None, 'verification_ref': None, 'authority_ref': None, 'evidence_ids': []}
                return {'schema_version': candidate.SCHEMA, 'input_stage': '3b', 'input_identity': self.frozen['input_identity'], 'provenance': {'kind': 'manual', 'declaration': 'Complete manually supplied candidate', 'upstream_model_history': 'unknown', 'draft_chain': [], 'final_draft_identity': None}, 'content': {'source_identity': {'manifest_ref': self.owned('source_manifest', 'native-manifest.json'), 'ledger_ref': self.owned('source_ledger', 'native-ledger.json'), 'source_revision': self.manifest['source_revision'], 'source_manifest_digest': self.manifest['manifest_sha256']}, 'requirements': [{'requirement_id': rid, **{k: deepcopy(self.proposal[k]) for k in ('source_block_ids', 'acceptance_intent', 'prior_requirement_ids', 'non_task_sinks')}}], 'out_of_scope_requirement_ids': [], 'selected_dependencies': [], 'definitions': {'flows': [self.flow()], 'commands': [], 'states': []}, 'logical_references': [], 'requirement_verification': [verification], 'coverage_table': [{k: v for k, v in verification.items() if k != 'evidence_ids'}], 'requirement_route_memberships': [{'requirement_id': rid, 'flow_id': 'FLOW', 'observable_role': 'Primary visible result'}], 'requirement_evidence': [], 'evidence_source_refs': [], 'applicability': [{'requirement_id': rid, 'disposition': 'flow', 'rationale': 'Observable result', 'other_verification_refs': []}], 'unresolved': [], 'implementation_objects': [{'id': 'planned-scene', 'kind': 'scene', 'availability': 'planned', 'owner': use(), 'expected_type': 'LaterScene', 'lifecycle': 'Bound later', 'target_ref': None, 'later_checks': ['type', 'compile', 'binding', 'engine']}]}}
            def owned(self, owner, path):
                return {'owner': owner, 'ref': path,
                    'files': [{'path': path, 'raw_digest': codec.raw_digest(b'neutral-view-only')}]}
        fixture = NeutralContent()
        fixture.manifest = {'source_revision': 'neutral-view-only', 'manifest_sha256': 'sha256:'+'1'*64}
        fixture.proposal = {'proposal_id': 'proposal:neutral-rule', 'source_block_ids': ['B1'],
            'acceptance_intent': 'Neutral observable rule', 'prior_requirement_ids': [], 'non_task_sinks': []}
        fixture.frozen = {'input_identity': 'sha256:'+'2'*64}
        self.content = fixture.envelope()['content']
        self.allocations = {'plan_id': 'PLAN-STABLE', 'plan_revision': 3,
            'requirements': {self.content['requirements'][0]['requirement_id']: 'RQ-STABLE'},
            'flows': {'FLOW': 'FLOW-STABLE'}}
        item=self.content['implementation_objects'][0]
        self.content['implementation_objects']=[{**deepcopy(item),'id':'planned-neutral-'+str(i)} for i in range(10)]
        registered={'schema_version':'chapter3.source-set.v1','active_patterns':[origin.SOURCE],
                    'active_sources':[origin.SOURCE],'retirements':[]}
        raw=(json.dumps(registered,indent=2)+'\n').encode();digest=codec.raw_digest(raw)
        handoff={'path':'native/capsule.json','raw_digest':'sha256:'+'2'*64}
        self.plan={'schema_version':'newrouge.b-route-plan.v1',**projection.project_content(self.content,self.allocations),
            'plan_id':self.allocations['plan_id'],'revision':self.allocations['plan_revision'],
            'lineage':{'previous_plan_ref':None},'native_candidate_ref':{'owner':'planning_proof',
                'ref':handoff['path']+'#/proposal/content','files':[deepcopy(handoff)]}}
        self.subject={'schema_version':view.SUBJECT,'operation_id':'OP-neutral',
            'request':{'review_profile':view.PROFILE,'material':{'handoff_ref':handoff,
                'identity_alignment':{'requirements':[],'flows':[]}}},
            'origin_capsule':{'source_set_digest':digest,'target_identity':{'path':'neutral-target'}},
            'registered_source_set':{'path':origin.SOURCE_SET,'raw_digest':digest,'raw_base64':base64.b64encode(raw).decode()},
            'target_dependencies':{origin.SOURCE_SET:digest},'native_content':self.content,
            'preview':{'allocations':self.allocations,'targets':[{'path':'docs/planning/b-route/plans/PLAN-STABLE/3.json',
                'schema_version':'newrouge.b-route-plan.v1','after_payload':self.plan}]},
            'protection':self.protection(), 'selected_design_history':self.history()}

    def history(self):
        profile={'name':'exclusive-reward-jsonl','version':1,'owner':'neutral implementer','launch':'neutral launch',
            'launch_bindings':[],'framing':'neutral framing','messages':[],'ordering':[],
            'independent_observations':{'readUI':'neutral actual surface observation',
                'readJ':'neutral complete journal read','startup_identity':'neutral owned identity check'}}
        return {'schema_version':'newrouge.b-route-selected-design-history.v1',
            'document':{'origin_relative_path':'logs/ci/mvg-planning/m4/accepted-chain/proposal.json',
                'raw_digest':'sha256:'+'1'*64,'raw_bytes':10,'input_identity':'sha256:'+'2'*64},
            'drafts':[{'source_pointer':'/provenance/draft_chain/'+str(i), 'draft_identity':'sha256:'+str(i+1)*64,
                'schema_version':'newrouge.b-route-planning-draft.v1','input_identity':'sha256:'+'2'*64,
                'stage':'batch' if i==0 else 'synthesis','ordinal':i+1,
                'parent_draft_identities':[] if i==0 else ['sha256:'+'1'*64]} for i in range(2)],
            'final_draft_identity':'sha256:'+'2'*64,
            'fragments':[{'source_pointer':p,'value':v} for p,v in [
                ('/provenance/draft_chain/0/content/design_choices/selected_choices/0','neutral selected profile'),
                ('/provenance/draft_chain/0/content/design_choices/selected_choices/2','neutral selected observer'),
                ('/provenance/draft_chain/0/content/launch_message_profile',profile)]],
            'current_correspondence':{'profile_command_pointer':'/definitions/commands/0',
                'observer_command_pointer':'/definitions/commands/1','final_content_equals_current_native':True},
            'scope':'selected semantic fragments; neutral fixture, never eligibility'}

    def protection(self):
        return {'schema_version':'newrouge.b-route-protection-snapshot.v3','stable':True,'capture_complete':True,
            'diagnostics':[],'inventory':{'artifact':'inventory.json','raw_digest':'sha256:'+'1'*64,
                'content_identity':'sha256:'+'2'*64,'adoptable':True,'diagnostics':[]},
            'authorization':{'formal_protection_baseline':False,'frozen_a':False,'write':False,
                'policy_bootstrap':False,'target_projection_verified':False},
            'raw_files':[{'path':origin.SOURCE,'exists':True,'raw_digest':'sha256:'+'3'*64,
                'canonical_digest':None,'size_bytes':10,'artifact':'raw/neutral.bin','roles':['declared-active-source']}],
            'tasks':[],'cumulative':[],'historical_inventory':None,
            'triplet':{'counts':{'master':0,'back':0,'gameplay':0},
                'documents':{'master':{'master':{'tasks':[]}},'back':[],'gameplay':[]}},
            'frozen_a':{'task_set':'verified-empty','candidate_count':0,'candidates':[],'classification_authorized':False},
            'legacy_manifest_requirement':{'schema_version':'newrouge.b-route-legacy-manifest-requirement.v3',
                'state':'initially_absent','reason':'governed_originals','original_observation_digest':'sha256:'+'4'*64,
                'governed_boundary':{'root_real':'neutral-target','head':'a'*40,'anchors':[],'reachable_commit_ids':[],
                    'controls_absent':[],'source_members':[origin.SOURCE],'manifest_directory_exists':False,
                    'manifest_members':[],'owner_records':[],'original_raw_digests':{origin.SOURCE:'sha256:'+'3'*64}}},
            'verification_limits':[
                'Read-only candidate, not a formal protection baseline or frozen-A policy.',
                'Missing historical debug attachments remain unresolved observations, not operation prerequisites; old done never satisfies new obligations.',
                'No committed reverse-governance proof is implemented; every Task candidate is blocked.',
                'Double-read observations do not isolate against external concurrent writers.',
                'Receipt target projections, policy bootstrap, journal and publication are not implemented.']}

    def expand(self):
        # Base rendering/real origin eligibility are separate original owners.
        return view.expand(self.subject,{'only_existing_positive_base':True})

    def test_all_ten_original_objects_and_four_fields_remain_literal_by_ref(self):
        original=deepcopy(self.subject);visible=self.expand();storage=visible['plan_storage']
        self.assertEqual(self.subject,original)
        self.assertEqual(set(storage['retained_native_fields']),set(projection.RETAINED_IN_NATIVE_PROOF))
        self.assertEqual(storage['retained_native_fields']['implementation_objects'],self.content['implementation_objects'])
        self.assertEqual(len(storage['retained_native_fields']['implementation_objects']),10)
        self.assertEqual(len(storage['inline_field_names']),10)
        self.assertFalse(storage['formal_bundle_read_automatically_expands_native_fields'])
        self.assertNotIn('implementation_objects',self.plan)

    def test_retained_owner_interpretation_is_derived_and_not_stored_raw(self):
        visible=self.expand()['plan_storage'];raw=visible['retained_native_fields']['implementation_objects'][0]
        derived=visible['retained_fields_with_host_identity_interpretation']['implementation_objects'][0]
        self.assertIn('proposed_owner_key',raw['owner']);self.assertNotIn('proposed_owner_key',derived['owner'])
        self.assertEqual(derived['owner']['owner_plan_id'],self.allocations['plan_id'])
        for name in ('availability','expected_type','lifecycle','target_ref','later_checks'):
            self.assertEqual(raw[name],derived[name])

    def test_wrong_native_ref_and_changed_inline_projection_are_rejected(self):
        for change in ('ref','inline'):
            old=deepcopy(self.plan)
            if change=='ref':self.plan['native_candidate_ref']['ref']='native/other.json#/proposal/content'
            else:self.plan['requirements'][0]['acceptance_intent']='Changed accepted meaning'
            with self.subTest(change=change),self.assertRaises(codec.CodecError):self.expand()
            self.plan.clear();self.plan.update(old)

    def test_missing_lifecycle_or_any_later_check_is_not_normalized_away(self):
        original=deepcopy(self.content['implementation_objects'][0])
        for field in ('lifecycle','availability','later_checks'):
            self.content['implementation_objects'][0].pop(field)
            with self.subTest(field=field),self.assertRaises(codec.CodecError):self.expand()
            self.content['implementation_objects'][0]=deepcopy(original)
        self.content['implementation_objects'][0]['later_checks']=['engine']
        with self.assertRaises(codec.CodecError):self.expand()

    def test_unknown_retained_proposed_owner_fails_closed(self):
        self.content['implementation_objects'][0]['owner']['proposed_owner_key']='unknown-neutral-owner'
        with self.assertRaises(codec.CodecError):self.expand()

    def test_actual_source_set_raw_value_and_dependency_are_all_bound(self):
        visible=self.expand()['review_scope']['source_set']
        self.assertEqual(visible['value']['active_sources'],[origin.SOURCE])
        self.subject['registered_source_set']['raw_base64']=base64.b64encode(b'{"private":"CANARY"}').decode()
        with self.assertRaises(codec.CodecError):self.expand()

    def test_extra_registered_source_and_rebound_dependency_rejected(self):
        raw=json.dumps({'schema_version':'chapter3.source-set.v1','active_patterns':[origin.SOURCE],
            'active_sources':[origin.SOURCE,'docs/foreign.md'],'retirements':[]}).encode()
        digest=codec.raw_digest(raw);self.subject['registered_source_set'].update(raw_base64=base64.b64encode(raw).decode(),raw_digest=digest)
        self.subject['origin_capsule']['source_set_digest']=digest;self.subject['target_dependencies'][origin.SOURCE_SET]=digest
        with self.assertRaises(codec.CodecError):self.expand()

    def test_separate_empty_sets_and_false_authorizations_are_visible_not_grants(self):
        scope=self.expand()['review_scope'];self.assertEqual(scope['protection']['tasks'],[])
        self.assertEqual(scope['protection']['cumulative'],[])
        self.assertFalse(scope['protection']['frozen_a']['classification_authorized'])
        self.assertTrue(all(v is False for v in scope['protection']['authorization'].values()))
        self.assertEqual(scope['protection']['legacy_manifest_requirement']['state'],'initially_absent')
        self.assertNotIn('write_allowed',scope)

    def test_task_zero_cannot_hide_nonempty_frozen_cumulative_or_legacy(self):
        original=deepcopy(self.subject['protection'])
        for field,value in [('cumulative',[{'private':'CANARY'}]),('tasks',[{'task_id':1}]),('historical_inventory',{})]:
            self.subject['protection'][field]=value
            with self.subTest(field=field),self.assertRaises(codec.CodecError):self.expand()
            self.subject['protection']=deepcopy(original)
        self.subject['protection']['frozen_a']['candidates']=[{'private':'CANARY'}]
        with self.assertRaises(codec.CodecError):self.expand()

    def test_unknown_body_sensitive_metadata_and_fake_grant_are_rejected(self):
        original=deepcopy(self.subject['protection'])
        for change in ('body','sensitive','grant'):
            if change=='body':self.subject['protection']['raw_files'][0]['raw_body']='CANARY-production-source'
            elif change=='sensitive':self.subject['protection']['raw_files'][0]['path']='.codex/auth.json'
            else:self.subject['protection']['authorization']['policy_bootstrap']=True
            with self.subTest(change=change),self.assertRaises(codec.CodecError):self.expand()
            self.subject['protection']=deepcopy(original)

    def test_unselected_private_fields_are_never_dumped(self):
        self.subject['prepared']={'protocol_base64':'CANARY-private-protocol'}
        self.subject['protection']['private_raw_body']='CANARY-production-code'
        raw=json.dumps(self.expand());self.assertNotIn('CANARY',raw)
        self.assertTrue(self.expand()['current_selection']['semantic_dependency_on_unprovided_text_remains_blocking'])

    def test_complete_selected_history_is_visible_and_missing_or_private_fields_block(self):
        visible=self.expand()['current_selection']['selected_design_history']
        self.assertEqual(visible,self.subject['selected_design_history'])
        self.assertEqual(len(visible['fragments']),3)
        old=deepcopy(self.subject['selected_design_history'])
        self.subject['selected_design_history']['fragments'].pop()
        with self.assertRaises(codec.CodecError):self.expand()
        self.subject['selected_design_history']=old
        self.subject['selected_design_history']['private_protocol']='CANARY'
        with self.assertRaises(codec.CodecError):self.expand()

    def test_original_draft_extractor_checks_raw_final_content_and_parent_chain(self):
        content=deepcopy(self.content);profile=deepcopy(self.history()['fragments'][2]['value'])
        content['definitions']['commands']=[{'id':'profile-and-hooks','responsibility':'use '+profile['launch']},
                                           {'id':'render-and-probe-adapter','responsibility':'observe actual surface'}]
        chain=[];identities=[]
        for i in range(3):
            draft={'schema_version':'newrouge.b-route-planning-draft.v1','input_identity':'sha256:'+'1'*64,
                'stage':'batch' if i==0 else 'synthesis','ordinal':i+1,'parent_draft_identities':list(identities),
                'content':{'design_choices':{'selected_choices':['profile','other','observer']},
                    'launch_message_profile':profile} if i==0 else deepcopy(content)}
            chain.append(draft);identities.append(codec.canonical_digest(draft))
        proposal={'input_identity':'sha256:'+'1'*64,'content':content,
                  'provenance':{'kind':'model_draft','draft_chain':chain,'final_draft_identity':identities[-1]}}
        raw=json.dumps(proposal).encode();path=str(origin.ORIGIN/origin.RUN/'accepted-chain/proposal.json')
        cap={'profile':origin.PROFILE,'proposal':{'content':content},
            'prepared_identity':{'input_identity':proposal['input_identity']},
            'native_capture':{'files':{path:codec.raw_digest(raw)}}}
        observed=view.extract_design_history(raw,cap)
        self.assertEqual(observed['fragments'][2]['value'],profile)
        self.assertEqual(observed['final_draft_identity'],identities[-1])
        for mutation in ('raw', 'final', 'parents'):
            changed=deepcopy(proposal);current=deepcopy(cap)
            if mutation=='final':changed['provenance']['draft_chain'][-1]['content']['unresolved']=['not original']
            if mutation=='parents':changed['provenance']['draft_chain'][-1]['parent_draft_identities']=[]
            bad=json.dumps(changed).encode()
            if mutation=='raw':bad+=b' '
            else:current['native_capture']['files'][path]=codec.raw_digest(bad)
            with self.subTest(mutation=mutation),self.assertRaises(codec.CodecError):
                view.extract_design_history(bad,current)

    def test_v2_v3_mix_and_unknown_profile_fail_closed(self):
        for version,selected in [(origin.SUBJECT,view.PROFILE),(view.SUBJECT,None),(view.SUBJECT,'unknown.v4')]:
            subject={'schema_version':version,'request':{} if selected is None else {'review_profile':selected}}
            with self.subTest(version=version,profile=selected),self.assertRaises(codec.CodecError):origin.public_subject(subject)

    def test_same_check_ids_and_distinct_v3_verdict_marker(self):
        old=deepcopy(self.subject);old['schema_version']=origin.SUBJECT;old['request'].pop('review_profile')
        self.assertEqual(review.obligations(old),review.obligations(self.subject))
        self.assertEqual(review.verdict_schema(old)['properties']['schema_version']['const'],'newrouge.b-route-adoption-review-verdict.v2')
        self.assertEqual(review.verdict_schema(self.subject)['properties']['schema_version']['const'],view.VERDICT)
        value={'schema_version':'newrouge.b-route-adoption-review-verdict.v2','subject_digest':codec.canonical_digest(self.subject),
            'verdict':'approved','findings':[],'checks':[{'id':i,'verdict':'approved','rationale':'neutral'} for i in review.obligations(self.subject)]}
        with self.assertRaises(codec.CodecError):review.check_verdict(self.subject,value)

    def test_v3_policy_internally_binds_new_view_and_retained_bridge_bytes(self):
        values={name:b'neutral rule '+name.encode() for name in ('_b_route_adoption_semantic_view.py',
            '_b_route_qualified_origin.py','_b_route_retained_execution.py','_b_route_adoption_projection.py')}
        with patch.object(review,'policy_identity',return_value='sha256:'+'1'*64), \
             patch.object(Path,'read_bytes',autospec=True,side_effect=lambda path:values[path.name]):
            original=review.policy_identity_v3()
            values['_b_route_adoption_semantic_view.py']+=b'changed'
            self.assertNotEqual(original,review.policy_identity_v3())
            values['_b_route_adoption_semantic_view.py']=b'neutral rule _b_route_adoption_semantic_view.py'
            values['_b_route_retained_execution.py']+=b'changed producer bridge'
            self.assertNotEqual(original,review.policy_identity_v3())

if __name__=='__main__':unittest.main()
