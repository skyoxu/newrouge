"""New-protocol COLD DATA / API tests; no native/model qualification.

One existing isolated legacy business fixture supplies complete valid Frozen/
Task/B/current data. The manually assembled public history is DATA ONLY, never
an authenticated handle or converted old ticket. Real-archive owner preparation
has its separate read-only acceptance harness and requires actual final input.
"""
from copy import deepcopy
from pathlib import Path
import json
import base64
import unittest
from unittest.mock import patch
import _b_route_codec as codec
import _b_route_compact_literal as compact
import _b_route_adoption as adoption
import _b_route_adoption_review as review
import _b_route_compensation_review_materials as legacy
import _b_route_qualified_compensation_materials as materials
import _b_route_qualified_compensation_review as qualified
import _b_route_qualified_public_history as public
import _b_route_qualified_history_host as history_host
import b_route_adoption as cli
from test_b_route_compensation import CompensationTests
from fixtures.codex_app_server_protocol import protocol, encoded
import _codex_app_server as transport


def refresh(packet):
    p=packet['presentation']
    p['materials_digest']=codec.canonical_digest(packet['materials'])
    p['roles_digest']=codec.canonical_digest(packet['roles'])
    return packet


def cold_data_fixture(case):
    old=case.material_subject()
    packet=review.model_packet(case.root,old)
    parent=old['original_operation'];old_subject=review.read_subject(case.root,parent['operation_id'])
    leaf_id=codec.canonical_digest(old_subject);old_id=codec.canonical_digest(old)
    private=deepcopy(old);private['schema_version']=materials.SUBJECT;private['private_files']={}
    root_id=codec.canonical_digest(private)
    source=(Path(__file__).with_name('fixtures')/'qualified_v2_public_source.txt').read_bytes().decode('utf-8')
    native=deepcopy(old_subject['native_content']);targets=deepcopy(old_subject['preview']['targets'])
    pub={'schema_version':public.PUBLIC,'operation_id':parent['operation_id'],
        'private_subject_digest':leaf_id,'policy_identity':old_subject['policy_identity'],
        'source':{'path':public.SOURCE,'raw_digest':codec.raw_digest(source.encode()),'text':source},
        'native_content':native,'identity_alignment':deepcopy(old_subject['request']['material']['identity_alignment']),
        'allocations':deepcopy(old_subject['preview']['allocations']),
        'target_before_files':deepcopy(old_subject['target_before_files']),'targets':targets,
        'origin_binding':{'profile':'r22-m4-nx-original.v1','capture_digest':'sha256:'+'1'*64,
            'prepared_identity':{'input_identity':'cold-data-only','canonical_digest':'sha256:'+'2'*64}},
        'target_binding':{'identity':{'path':'cold-data-only','device':1,'inode':1},
            'source_set_digest':'sha256:'+'3'*64,'protection_digest':'sha256:'+'4'*64,
            'task_count':0,'catalog_before':None},
        'disclosure':{'complete_source':codec.raw_digest(source.encode()),
            'complete_candidate':codec.canonical_digest(native),'complete_targets':codec.canonical_digest(targets),
            'opaque_proof_is_machine_verified_not_model_evidence':True}}
    pub_id=codec.canonical_digest(pub);auth='sha256:'+'5'*64
    opview={'schema_version':public.OPERATION_VIEW,'claim':materials.CLAIM,'operation_id':parent['operation_id'],
        'operation_raw_digest':codec.raw_digest((case.root/__import__('_planning_apply_journal')._operation_ref(parent['operation_id'])).read_bytes()),
        'frozen_digest':parent['frozen_digest'],'request_raw_digest':parent['request_raw_digest'],
        'private_subject_digest':leaf_id,'public_subject_digest':pub_id,
        **{k:deepcopy(pub[k]) for k in ('identity_alignment','allocations','target_before_files','targets')}}
    original_root=next(f for f in packet['materials']['frames'] if f['subject_digest']==old_id)
    fields={k:deepcopy(v) for k,v in original_root['semantic_fields'].items()
            if k not in ('native_threads','native_turns')}
    fields['schema_version']=materials.SUBJECT;fields['original_operation']=opview
    root={'schema_version':materials.FRAME,'subject_digest':root_id,'operation_id':private['operation_id'],
        'subject_schema':materials.SUBJECT,'semantic_fields':fields,'operation_view':None,
        'public_subject_digest':codec.canonical_digest(fields),'historical_auth_digest':None,
        'previous_subject':leaf_id,'source_subjects':[],'files':[]}
    leaf={'schema_version':materials.FRAME,'subject_digest':leaf_id,'operation_id':parent['operation_id'],
        'subject_schema':materials.ADOPTION_SUBJECT,'semantic_fields':pub,'operation_view':opview,
        'public_subject_digest':pub_id,'historical_auth_digest':auth,'previous_subject':None,'source_subjects':[],'files':[]}
    docs={n['raw_digest']:deepcopy(n) for n in packet['materials']['documents']}
    operation_path=__import__('_planning_apply_journal')._operation_ref(parent['operation_id'])
    for old_row in original_root['files']:
        row={k:deepcopy(old_row[k]) for k in ('subject_digest','path','raw_digest','raw_bytes','roles','owner_uses','document_ref')}
        row['subject_digest']=root_id;row['public_mapping']=None
        for use in row['owner_uses']:
            if use['subject_digest']==old_id:use['subject_digest']=root_id
        if row['path']==operation_path:
            data=review.raw(opview);digest=codec.raw_digest(data)
            docs.pop(row['document_ref']);docs[digest]={'raw_digest':digest,'raw_bytes':len(data),'text':data.decode()}
            row['document_ref']=digest
            row['public_mapping']={'kind':'qualified_operation','historical_subject_digest':leaf_id,
                'historical_auth_digest':auth,'carrier_raw_digest':row['raw_digest'],'public_document_digest':digest}
        root['files'].append(row)
    ms={'schema_version':materials.MATERIALS,'full_subject_digest':root_id,
        'frames':sorted([root,leaf],key=lambda f:f['subject_digest']),
        'documents':[docs[k] for k in sorted(docs)]}
    rs={'schema_version':materials.ROLES,'full_subject_digest':root_id,
        'files':sorted(deepcopy(root['files']),key=lambda row:(row['subject_digest'],row['path']))}
    p={'schema_version':materials.PRESENTATION,'claim':materials.CLAIM,'full_subject_digest':root_id,
        'policy_identity':private['policy_identity'],'required_checks':review.obligations(private),
        'materials_digest':codec.canonical_digest(ms),'roles_digest':codec.canonical_digest(rs),
        'historical_auth_digest':'sha256:'+'6'*64}
    return private,{'schema_version':materials.PACKET,'presentation':p,'roles':rs,'materials':ms}


class QualifiedPublicPrivateColdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case=CompensationTests(methodName='runTest');cls.case.setUp()
        try:cls.subject,cls.packet=cold_data_fixture(cls.case)
        except BaseException:cls.case.tearDown();raise
    @classmethod
    def tearDownClass(cls):cls.case.tearDown()
    def data(self):return deepcopy(self.packet)
    def wire(self,packet=None):
        packet=self.data() if packet is None else packet
        return materials.DELIVERY+' '+materials.INSTRUCTION+' '+compact.instruction(compact.RESIDUAL_SCHEMA)+'\n'+compact.dumps(packet,schema=compact.RESIDUAL_SCHEMA)

    def test_complete_new_cold_packet_is_exact_data_and_not_native_authority(self):
        p=self.data();self.assertEqual(p,materials.read_prompt(self.wire(p)))
        with self.assertRaises(codec.CodecError):materials.render(p)
        old=qualified.history(self.case.root,self.subject['original_operation'])
        self.assertIs(type(old),qualified.LegacyHistory)
        with self.assertRaises(ValueError):public.frame(self.case.root,self.subject['original_operation'],old)

    def test_caller_dictionary_cannot_mint_history_or_saved_scope(self):
        with self.assertRaises(ValueError):history_host.AuthenticatedHistory(None,{'approved':True})
        with self.assertRaises(codec.CodecError):qualified._SavedInputs(None,None,None,None,None,None,None,None)

    def test_mixed_legacy_marker_claim_decoder_or_body_reject(self):
        good=self.wire();header,body=good.split('\n',1)
        wrong_claim=self.data();wrong_claim['presentation']['claim']=legacy.CLAIM
        for changed in (good.replace(materials.DELIVERY,legacy.MULTIVIEW_DELIVERY,1),
            self.wire(wrong_claim),
            header.replace(compact.RESIDUAL_SCHEMA,compact.ATOM_SCHEMA,1)+'\n'+body,
            header+'\n'+compact.dumps({'schema_version':legacy.PACKET},schema=compact.ATOM_SCHEMA),
            good+' ',good[:-1]):
            with self.subTest(changed=changed[:60]),self.assertRaises(codec.CodecError):materials.read_prompt(changed)

    def test_source_and_target_meaning_cannot_be_omitted_even_with_outer_rehash(self):
        for kind in ('source','candidate','target'):
            p=self.data();leaf=next(f for f in p['materials']['frames'] if f['subject_schema']==materials.ADOPTION_SUBJECT)
            if kind=='source':leaf['semantic_fields']['source']['text']='summary'
            elif kind=='candidate':leaf['semantic_fields']['native_content']={}
            else:leaf['semantic_fields']['targets']=[]
            leaf['public_subject_digest']=codec.canonical_digest(leaf['semantic_fields'])
            leaf['operation_view']['public_subject_digest']=leaf['public_subject_digest']
            with self.subTest(kind=kind),self.assertRaises(codec.CodecError):materials.validate(refresh(p))

    def test_current_task_b_scope_and_effect_literals_are_exact(self):
        p=self.data();root=next(f for f in p['materials']['frames'] if f['subject_schema']==materials.SUBJECT)
        original=next(f for f in review.model_packet(self.case.root,review.read_subject(self.case.root,'COMP-one'))['materials']['frames']
                      if f['subject_schema']==legacy.COMP_SUBJECT)
        for k in ('original_effects','preview','task_definitions','request'):
            self.assertEqual(original['semantic_fields'][k],root['semantic_fields'][k])
        self.assertNotIn('native_threads',root['semantic_fields'])
        self.assertNotIn('native_turns',root['semantic_fields'])
        docs={n['raw_digest']:n for n in p['materials']['documents']}
        for row in root['files']:
            if row['document_ref'] is not None and row['public_mapping'] is None:
                self.assertEqual((self.case.root/row['path']).read_bytes(),docs[row['document_ref']]['text'].encode())

    def test_unknown_missing_roles_frames_sources_and_cycles_reject(self):
        for kind in ('role','document','frame','cycle','extra'):
            p=self.data();root=next(f for f in p['materials']['frames'] if f['subject_schema']==materials.SUBJECT)
            if kind=='role':root['files'][0]['roles']=['host:approved']
            elif kind=='document':p['materials']['documents'].pop()
            elif kind=='frame':p['materials']['frames'].remove(root)
            elif kind=='cycle':root['previous_subject']=root['subject_digest']
            else:root['semantic_fields']['private_prepared_blob']={'opaque':'not model evidence'}
            p['roles']['files']=sorted([deepcopy(r) for f in p['materials']['frames'] for r in f['files']],key=lambda r:(r['subject_digest'],r['path']))
            with self.subTest(kind=kind),self.assertRaises(codec.CodecError):materials.validate(refresh(p))

    def test_private_binding_blob_and_bool_count_are_not_public_fields(self):
        for kind in ('private','boolean','unknown_profile'):
            p=self.data();leaf=next(f for f in p['materials']['frames'] if f['subject_schema']==materials.ADOPTION_SUBJECT)
            if kind=='private':leaf['semantic_fields']['origin_binding']['prepared']={'private':'blob'}
            elif kind=='boolean':leaf['semantic_fields']['target_binding']['task_count']=False
            else:leaf['semantic_fields']['origin_binding']['profile']='unknown-profile.v1'
            leaf['public_subject_digest']=codec.canonical_digest(leaf['semantic_fields'])
            leaf['operation_view']['public_subject_digest']=leaf['public_subject_digest']
            with self.subTest(kind=kind),self.assertRaises(codec.CodecError):materials.validate(refresh(p))

    def test_original_work_limit_is_not_reset_for_cold_reader(self):
        work=compact._EncodingWork();work.spend(work.remaining-1)
        with self.assertRaises(codec.CodecError):materials.read_prompt(self.wire(),work=work)
        self.assertLessEqual(work.remaining,1)

    def test_public_cli_exposes_exact_new_family_without_default_switch(self):
        parser=cli.build_parser();args=parser.parse_args(['--stage','review-prepare','--operation-id','Q',
            '--request','request.json','--compensation-review-delivery',materials.DELIVERY])
        self.assertEqual(materials.DELIVERY,args.compensation_review_delivery)
        args=parser.parse_args(['--stage','review-prepare','--operation-id','Q','--request','request.json'])
        self.assertIsNone(args.compensation_review_delivery)

    def test_public_api_passes_selector_and_legacy_family_rejects_it_without_writes(self):
        ref=self.case.fx.request_ref(self.case.comp_request)
        with patch.object(adoption,'_review_preview',return_value={'probe':True}) as probe:
            adoption.prepare_review(self.case.root,operation_id='COMP-one',request_ref=ref,compensation_delivery=materials.DELIVERY)
        self.assertEqual(materials.DELIVERY,probe.call_args.kwargs['compensation_delivery'])
        home=self.case.root/review.location('COMP-one');before={p.relative_to(home).as_posix():p.read_bytes() for p in home.rglob('*') if p.is_file()}
        with self.assertRaises(codec.CodecError):
            adoption.prepare_review(self.case.root,operation_id='COMP-one',request_ref=ref,compensation_delivery=materials.DELIVERY)
        self.assertEqual(before,{p.relative_to(home).as_posix():p.read_bytes() for p in home.rglob('*') if p.is_file()})

    def protocol_data(self, *, thread='qualified-synthetic-data-thread'):
        packet=self.data();subject=deepcopy(self.subject)
        work=compact._EncodingWork()
        bindings=qualified._bindings_from_packet(subject,packet,work=work)
        schema=qualified.schema_from_bindings(subject,bindings)
        prompt=self.wire(packet);request=review._runner_frame(prompt,schema)
        verdict={**bindings,'verdict':'approved','findings':[],
            'checks':[{'id':key,'verdict':'approved','rationale':'Synthetic protocol DATA only: '+key}
                for key in review.obligations(subject)]}
        output=json.dumps(verdict,separators=(',',':'))
        # Match the real owner's canonical checked workspace, including Windows path spelling.
        workspace=review.path(self.case.root,review.location(subject['operation_id'])+'/w')
        rows=protocol(workspace,prompt=request,output=output,schema=schema,provider='openai')
        def rename(value):
            if type(value) is dict:return {k:rename(v) for k,v in value.items()}
            if type(value) is list:return [rename(v) for v in value]
            return thread if value=='fresh-thread' else value
        for row in rows:
            m=row['message']
            if row['direction']=='client' and m.get('method')=='thread/start':
                m['params']['config']['model_reasoning_effort']='high'
            if m.get('result',{}).get('thread'):m['result']['reasoningEffort']='high'
            row['message']=rename(m)
        text,proof=transport.replay(encoded(rows))
        receipt={'schema_version':'newrouge.isolated-model-runner-receipt.v1',
            'model':proof['model'],'model_provider':proof['model_provider'],'model_identity':'openai/'+proof['model'],
            'model_identity_source':transport.SOURCE,'model_identity_scope':'runtime_configuration',
            'evidence_policy':transport.POLICY,'runtime_identity_verified':True,'model_identity_verified':False,
            'provider_identity_verified':False,'provider_reported_model':None,'provider_dispatch_count':'unknown',
            'model_identity_evidence':[proof],'model_tools':[],'request_count_observable':True,
            'model_request_count':1,'runner_invocations':1,'workspace':workspace.as_posix(),'output_chars':len(text)}
        stdout=json.dumps(receipt)+'\n'
        execution={'command':review.runner_command(self.case.root,subject['operation_id']),
            'status':'completed','returncode':0,'runner_dispatch_count':1,'active_elapsed_seconds':1.0,
            'stdout':stdout,'stdout_base64':base64.b64encode(stdout.encode()).decode()}
        # These bytes are NOT persisted and cannot mint a real saved/native
        # history scope. The public owner always reads its actual owned files.
        buffers={'w/prompt.txt':prompt.encode(),'w/schema.json':review.raw(schema),
            'request.txt':request.encode(),'w/output.json':text.encode(),'execution.json':review.raw(execution)}
        return subject,buffers,schema

    def test_new_claim_schema_request_output_and_runtime_replay_on_offline_data(self):
        subject,buffers,schema=self.protocol_data()
        result=qualified._protocol(self.case.root,subject,buffers,schema)
        self.assertEqual('high',result['runtime_configuration']['reasoning_effort'])
        self.assertEqual('unknown',result['physical_requests'])
        # The synthetic DATA result does not authorize a caller-supplied scope.
        with self.assertRaises(codec.CodecError):
            qualified._SavedInputs(None,self.case.root,subject,buffers,None,[],result,compact._EncodingWork())

    def test_new_protocol_wrong_request_schema_output_and_same_thread_reject(self):
        expected={
            'request':'exact full saved wrapper/schema/request',
            'schema':'exact original strict schema bytes',
            'output':'exact host protocol, frozen request, schema, output and runtime configuration',
            'same_thread':'official independent qualified high/no-tools review',
            'workspace':'actual identity evidence, exact workspace and output length'}
        for kind in ('request','schema','output','same_thread','workspace'):
            subject,buffers,schema=self.protocol_data()
            if kind=='request':buffers['request.txt']+=b' '
            elif kind=='schema':buffers['w/schema.json']=review.raw(review._legacy_verdict_schema(subject))
            elif kind=='output':buffers['w/output.json']+=b' '
            elif kind=='same_thread':subject['native_threads'].append('qualified-synthetic-data-thread')
            else:
                # Coherently edit only the captured receipt workspace. Complete
                # original protocol replay still runs and must reach its exact
                # workspace check; stdout/base64 disagreement is not this case.
                execution=codec.strict_json_loads(buffers['execution.json'])
                receipt=json.loads(execution['stdout'])
                receipt['workspace']+='/wrong-workspace'
                stdout=json.dumps(receipt)+'\n'
                execution['stdout']=stdout
                execution['stdout_base64']=base64.b64encode(stdout.encode()).decode()
                buffers['execution.json']=review.raw(execution)
            with self.subTest(kind=kind),self.assertRaises(codec.CodecError) as caught:
                qualified._protocol(self.case.root,subject,buffers,schema)
            self.assertEqual(expected[kind],caught.exception.diagnostic.expected)

    def test_factored_private_reference_resolves_only_real_owner_bytes_and_roles(self):
        handle=qualified.history(self.case.root,self.subject['original_operation'])
        name,data=next(iter(handle.files().items()))
        meta=qualified._private_meta(handle,'review_support',handle.roles()[name],data)
        restored,checked=qualified.resolve_private_file(self.case.root,name,meta)
        self.assertEqual(data,restored);self.assertIs(type(checked),qualified.LegacyHistory)
        for kind in ('role','digest','native_kind','unowned_path'):
            changed=deepcopy(meta);path=name
            if kind=='role':changed['role']='host:approved-by-caller'
            elif kind=='digest':changed['raw_digest']='sha256:'+'0'*64
            elif kind=='native_kind':changed['kind']='qualified_capsule'
            else:path='not-owned/source.json'
            with self.subTest(kind=kind),self.assertRaises(codec.CodecError):
                qualified.resolve_private_file(self.case.root,path,changed)

    def test_factored_logical_capture_restores_every_original_byte(self):
        handle=qualified.history(self.case.root,self.subject['original_operation'])
        files=handle.files()
        private={name:qualified._private_meta(handle,'review_support',handle.roles()[name],data)
                 for name,data in files.items()}
        value={'schema_version':qualified.SUBJECT,'current_files':{},'private_files':private}
        self.assertEqual(files,qualified.restore_captured_files(self.case.root,value))
        self.assertNotIn('raw_base64',next(iter(private.values())))
