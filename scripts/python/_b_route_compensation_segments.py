"""Deterministic offline compensation segment preparation, never dispatch.

The first conservative closure retains the complete owner-derived packet.
No independent semantic partition has yet been proven for its shared graph.
This is not a paid runner, old proof consumer, budget issuer or business journal.
"""
from pathlib import Path

import _b_route_codec as codec
import _b_route_adoption_review as review
import _b_route_qualified_compensation_materials_v2 as materials
import _b_route_compact_literal as compact
import _b_route_compensation_review_materials as accounting
import _b_route_compensation_review_profiles as profiles
from _b_route_segmented_requests import (
    INPUT_TOKEN_LIMIT, CONTEXT_TOKEN_LIMIT, MAX_REQUEST_BYTES, _measurement,
)
from _capability_input_integrity import request_measurement

PLAN = 'newrouge.b-route-compensation-segment-plan.v1'
STATE = 'newrouge.b-route-compensation-segment-preflight.v1'
OUTPUT_RESERVE = 2000
CLAIM = 'offline_complete_context_preflight_without_execution_authority'


def _archive_packet(derived, *, metrics=(), buffers=()):
    pm,pb=derived.private_metrics()
    held=(*pm,*metrics);raw_buffers=(*pb,*buffers)
    text,metric=accounting._ordered(derived.packet,derived.work,held,raw_buffers,'segment.archive.packet')
    accounting._live(derived.work,'segment.archive.packet.utf8',(*held,metric),
                     (*raw_buffers,3*(metric[5]+1)))
    derived.work.spend(len(text)+2*metric[5]+3,phase='segment.archive.packet.utf8')
    return (text+'\n').encode('utf-8')


def _inventory(packet,work,metrics=(),buffers=()):
    """Cover complete semantic subtrees, literal bytes and role correspondence."""
    values=[{'path':'/presentation','value':packet['presentation']},
            {'path':'/roles','value':packet['roles']}]
    values += [{'path':'/materials/frames/'+str(i),'value':v}
               for i,v in enumerate(packet['materials']['frames'])]
    values += [{'path':'/materials/documents/'+str(i),'value':v}
               for i,v in enumerate(packet['materials']['documents'])]
    meta=accounting._mv_metadata(work,len(values),metrics,buffers,'segment.inventory.metadata')
    rows=[]
    for row in values:
        text,metric=accounting._ordered(row['value'],work,(*metrics,meta),buffers,'segment.inventory.value')
        digest=accounting._ordered_digest(text,metric[5],work,(*metrics,meta,metric),buffers)
        rows.append({'path':row['path'],'ordered_raw_digest':digest,'ordered_bytes':metric[5]})
    return rows


def _resume(root,home,derived,canonical_prompt):
    """Reuse only a complete matching offline archive; never repair or execute it."""
    observed,source_pins=review.policy_observations()
    review.require(observed==derived.subject['policy_identity'],'same current segment policy','changed policy')
    state=codec.strict_json_loads(review.path(root,home+'/state.json').read_bytes())
    review.require(state.get('schema_version')==STATE and state.get('model_dispatched') is False
        and state.get('completed_model_nodes')==[] and state.get('next_model_node')=='complete-context',
        'original offline-only segment state','changed segment state')
    refs=state['files']
    review.require(type(refs) is dict and set(refs)=={'packet.json','plan.json','source-pins.json',
        'nodes/000/w/prompt.txt','nodes/000/w/schema.json','nodes/000/request.txt','nodes/000/measurement.json'},
        'complete fixed preflight archive','changed segment file set')
    for name,digest in refs.items():
        review.require(codec.raw_digest(review.path(root,home+'/'+name).read_bytes())==digest,
                       'unchanged archived segment input',name)
    packet=derived.packet
    held=[compact._json_preflight(v,derived.work) for v in (state,source_pins)]
    prompt_size=compact._utf8_size(canonical_prompt,derived.work)
    packet_bytes=_archive_packet(derived,metrics=held,buffers=(2*prompt_size,))
    review.require(review.path(root,home+'/packet.json').read_bytes()==packet_bytes
        and review.path(root,home+'/source-pins.json').read_bytes()==review.raw(source_pins),
        'same actual owner packet and policy sources','stale segment preflight')
    plan=codec.strict_json_loads(review.path(root,home+'/plan.json').read_bytes())
    schema=__import__('_b_route_qualified_compensation_review_v2').verdict_schema(
        derived.subject,root=root,packet=derived)
    prompt_raw=review.path(root,home+'/nodes/000/w/prompt.txt').read_bytes()
    metrics,buffers=derived.private_metrics()
    metrics += [compact._json_preflight(v,derived.work) for v in (packet,state,plan,schema,source_pins)]
    buffers += [len(packet_bytes),len(prompt_raw),len(review.raw(schema))]
    accounting._live(derived.work,'segment.resume.prompt.utf8',metrics,(*buffers,2*prompt_size))
    derived.work.spend(len(canonical_prompt)+2*prompt_size+len(prompt_raw),phase='segment.resume.prompt.exact')
    review.require(prompt_raw==canonical_prompt.encode('utf-8'),
        'exact archived bytes equal current genuine canonical segment input','changed segment input')
    del canonical_prompt
    prompt=prompt_raw.decode('utf-8')
    request=review._runner_frame(prompt,schema)
    del prompt,prompt_raw
    review.require(review.path(root,home+'/nodes/000/w/schema.json').read_bytes()==review.raw(schema)
        and review.path(root,home+'/nodes/000/request.txt').read_bytes()==request.encode('utf-8'),
        'same actual complete segment wrapper and schema','changed segment request')
    buffers=[*derived.private_metrics()[1],len(packet_bytes),2*len(request.encode('utf-8')),len(review.raw(schema))]
    derived.work.spend(len(packet_bytes)+8,phase='segment.archive.packet.hash')
    expected_plan=_plan(derived.subject,packet,home,derived.subject['policy_identity'],
        request,codec.raw_digest(packet_bytes),work=derived.work,metrics=metrics,buffers=buffers)
    report=request_measurement(request,max_bytes=MAX_REQUEST_BYTES,
        max_input_tokens=CONTEXT_TOKEN_LIMIT,reserved_tokens=OUTPUT_RESERVE)
    expected_state=_state(report,request)
    expected_state['files']=refs
    review.require(review.raw(plan)==review.raw(expected_plan) and review.raw(state)==review.raw(expected_state)
        and review.path(root,home+'/nodes/000/measurement.json').read_bytes()==review.raw(report),
        'rederived deterministic plan and actual measurement/state','changed offline state')
    derived.recheck()
    return _result(home,plan,expected_state,resumed=True)


def _result(home,plan,state, *, resumed=False):
    result={'status':'blocked' if state['blocked'] else 'ready','stage':'review-segmented-preflight',
        'operation_id':plan['operation_id'],'claim':CLAIM,'plan_ref':home+'/plan.json',
        'state_ref':home+'/state.json','resume_ref':home+'/state.json','resumed_offline_archive':resumed,
        'node_count':len(plan['nodes']),'nodes':state['nodes'],
        'segmentation_qualification':'not_established','safe_further_partition':'not_established',
        'semantic_execution_required':True,'model_dispatched':False,'paid_execution_enabled':False,
        'host_review_ref':None,'formal_adoption':False,'readiness':False,'runtime_verified':False}
    if state['blocked']:
        result['diagnostics']=[codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT,codec.Stage.BUNDLE,
            entity_id=plan['operation_id'],expected='each segment input<=70000 and input+reserve<=96000',
            actual=state['nodes'][0]['reason'],resume_ref=home+'/state.json').to_dict()]
    return result


def _plan(subject,packet,home,policy,request,packet_digest, *, work=None,metrics=(),buffers=()):
    inventory=_inventory(packet,compact._work(work),metrics,buffers)
    node={'node_id':'complete-context','ordinal':0,'dependencies':[],
        'required_checks':packet['presentation']['required_checks'],
        'inventory_paths':[r['path'] for r in inventory],
        'closure':'complete_owner_packet_pending_proven_semantic_partition',
        'input_token_limit':INPUT_TOKEN_LIMIT,'context_token_limit':CONTEXT_TOKEN_LIMIT,
        'output_reserve':OUTPUT_RESERVE,'request_ref':home+'/nodes/000/request.txt',
        'request_raw_digest':codec.raw_digest(request.encode('utf-8'))}
    plan={'schema_version':PLAN,'claim':CLAIM,'operation_id':subject['operation_id'],
        'subject_digest':codec.canonical_digest(subject),'packet_raw_digest':packet_digest,
        'source_policy':policy,'delivery':materials.SEGMENT_DELIVERY,
        'orchestrator':'deterministic_cli','cross_request_memory':False,
        'partition_basis':'Conservative complete closure; safe further decomposition is not yet established. '
            'Length does not establish a semantic boundary. No LLM partition or continuation decisions.',
        'inventory':inventory,'nodes':[node],'required_model_requests_if_admitted':1,
        'model_budget_authority':None,'new_execution_proof_implemented':False}
    return plan


def _state(report,request):
    blocked=None
    try:_measurement(report,request,OUTPUT_RESERVE)
    except ValueError as error:blocked=str(error)
    state={'schema_version':STATE,'model_dispatched':False,'completed_model_nodes':[],
        'next_model_node':'complete-context','blocked':blocked is not None,
        'nodes':[{'node_id':'complete-context','status':'preflight_blocked' if blocked else 'preflight_ready_not_executed',
            'reason':blocked,'measurement':report}],
        'limitations':['No safe independent partition proven; not a theorem that all input is indivisible.',
            'Byte-upper refusal is not measured token overflow; no provider/model admission established.',
            'No paid/fiscal authority, execution proof, compensation reservation or publication.']}
    return state


def prepare(root,derived):
    """Freeze an actual closure before any per-node admission; no whole-run cap."""
    review.require(type(derived) is materials.Derived and
        profiles.subject(derived.subject) is profiles.PUBLISHED,
        'actual published-history compensation derivation','unsupported segment input')
    root=Path(root).absolute()
    derived.recheck()
    packet=derived.packet
    # Do not retain a separately serialized full packet/schema/pin archive
    # during the codec's genuine private-graph peak.
    policy=derived.subject['policy_identity']
    # Reuse genuine owner digests instead of allocating the full packet merely
    # to choose an archive directory before its bounded renderer.
    p=packet['presentation']
    identity=codec.canonical_digest({'subject':p['full_subject_digest'],'materials':p['materials_digest'],
        'roles':p['roles_digest'],'history':p['historical_auth_digest'],'policy':policy,'protocol':PLAN})[7:]
    home='logs/ci/b-route-compensation-segments/'+identity
    state_path=review.path(root,home+'/state.json')
    if state_path.exists():
        # The genuine originals already exist in this action. Re-render their
        # canonical input before loading archive buffers, then compare raw bytes.
        # This avoids a second parsed-view graph at the proven 64MiB peak.
        return _resume(root,home,derived,materials.render_segment_input(derived))
    prompt=materials.render_segment_input(derived)
    packet_bytes=_archive_packet(derived,buffers=(2*compact._utf8_size(prompt,derived.work),))
    derived.work.spend(len(packet_bytes)+8,phase='segment.archive.packet.hash')
    packet_digest=codec.raw_digest(packet_bytes)
    schema=__import__('_b_route_qualified_compensation_review_v2').verdict_schema(
        derived.subject,root=root,packet=derived)
    observed,pins=review.policy_observations()
    review.require(observed==policy,'same current segment policy','changed policy')
    request=review._runner_frame(prompt,schema)
    report=request_measurement(request,max_bytes=MAX_REQUEST_BYTES,
        max_input_tokens=CONTEXT_TOKEN_LIMIT,reserved_tokens=OUTPUT_RESERVE)
    metrics,buffers=derived.private_metrics()
    metrics += [compact._json_preflight(v,derived.work) for v in (packet,schema,pins)]
    buffers += [len(packet_bytes),2*len(request.encode('utf-8'))]
    plan=_plan(derived.subject,packet,home,policy,request,packet_digest,
               work=derived.work,metrics=metrics,buffers=buffers)
    state=_state(report,request)
    values={'packet.json':packet_bytes,'plan.json':review.raw(plan),'source-pins.json':review.raw(pins),
        'nodes/000/w/prompt.txt':prompt.encode('utf-8'),'nodes/000/w/schema.json':review.raw(schema),
        'nodes/000/request.txt':request.encode('utf-8'),'nodes/000/measurement.json':review.raw(report)}
    state['files']={name:codec.raw_digest(data) for name,data in values.items()}
    derived.recheck()
    review.require(review.policy_observations()==(policy,pins),'same checked segment source pins','source drift')
    for name,data in values.items():review.write_once(root,home+'/'+name,data)
    # State is published last; an interrupted archive is never called complete.
    review.write_once(root,home+'/state.json',review.raw(state))
    return _result(home,plan,state)
