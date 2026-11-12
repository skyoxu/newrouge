"""Narrow, exactly reconstructible no-Task same-plan compensation closures.

Unsupported business families return None and keep the complete closure. These
conditions select an optimization; they are not new compensation requirements.
"""
from copy import deepcopy
import json
import base64
import re

import _b_route_codec as codec
import _b_route_compact_literal as compact
import _b_route_compensation_review_materials as accounting
import _b_route_qualified_compensation_materials_v2 as materials
import _b_route_adoption_projection as projection
import _b_route_records as records

WIRE='newrouge.b-route-compensation-preserving-closures.v1'
INSTRUCTION=(
    'Collective compensation review. History verifies publication/bytes, not old-owner execution. '
    'Host checks retained-native-execution-binding.v2 request/material/capsule links; this evidence '
    'is not a formal B binding or new approval. Read all visible meaning; block missing semantic '
    'relationships. Atom links equal complete originals reviewed in the predecessor. CLI owns '
    'continuation. Use projection_decoder/json2_decoder as wire definitions. ')
PROJECTION=(
    'Typed view decoder: the original native object is complete, including all14 fields. '
    'For original_current_plan, replace only each typed_native_projection_field with that '
    'field of the formal projection: map requirement_id(s)/flow_id(s) recursively using '
    'original allocations; in definitions only, map id using definition_assignments and '
    'remove proposed_owner_key. Replace exact {kind,definition_id,proposed_owner_key} uses '
    'with the matching assigned definition id plus owner_plan_id/revision from allocations; '
    'preserve exact existing {kind,definition_id,owner_plan_id,owner_revision} uses. Preserve '
    'every other field, order, type and string. The new plan copies this whole plan, changes '
    'revision and lineage to the printed values, and rebinds only exact four-field same-plan '
    'typed owner uses to that revision. Retained views select all four named original native '
    'fields, or apply the same typed owner/id projection. No omitted source or summary. ')
SPELLING=(
    'After compact decoding, undo identity spelling in all keys and string values: '
    '~~ removes one leading ~; otherwise ~h64: plus canonical unpadded URL-safe base64 '
    'of exactly32 bytes means sha256: plus lowercase hex of those same256 bits. '
    'Other ~ prefixes are invalid. Preserve object order and reject decoded key collisions. '
    'Then apply target_projection.projection_decoder and json2_decoder. ')
# Equivalent complete decoder for this explicit closure format only.
DECODER="Canonical Python DATA literal only; never execute. Parse dict/list/tuple/string/finite-number/True/False/None; decode string escapes exactly. schema_version must be newrouge.b-route-compact-literal.v4. Preserve every type, object/array order and string character. SN/DN/PN restore strings[N]/fresh shared[N]/phrases[N]; these and RN are closed DATA names, never variables. N is ASCII decimal without leading zeros (except0), exact int not bool; references must exist, shared/phrase definitions reference only earlier entries. Phrase definitions concatenate their literal strings and earlier P pieces. (C,pieces...) concatenates restored pieces with no separators. (B,text) returns standard padded base64 of the restored text's strict UTF8 bytes. B only aliases text assembled from visible original fragments. Restore P/C/B before strings/shared and ordinary objects. HN means 'sha256:'+N in lowercase hex padded to64 digits; 0<=N<2**256, no truncation or hash computation. RN means {'r':N} with N>=0. Tuple(child,) restores {'r':restored child}; other tuples (N,values...) restore the ordered object from nonempty keysets[N] with exactly its key count. Recursively restore children. Restore object keys by removing one leading '~', otherwise expand r/o/l/s to $mvg_ref/$mvg_object/$mvg_lines/$mvg_source; all other keys literal. Original marker-like data stays data. v4 residual prefixes use the same visible P/C grammar. Every fragment is printed here; no external dictionary or omitted source. Host checks canonical spelling, digests and equality; these do not prove authorship. Use restored data; do not reproduce transport or calculate hashes."
HEADER=WIRE+' '+INSTRUCTION+SPELLING+DECODER
_HASH=re.compile(r'sha256:[0-9a-f]{64}\Z')
_MARKER=re.compile(r'~h64:[A-Za-z0-9_-]{43}\Z')


class NotApplicable(Exception):pass
def family(ok):
    if not ok:raise NotApplicable()
def same(a,b):return materials.ordered(a)==materials.ordered(b)


class _Resources:
    """Local retained JSON graphs; use the existing resource owner throughout."""
    def __init__(self,work,metrics=(),buffers=()):
        self.w=work;self.base=tuple(metrics);self.raw=tuple(buffers);self.graphs={};self.texts={}
    @property
    def metrics(self):return (*self.base,*self.graphs.values())
    @property
    def buffers(self):return (*self.raw,*self.texts.values())
    def keep(self,key,value):self.graphs[key]=compact._json_preflight(value,self.w)
    def drop(self,*keys):
        for key in keys:self.graphs.pop(key,None);self.texts.pop(key,None)
    def live(self,phase,extra=(),buffers=()):
        return accounting._live(self.w,phase,(*self.metrics,*extra),(*self.buffers,*buffers))
    def metadata(self,count,phase):
        metric=accounting._mv_metadata(self.w,count,self.metrics,self.buffers,phase)
        self.graphs[phase]=metric
    def ordered(self,value,phase):return accounting._ordered(value,self.w,self.metrics,self.buffers,phase)
    def equal(self,a,b):
        left,lm=self.ordered(a,'partition.compare.left')
        right,_=accounting._ordered(b,self.w,self.metrics,(*self.buffers,lm[5]),'partition.compare.right')
        self.w.spend(len(left)+len(right),phase='partition.compare');return left==right
    def digest(self,value):
        text,metric=self.ordered(value,'partition.digest.value')
        return accounting._ordered_digest(text,metric[5],self.w,(*self.metrics,metric),self.buffers)
    def copy(self,value,key):
        vm=compact._json_preflight(value,self.w)
        self.live('partition.copy.'+key,(vm,vm))
        self.w.spend(vm[0]+vm[1],phase='partition.copy.'+key)
        result=deepcopy(value);self.keep(key,result);return result
    def project(self,native,alloc,key,retained=False):
        vm=compact._json_preflight(native,self.w);am=compact._json_preflight(alloc,self.w)
        ids=[alloc['plan_id'],*[v for name in ('requirements','flows','commands','states')
                                  for v in alloc.get(name,{}).values()]]
        width=max(compact._utf8_size(value,self.w) for value in ids)
        # Prepay every possible projected use at the actual largest allocated
        # identity width, plus fixed new field names/scalars and both passes.
        bound=compact._metric(vm[0]+(6*width+512)*vm[1]+8192,3*vm[1]+128,vm[2]+4,phase='partition.project.bound')
        self.live('partition.project.'+key,(am,bound,bound))
        self.w.spend(8*(vm[0]+vm[1]+am[0]+am[1]),phase='partition.project.'+key)
        value=(projection.project_retained_fields if retained else projection.project_content)(native,alloc)
        self.keep(key,value);return value


def identity_spelling(value, *, decode=False, resources=None):
    """Lossless numeral spelling, never a digest in place of semantic text."""
    r=resources or _Resources(compact._work(None))
    vm=compact._json_preflight(value,r.w)
    bound=compact._metric(2*vm[0]+vm[1]+1024,vm[1],vm[2],phase='partition.identity_spelling.bound')
    r.live('partition.identity_spelling',(vm,bound))
    def string(text):
        r.w.spend(len(text)+1,phase='partition.identity_spelling.string')
        if decode:
            if text.startswith('~~'):return text[1:]
            if text.startswith('~'):
                family(_MARKER.fullmatch(text) is not None)
                raw=base64.urlsafe_b64decode(text[5:]+'=')
                family(len(raw)==32 and base64.urlsafe_b64encode(raw).decode().rstrip('=')==text[5:])
                return 'sha256:'+raw.hex()
            return text
        if text.startswith('~'):return '~'+text
        if _HASH.fullmatch(text):return '~h64:'+base64.urlsafe_b64encode(bytes.fromhex(text[7:])).decode().rstrip('=')
        return text
    def visit(node):
        r.w.spend(1,phase='partition.identity_spelling.node')
        if type(node) is str:return string(node)
        if type(node) is list:return [visit(v) for v in node]
        if type(node) is dict:
            result={}
            for key,val in node.items():
                new=string(key);family(new not in result);result[new]=visit(val)
            return result
        return node
    return visit(value)


def _new_plan(original,revision,lineage,resources=None):
    value=resources.copy(original,'new_plan_copy') if resources else deepcopy(original)
    value['revision']=revision;value['lineage']=lineage
    count=0
    for use in records._walk(value):
        if resources:resources.w.spend(32,phase='partition.typed_rebind')
        if use.get('owner_plan_id')==original['plan_id'] and 'owner_revision' in use:
            family(set(use)=={'kind','definition_id','owner_plan_id','owner_revision'}
                   and use['owner_revision']==original['revision'])
            use['owner_revision']=revision;count+=1
    return value,count


def _prepare_data(packet,work,metrics=(),buffers=()):
    frames=packet['materials']['frames'];family(len(frames)==2)
    current=next((f for f in frames if f['subject_schema']=='newrouge.b-route-qualified-compensation-review-subject.v3'),None)
    old=next((f for f in frames if f['subject_schema']=='newrouge.b-route-adoption-review-subject.v3'),None)
    family(current is not None and old is not None)
    c,o=current['semantic_fields'],old['semantic_fields'];protection=o['review_scope']['protection']
    relation=c['preview']['compensation'];native=o['native_content'];alloc=o['allocations']
    family(c['task_definitions']=={} and c['request']['selection']['binding_ref'] is None
        and not protection['tasks'] and not protection['cumulative']
        and not relation['retained_plan_refs'] and not relation['retained_binding_refs']
        and not native['selected_dependencies']
        and all(v==0 for v in protection['triplet_counts'].values()) and len(c['preview']['targets'])==1)
    native_metric=compact._json_preflight(native,work)
    work.spend(8*native_metric[1],phase='partition.selector.native_walk')
    for value in records._walk(native):
        family(set(value)!={'kind','definition_id','owner_plan_id','owner_revision'})
    source_set=o['review_scope']['source_set']
    family(source_set['value']['active_sources']==[o['source']['path']]
        and source_set['value']['active_patterns']==[o['source']['path']])
    r=_Resources(work,metrics,buffers)
    count=len(current['files'])+len(packet['materials']['documents'])+sum(len(v) for v in native['definitions'].values())+16
    r.metadata(count,'partition.metadata')
    rows={row['path']:row for row in current['files']}
    docs={node['raw_digest']:(i,node) for i,node in enumerate(packet['materials']['documents'])}
    # Reuse the original JSON2 producer before reading typed document values.
    envelope=materials._json_views(packet,work,r.metrics,r.buffers);r.keep('envelope',envelope)
    views={row['document']:row['value'] for row in envelope['views']}
    def document(path,digest=None):
        row=rows[path];index,node=docs[row['document_ref']]
        family(digest is None or row['raw_digest']==digest)
        if index in views:return views[index],node
        size=compact._utf8_size(node['text'],work)
        nodes=compact._syntax_preflight(node['text'],work,json_only=True)
        bound=compact._metric(6*size+32*nodes+2,nodes,compact.MAX_DEPTH,phase='partition.source.parse')
        r.live('partition.source.parse',(bound,),(size,));work.spend(size+nodes,phase='partition.source.parse')
        value=codec.strict_json_loads(node['text'].encode('utf-8'));r.keep('source-'+str(index),value)
        return value,node
    ref=relation['source_plan_ref'];original,node=document(ref['path'],ref['digest'])
    plans=[row['after_payload'] for row in o['targets'] if row['schema_version']==codec.PLAN_SCHEMA]
    family(len(plans)==1 and r.equal(original,plans[0]))
    new=c['preview']['targets'][0]['after_payload'];family(new['plan_id']==original['plan_id'])
    reason_size=compact._utf8_size(c['request']['reason'],work)
    r.live('partition.lineage.string',buffers=(6*reason_size+1024,));r.texts['lineage_string']=6*reason_size+1024
    lineage={'previous_plan_ref':ref,
        'change_summary':'Reviewed compensation '+c['operation_id']+': '+c['request']['reason'],
        'identity_alignment':[{'kind':kind,'previous_id':row['id'],'current_id':row['id'],
            'rationale':'Retained existing formal identity during reviewed compensation'}
            for kind,plural in (('flow','flows'),('command','commands'),('state','states'))
            for row in original['definitions'][plural]]}
    expected,typed_count=_new_plan(original,new['revision'],lineage,r);r.keep('new_plan_copy',expected)
    family(r.equal(expected,new));del expected;r.drop('new_plan_copy')
    projected=r.project(native,alloc,'projected')
    family(r.equal(projected,{k:original[k] for k in projection.FIELDS}))
    retained=r.project(native,alloc,'retained',retained=True)
    family(set(o['plan_storage']['retained_native_fields'])==set(projection.RETAINED_IN_NATIVE_PROOF)
        and r.equal(o['plan_storage']['retained_native_fields'],{k:native[k] for k in o['plan_storage']['retained_native_fields']})
        and r.equal(o['plan_storage']['retained_fields_with_host_identity_interpretation'],retained))
    wanted={source_set['path']}
    for key,owner in (('manifest_ref','source_manifest'),('ledger_ref','source_ledger')):
        source=native['source_identity'][key]
        family(source['owner']==owner and len(source['files'])==1 and source['files'][0]['path']==source['ref'])
        wanted.add(source['ref']);document(source['ref'],source['files'][0]['raw_digest'])
    family({row['path'] for row in current['files'] if 'semantic:declared_source' in row['roles']}==wanted|{o['source']['path']})
    family(all('semantic:declared_source' in rows[path]['roles'] for path in wanted))
    family(r.equal(document(source_set['path'],source_set['raw_digest'])[0],source_set['value']))
    work.spend(8*native_metric[1],phase='partition.selector.locator_walk')
    for locator in records._walk(native):
        if set(locator)=={'owner','ref','files'}:
            family({pin['path'] for pin in locator['files']}<=wanted|{o['source']['path']})
    source_nodes={rows[path]['document_ref'] for path in wanted}
    # Original document ordering is preserved, independent of path/size guesses.
    source_documents=[document(next(path for path in wanted if rows[path]['document_ref']==node['raw_digest']))[0]
        for node in packet['materials']['documents'] if node['raw_digest'] in source_nodes]
    atoms={'native':native,'original_current_plan':original,'new_plan':new,'selected_history':o['current_selection'],
           'source_object':o['source'],'source_text':o['source']['text']}
    for i,value in enumerate(source_documents):atoms['source_document_'+str(i)]=value
    formal={k:({'typed_native_projection_field':k} if k in projection.FIELDS else value) for k,value in original.items()}
    assignments={plural:[{'native_id':a['id'],'formal_id':b['id']} for a,b in zip(native['definitions'][plural],projected['definitions'][plural],strict=True)]
                 for plural in ('flows','commands','states')}
    business={'schema_version':WIRE,'kind':'complete_business',
        'atoms':{**atoms,'original_current_plan':formal,'new_plan':{'original_plan':'original_current_plan',
                  'revision':new['revision'],'lineage':lineage}},
        'source':o['source'],'original_lineage':original['lineage'],
        'source_controls':{'legacy_manifest_requirement':{k:protection['legacy_manifest_requirement'][k] for k in ('schema_version','state','reason')},
            **{k:protection[k] for k in ('authorization','verification_limits')}},
        'source_set':source_set,'typed_original_allocations':alloc,'identity_alignment':o['identity_alignment'],
        'old_current_new_scope':relation,'request':c['request'],'source_documents':source_documents}
    target_projection={'atom_order':list(atoms),
        'original_current_plan':business['atoms'].pop('original_current_plan'),
        'new_plan':business['atoms'].pop('new_plan'),
        'definition_assignments':assignments,'projection_decoder':PROJECTION}
    del projected,retained;r.drop('projected','retained');r.keep('business',business)
    r.metadata(len(atoms),'partition.atom_index')
    signatures={};shapes=set();signature_bytes=0
    def shape(value):return (type(value),frozenset(value) if type(value) is dict else len(value))
    for name,value in atoms.items():
        text,vm=r.ordered(value,'partition.atom.identity')
        work.spend(len(text)+len(name),phase='partition.atom.index')
        signature_bytes+=vm[5];r.live('partition.atom.retained',buffers=(signature_bytes,))
        r.texts['signatures']=signature_bytes;signatures[text]=name;shapes.add(shape(value))
    em=r.graphs['envelope'];r.live('partition.remaining.cow',(em,));r.graphs['remaining_cow']=em
    replacements=[];path_bytes=0
    def split(value,path=()):
        nonlocal path_bytes
        work.spend(32+sum(len(k) for k in value) if type(value) is dict else 32,phase='partition.complete_walk')
        if type(value) in (dict,str) and shape(value) in shapes:
            text,_=r.ordered(value,'partition.match');work.spend(len(text),phase='partition.match.lookup')
            name=signatures.get(text)
            del text
            if name is not None:
                added=8192+128*len(path)+6*sum(len(p) for p in path if type(p) is str)
                path_bytes+=added;r.live('partition.path.before_append',buffers=(path_bytes,));r.texts['paths']=path_bytes
                replacements.append({'path':list(path),'atom':name});return {'reviewed_business_atom':name}
        if type(value) is dict:return {k:split(v,path+(k,)) for k,v in value.items()}
        if type(value) is list:return [split(v,path+(i,)) for i,v in enumerate(value)]
        return value
    remaining=split(envelope)
    governance={'schema_version':WIRE,'kind':'complete_governance_joint','governance_packet':remaining,
        'target_projection':target_projection,'exact_replacements':replacements,'business_atoms_digest':r.digest(atoms),
        'typed_owner_rebindings':typed_count,
        'json2_decoder':'For each views row, replace packet_core.materials.documents[document].text placeholder '
            '{json2_view: row ordinal} by the complete value serialized as JSON ensure_ascii=False, indent=2, '
            'allow_nan=False and one final LF. Preserve every field order, type and string.',
        'claim':'All governance originals are complete; business links equal complete originals in the verified predecessor.'}
    del signatures,shapes,text;r.drop('signatures','remaining_cow');r.keep('governance',governance)
    decoded=decode_business(business,governance['target_projection'],resources=r)
    family(r.equal(decoded,atoms))
    restored_envelope=restore_governance(governance,decoded,resources=r)
    family(r.equal(restored_envelope,envelope))
    del envelope,decoded,views,document,original,atoms
    r.drop('envelope','decoded')
    # The restoration owner accounts for its own envelope graph internally.
    r.graphs.pop('restored_envelope')
    restored=materials._restore_json_views(restored_envelope,work,r.metrics,r.buffers)
    r.keep('restored_packet',restored);del restored_envelope
    r.live('partition.complete.validation',buffers=(2*r.graphs['restored_packet'][5],))
    materials.validate(restored,work=work);family(r.equal(packet,restored))
    return business,governance


def decode_business(value,target,resources=None):
    r=resources or _Resources(compact._work(None))
    r.metadata(len(value['atoms'])+8,'partition.decode.metadata')
    family(set(target)=={'atom_order','original_current_plan','new_plan','definition_assignments','projection_decoder'}
        and target['projection_decoder']==PROJECTION)
    combined={**value['atoms'],**{k:target[k] for k in ('original_current_plan','new_plan')}}
    order=target['atom_order'];family(type(order) is list and len(order)==len(set(order)) and set(order)==set(combined))
    atoms=r.copy({k:combined[k] for k in order},'decoded');native=atoms['native'];alloc=value['typed_original_allocations']
    projected=r.project(native,alloc,'decoded_projected');formal=atoms['original_current_plan']
    for key in projection.FIELDS:
        family(formal[key]=={'typed_native_projection_field':key});formal[key]=projected[key]
    new=atoms['new_plan'];family(set(new)=={'original_plan','revision','lineage'} and new['original_plan']=='original_current_plan')
    atoms['new_plan'],_count=_new_plan(formal,new['revision'],new['lineage'],r)
    assignments={plural:[{'native_id':a['id'],'formal_id':b['id']} for a,b in zip(native['definitions'][plural],projected['definitions'][plural],strict=True)]
                 for plural in ('flows','commands','states')}
    family(r.equal(assignments,target['definition_assignments']))
    del projected;r.drop('decoded_projected','new_plan_copy');r.keep('decoded',atoms)
    return atoms


def restore_governance(value,atoms,resources=None):
    r=resources or _Resources(compact._work(None))
    family(r.digest(atoms)==value['business_atoms_digest'])
    r.metadata(len(value['exact_replacements'])+1,'partition.restore.metadata')
    core=r.copy(value['governance_packet'],'restored_envelope');seen=set();used=set()
    for row in value['exact_replacements']:
        family(type(row) is dict and set(row)=={'path','atom'} and type(row['atom']) is str)
        path=row['path'];family(type(path) is list and path and tuple(path) not in seen
            and all(type(p) is str or (type(p) is int and p>=0) for p in path))
        r.w.spend(64+32*len(path),phase='partition.restore.path')
        family(not any(tuple(path[:len(p)])==p or p[:len(path)]==tuple(path) for p in seen))
        seen.add(tuple(path));parent=core
        for part in path[:-1]:parent=parent[part]
        family(parent[path[-1]]=={'reviewed_business_atom':row['atom']} and row['atom'] in atoms)
        # Parsed JSON is immutable here; shared references preserve exact JSON
        # values without making N redundant whole-business deepcopy graphs.
        parent[path[-1]]=atoms[row['atom']];used.add(row['atom'])
    family(used==set(atoms));r.keep('restored_envelope',core)
    return core


def _render(derived,payload,others=(),base_buffers=()):
    derived.freeze_auth();w=derived.work;pm,pb=derived.private_metrics()
    pm += [compact._json_preflight(v,w) for v in (derived.packet,*others)]
    pb += list(base_buffers)
    original,metric=accounting._ordered(payload,w,pm,pb,'closure.original')
    accounting._live(w,'closure.snapshot',(*pm,metric,metric),(*pb,metric[5]))
    resources=_Resources(w,(*pm,metric),(*pb,metric[5]))
    snapshot=identity_spelling(payload,resources=resources)
    sm=compact._json_preflight(snapshot,w)
    wire,wm=accounting._ordered(snapshot,w,(*pm,metric,sm),(*pb,metric[5]),'closure.wire')
    held=accounting._live(w,'closure.encode',(*pm,metric,sm),(*pb,metric[5],wm[5],compact.MAX_ENCODED_BYTES))
    before=getattr(w,'_residual_retained',None);w._residual_retained=(held[0]-compact.MAX_ENCODED_BYTES,held[1]-1,held[2])
    try:body=compact._ATOMIC_PRODUCER(snapshot,schema=compact.RESIDUAL_SCHEMA,work=w)
    finally:w._residual_retained=before
    del snapshot
    size=compact._encoded_preflight(body,w)
    retained=accounting._live(w,'closure.decode',(*pm,metric),(*pb,metric[5],wm[5],size))
    restored,schema=compact._decode_complete(body,w,retained=retained)
    family(schema==compact.RESIDUAL_SCHEMA)
    text,rm=accounting._ordered(restored,w,(*pm,metric),(*pb,metric[5],wm[5],size),'closure.restored_wire')
    w.spend(len(text)+len(wire),phase='closure.wire.exact');family(text==wire)
    del text,wire
    decoded=identity_spelling(restored,decode=True,resources=_Resources(w,(*pm,metric,rm),(*pb,metric[5],size)))
    dm=compact._json_preflight(decoded,w)
    text,_=accounting._ordered(decoded,w,(*pm,metric,rm,dm),(*pb,metric[5],size),'closure.restored')
    w.spend(len(text)+len(original),phase='closure.exact');family(text==original)
    current,_=accounting._ordered(payload,w,(*pm,metric,rm,dm),(*pb,metric[5],size,len(text)),'closure.current')
    w.spend(len(current)+len(original),phase='closure.current.exact');family(current==original)
    del text,current,restored,decoded,original
    hb=compact._utf8_size(HEADER,w)
    accounting._live(w,'closure.frame',(*pm,metric),(*pb,size,hb,hb+size+1))
    return compact._join([HEADER,'\n',body],w)


def build(derived):
    derived.freeze_auth();w=derived.work;metrics,buffers=derived.private_metrics()
    metrics.append(compact._json_preflight(derived.packet,w))
    try:business,governance=_prepare_data(derived.packet,w,metrics,buffers)
    except NotApplicable:return None
    # Both actual payloads are retained while encoding. The second call also
    # reserves the already produced first frame; no fresh account is created.
    first=_render(derived,business,(governance,))
    first_bytes=compact._utf8_size(first,w)
    second=_render(derived,governance,(business,),(2*first_bytes,))
    checks=derived.packet['presentation']['required_checks']
    business_checks=sorted(['cumulative_requirements_and_obligations','existing_formal_semantic_sources'])
    family(set(business_checks)<=set(checks))
    frames=derived.packet['materials']['frames']
    old_index=next(i for i,f in enumerate(frames) if f['subject_schema']=='newrouge.b-route-adoption-review-subject.v3')
    current_index=1-old_index
    old_path='/materials/frames/'+str(old_index)+'/semantic_fields'
    current_path='/materials/frames/'+str(current_index)+'/semantic_fields'
    paths=[old_path+'/'+field for field in ('source','native_content','current_selection',
        'allocations','identity_alignment','review_scope/source_set','review_scope/protection/authorization',
        'review_scope/protection/verification_limits','review_scope/protection/legacy_manifest_requirement/schema_version',
        'review_scope/protection/legacy_manifest_requirement/state','review_scope/protection/legacy_manifest_requirement/reason')]
    paths += [current_path+'/'+field for field in ('request','preview/compensation')]
    old_fields=frames[old_index]['semantic_fields'];current_fields=frames[current_index]['semantic_fields']
    names={old_fields['review_scope']['source_set']['path'],
        old_fields['native_content']['source_identity']['manifest_ref']['ref'],
        old_fields['native_content']['source_identity']['ledger_ref']['ref'],
        current_fields['preview']['compensation']['source_plan_ref']['path']}
    digests={row['document_ref'] for row in frames[current_index]['files'] if row['path'] in names}
    paths += ['/materials/documents/'+str(i) for i,node in enumerate(derived.packet['materials']['documents'])
              if node['raw_digest'] in digests]
    return [{'node_id':'business','dependencies':[],'check_ids':business_checks,'source_paths':paths,'base_prompt':first},
        {'node_id':'governance-joint','dependencies':['business'],'check_ids':[c for c in checks if c not in business_checks],
         'source_paths':['/'],'base_prompt':second}]
