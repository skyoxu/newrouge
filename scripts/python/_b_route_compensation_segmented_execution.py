"""Finite compensation review consumer; CLI alone owns order and continuation.

Every node is replayed from exact inputs, runtime protocol and the original
budget owner. This is distinct from both the old single-turn proof and the
offline capacity archive. No arbitrary caller plan issues semantic authority.
"""
from copy import deepcopy
from pathlib import Path

import _b_route_codec as codec
import _b_route_adoption_review as review
import _b_route_qualified_compensation_review_v2 as qualified
import _b_route_qualified_compensation_materials_v2 as materials
from _b_route_compensation_review_profiles import PUBLISHED
import _b_route_compensation_segment_funding as funding
from _b_route_segmented_requests import _measurement, MAX_REQUEST_BYTES, CONTEXT_TOKEN_LIMIT
from _capability_input_integrity import request_measurement
from _planning_execution_binding import receipt_from, validate_execution
from _planning_skill_common import run_isolated_model, _runner_prefix
from _mvg_capability_checkpoint import coordinator_lock

DELIVERY='newrouge.b-route-compensation-segmented-delivery.v1'
PROOF='newrouge.b-route-compensation-segmented-proof.v1'
PLAN='newrouge.b-route-compensation-segmented-execution-plan.v1'
VERDICT='newrouge.b-route-compensation-segmented-verdict.v1'
CLAIM='complete_owner_dependency_closures_with_independent_sequential_runtime_reviews'
RESERVE=2000
TIMEOUT=1800
MARKER='segmented/plan.json'
STATIC=('subject.json','materials.json','roles.json','presentation.json','historical-auth.json','segmented/source-pins.json',MARKER)

def need(ok,expected,actual='segmented compensation mismatch'):
    review.require(ok,expected,actual)

def selected(root,operation_id):
    return review.path(root,review.location(operation_id)+'/'+MARKER).exists()

def _spec(derived):
    """Original owner partition boundary, never a CLI or model-supplied graph.

    Use the proved same-plan closure family where applicable. Other business
    graphs retain the complete closure rather than arbitrary byte slices.
    """
    need(type(derived) is materials.Derived and PUBLISHED is __import__(
        '_b_route_compensation_review_profiles').subject(derived.subject),'genuine published-history source')
    from _b_route_compensation_partition import build as preserving_partition
    partition=preserving_partition(derived)
    if partition is not None:return partition
    return [{'node_id':'complete-context','dependencies':[],
        'check_ids':review.obligations(derived.subject),'source_paths':['/'],
        'base_prompt':materials.render_segment_input(derived)}]

def _plan(subject,packet,spec):
    need(type(spec) is list and spec,'finite original owner node sequence')
    nodes=[];seen=set();checks=[]
    for ordinal,row in enumerate(spec):
        review.shape(row,('node_id','dependencies','check_ids','source_paths','base_prompt'),'owner closure')
        name=row['node_id']
        need(type(name) is str and name and name not in seen,'unique original node identity')
        need(type(row['dependencies']) is list and len(set(row['dependencies']))==len(row['dependencies'])
            and set(row['dependencies'])<=seen,'fixed preceding dependency closure')
        need(row['check_ids'] and row['check_ids']==sorted(set(row['check_ids']))
            and row['source_paths'] and all(type(p) is str and p.startswith('/') for p in row['source_paths']),
            'complete typed owner checks and original source ranges')
        checks.extend(row['check_ids']);seen.add(name)
        nodes.append({k:deepcopy(row[k]) for k in ('node_id','dependencies','check_ids','source_paths')}
                     | {'ordinal':ordinal,'base_prompt_digest':codec.raw_digest(row['base_prompt'].encode('utf-8'))})
    need(sorted(checks)==review.obligations(subject) and len(checks)==len(set(checks)),
         'exact original complete check denominator; no caller coverage grant')
    core={'schema_version':PLAN,'operation_id':subject['operation_id'],
        'subject_digest':codec.canonical_digest(subject),'source_policy':subject['policy_identity'],
        'presentation_digest':codec.canonical_digest(packet['presentation']),
        'nodes':nodes,'orchestrator':'deterministic-cli','output_reserve':RESERVE,
        'timeout_sec':TIMEOUT,'history_claim':PUBLISHED.claim,'execution_claim':CLAIM}
    return {**core,'plan_digest':codec.canonical_digest(core)}

def _home(subject):return review.location(subject['operation_id'])
def _dir(home,node):return home+'/segmented/nodes/'+str(node['ordinal']).zfill(3)
def _read(root,name):return review.path(root,name).read_bytes()
def _json(root,name):return codec.strict_json_loads(_read(root,name))
def _write(root,name,value):review.write_once(root,name,review.raw(value))
def _exists(root,name):return review.path(root,name).exists()
def _ref(root,name):return {'path':name,'schema_version':'raw.bytes.v1','raw_digest':codec.raw_digest(_read(root,name))}
def _prefix(rows):return codec.canonical_digest(rows)
def _schema_bytes(schema):return (review.text(schema)+'\n').encode('utf-8')
def _frame(prompt,schema):return review._runner_frame(prompt,schema,schema_bytes=_schema_bytes(schema))

def _schema(subject,packet,plan,node,prefix):
    p=packet['presentation']
    need(p['full_subject_digest']==codec.canonical_digest(subject) and p['policy_identity']==subject['policy_identity']
        and p['required_checks']==review.obligations(subject),'same validated complete packet/check denominator')
    # The exact plan/presentation/request/proof already bind all packet hashes.
    # Do not spend model context echoing six redundant host-only constants.
    schema=review._legacy_verdict_schema(subject)
    del schema['properties']['subject_digest'];schema['required'].remove('subject_digest')
    schema['properties']['schema_version']['const']=VERDICT
    schema['properties']['checks'].update(minItems=len(node['check_ids']),maxItems=len(node['check_ids']))
    schema['properties']['checks']['items']['properties']['id']['enum']=node['check_ids']
    for key,value in {'plan_digest':plan['plan_digest'],'node_id':node['node_id'],'prefix_digest':prefix}.items():
        schema['properties'][key]={'type':'string','const':value};schema['required'].append(key)
    return schema

def _request(subject,packet,plan,node,base,completed):
    prefix=_prefix(completed)
    parents=[{'node_id':r['node_id'],'result_digest':r['result_digest'],'verdict':r['verdict']}
             for r in completed if r['node_id'] in node['dependencies']]
    context={'plan_digest':plan['plan_digest'],'node_id':node['node_id'],'prefix_digest':prefix,
        'parents':parents,
        'rule':'Return the schema checks only. Parent verdicts do not replace required originals. CLI controls continuation.'}
    prompt=base+'\n\nCLI NODE CONTEXT (data):\n'+review.text(context)
    schema=_schema(subject,packet,plan,node,prefix)
    # Match the shared segmented renderer: admission binds the full logical
    # RPC container, including escaping and the outer output_schema field.
    request=review.text({'prompt':_frame(prompt,schema),'output_schema':schema})
    report=request_measurement(request,max_bytes=MAX_REQUEST_BYTES,max_input_tokens=CONTEXT_TOKEN_LIMIT,reserved_tokens=RESERVE)
    try:_measurement(report,request,RESERVE)
    except ValueError as error:
        review.require(False,'each complete node input<=70000 and input+reserve<=96000',
            {'node_id':node['node_id'],'reason':str(error),'measurement':report},codec.ReasonCode.INVALID_ARGUMENT)
    return prompt,schema,request,report

def _command(workspace):
    runner=Path(__file__).with_name('codex_isolated_model_runner.py')
    return [*_runner_prefix(runner,suppress_bytecode=True),'--workspace',str(workspace),
        '--prompt-file',str(workspace/'prompt.txt'),'--output',str(workspace/'output.json'),
        '--timeout-sec',str(TIMEOUT),'--output-schema',str(workspace/'schema.json'),'--model-request-budget','1']

def _verdict(value,schema,node):
    import jsonschema
    need(not list(jsonschema.Draft202012Validator(schema).iter_errors(value)),'exact node verdict/schema')
    rows=value['checks'];blocked=[r['rationale'] for r in rows if r['verdict']=='blocked']
    need(sorted(r['id'] for r in rows)==node['check_ids'] and len({r['id'] for r in rows})==len(rows)
        and all(r['rationale'].strip() for r in rows),'complete substantive node check accounting')
    need(len(value['findings'])==len(set(value['findings'])) and set(value['findings'])==set(blocked)
        and (value['verdict']=='blocked')==bool(blocked),'exact blocked node findings')
    need(not blocked and value['verdict']=='approved','no unresolved node findings')

def prepare(root,derived):
    """Freeze a fresh explicit execution plan; never a budget/model action."""
    subject=derived.subject;home=_home(subject)
    need(not _exists(root,home+'/w/prompt.txt') and not _exists(root,home+'/review.json'),
         'fresh segmented route cannot reinterpret an old single-turn review')
    spec=_spec(derived);plan=_plan(subject,derived.packet,spec)
    policy,pins=review.policy_observations();need(policy==subject['policy_identity'],'same actual source policy')
    values={'subject.json':review.raw(subject),'materials.json':review.raw(derived.packet['materials']),
        'roles.json':review.raw(derived.packet['roles']),'presentation.json':review.raw(derived.packet['presentation']),
        'historical-auth.json':derived.freeze_auth(),'segmented/source-pins.json':review.raw(pins),MARKER:review.raw(plan)}
    reports=[]
    for row,node in zip(spec,plan['nodes'],strict=True):
        directory=_dir(home,node)
        values['segmented/nodes/'+str(node['ordinal']).zfill(3)+'/base-prompt.txt']=row['base_prompt'].encode('utf-8')
        try:
            _prompt,_schema_value,_request_value,report=_request(subject,derived.packet,plan,node,row['base_prompt'],[])
            reports.append({'node_id':node['node_id'],'status':'literal_ready; actual prefix measured before dispatch','measurement':report})
        except codec.CodecError as error:
            reports.append({'node_id':node['node_id'],'status':'blocked','diagnostic':error.diagnostic.to_dict()})
    derived.recheck()
    need(review.policy_observations()==(policy,pins),'unchanged checked source at plan publication')
    for name,data in values.items():review.write_once(root,home+'/'+name,data)
    return {'status':'blocked' if any(r['status']=='blocked' for r in reports) else 'review_segmented_prepared',
        'operation_id':subject['operation_id'],'plan_ref':home+'/'+MARKER,'nodes':reports,
        'model_dispatched':False,'budget_authority':'not acquired','host_review_ref':None,
        'formal_adoption':False,'readiness':False,'runtime_verified':False}

def _saved(root,subject, *, work=None,packet=None):
    home=_home(subject);plan=_json(root,home+'/'+MARKER)
    need(not _exists(root,home+'/w/prompt.txt'),'no mixed old and segmented inputs')
    need(plan['subject_digest']==codec.canonical_digest(subject) and plan['source_policy']==review.policy_identity()
        and plan['operation_id']==subject['operation_id'],'current exact segmented subject/plan')
    core={k:v for k,v in plan.items() if k!='plan_digest'}
    need(codec.canonical_digest(core)==plan['plan_digest'],'complete immutable logical plan')
    if packet is None:
        packet={'schema_version':PUBLISHED.name('packet'),**{k:_json(root,home+'/'+k+'.json') for k in ('materials','roles','presentation')}}
    materials.validate(packet,work=work)
    need(_read(root,home+'/subject.json')==review.raw(subject),'exact canonical saved private subject bytes')
    policy,pins=review.policy_observations()
    need(policy==plan['source_policy'] and _read(root,home+'/segmented/source-pins.json')==review.raw(pins),'actual current source pins')
    # Structural coverage is checked again; only _complete's genuine owner
    # rederivation can qualify the partition's semantic independence.
    spec=[{k:node[k] for k in ('node_id','dependencies','check_ids','source_paths')}
        | {'base_prompt':_read(root,_dir(home,node)+'/base-prompt.txt').decode('utf-8')} for node in plan['nodes']]
    need(review.raw(_plan(subject,packet,spec))==review.raw(plan),'canonical complete plan/check coverage')
    return home,plan,packet

def _identity(plan,node,prefix,request,schema,report):
    return {'plan_digest':plan['plan_digest'],'node_id':node['node_id'],'ordinal':node['ordinal'],
        'prefix_digest':_prefix(prefix),'request_digest':codec.raw_digest(request.encode('utf-8')),
        'schema_digest':codec.raw_digest(_schema_bytes(schema)),'measurement':report,'source_policy':plan['source_policy'],
        'timeout_sec':TIMEOUT,'output_reserve':RESERVE}

def _replay(root,subject,plan,packet,node,prefix,session, *, completed=True,publish_result=False):
    home=_home(subject);directory=_dir(home,node);workspace=review.path(root,directory+'/w')
    base=_read(root,directory+'/base-prompt.txt').decode('utf-8')
    prompt,schema,request,report=_request(subject,packet,plan,node,base,prefix)
    identity=_identity(plan,node,prefix,request,schema,report)
    intent=_json(root,directory+'/intent.json');key=codec.canonical_digest(identity)
    need(intent=={'schema_version':DELIVERY,'key':key,'identity':identity},'original exact pending intent')
    need(_read(root,directory+'/w/prompt.txt')==prompt.encode('utf-8')
        and _read(root,directory+'/w/schema.json')==_schema_bytes(schema)
        and _read(root,directory+'/request.txt')==request.encode('utf-8')
        and _read(root,directory+'/measurement.json')==review.raw(report),'complete original node inputs and remeasured wrapper')
    execution=_json(root,directory+'/execution.json');output=_read(root,directory+'/w/output.json')
    need(execution['command']==_command(workspace),'exact official single-request runner argv')
    receipt=receipt_from(execution)
    validate_execution(workspace,execution,receipt,'auto',output,prompt=_frame(prompt,schema),schema=schema,
                       require_runtime=True,expected_reasoning_effort='high')
    evidence=receipt['model_identity_evidence'][0]
    threads=set(subject['native_threads'])|{r['evidence']['thread_id'] for r in prefix}
    turns=set(subject['native_turns'])|{r['evidence']['turn_id'] for r in prefix}
    need(evidence['model_provider']=='openai' and evidence['thread_id'] not in threads
         and evidence['turn_id'] not in turns,'official high/no-tools thread and turn independent of all ancestors and nodes')
    verdict=codec.strict_json_loads(output);_verdict(verdict,schema,node)
    reservation=_json(root,directory+'/reservation.json')
    outcome={'output_digest':codec.raw_digest(output),'execution_digest':codec.raw_digest(_read(root,directory+'/execution.json'))}
    session.verify(reservation,key,identity,outcome)
    result={'schema_version':DELIVERY,'node_id':node['node_id'],'identity':identity,'reservation':reservation,
        'outcome':outcome,'evidence':{'thread_id':evidence['thread_id'],'turn_id':evidence['turn_id'],
        'protocol_digest':evidence['protocol_sha256'],'runtime_configuration':{'model':evidence['model'],
        'provider':evidence['model_provider'],'reasoning_effort':'high'},'provider_actual_model':'unknown','physical_requests':'unknown'}}
    if publish_result and not _exists(root,directory+'/result.json'):_write(root,directory+'/result.json',result)
    need(_read(root,directory+'/result.json')==review.raw(result),'exact original verified node result')
    result_ref=_ref(root,directory+'/result.json')
    if completed:need(_json(root,directory+'/completed.json')==result_ref,'durable completed node publication')
    return {'node_id':node['node_id'],'result_digest':result_ref['raw_digest'],'verdict':verdict,'evidence':result['evidence']}

def verify_current_plan(root,derived):
    spec=_spec(derived);plan=_plan(derived.subject,derived.packet,spec);home=_home(derived.subject)
    need(_read(root,home+'/'+MARKER)==review.raw(plan),'same genuine owner-derived dependency partition before dispatch')
    for row,node in zip(spec,plan['nodes'],strict=True):
        need(_read(root,_dir(home,node)+'/base-prompt.txt')==row['base_prompt'].encode('utf-8'),
             'same complete actual closure originals before dispatch')
    for name in ('materials','roles','presentation'):
        need(_read(root,home+'/'+name+'.json')==review.raw(derived.packet[name]),'same complete current '+name)
    need(_read(root,home+'/historical-auth.json')==derived.freeze_auth(),'same actual historical verification')
    derived.recheck()

def execute(root,operation_id, *, publication_only=False,derived=None):
    """Sequential finite CLI consumer. Unknown never becomes a new dispatch."""
    subject=qualified.read_subject(root,operation_id)
    derived=qualified.model_packet(root,subject) if derived is None else derived
    # Share the genuine factory account and graph. verify_current_plan checks
    # every saved packet byte before funding; do not retain a second packet.
    home,plan,packet=_saved(root,subject,work=derived.work,packet=derived.packet)
    verify_current_plan(root,derived)
    with coordinator_lock(review.path(root,home)):
        session=funding.capture(root,plan,read_only=publication_only);funding.require_session(session)
        prefix=[];dispatch_attempts=0
        for node in plan['nodes']:
            derived.recheck()
            need(review.policy_identity()==plan['source_policy'],'unchanged current source before node reservation/replay')
            directory=_dir(home,node)
            if _exists(root,directory+'/completed.json'):
                prefix.append(_replay(root,subject,plan,packet,node,prefix,session));continue
            if _exists(root,directory+'/intent.json'):
                # Only an original owner-confirmed completed outcome and all
                # actual saved bytes can finish a missing local publication.
                if all(_exists(root,directory+'/'+n) for n in ('execution.json','reservation.json','w/output.json')):
                    row=_replay(root,subject,plan,packet,node,prefix,session,completed=False,publish_result=True)
                    _write(root,directory+'/completed.json',_ref(root,directory+'/result.json'))
                    prefix.append(row);continue
                return {'status':'blocked','reason':'pending_or_unknown_requires_original_owner_reconciliation',
                    'node_id':node['node_id'],'automatic_retry':False,'model_dispatched':dispatch_attempts>0,
                    'runner_dispatch_attempts':dispatch_attempts}
            if publication_only:return {'status':'ready','next_node':node['node_id'],'model_dispatched':False,'runner_dispatch_attempts':0}
            base=_read(root,directory+'/base-prompt.txt').decode('utf-8')
            prompt,schema,request,report=_request(subject,packet,plan,node,base,prefix)
            identity=_identity(plan,node,prefix,request,schema,report);key=codec.canonical_digest(identity)
            workspace=review.path(root,directory+'/w')
            for name,data in {'w/prompt.txt':prompt.encode('utf-8'),'w/schema.json':_schema_bytes(schema),
                'request.txt':request.encode('utf-8'),'measurement.json':review.raw(report)}.items():
                review.write_once(root,directory+'/'+name,data)
            _write(root,directory+'/intent.json',{'schema_version':DELIVERY,'key':key,'identity':identity})
            reservation=None;outcome=None;settled=False
            try:
                reservation=session.reserve(key,identity,len(plan['nodes'])-len(prefix))
                _write(root,directory+'/reservation.json',reservation)
                # Recheck exact inputs before invoking; no model owns continuation.
                need(_read(root,directory+'/request.txt')==request.encode('utf-8')
                    and _read(root,directory+'/w/prompt.txt')==prompt.encode('utf-8')
                    and _read(root,directory+'/w/schema.json')==_schema_bytes(schema)
                    and {p.name for p in workspace.iterdir()}=={'prompt.txt','schema.json'},'unchanged complete reserved input files')
                dispatch_attempts+=1
                run_isolated_model(Path(__file__).with_name('codex_isolated_model_runner.py'),workspace=workspace,
                    prompt_path=workspace/'prompt.txt',output_path=workspace/'output.json',timeout_sec=TIMEOUT,
                    wall_timeout_sec=TIMEOUT+30,output_schema=workspace/'schema.json',model_request_budget=1,
                    execution_log=review.path(root,directory+'/execution.json'),suppress_bytecode=True,reasoning_effort='high')
                execution=_json(root,directory+'/execution.json');output=_read(root,directory+'/w/output.json')
                receipt=receipt_from(execution)
                validate_execution(workspace,execution,receipt,'auto',output,prompt=_frame(prompt,schema),schema=schema,
                                   require_runtime=True,expected_reasoning_effort='high')
                derived.recheck()
                need(review.policy_identity()==plan['source_policy'],'unchanged current source after node execution')
                outcome={'output_digest':codec.raw_digest(output),'execution_digest':codec.raw_digest(_read(root,directory+'/execution.json'))}
                session.complete(reservation,key,identity,outcome)
                settled=True
                evidence=receipt['model_identity_evidence'][0]
                result={'schema_version':DELIVERY,'node_id':node['node_id'],'identity':identity,'reservation':reservation,
                    'outcome':outcome,'evidence':{'thread_id':evidence['thread_id'],'turn_id':evidence['turn_id'],
                    'protocol_digest':evidence['protocol_sha256'],'runtime_configuration':{'model':evidence['model'],
                    'provider':evidence['model_provider'],'reasoning_effort':'high'},'provider_actual_model':'unknown','physical_requests':'unknown'}}
                _write(root,directory+'/result.json',result)
                row=_replay(root,subject,plan,packet,node,prefix,session,completed=False)
                _write(root,directory+'/completed.json',_ref(root,directory+'/result.json'));prefix.append(row)
            except BaseException as error:
                settlement_error=None
                if not settled and reservation is not None and outcome is not None:
                    try:session.verify(reservation,key,identity,outcome);settled=True
                    except BaseException:pass
                if not settled:
                    try:session.unknown(reservation,key,identity,type(error).__name__)
                    except BaseException as secondary:settlement_error=type(secondary).__name__
                _write(root,directory+('/blocked.json' if settled else '/unknown.json'),{'schema_version':DELIVERY,'key':key,
                    'error_type':type(error).__name__,'owner_recording_error_type':settlement_error})
                raise
        return {'status':'review_segmented_executed','completed_nodes':len(prefix),'model_dispatched':dispatch_attempts>0,
                'runner_dispatch_attempts':dispatch_attempts,
                'physical_provider_requests':'unknown','host_review_ref':None}

def _buffers(root,home,plan):
    names=list(STATIC)
    for node in plan['nodes']:
        base='segmented/nodes/'+str(node['ordinal']).zfill(3)+'/'
        names += [base+n for n in ('base-prompt.txt','w/prompt.txt','w/schema.json','request.txt','measurement.json',
            'intent.json','reservation.json','execution.json','w/output.json','result.json','completed.json')]
        for auxiliary in ('unknown.json','blocked.json'):
            if _exists(root,home+'/'+base+auxiliary):names.append(base+auxiliary)
    return {name:_read(root,home+'/'+name) for name in names}

def labels(buffers):
    def role(name):
        if name in ('materials.json','roles.json','presentation.json'):return 'host:'+name[:-5]
        if name=='historical-auth.json':return 'host:historical_auth'
        if name=='subject.json':return 'host:subject'
        if name.endswith('prompt.txt'):return 'host:prompt'
        if name.endswith('schema.json'):return 'host:schema'
        if name.endswith('output.json'):return 'host:output'
        if name.endswith('execution.json'):return 'host:execution'
        return 'host:proof'
    return {name:role(name) for name in buffers}

def inputs(root,subject, *, proof=None):
    work=__import__('_b_route_compact_literal')._work(None)
    home,plan,packet=_saved(root,subject,work=work)
    session=funding.capture(root,plan,read_only=True);funding.require_session(session)
    prefix=[]
    for node in plan['nodes']:prefix.append(_replay(root,subject,plan,packet,node,prefix,session))
    buffers=_buffers(root,home,plan)
    refs=[{'path':home+'/'+n,'schema_version':'raw.bytes.v1','raw_digest':codec.raw_digest(data)} for n,data in buffers.items()]
    evidence={'nodes':[r['evidence'] for r in prefix],'scope':'verified_independent_sequence',
        'provider_actual_model':'unknown','physical_requests':'unknown'}
    if proof is not None:
        requests=[_ref(root,_dir(home,n)+'/request.txt') for n in plan['nodes']]
        need(review.raw(proof)==review.raw(_proof_value(subject,packet,plan,refs,evidence,requests)),
             'complete segmented proof/files/evidence binding before saved before-view scope')
    return qualified._SavedInputs(qualified._MINT,Path(root).absolute(),subject,buffers,proof,refs,evidence,work)

def complete_inputs(saved):
    d=qualified.model_packet(saved.root,saved.subject,context=saved)
    spec=_spec(d);plan=_plan(saved.subject,d.packet,spec);home=_home(saved.subject)
    need(saved.buffers[MARKER]==review.raw(plan),'genuine source rederived complete semantic partition')
    for row,node in zip(spec,plan['nodes'],strict=True):
        need(saved.buffers['segmented/nodes/'+str(node['ordinal']).zfill(3)+'/base-prompt.txt']==row['base_prompt'].encode('utf-8'),
             'complete genuine owner-derived node originals and global/dependency context')
    for k in ('materials','roles','presentation'):
        need(saved.buffers[k+'.json']==review.raw(d.packet[k]),'complete current rederived '+k)
    need(saved.buffers['historical-auth.json']==d.freeze_auth(),'complete actual private historical byte verification')
    d.recheck();return d

def _proof_value(subject,packet,plan,refs,evidence,requests):
    p=packet['presentation']
    return {'schema_version':PROOF,'operation_id':subject['operation_id'],'subject_digest':codec.canonical_digest(subject),
        'policy_identity':subject['policy_identity'],'delivery':DELIVERY,'claim':CLAIM,'history_claim':PUBLISHED.claim,
        'plan_digest':plan['plan_digest'],'requests_digest':codec.canonical_digest(requests),'evidence':evidence,
        'files':refs,**{k:p[k] for k in ('materials_digest','roles_digest','historical_auth_digest')},
        'presentation_digest':codec.canonical_digest(p)}

def produce_proof(root,operation_id, *, proof=None):
    subject=qualified.read_subject(root,operation_id);saved=inputs(root,subject,proof=proof)
    d=complete_inputs(saved);qualified.bindings(subject,d);plan=codec.strict_json_loads(saved.buffers[MARKER])
    requests=[_ref(root,_dir(_home(subject),n)+'/request.txt') for n in plan['nodes']]
    value=_proof_value(subject,d.packet,plan,saved.refs,saved.evidence,requests)
    return value,saved,d

def verify_saved_private(root,request):
    ref=request['host_review_ref'];home=review.location(request['operation_id'])
    review.shape(ref,('path','schema_version','raw_digest'),'closed owned segmented proof reference')
    need(ref.get('schema_version')==PROOF and ref.get('path')==home+'/review.json','exact owned segmented proof reference')
    data=_read(root,ref['path']);need(codec.raw_digest(data)==ref['raw_digest'],'exact segmented proof bytes')
    proof=codec.strict_json_loads(data)
    value,saved,d=produce_proof(root,request['operation_id'],proof=proof)
    need(data==review.raw(value) and qualified.same(saved.subject['request'],review.request_body(request)),
         'complete new sequential proof and exact compensation request')
    saved.refs=[ref,*saved.refs];return saved,d
