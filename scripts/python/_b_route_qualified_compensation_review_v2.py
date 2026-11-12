"""Versioned qualified compensation owner. Old proofs remain old verifiers.

No native/model production here. Existing actual v2 is authenticated by its
explicit historical owner, and new qualified ancestors replay their new exact
saved buffers/runtime under their own same installed policy. No ticket upgrade.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
import base64
import json
import _b_route_codec as codec
import _planning_apply_journal as journal
import _b_route_adoption_review as review
import _b_route_qualified_compensation_materials_v2 as materials
import _b_route_qualified_history_router as original_host
import _b_route_compensation_review_profiles as profiles
import _b_route_published_history as published
import _b_route_qualified_compensation_review as previous_owner

SUBJECT=materials.SUBJECT
PROOF=materials.PREFIX+'proof.v2'
VERDICT=materials.PREFIX+'verdict.v2'
MODE='qualified_public_private.v2'
DELIVERY=materials.DELIVERY
CLAIM=materials.CLAIM
OUTPUT_RESERVE_TOKENS=2000
_ACTION=ContextVar('qualified_review_action',default=None)
_MINT=object()


def need(ok, expected, actual='qualified review mismatch'):
    review.require(ok,expected,actual)


def raw(value):return review.raw(value)


def same(a,b):return materials.ordered(a)==materials.ordered(b)


@contextmanager
def action():
    graph=_ACTION.get();token=None
    if graph is None:
        graph={'active':set(),'histories':{}}
        token=_ACTION.set(graph)
    try:yield graph
    finally:
        if token is not None:_ACTION.reset(token)


def selected(original):
    version=original.get('schema_version')
    req=original.get('frozen',{}).get('request',{})
    proof=req.get('host_review_ref',{}).get('schema_version')
    if version=='newrouge.b-route-adoption-operation.v2':
        need(req.get('schema_version')=='newrouge.b-route-adoption-request.v2'
             and proof in ('newrouge.b-route-adoption-review-proof.v2','newrouge.b-route-adoption-review-proof.v3'),'exact qualified original adoption family')
        original_host.family(original)
        return True
    if version=='newrouge.b-route-compensation-operation.v2':
        return proof in (PROOF,profiles.PUBLISHED.name('proof'))
    return False


def support_names():
    return ['subject.json','w/prompt.txt','w/schema.json','request.txt','execution.json','w/output.json',
            'materials.json','roles.json','presentation.json','historical-auth.json']


def labels():
    return {'subject.json':'host:subject','w/prompt.txt':'host:prompt','w/schema.json':'host:schema',
        'request.txt':'host:request','execution.json':'host:execution','w/output.json':'host:output',
        'materials.json':'host:materials','roles.json':'host:roles','presentation.json':'host:presentation',
        'historical-auth.json':'host:historical_auth','review.json':'host:proof'}


class _SavedInputs:
    """Only actual same-read proof/support/schema/runtime may mint this scope.

    This grants access to ORIGINAL captured business bytes for reconstruction;
    it is not a historical/native approval and cannot be supplied as a dictionary.
    Final proof validation still rederives all real historical auth and materials.
    """
    __slots__=('root','subject','buffers','proof','refs','evidence','work')
    def __init__(self,key,root,subject,buffers,proof,refs,evidence,work):
        need(key is _MINT,'actual saved qualified input verifier')
        self.root,self.subject,self.buffers,self.proof,self.refs,self.evidence,self.work=root,subject,buffers,proof,refs,evidence,work


class SavedHistory:
    __slots__=('_root','_operation','_operation_raw','_inputs','_derived','_binding')
    def __init__(self,key,root,operation,operation_raw,inputs,derived):
        need(key is _MINT,'actual completely verified saved qualified owner only')
        self._root,self._operation,self._operation_raw=root,operation,operation_raw
        self._inputs,self._derived=inputs,derived
        self._binding={'schema_version':profiles.subject(inputs.subject).name('saved-history-auth'),
            'claim':'exact_new_qualified_saved_proof_and_private_captures',
            'operation_id':operation['operation_id'],'operation_raw_digest':codec.raw_digest(operation_raw),
            'frozen_digest':operation['frozen_digest'],'subject_digest':codec.canonical_digest(inputs.subject),
            'policy_identity':inputs.subject['policy_identity'],'proof_raw_digest':
                operation['frozen']['request']['host_review_ref']['raw_digest'],
            'materials_digest':inputs.proof['materials_digest'],'roles_digest':inputs.proof['roles_digest'],
            'presentation_digest':inputs.proof['presentation_digest'],
            'historical_auth_digest':inputs.proof['historical_auth_digest'],
            'request_raw_digest':inputs.proof['request_raw_digest'],'original_runtime':inputs.evidence,
            'files':deepcopy(inputs.refs)}
    def identity(self):return self._binding['subject_digest']
    def binding(self):return deepcopy(self._binding)
    def subject(self):return deepcopy(self._inputs.subject)
    def saved_inputs(self):return self._inputs
    def operation(self):return deepcopy(self._operation)
    def operation_raw(self):return self._operation_raw
    def files(self):
        home=review.location(self._operation['operation_id'])
        values={home+'/'+k:v for k,v in self._inputs.buffers.items()}
        values[home+'/review.json']=raw(self._inputs.proof)
        return values
    def roles(self):
        home=review.location(self._operation['operation_id'])
        return {home+'/'+k:v for k,v in labels().items()}
    def operation_view(self):
        s=self._inputs.subject
        # Complete new owner's public business semantics; exact full old raw
        # operation/frozen/request remain separately authenticated host evidence.
        return {'schema_version':profiles.subject(s).name('public-operation'),'claim':profiles.subject(s).claim,
            'operation_id':s['operation_id'],'operation_schema':self._operation['schema_version'],
            'operation_raw_digest':codec.raw_digest(self._operation_raw),'frozen_digest':self._operation['frozen_digest'],
            'request_raw_digest':self._operation['request_raw_digest'],'subject_digest':codec.canonical_digest(s),
            'request':deepcopy(s['request']),'allocations':deepcopy(s['preview']['allocations']),
            'scope_ids':deepcopy(s['preview']['scope_ids']),'targets':deepcopy(s['preview']['targets'])}
    def recheck(self):
        need(review.policy_identity()==self._inputs.subject['policy_identity'],'unchanged qualified saved owner policy')
        for ref in self._inputs.refs:
            need(codec.raw_digest(review.path(self._root,ref['path']).read_bytes())==ref['raw_digest'],
                 'unchanged exact saved qualified support',ref['path'])
        need(review.path(self._root,journal._operation_ref(self._operation['operation_id'])).read_bytes()==self._operation_raw,
             'same actual original operation raw')
        self._derived.recheck()
    def retained_graphs(self):
        return [self._inputs.subject,self._inputs.proof,self._derived.packet,self._binding]
    def retained_buffers(self):
        return list(self._inputs.buffers.values())+[self._operation_raw,self._derived.freeze_auth()]


def captured_source(root,subject,name,context=None):
    if type(context) in (previous_owner._SavedInputs,previous_owner.LegacyHistory):
        return previous_owner.captured_source(root,subject,name,context)
    encoded=subject['current_files'].get(name)
    if encoded is None and subject.get('schema_version') in (SUBJECT,profiles.PUBLISHED.name('subject')):
        need(name in subject['private_files'],'complete actual private carrier reference',name)
        data=resolve_private_file(root,name,subject['private_files'][name],context=context)[0]
    else:
        need(type(encoded) is str,'complete private captured semantic source',name)
        data=base64.b64decode(encoded,validate=True)
    if context is None:
        actual=review.path(root,name).read_bytes()
        need(actual==data,'actual current source byte capture',name)
    else:
        need((type(context) is _SavedInputs and Path(root).absolute()==context.root
              and same(context.subject,subject))
             or (type(context) is LegacyHistory and Path(root).absolute()==context._root
                 and same(context._subject,subject)), 'actual same-read saved original owner frame scope')
        # The complete private subject and this exact captured raw map are bound
        # by the actual saved original schema/request/output/runtime. Do not
        # re-admit old current Task/catalog/source bytes against today's target.
    return data


def history(root,original, *, profile=profiles.ORIGINAL, context=None):
    root=Path(root).absolute()
    actual=journal.read_operation(root,operation_id=original['operation_id'])
    need(same(actual,original),'actual complete mixed-journal original operation')
    key=(str(root),original['operation_id'],codec.canonical_digest(original),profile.name('subject'),
         codec.canonical_digest(context.subject) if context is not None else None)
    with action() as graph:
        need(key not in graph['active'],'acyclic genuine original review history')
        if key in graph['histories']:
            value=graph['histories'][key];value.recheck();return value
        graph['active'].add(key)
        try:
            if original['schema_version']=='newrouge.b-route-adoption-operation.v2':
                need(selected(original),'exact qualified original adoption family')
                value=(published.verify(root,original['operation_id'],context=context) if profile is profiles.PUBLISHED
                       else original_host.authenticate(root,original['operation_id']))
                value.checked_original(root,original)
            elif selected(original):
                inputs,derived=_verify_saved(root,original['frozen']['request'])
                expected=deepcopy(inputs.subject['preview']);expected['request']=original['frozen']['request']
                expected['authority_refs']=sorted([*expected['authority_refs'],*inputs.refs],key=lambda r:r['path'])
                need(codec.canonical_digest(expected)==original['frozen_digest'],'exact new qualified original frozen/effects')
                value=SavedHistory(_MINT,root,deepcopy(original),
                    review.path(root,journal._operation_ref(original['operation_id'])).read_bytes(),inputs,derived)
            elif previous_owner.selected(original):
                value=previous_owner.history(root,original)
            else:
                value=_legacy_history(root,original)
            graph['histories'][key]=value
            return value
        finally:graph['active'].remove(key)


def original_review(snapshot,original, *, profile=profiles.ORIGINAL):
    handle=history(snapshot.root,original,profile=profile)
    # These are actual verified raw supports, not caller roles or dictionaries.
    for name,data in handle.files().items():need(snapshot.read(name)==data,'original exact historical support',name)
    need(snapshot.read(journal._operation_ref(original['operation_id']))==handle.operation_raw(),
         'same observed original operation raw')
    bound=getattr(snapshot,'_qualified_history_handles',None)
    need(type(bound) is list,'current owner Snapshot historical boundary')
    if all(h.identity()!=handle.identity() for h in bound):bound.append(handle)
    snapshot.qualified_family=True
    subject=handle.subject();threads=set(subject['native_threads'])
    binding=handle.binding();evidence=binding.get('original_runtime',{})
    if type(evidence.get('thread_id')) is str:threads.add(evidence['thread_id'])
    return sorted(threads),list(subject['native_turns'])


def read_subject(root,operation_id):
    value=codec.strict_json_loads(review.path(root,review.location(operation_id)+'/subject.json').read_bytes())
    review.shape(value,('schema_version','producer','operation_id','request','preview','policy_identity',
        'original_operation','original_effects','current_files','private_files','task_definitions','native_threads','native_turns'),
        'complete explicit factored qualified private subject')
    need(value['schema_version'] in (SUBJECT,profiles.PUBLISHED.name('subject')) and value['producer']=='compensation' and value['operation_id']==operation_id
         and value['policy_identity']==review.policy_identity(),'same installed qualified owner policy')
    journal.validate_operation_request(value['request']);journal._operation_schema(value['preview'],'Frozen')
    need(value['request']['operation_id']==operation_id and same(value['preview']['request'],value['request'])
         and (selected(value['original_operation']) or previous_owner.selected(value['original_operation']) or qualified_capture_hint(value)),
         'complete actual qualified subject/version binding')
    return value


def model_packet(root,subject, *, context=None):
    need(root is not None,'actual qualified evidence repository is mandatory')
    with action():
        derived=materials.derive(root,subject,checks=review.obligations(subject),context=context,
            work=context.work if context is not None else None)
        derived.freeze_auth()
        return derived


def bindings(subject,derived):
    need(type(derived) is materials.Derived and same(derived.subject,subject),'same actual qualified derivation')
    p=derived.packet['presentation']
    need(p['full_subject_digest']==codec.canonical_digest(subject)
         and p['policy_identity']==subject['policy_identity']
         and p['required_checks']==review.obligations(subject),
         'same complete private subject/policy/original denominator')
    return {'schema_version':profiles.subject(subject).name('verdict'),'subject_digest':codec.canonical_digest(subject),'claim':profiles.subject(subject).claim,
        'materials_digest':p['materials_digest'],'roles_digest':p['roles_digest'],
        'presentation_digest':codec.canonical_digest(p),'historical_auth_digest':p['historical_auth_digest']}


def _bindings_from_packet(subject,packet, *, work):
    materials.validate(packet,work=work)
    p=packet['presentation']
    need(p['full_subject_digest']==codec.canonical_digest(subject) and p['policy_identity']==subject['policy_identity']
         and p['required_checks']==review.obligations(subject),'exact private subject/policy/denominator')
    return {'schema_version':profiles.subject(subject).name('verdict'),'subject_digest':codec.canonical_digest(subject),'claim':profiles.subject(subject).claim,
        'materials_digest':p['materials_digest'],'roles_digest':p['roles_digest'],
        'presentation_digest':codec.canonical_digest(p),'historical_auth_digest':p['historical_auth_digest']}


def schema_from_bindings(subject,b):
    schema=review._legacy_verdict_schema(subject)
    for name,value in b.items():
        schema['properties'][name]={'type':'string','const':value}
        if name not in schema['required']:schema['required'].append(name)
    return schema


def verdict_schema(subject, *, root=None, packet=None):
    d=model_packet(root,subject) if packet is None else packet
    return schema_from_bindings(subject,bindings(subject,d))


def check_verdict(subject,value, *, schema):
    import jsonschema
    need(not list(jsonschema.Draft202012Validator(schema).iter_errors(value)),'strict new qualified verdict schema')
    legacy={k:deepcopy(value[k]) for k in review._legacy_verdict_schema(subject)['required']}
    legacy['schema_version']=review.VERDICT
    review._legacy_check_verdict(subject,legacy)


def prompt(subject, *, root=None, packet=None, delivery=None):
    need(delivery in (None,profiles.subject(subject).name('delivery')),'exact qualified delivery family; no legacy fallback')
    d=model_packet(root,subject) if packet is None else packet
    return materials.render(d)


def artifacts(root,subject, *, packet=None,delivery=None):
    need(delivery in (None,profiles.subject(subject).name('delivery')),'qualified delivery only')
    d=model_packet(root,subject) if packet is None else packet
    schema=verdict_schema(subject,root=root,packet=d)
    text=prompt(subject,root=root,packet=d,delivery=profiles.subject(subject).name('delivery'))
    request=review._runner_frame(text,schema)
    from _capability_input_integrity import CODEX_MAX_TURN_BYTES,configured_input_limit,measure_request
    # This is headroom within the unchanged total input policy, not a provider
    # output-max assertion and not permission for extra requests/output clipping.
    try:
        measure_request(request,max_bytes=CODEX_MAX_TURN_BYTES,
            max_input_tokens=min(70000,configured_input_limit()),reserved_tokens=OUTPUT_RESERVE_TOKENS)
    except ValueError as error:
        review.require(False,'complete qualified materials within byte/token budget',
            str(error),codec.ReasonCode.INVALID_ARGUMENT)
    auth_bytes=_auth_raw(d,request,schema)
    values={'subject.json':raw(subject),'w/prompt.txt':text.encode('utf-8'),'w/schema.json':raw(schema),
        'request.txt':request.encode('utf-8'),'materials.json':raw(d.packet['materials']),
        'roles.json':raw(d.packet['roles']),'presentation.json':raw(d.packet['presentation']),
        'historical-auth.json':auth_bytes}
    return values


def _protocol(root,subject,buffers,schema):
    from _planning_execution_binding import receipt_from,validate_execution
    need(buffers['w/schema.json']==raw(schema),'exact original strict schema bytes')
    text=buffers['w/prompt.txt'].decode('utf-8')
    need(text.startswith(profiles.subject(subject).name('delivery')+' '),'explicit saved qualified route hint')
    request=review._runner_frame(text,schema)
    need(buffers['request.txt']==request.encode('utf-8'),'exact full saved wrapper/schema/request')
    execution=codec.strict_json_loads(buffers['execution.json'])
    need(execution.get('command')==review.runner_command(root,subject['operation_id']),'exact actual unchanged runner command')
    receipt=receipt_from(execution);output=buffers['w/output.json']
    validate_execution(review.path(root,review.location(subject['operation_id'])+'/w'),execution,receipt,'auto',output,
        prompt=request,schema=schema,require_runtime=True,expected_reasoning_effort='high')
    evidence=receipt['model_identity_evidence'][0]
    need(evidence['model_provider']=='openai' and evidence['thread_id'] not in subject['native_threads'],
         'official independent qualified high/no-tools review')
    check_verdict(subject,codec.strict_json_loads(output),schema=schema)
    return {'thread_id':evidence['thread_id'],'turn_id':evidence['turn_id'],
        'protocol_digest':evidence['protocol_sha256'],'runtime_configuration':{
        'model':evidence['model'],'provider':evidence['model_provider'],'reasoning_effort':'high'},
        'provider_actual_model':'unknown','physical_requests':'unknown'}


def _inputs(root,subject, *, proof=None):
    root=Path(root).absolute();home=review.location(subject['operation_id'])
    buffers={name:review.path(root,home+'/'+name).read_bytes() for name in support_names()}
    need(buffers['subject.json']==raw(subject),'same actual private saved subject bytes')
    packet={'schema_version':profiles.subject(subject).name('packet'),'presentation':codec.strict_json_loads(buffers['presentation.json']),
        'roles':codec.strict_json_loads(buffers['roles.json']),'materials':codec.strict_json_loads(buffers['materials.json'])}
    import _b_route_compact_literal as compact
    work=compact._work(None)
    b=_bindings_from_packet(subject,packet,work=work)
    schema=schema_from_bindings(subject,b)
    evidence=_protocol(root,subject,buffers,schema)
    refs=[{'path':home+'/'+name,'schema_version':'raw.bytes.v1','raw_digest':codec.raw_digest(buffers[name])}
        for name in support_names()]
    if proof is not None:
        need(proof['files']==refs and proof['request_raw_digest']==codec.raw_digest(buffers['request.txt'])
             and all(proof[k]==b[k] for k in ('claim','materials_digest','roles_digest','presentation_digest','historical_auth_digest'))
             and same(proof['evidence'],evidence),'complete actual new proof/support/runtime binding')
    return _SavedInputs(_MINT,root,subject,buffers,proof,refs,evidence,work)


def _complete(inputs):
    with action():
        d=model_packet(inputs.root,inputs.subject,context=inputs)
        expected=artifacts(inputs.root,inputs.subject,packet=d,delivery=profiles.subject(inputs.subject).name('delivery'))
        need(all(inputs.buffers[k]==v for k,v in expected.items()),
             'complete rederived new prompt/schema/request/materials/roles/presentation/private-auth buffers')
        d.recheck()
        return d


def produce_proof(root,operation_id):
    subject=read_subject(root,operation_id);inputs=_inputs(root,subject)
    d=_complete(inputs);b=bindings(subject,d)
    return {'schema_version':profiles.subject(subject).name('proof'),'operation_id':operation_id,'subject_digest':codec.canonical_digest(subject),
        'policy_identity':subject['policy_identity'],'mode':profiles.subject(subject).mode,'evidence':inputs.evidence,'files':inputs.refs,
        **{k:b[k] for k in ('claim','materials_digest','roles_digest','presentation_digest','historical_auth_digest')},
        'request_raw_digest':codec.raw_digest(inputs.buffers['request.txt']),'delivery':profiles.subject(subject).name('delivery')}


def _verify_saved(root,request):
    ref=request.get('host_review_ref');home=review.location(request['operation_id'])
    review.shape(ref,('path','schema_version','raw_digest'),'qualified proof reference')
    need(ref['path']==home+'/review.json' and ref['schema_version'] in (PROOF,profiles.PUBLISHED.name('proof')),'exact owned new proof family/path')
    data=review.path(root,ref['path']).read_bytes();need(codec.raw_digest(data)==ref['raw_digest'],'exact actual new proof raw')
    proof=codec.strict_json_loads(data)
    need(data==raw(proof),'new owner canonical actual proof raw bytes')
    review.shape(proof,('schema_version','operation_id','subject_digest','policy_identity','mode','evidence','files',
        'claim','materials_digest','roles_digest','presentation_digest','historical_auth_digest','request_raw_digest','delivery'),
        'closed qualified proof')
    subject=read_subject(root,request['operation_id'])
    need(ref['schema_version']==proof['schema_version']==profiles.subject(subject).name('proof') and proof['operation_id']==request['operation_id']
         and proof['mode']==profiles.subject(subject).mode and proof['delivery']==profiles.subject(subject).name('delivery') and proof['claim']==profiles.subject(subject).claim
         and proof['subject_digest']==codec.canonical_digest(subject)
         and proof['policy_identity']==subject['policy_identity']
         and same(subject['request'],review.request_body(request)),'complete new request/subject/policy/claim binding')
    inputs=_inputs(root,subject,proof=proof);d=_complete(inputs)
    # Include the actual proof raw identity in the final authenticated closure.
    inputs.refs=[ref,*inputs.refs]
    return inputs,d


def verify_saved(root,request):
    with action():
        inputs,_=_verify_saved(root,request)
        return deepcopy(inputs.subject),deepcopy(inputs.refs)


def seal(root,operation_id,value):
    need(value['schema_version'] in (PROOF,profiles.PUBLISHED.name('proof')) and value['operation_id']==operation_id
         and value['policy_identity']==review.policy_identity(),'same actual qualified proof/current policy')
    _proof_shape(value)
    # Writer receives only produce_proof's fully checked result, as the original
    # owner does; no model/native/codec replay is moved into the short writer.
    home=review.location(operation_id);review.write_once(root,home+'/review.json',raw(value))
    return {'path':home+'/review.json','schema_version':value['schema_version'],'raw_digest':codec.raw_digest(raw(value))}


def bind_action(snapshot):
    graph=_ACTION.get()
    if graph is None:return
    root=str(Path(snapshot.root).absolute())
    values=snapshot._qualified_history_handles
    profile=getattr(snapshot,'review_profile',profiles.ORIGINAL)
    for key,handle in graph['histories'].items():
        if key[0]!=root or key[3]!=profile.name('subject'):continue
        need(type(handle) in (*original_host.AUTHENTICATED_TYPES,published.PublishedHistoryVerification,SavedHistory,LegacyHistory,previous_owner.SavedHistory,previous_owner.LegacyHistory),
             'genuine actual historical owner handles only')
        if all(v.identity()!=handle.identity() for v in values):values.append(handle)


def verify_semantic(root,subject, *, packet=None,buffers=None):
    with action():
        inputs=_inputs(root,subject)
        if buffers is not None:
            need(set(buffers)==set(inputs.buffers) and all(buffers[k]==v for k,v in inputs.buffers.items()),
                 'actual same-read original qualified buffers')
        derived=_complete(inputs)
        if packet is not None:
            need(type(packet) is materials.Derived and same(packet.packet,derived.packet)
                 and packet.freeze_auth()==derived.freeze_auth(),'same real rederived qualified packet/auth')
        return inputs.evidence


def _proof_shape(value):
    review.shape(value,('schema_version','operation_id','subject_digest','policy_identity','mode','evidence','files',
        'claim','materials_digest','roles_digest','presentation_digest','historical_auth_digest','request_raw_digest','delivery'),
        'closed qualified proof')
    profile=profiles.select('proof',value['schema_version'])
    need(value['mode']==profile.mode and value['claim']==profile.claim
         and value['delivery']==profile.name('delivery'),'explicit new proof/mode/claim/delivery')


def _auth_raw(derived,request,schema):
    # New private metadata is serialized under the actual original work/live
    # account. Full host subject/public support serialization otherwise retains
    # the established raw() format; no global host-RSS limit is invented here.
    import _b_route_compact_literal as compact
    import _b_route_compensation_review_materials as accounting
    data=derived.freeze_auth()
    metrics,buffers=derived.private_metrics()
    buffers.extend((2*len(request.encode('utf-8')),len(raw(schema))))
    accounting._live(derived.work,'qualified.auth.storage.reuse',metrics,buffers)
    return data


class LegacyHistory:
    __slots__=('_root','_op','_raw','_subject','_files','_roles','_refs','_binding')
    def __init__(self,key,root,op,saved,refs):
        need(key is _MINT,'actual unchanged legacy verifier result')
        self._root,self._op=root,deepcopy(op)
        self._raw=review.path(root,journal._operation_ref(op['operation_id'])).read_bytes()
        self._subject,self._files,self._roles=saved['subject'],saved['files'],saved['roles']
        self._refs=refs
        proof=codec.strict_json_loads(self._files[op['frozen']['request']['host_review_ref']['path']])
        self._binding={'schema_version':materials.PREFIX+'legacy-history-auth.v1',
            'claim':'original_legacy_ticket_replayed_unchanged_by_its_original_verifier',
            'operation_id':op['operation_id'],'subject_digest':codec.canonical_digest(self._subject),
            'policy_identity':self._subject['policy_identity'],'operation_raw_digest':codec.raw_digest(self._raw),
            'frozen_digest':op['frozen_digest'],'original_proof':deepcopy(op['frozen']['request']['host_review_ref']),
            'original_runtime':deepcopy(proof['evidence']),'files':deepcopy(refs)}
    def identity(self):return self._binding['subject_digest']
    def binding(self):return deepcopy(self._binding)
    def subject(self):return deepcopy(self._subject)
    def operation(self):return deepcopy(self._op)
    def operation_raw(self):return self._raw
    def operation_view(self):return deepcopy(self._op)
    def files(self):return dict(self._files)
    def roles(self):return dict(self._roles)
    def saved_inputs(self):return self
    def recheck(self):
        need(self._subject['policy_identity']==review.policy_identity(),'unchanged strict legacy owner policy')
        for ref in self._refs:
            need(codec.raw_digest(review.path(self._root,ref['path']).read_bytes())==ref['raw_digest'],
                 'same actual legacy saved support',ref['path'])
        need(review.path(self._root,journal._operation_ref(self._op['operation_id'])).read_bytes()==self._raw,
             'same actual legacy original operation raw')
    def retained_graphs(self):return [self._subject,self._op,self._roles,self._binding]
    def retained_buffers(self):return list(self._files.values())+[self._raw]


def _legacy_history(root,original):
    need(original['schema_version'] in ('newrouge.b-route-adoption-operation.v1',
        'newrouge.b-route-compensation-operation.v2'),'known original legacy operation family')
    ref=original['frozen']['request']['host_review_ref']
    need(ref['schema_version'] in (review.PROOF,review.COMPENSATION_PROOF),
         'legacy tickets retain original proof versions')
    saved=review.verified_historical_support(root,original)
    refs=[{'path':name,'schema_version':'raw.bytes.v1','raw_digest':codec.raw_digest(data)}
          for name,data in saved['files'].items()]
    # Preserve the actual typed proof ref; old proof raw is not a raw.bytes
    # alias for consumption, although every support byte remains exact.
    refs=[deepcopy(ref) if r['path']==ref['path'] else r for r in refs]
    return LegacyHistory(_MINT,root,original,saved,refs)


def qualified_capture_hint(subject):
    # Only a route hint. Actual owner/capsule/source mapping is always rederived
    # before any new qualified proof may be sealed or consumed.
    for name,meta in subject.get('private_files',{}).items():
        if meta.get('kind')=='qualified_capsule':return True
    for name,encoded in subject['current_files'].items():
        if name.startswith(review.BASE+'/'):continue
        try:value=codec.strict_json_loads(base64.b64decode(encoded,validate=True))
        except (ValueError,codec.CodecError):continue
        if type(value) is dict and str(value.get('schema_version','')).startswith('newrouge.b-route-qualified-origin-capsule.'):
            need(value['schema_version']=='newrouge.b-route-qualified-origin-capsule.v1','known qualified capsule version; no fallback')
            return True
    return False


def family_for_snapshot(snapshot, *, profile=profiles.ORIGINAL):
    qualified_family=getattr(snapshot,'qualified_family',False)
    threads=set(snapshot.compensation_threads);turns=set(snapshot.compensation_turns)
    for name in list(snapshot.files):
        if snapshot.files[name] is None or name.startswith(review.BASE+'/') or not name.endswith('.json'):continue
        data=snapshot.read(name)
        try:value=codec.strict_json_loads(data)
        except codec.CodecError:continue
        if type(value) is not dict or not str(value.get('schema_version','')).startswith('newrouge.b-route-qualified-origin-capsule.'):continue
        need(value['schema_version']=='newrouge.b-route-qualified-origin-capsule.v1','known qualified capsule version; no legacy downgrade')
        op=journal.read_operation(snapshot.root,operation_id=value['operation_id'])
        h=history(snapshot.root,op,profile=profile)
        need(type(h) in (*original_host.AUTHENTICATED_TYPES,published.PublishedHistoryVerification) if profile is profiles.PUBLISHED else type(h) in original_host.AUTHENTICATED_TYPES,'actual qualified capsule original owner')
        cap_ref=op['frozen']['request']['material']['handoff_ref']
        need(codec.raw_digest(data)==cap_ref['raw_digest'] and value==h._capsule,
             'exact genuine captured qualified source carrier')
        original=h.subject();threads.update(original['native_threads']);turns.update(original['native_turns'])
        evidence=h.binding()['original_runtime'];threads.add(evidence['thread_id'])
        qualified_family=True
    snapshot.compensation_threads=sorted(threads);snapshot.compensation_turns=sorted(turns)
    snapshot.qualified_family=qualified_family
    bind_action(snapshot)
    return qualified_family


def consider_legacy_authorities(snapshot,subject, *, profile=profiles.ORIGINAL):
    for row in subject.get('authority_files',[]):
        ref=row['reference']
        data=base64.b64decode(row['raw_base64'],validate=True)
        try:cap=codec.strict_json_loads(data)
        except codec.CodecError:continue
        if type(cap) is not dict or not str(cap.get('schema_version','')).startswith('newrouge.b-route-qualified-origin-capsule.'):continue
        need(cap['schema_version']=='newrouge.b-route-qualified-origin-capsule.v1','known typed authority capsule version')
        need(ref['schema_version'] in ('newrouge.b-route-qualified-origin-capsule.v1','raw.bytes.v1')
             and data==row['text'].encode('utf-8') and codec.raw_digest(data)==ref['raw_digest']
             and snapshot.read(ref['path'])==data,'actual typed qualified authority, never a caller role label')
        op=journal.read_operation(snapshot.root,operation_id=cap['operation_id'])
        handle=history(snapshot.root,op,profile=profile)
        need(type(handle) in (*original_host.AUTHENTICATED_TYPES,published.PublishedHistoryVerification)
             and ref['path']==op['frozen']['request']['material']['handoff_ref']['path']
             and ref['raw_digest']==op['frozen']['request']['material']['handoff_ref']['raw_digest']
             and cap==handle._capsule,
             'actual original qualified authority owner; no caller role')
        snapshot.qualified_family=True
    # family_for_snapshot includes every actually captured qualified carrier's
    # native/review independence IDs; no private identifiers enter model view.


def _private_meta(handle,kind,role,data, *, profile=profiles.ORIGINAL):
    return {'schema_version':profile.name('private-file'),'owner_operation_id':handle.operation()['operation_id'],
        'owner_subject_digest':handle.identity(),'owner_auth_digest':codec.canonical_digest(handle.binding()),
        'kind':kind,'role':role,'raw_digest':codec.raw_digest(data),'raw_bytes':len(data)}


def capture_files(snapshot, *, original, profile=profiles.ORIGINAL):
    """New subject only: complete inline semantics + exact private file refs.

    Old actual bytes are neither rewritten nor recursively base64 copied. This
    is not a compression witness: each referenced original is resolved through
    its real opaque owner again when consumed. Old v2 subjects remain unchanged.
    """
    history(snapshot.root,original,profile=profile)
    bind_action(snapshot)
    owners={}
    for handle in snapshot._qualified_history_handles:
        for name,data in handle.files().items():
            owners[name]=_private_meta(handle,'review_support',handle.roles()[name],data,profile=profile)
        name=journal._operation_ref(handle.operation()['operation_id'])
        owners[name]=_private_meta(handle,'original_operation','semantic:original_operation',handle.operation_raw(),profile=profile)
        if type(handle) in (*original_host.AUTHENTICATED_TYPES,published.PublishedHistoryVerification):
            ref=handle.operation()['frozen']['request']['material']['handoff_ref']
            if ref['path'] in snapshot.files:
                data=snapshot.read(ref['path'])
                need(codec.raw_digest(data)==ref['raw_digest'],'actual qualified private carrier')
                owners[ref['path']]=_private_meta(handle,'qualified_capsule','host:qualified_origin_proof',data,profile=profile)
    inline,private={},{}
    for name,digest in list(snapshot.files.items()):
        if digest is None:continue
        if name in owners:
            need(owners[name]['raw_digest']==digest,'same actually observed owner private original',name)
            private[name]=owners[name]
        else:inline[name]=base64.b64encode(snapshot.read(name)).decode('ascii')
    return inline,private


def resolve_private_file(root,name,meta, *, context=None):
    if type(meta) is dict and meta.get('schema_version')==materials.PREFIX+'private-file.v1':
        return previous_owner.resolve_private_file(root,name,meta)
    review.shape(meta,('schema_version','owner_operation_id','owner_subject_digest','owner_auth_digest',
        'kind','role','raw_digest','raw_bytes'),'closed qualified private file reference')
    profile=profiles.select('private-file',meta['schema_version'])
    need(meta['schema_version']==profile.name('private-file') and type(meta['raw_bytes']) is int
         and meta['raw_bytes']>=0,'known qualified private reference version/type')
    codec.validate_reference_path(name)
    operation=journal.read_operation(root,operation_id=meta['owner_operation_id'])
    handle=history(root,operation,profile=profile,context=context)
    need(meta['owner_subject_digest']==handle.identity()
         and meta['owner_auth_digest']==codec.canonical_digest(handle.binding()),'actual opaque original owner binding')
    if meta['kind']=='review_support':
        files=handle.files();roles=handle.roles()
        need(name in files and meta['role']==roles[name],'actual owner-declared private support role',name)
        data=files[name]
    elif meta['kind']=='original_operation':
        need(name==journal._operation_ref(operation['operation_id']) and meta['role']=='semantic:original_operation',
             'actual original operation carrier')
        data=handle.operation_raw()
    elif meta['kind']=='qualified_capsule':
        need(type(handle) in (*original_host.AUTHENTICATED_TYPES,published.PublishedHistoryVerification),'actual original qualified capsule owner')
        ref=operation['frozen']['request']['material']['handoff_ref']
        need(name==ref['path'] and meta['raw_digest']==ref['raw_digest']
             and meta['role']=='host:qualified_origin_proof','exact original private capsule carrier')
        data=review.path(root,name).read_bytes()
    else:need(False,'known actual private carrier kind')
    need(codec.raw_digest(data)==meta['raw_digest'] and len(data)==meta['raw_bytes'],
         'complete exact original private bytes, never caller dictionary proof',name)
    return data,handle


def restore_captured_files(root,subject, *, context=None):
    """Audit-only lossless logical capture reconstruction, no writes/approval."""
    need(subject['schema_version'] in (SUBJECT,profiles.PUBLISHED.name('subject')),'explicit factored qualified subject only')
    result={name:base64.b64decode(value,validate=True) for name,value in subject['current_files'].items()}
    for name,meta in subject['private_files'].items():
        need(name not in result,'disjoint inline/private current capture')
        result[name]=resolve_private_file(root,name,meta,context=context)[0]
    return result
