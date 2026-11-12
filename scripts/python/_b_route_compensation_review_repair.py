"""One explicit completed-refusal repair; old calls stay occupied and immutable."""
import ast
from copy import deepcopy
from pathlib import Path
import sys

import _b_route_adoption_review as review
import _b_route_codec as codec
import _b_route_compensation_segmented_execution as engine
import _b_route_qualified_compensation_review_v2 as qualified
from _b_route_compensation_review_profiles import PUBLISHED
from _mvg_capability_checkpoint import coordinator_lock
from _planning_execution_binding import receipt_from, validate_execution
from _planning_skill_common import run_isolated_model

PROOF='newrouge.b-route-compensation-segmented-proof.v2'
DELIVERY='newrouge.b-route-compensation-review-repair.v1'
CLAIM='same_exact_previously_approved_business_closure_and_fresh_current_governance_review'
LANE='segmented/review-repair'
MANIFEST=LANE+'/manifest.json'
LEGACY_POLICY='sha256:65e75d61df84da606dd80eca6bbcb2d7fc9a1c3f3ddf08f3c96795ecc8c6d4c5'
ALLOWANCE=LANE+'/allowance.json'
STATIC=('subject.json','materials.json','roles.json','presentation.json','historical-auth.json',
        'source-pins.json','plan.json','business-base.txt','governance-base.txt','claim.json')
ROUTE_CHANGES={'_b_route_adoption.py','_b_route_adoption_review.py','_b_route_compensation.py',
    '_b_route_compensation_partition.py','_b_route_compensation_segmented_execution.py',
    '_b_route_qualified_compensation_review_v2.py','_b_route_qualified_compensation_dispatch.py',
    '_b_route_published_history.py'}
need=engine.need

def home(operation_id):return review.location(operation_id)
def selected(root,operation_id):return review.path(root,home(operation_id)+'/'+LANE).exists()
def read(root,name):return review.path(root,name).read_bytes()
def value(root,name):return codec.strict_json_loads(read(root,name))
def write(root,name,obj):review.write_once(root,name,review.raw(obj))
def ref(root,name):return {'path':name,'schema_version':'raw.bytes.v1','raw_digest':codec.raw_digest(read(root,name))}

def _original_files(root,base):
    directory=review.path(root,base)
    return {p.relative_to(directory).as_posix():codec.raw_digest(read(root,p.relative_to(root).as_posix()))
        for p in directory.rglob('*') if p.is_file()
        and not p.relative_to(directory).as_posix().startswith(LANE+'/')
        and p.relative_to(directory).as_posix()!='review.json'}

def _source_epoch(root,base,source_root=None):
    """Hash original source DATA; never import or execute historical code."""
    pins=value(root,base+'/segmented/source-pins.json')
    need(len(pins)==83,'known complete 83-file original source epoch')
    repo=Path(__file__).resolve().parents[2];sources={};schemas={};hosts={};intent=None;raws={}
    for name,digest in pins.items():
        relative=Path(name).relative_to(repo).as_posix()
        raw=(read(source_root,relative) if source_root is not None else
             read(root,base+'/'+LANE+'/original-source/'+relative))
        need(codec.raw_digest(raw)==digest,'exact retained original source bytes',relative)
        raws[relative]=raw;leaf=Path(relative).name
        if leaf.endswith('.py'):sources[leaf]=digest
        elif leaf.startswith('qualified-historical-owner-authority.'):hosts[leaf]=digest
        elif leaf=='commit-intent.schema.json':intent=digest
        elif leaf.endswith('.schema.json'):schemas[leaf[:-len('.schema.json')]]=digest
        else:need(False,'closed original source/resource family',relative)
        if leaf not in ROUTE_CHANGES:
            current=(repo/relative).read_bytes()
            need(codec.raw_digest(current)==digest or
                (leaf=='_b_route_qualified_compensation_materials_v2.py' and _retention_only_change(raw,current)),
                 'unchanged semantic decoder/protocol/resource owner',relative)
    policy=codec.canonical_digest({'python':sys.version,'sources':sources,
        'schemas':{**schemas,'commit-intent.schema.json':intent},'host_resources':hosts})
    need(policy==LEGACY_POLICY,'known original full source policy; no arbitrary source transition')
    return raws

def _retention_only_change(before,after):
    """Only account two real context graphs; all decoding/meaning code stays exact."""
    old=ast.parse(before.decode('utf-8'));new=ast.parse(after.decode('utf-8'))
    addition=ast.parse('graphs.extend([self.context.refs,self.context.evidence])').body[0]
    removed=0
    for cls in new.body:
        if isinstance(cls,ast.ClassDef) and cls.name=='Derived':
            for method in cls.body:
                if isinstance(method,ast.FunctionDef) and method.name=='private_metrics':
                    for node in ast.walk(method):
                        if isinstance(node,ast.If):
                            keep=[]
                            for statement in node.body:
                                if ast.dump(statement)==ast.dump(addition):removed+=1
                                else:keep.append(statement)
                            node.body=keep
    return removed==1 and ast.dump(old)==ast.dump(new)

def _constants(raw):
    """Read only closed string DATA expressions, never run source statements."""
    wanted={'WIRE','INSTRUCTION','PROJECTION','SPELLING','DECODER','HEADER'};result={}
    def literal(node):
        if isinstance(node,ast.Constant) and type(node.value) is str:return node.value
        if isinstance(node,ast.Name) and node.id in result:return result[node.id]
        if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):return literal(node.left)+literal(node.right)
        need(False,'literal string-only historical wire definition')
    for node in ast.parse(raw.decode('utf-8')).body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id
            if name in wanted:result[name]=literal(node.value)
    need(set(result)==wanted,'complete original wire and decoder DATA definitions')
    return result

def _rule(raw):
    rules=[]
    for node in ast.walk(ast.parse(raw.decode('utf-8'))):
        if isinstance(node,ast.Dict):
            for key,val in zip(node.keys,node.values):
                if isinstance(key,ast.Constant) and key.value=='rule' and isinstance(val,ast.Constant):
                    if type(val.value) is str and 'Parent verdicts' in val.value:rules.append(val.value)
    need(len(rules)==1,'one known original node-context instruction');return rules[0]

def _recorded_node(root,subject,packet,plan,node,prefix,rule,header):
    base=home(subject['operation_id']);directory=engine._dir(base,node);workspace=review.path(root,directory+'/w')
    prompt=read(root,directory+'/base-prompt.txt').decode('utf-8')
    need(prompt.startswith(header+'\n') and codec.raw_digest(prompt.encode())==node['base_prompt_digest'],
        'exact original source-bound header, body and decoder')
    parents=[{'node_id':r['node_id'],'result_digest':r['result_digest'],'verdict':r['verdict']}
             for r in prefix if r['node_id'] in node['dependencies']]
    context={'plan_digest':plan['plan_digest'],'node_id':node['node_id'],'prefix_digest':engine._prefix(prefix),
             'parents':parents,'rule':rule}
    prompt+='\n\nCLI NODE CONTEXT (data):\n'+review.text(context)
    schema=engine._schema(subject,packet,plan,node,engine._prefix(prefix))
    request=review.text({'prompt':engine._frame(prompt,schema),'output_schema':schema})
    report=engine.request_measurement(request,max_bytes=engine.MAX_REQUEST_BYTES,
        max_input_tokens=engine.CONTEXT_TOKEN_LIMIT,reserved_tokens=engine.RESERVE)
    engine._measurement(report,request,engine.RESERVE)
    identity=engine._identity(plan,node,prefix,request,schema,report);key=codec.canonical_digest(identity)
    intent=value(root,directory+'/intent.json')
    need(intent=={'schema_version':engine.DELIVERY,'key':key,'identity':identity,
        'admission':ref(root,base+'/'+engine.ADMISSION)},'complete exact original occupied intent')
    need(read(root,directory+'/w/prompt.txt')==prompt.encode() and
        read(root,directory+'/w/schema.json')==engine._schema_bytes(schema) and
        read(root,directory+'/request.txt')==request.encode() and
        read(root,directory+'/measurement.json')==review.raw(report),'exact original complete request/schema/measurement')
    execution=value(root,directory+'/execution.json');output=read(root,directory+'/w/output.json')
    need(execution['command']==engine._command(workspace),'original official runner command')
    receipt=receipt_from(execution)
    validate_execution(workspace,execution,receipt,'auto',output,prompt=engine._frame(prompt,schema),schema=schema,
                       require_runtime=True,expected_reasoning_effort='high')
    evidence=receipt['model_identity_evidence'][0]
    need(evidence['model_provider']=='openai' and evidence['thread_id'] not in
        set(subject['native_threads'])|{p['evidence']['thread_id'] for p in prefix} and evidence['turn_id'] not in
        set(subject['native_turns'])|{p['evidence']['turn_id'] for p in prefix},'independent completed original official high/no-tools turn')
    return directory,schema,codec.strict_json_loads(output),identity,evidence

def original(root,operation_id,source_root=None,*,work=None):
    base=home(operation_id);s=value(root,base+'/subject.json');p=value(root,base+'/segmented/plan.json')
    need(s['operation_id']==operation_id and s['policy_identity']==p['source_policy']==LEGACY_POLICY and
        p['subject_digest']==codec.canonical_digest(s) and
        p['plan_digest']==codec.canonical_digest({k:v for k,v in p.items() if k!='plan_digest'}),
        'intact known original operation/subject/plan/source')
    need([n['node_id'] for n in p['nodes']]==['business','governance-joint'] and
        p['nodes'][0]['dependencies']==[] and p['nodes'][1]['dependencies']==['business'],
        'known complete two-closure original family only')
    packet={'schema_version':PUBLISHED.name('packet'),**{k:value(root,base+'/'+k+'.json')
        for k in ('presentation','roles','materials')}}
    engine.materials.validate(packet,work=work)
    need(p['presentation_digest']==codec.canonical_digest(packet['presentation']) and
        sorted(sum((n['check_ids'] for n in p['nodes']),[]))==review.obligations(s),
        'same complete original check denominator')
    auth=value(root,base+'/historical-auth.json')
    need(codec.canonical_digest(auth)==packet['presentation']['historical_auth_digest'] and
        auth['full_subject_digest']==codec.canonical_digest(s),'complete original subject-bound historical auth digest')
    admission=value(root,base+'/'+engine.ADMISSION)
    need(admission=={'schema_version':engine.DELIVERY+'.call-limit','operation_id':operation_id,
        'plan_digest':p['plan_digest'],'model_request_budget':2,'claim':engine.BUDGET_CLAIM},'original lifetime2 remains occupied')
    raws=_source_epoch(root,base,source_root)
    definitions=_constants(raws['scripts/python/_b_route_compensation_partition.py'])
    from _b_route_compensation_partition import WIRE,PROJECTION,SPELLING,DECODER
    need(all(definitions[k]==v for k,v in {'WIRE':WIRE,'PROJECTION':PROJECTION,'SPELLING':SPELLING,'DECODER':DECODER}.items()),
        'same body must retain the exact original interpretation')
    rule=_rule(raws['scripts/python/_b_route_compensation_segmented_execution.py'])
    directory,schema,out,identity,evidence=_recorded_node(root,s,packet,p,p['nodes'][0],[],rule,definitions['HEADER'])
    engine._verdict(out,schema,p['nodes'][0])
    result=value(root,directory+'/result.json');result_ref=ref(root,directory+'/result.json')
    expected={'schema_version':engine.DELIVERY,'node_id':'business','identity':identity,
        'admission':ref(root,base+'/'+engine.ADMISSION),'outcome':{
            'output_digest':codec.raw_digest(read(root,directory+'/w/output.json')),
            'execution_digest':codec.raw_digest(read(root,directory+'/execution.json'))},
        'evidence':{'thread_id':evidence['thread_id'],'turn_id':evidence['turn_id'],
            'protocol_digest':evidence['protocol_sha256'],'runtime_configuration':{
                'model':evidence['model'],'provider':'openai','reasoning_effort':'high'},
            'provider_actual_model':'unknown','physical_requests':'unknown'}}
    need(result==expected and value(root,directory+'/completed.json')==result_ref,'original durable approved prefix')
    prefix=[{'node_id':'business','result_digest':result_ref['raw_digest'],'verdict':out,'evidence':result['evidence']}]
    directory,schema,failed,identity,failed_evidence=_recorded_node(root,s,packet,p,p['nodes'][1],prefix,rule,definitions['HEADER'])
    import jsonschema
    need(not list(jsonschema.Draft202012Validator(schema).iter_errors(failed)) and failed['verdict']=='blocked'
        and sorted(r['id'] for r in failed['checks'])==p['nodes'][1]['check_ids']
        and all(r['rationale'].strip() for r in failed['checks']) and any(r['verdict']=='blocked' for r in failed['checks']),
        'completed explicit semantic refusal; transport unknown is not retryable')
    need(not review.path(root,directory+'/completed.json').exists() and
        value(root,directory+'/unknown.json')=={'schema_version':engine.DELIVERY,
            'key':codec.canonical_digest(identity),'error_type':'CodecError'},'intact original refusal and occupied unknown marker')
    return {'subject':s,'plan':p,'prefix':prefix,'failed_evidence':failed_evidence,
        'auth':auth,'source':raws,'header':definitions['HEADER']}

def _subject_transition(old,derived):
    s=deepcopy(old['subject']);current=derived.subject
    before=old['auth'];after=codec.strict_json_loads(derived.freeze_auth())
    need(set(before)==set(after)=={'schema_version','full_subject_digest','histories'} and
        before['schema_version']==after['schema_version'] and after['full_subject_digest']==codec.canonical_digest(current)
        and set(before['histories'])==set(after['histories']),
         'same complete historical owner set')
    digests={}
    for key,binding in before['histories'].items():
        expected={**binding,'current_verifier_policy':current['policy_identity']}
        need(review.raw(expected)==review.raw(after['histories'][key]),'only current verifier policy may change; same actual root/history')
        digests[codec.canonical_digest(binding)]=codec.canonical_digest(expected)
    s['policy_identity']=current['policy_identity']
    for meta in s['private_files'].values():
        need(meta['owner_auth_digest'] in digests,'actual source-bound old private owner auth')
        meta['owner_auth_digest']=digests[meta['owner_auth_digest']]
    need(review.raw(s)==review.raw(current),'exact request/current-before/effects/scope/Task/history semantics across source transition')

def _business_transition(old,derived,spec):
    need(len(spec)==2 and all(a['node_id']==b['node_id'] and a['dependencies']==b['dependencies'] and
        a['check_ids']==b['check_ids'] for a,b in zip(spec,old['plan']['nodes'],strict=True)),
        'same fixed node dependency order and complete nine checks')
    old_base=read(derived_root(derived),engine._dir(home(derived.subject['operation_id']),old['plan']['nodes'][0])+'/base-prompt.txt').decode()
    need(old_base.startswith(old['header']+'\n') and spec[0]['base_prompt'].split('\n',1)[1]==old_base.split('\n',1)[1],
         'exact complete previously approved business body under unchanged decoder')

def transition(old,derived,spec):
    _subject_transition(old,derived);_business_transition(old,derived,spec)

def _release_audit_bytes(old):
    # These exact bytes remain in original records and manifest refs. They are
    # no longer used by the renderer; do not keep duplicate audit buffers alive.
    for name in ('subject','auth','source'):old.pop(name)

def derived_root(derived):
    # All published handles bind the same actual root; no caller path alias.
    roots={str(h._root) for h in derived.handles if hasattr(h,'_root')}
    need(len(roots)==1,'one actual published-history root');return Path(next(iter(roots)))

def _load(root,operation_id):
    base=home(operation_id);m=value(root,base+'/'+MANIFEST)
    review.shape(m,('schema_version','operation_id','original_plan_digest','source_policy','current_plan_digest',
        'original_files','static_files','source_files'),'closed repair manifest')
    need(m['schema_version']==DELIVERY and m['operation_id']==operation_id and
        m['source_policy']==review.policy_identity(),'complete explicit same-source repair preparation')
    pins=value(root,base+'/segmented/source-pins.json');repo=Path(__file__).resolve().parents[2]
    need(set(m['static_files'])=={LANE+'/'+n for n in STATIC} and
        set(m['source_files'])=={LANE+'/original-source/'+Path(n).relative_to(repo).as_posix() for n in pins},
        'complete exact repair static and source inventories')
    need(_original_files(root,base)==m['original_files'],'every original attempted record remains byte exact')
    for name,digest in {**m['static_files'],**m['source_files']}.items():
        need(codec.raw_digest(read(root,base+'/'+name))==digest,'exact immutable repair support',name)
    s=value(root,base+'/'+LANE+'/subject.json');p=value(root,base+'/'+LANE+'/plan.json')
    need(s['operation_id']==operation_id and s['policy_identity']==m['source_policy'] and
        p['subject_digest']==codec.canonical_digest(s) and p['plan_digest']==m['current_plan_digest'] and
        p['source_policy']==m['source_policy'] and
        p['plan_digest']==codec.canonical_digest({k:v for k,v in p.items() if k!='plan_digest'}),
        'complete actual current repair subject/plan/source')
    need(m['original_plan_digest']==value(root,base+'/segmented/plan.json')['plan_digest'] and
        read(root,base+'/'+LANE+'/source-pins.json')==review.raw(review.policy_observations()[1]),
        'exact original plan and actual current source pins')
    return base,m,s,p

def read_subject(root,operation_id):return _load(root,operation_id)[2]

def prepare(root,derived,source_root):
    base=home(derived.subject['operation_id']);directory=review.path(root,base+'/'+LANE)
    need(not directory.exists(),'one repair only; partial preparations require reconciliation')
    old=original(root,derived.subject['operation_id'],source_root,work=derived.work)
    _subject_transition(old,derived);_release_audit_bytes(old)
    spec=engine._spec(derived);_business_transition(old,derived,spec);plan=engine._plan(derived.subject,derived.packet,spec)
    policy,pins=review.policy_observations()
    values={'subject.json':review.raw(derived.subject),'materials.json':review.raw(derived.packet['materials']),
        'roles.json':review.raw(derived.packet['roles']),'presentation.json':review.raw(derived.packet['presentation']),
        'historical-auth.json':derived.freeze_auth(),'source-pins.json':review.raw(pins),'plan.json':review.raw(plan),
        'business-base.txt':spec[0]['base_prompt'].encode(),'governance-base.txt':spec[1]['base_prompt'].encode(),
        'claim.json':review.raw({'schema_version':DELIVERY,'operation_id':derived.subject['operation_id'],
            'original_plan_digest':old['plan']['plan_digest'],'current_plan_digest':plan['plan_digest']})}
    # Measure the full new request with the real retained approved prefix.
    _prompt,_schema,_request,report=engine._request(derived.subject,derived.packet,plan,plan['nodes'][1],
        spec[1]['base_prompt'],old['prefix'])
    originals=_original_files(root,base)
    derived.recheck()
    directory.mkdir(parents=False,exist_ok=False)
    review.write_once(root,base+'/'+LANE+'/claim.json',values['claim.json'])
    for name,data in values.items():review.write_once(root,base+'/'+LANE+'/'+name,data)
    sources={}
    for name,data in _source_epoch(root,base,source_root).items():
        relative=LANE+'/original-source/'+name;review.write_once(root,base+'/'+relative,data);sources[relative]=codec.raw_digest(data)
    m={'schema_version':DELIVERY,'operation_id':derived.subject['operation_id'],
        'original_plan_digest':old['plan']['plan_digest'],'source_policy':policy,'current_plan_digest':plan['plan_digest'],
        'original_files':originals,'static_files':{LANE+'/'+k:codec.raw_digest(v) for k,v in values.items()},'source_files':sources}
    need(_original_files(root,base)==originals and review.policy_identity()==policy,'unchanged original records and source before repair publication')
    write(root,base+'/'+MANIFEST,m)
    return {'status':'review_repair_prepared','operation_id':derived.subject['operation_id'],
        'measurement':report,'original_calls_occupied':2,'additional_calls':1,'cumulative_logical_limit':3,
        'model_dispatched':False,'formal_adoption':False,'readiness':False,'runtime_verified':False}

def _current(root,derived):
    base,m,s,p=_load(root,derived.subject['operation_id'])
    old=original(root,s['operation_id'],work=derived.work)
    _subject_transition(old,derived);_release_audit_bytes(old)
    spec=engine._spec(derived);_business_transition(old,derived,spec)
    need(review.raw(derived.subject)==read(root,base+'/'+LANE+'/subject.json') and
        review.raw(engine._plan(s,derived.packet,spec))==read(root,base+'/'+LANE+'/plan.json') and
        review.raw(review.policy_observations()[1])==read(root,base+'/'+LANE+'/source-pins.json'),
        'genuine complete current-source repair partition')
    for name in ('materials','roles','presentation'):
        need(review.raw(derived.packet[name])==read(root,base+'/'+LANE+'/'+name+'.json'),'complete current repair '+name)
    need(derived.freeze_auth()==read(root,base+'/'+LANE+'/historical-auth.json') and
        spec[0]['base_prompt'].encode()==read(root,base+'/'+LANE+'/business-base.txt') and
        spec[1]['base_prompt'].encode()==read(root,base+'/'+LANE+'/governance-base.txt'),
        'complete actual current auth and closure originals')
    derived.recheck();return base,m,s,p,old

def _request(root,base,s,p,old):
    return engine._request(s,{'presentation':value(root,base+'/'+LANE+'/presentation.json')},p,p['nodes'][1],
        read(root,base+'/'+LANE+'/governance-base.txt').decode(),old['prefix'])

def _new_result(root,base,s,p,old):
    lane=base+'/'+LANE;workspace=review.path(root,lane+'/w');prompt,schema,request,report=_request(root,base,s,p,old)
    identity=engine._identity(p,p['nodes'][1],old['prefix'],request,schema,report)
    allowance=value(root,lane+'/allowance.json')
    review.shape(allowance,('schema_version','original_plan_digest','current_plan_digest','original_limit','additional_limit',
        'cumulative_limit','authorization_source','claim'),'closed additive repair allowance')
    need(allowance['schema_version']==DELIVERY and allowance['original_plan_digest']==old['plan']['plan_digest'] and
        allowance['current_plan_digest']==p['plan_digest'] and allowance['original_limit']==2 and
        allowance['additional_limit']==1 and allowance['cumulative_limit']==3 and
        all(type(allowance[k]) is int for k in ('original_limit','additional_limit','cumulative_limit')) and
        type(allowance['authorization_source']) is str and allowance['authorization_source'].strip() and
        allowance['claim']==engine.BUDGET_CLAIM,'one explicit additive allowance; no refund or original limit reset')
    need(value(root,lane+'/intent.json')=={'schema_version':DELIVERY,'identity':identity,
        'allowance':ref(root,lane+'/allowance.json')},'original single occupied repair intent')
    need(read(root,lane+'/w/prompt.txt')==prompt.encode() and read(root,lane+'/w/schema.json')==engine._schema_bytes(schema)
        and read(root,lane+'/request.txt')==request.encode() and read(root,lane+'/measurement.json')==review.raw(report),
        'complete exact repair request/schema/measurement')
    execution=value(root,lane+'/execution.json');output=read(root,lane+'/w/output.json')
    need(execution['command']==engine._command(workspace),'exact official one-call repair runner')
    receipt=receipt_from(execution)
    validate_execution(workspace,execution,receipt,'auto',output,prompt=engine._frame(prompt,schema),schema=schema,
        require_runtime=True,expected_reasoning_effort='high')
    e=receipt['model_identity_evidence'][0]
    previous=[*old['prefix'],{'evidence':old['failed_evidence']}]
    need(e['model_provider']=='openai' and e['thread_id'] not in set(s['native_threads'])|{r['evidence']['thread_id'] for r in previous}
        and e['turn_id'] not in set(s['native_turns'])|{r['evidence']['turn_id'] for r in previous},
        'new high/no-tools review independent of candidate and both previous reviews')
    engine._verdict(codec.strict_json_loads(output),schema,p['nodes'][1])
    return {'schema_version':DELIVERY,'identity':identity,'allowance':ref(root,lane+'/allowance.json'),
        'output_digest':codec.raw_digest(output),'execution_digest':codec.raw_digest(read(root,lane+'/execution.json')),
        'evidence':{'thread_id':e['thread_id'],'turn_id':e['turn_id'],'protocol_digest':e['protocol_sha256'],
            'runtime_configuration':{'model':e['model'],'provider':'openai','reasoning_effort':'high'},
            'provider_actual_model':'unknown','physical_requests':'unknown'}}

def execute(root,derived,*,model_request_budget=None,authorization_source=None,publication_only=False):
    base,m,s,p,old=_current(root,derived);lane=base+'/'+LANE
    if review.path(root,lane+'/completed.json').exists():
        result=_new_result(root,base,s,p,old)
        need(read(root,lane+'/result.json')==review.raw(result) and
            value(root,lane+'/completed.json')==ref(root,lane+'/result.json'),'durable completed repair publication')
        return {'status':'review_repair_executed','model_dispatched':False,'new_logical_calls':0,'cumulative_logical_calls':3}
    if review.path(root,lane+'/intent.json').exists():
        return {'status':'blocked','reason':'repair_pending_or_unknown_requires_original_outcome_reconciliation',
            'automatic_retry':False,'model_dispatched':False,'original_calls_occupied':2,'repair_calls_occupied':1}
    if publication_only:return {'status':'ready','model_dispatched':False,'additional_calls_required':1}
    if model_request_budget is None:return {'status':'blocked','reason':'authorization_required','model_dispatched':False,'additional_calls_required':1}
    need(type(model_request_budget) is int and model_request_budget==1 and type(authorization_source) is str and
        0<len(authorization_source.strip())<=512,'one explicit additional subscription review and recorded authorization source')
    prompt,schema,request,report=_request(root,base,s,p,old)
    identity=engine._identity(p,p['nodes'][1],old['prefix'],request,schema,report)
    allowance={'schema_version':DELIVERY,'original_plan_digest':old['plan']['plan_digest'],'current_plan_digest':p['plan_digest'],
        'original_limit':2,'additional_limit':1,'cumulative_limit':3,'authorization_source':authorization_source,'claim':engine.BUDGET_CLAIM}
    write(root,lane+'/allowance.json',allowance)
    for name,data in {'w/prompt.txt':prompt.encode(),'w/schema.json':engine._schema_bytes(schema),
        'request.txt':request.encode(),'measurement.json':review.raw(report)}.items():review.write_once(root,lane+'/'+name,data)
    write(root,lane+'/intent.json',{'schema_version':DELIVERY,'identity':identity,'allowance':ref(root,lane+'/allowance.json')})
    try:
        workspace=review.path(root,lane+'/w')
        need({p.name for p in workspace.iterdir()}=={'prompt.txt','schema.json'},'unchanged isolated one-request repair workspace')
        derived.recheck();_load(root,s['operation_id'])
        run_isolated_model(Path(__file__).with_name('codex_isolated_model_runner.py'),workspace=workspace,
            prompt_path=workspace/'prompt.txt',output_path=workspace/'output.json',timeout_sec=engine.TIMEOUT,
            wall_timeout_sec=engine.TIMEOUT+30,output_schema=workspace/'schema.json',model_request_budget=1,
            execution_log=review.path(root,lane+'/execution.json'),suppress_bytecode=True,reasoning_effort='high')
        result=_new_result(root,base,s,p,old);derived.recheck();_load(root,s['operation_id'])
        write(root,lane+'/result.json',result);write(root,lane+'/completed.json',ref(root,lane+'/result.json'))
    except BaseException as error:
        write(root,lane+'/unknown.json',{'schema_version':DELIVERY,'error_type':type(error).__name__});raise
    return {'status':'review_repair_executed','model_dispatched':True,'new_logical_calls':1,'cumulative_logical_calls':3,
        'formal_adoption':False,'readiness':False,'runtime_verified':False}

def inputs(root,subject,*,proof=None):
    work=engine.materials.compact._work(None)
    base,m,s,p=_load(root,subject['operation_id']);old=original(root,s['operation_id'],work=work)
    need(review.raw(s)==review.raw(subject),'exact current repair subject')
    result=_new_result(root,base,s,p,old);lane=base+'/'+LANE
    need(read(root,lane+'/result.json')==review.raw(result) and
        value(root,lane+'/completed.json')==ref(root,lane+'/result.json'),'complete approved repair publication')
    names=[*m['original_files'],*m['static_files'],*m['source_files'],MANIFEST,
        *[LANE+'/'+n for n in ('allowance.json','intent.json','w/prompt.txt','w/schema.json','request.txt','measurement.json',
                              'execution.json','w/output.json','result.json','completed.json')]]
    if review.path(root,lane+'/unknown.json').exists():names.append(LANE+'/unknown.json')
    # All exact originals/current runtime bytes have been verified. Keep their
    # complete refs, not duplicate raw audit buffers, across semantic rendering.
    # complete_inputs genuinely rederives the packet from the captured subject;
    # _current and historical consumers reread every needed support by digest.
    buffers={}
    refs=[ref(root,base+'/'+name) for name in names]
    evidence={'nodes':[dict(old['prefix'][0]['evidence'],source_policy=LEGACY_POLICY,scope='retained_exact_business_closure'),
        dict(result['evidence'],source_policy=s['policy_identity'],scope='fresh_current_governance_closure')],
        'scope':'explicit_source_transition_and_one_additional_review','provider_actual_model':'unknown','physical_requests':'unknown'}
    requests=[ref(root,engine._dir(base,n)+'/request.txt') for n in old['plan']['nodes']]+[ref(root,base+'/'+LANE+'/request.txt')]
    if proof is not None:
        need(review.raw(proof)==review.raw(_proof_value(s,value(root,base+'/'+LANE+'/presentation.json'),p,refs,evidence,requests)),
             'complete source-transition proof before saved before-view scope')
    return qualified._SavedInputs(qualified._MINT,Path(root).absolute(),s,buffers,proof,refs,evidence,work)

def complete_inputs(saved):
    d=qualified.model_packet(saved.root,saved.subject,context=saved)
    _current(saved.root,d);return d

def _proof_value(s,presentation,p,refs,evidence,requests):
    return {'schema_version':PROOF,'operation_id':s['operation_id'],'subject_digest':codec.canonical_digest(s),
        'policy_identity':s['policy_identity'],'delivery':DELIVERY,'claim':CLAIM,'history_claim':PUBLISHED.claim,
        'plan_digest':p['plan_digest'],'budget_claim':engine.BUDGET_CLAIM,
        'original_calls_occupied':2,'additional_calls_occupied':1,'cumulative_logical_limit':3,
        'requests_digest':codec.canonical_digest(requests),'evidence':evidence,'files':refs,
        **{k:presentation[k] for k in ('materials_digest','roles_digest','historical_auth_digest')},
        'presentation_digest':codec.canonical_digest(presentation)}

def produce_proof(root,operation_id,*,proof=None):
    s=read_subject(root,operation_id);saved=inputs(root,s,proof=proof);d=complete_inputs(saved)
    qualified.bindings(s,d);base,m,s,p=_load(root,operation_id)
    old_plan=value(root,base+'/segmented/plan.json')
    requests=[ref(root,engine._dir(base,n)+'/request.txt') for n in old_plan['nodes']]+[ref(root,base+'/'+LANE+'/request.txt')]
    result=_proof_value(s,d.packet['presentation'],p,saved.refs,saved.evidence,requests)
    if proof is not None:need(review.raw(proof)==review.raw(result),'complete original/current-source repair proof before saved scope use')
    return result,saved,d

def verify_saved_private(root,request):
    r=request['host_review_ref'];base=home(request['operation_id'])
    review.shape(r,('path','schema_version','raw_digest'),'closed repair proof reference')
    data=read(root,r['path'])
    need(r['schema_version']==PROOF and r['path']==base+'/review.json' and codec.raw_digest(data)==r['raw_digest'],
        'exact owned repair proof reference')
    expected,saved,d=produce_proof(root,request['operation_id'],proof=codec.strict_json_loads(data))
    need(data==review.raw(expected) and qualified.same(saved.subject['request'],review.request_body(request)),
        'complete canonical repair proof and exact compensation request')
    saved.refs=[r,*saved.refs];return saved,d
