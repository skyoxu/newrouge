"""Neutral byte graphs. No actual fiscal/native qualification.

Only the pure local validator is imported. Every source, native row, model
identity, publication and result below is synthetic DATA, never owner evidence.
"""
from copy import deepcopy
import hashlib
import json
import unittest
import _b_route_segmented_fiscal_prefix as prefix


def wire(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def ident(value):
    return 'sha256:'+sha(wire(value))

def ref(path, schema, raw=b'neutral'):
    return {'path':path, 'schema_version':schema, 'raw_digest':'sha256:'+sha(raw)}

def chain(events):
    members={};previous=None
    for index,event in enumerate(events,1):
        body={'sequence':index,'previous':previous,'event':deepcopy(event)}
        row={**body,'sha256':sha(wire(body))};previous=row['sha256']
        members['%06d.json'%index]=wire(row)+b'\n'
    return members

def inventory(members):
    return {name:sha(raw) for name,raw in members.items()}

def events_of(members):
    return [json.loads(raw)['event'] for name,raw in sorted(members.items()) if name!='STOP.json']

def neutral_graph(completed=8, pending=False, persisted=True, stopped=False, observed_outcome=False, planner='capability'):
    labels=['A','B'] if planner=='capability' else ['A','B','C']
    mapping={label:'candidate-'+str(i+1) for i,label in enumerate(labels)}
    nodes=[]
    for phase,short,prev in [('generation','g',None),('synthesis','s','g'),('independent-review','r','s')]:
        for label in labels:
            nodes.append({'node_id':short+label,'phase':phase,'ordinal':len(nodes),'candidate_labels':[label],
                'segment_ids':['s'],'obligation_ids':['o'],'dependencies':[] if prev is None else [prev+label],
                'output_reserve':26000,'final':False})
    for node_id,parents,final in [('panel',['r'+label for label in labels],False),('final',['panel'],True)]:
        nodes.append({'node_id':node_id,'phase':'selection','ordinal':len(nodes),'candidate_labels':labels[:],
            'segment_ids':['s'],'obligation_ids':['o'],'dependencies':parents,'output_reserve':26000,'final':final})
    n=len(nodes)
    policy={'role':'neutral-request-policy','configured_reasoning_effort':'high'}
    runtime={'role':'neutral-runtime','configured_reasoning_effort':'high','provider_actual_reasoning':'unknown'}
    claim={'schema_version':prefix.CLAIM,'kind':'claim','allocation_id':'neutral-allocation',
        'binding':{'root':'C:/neutral/owner','source_root':'C:/neutral/source','run_id':'neutral-run',
            'planner':planner,'profile':'3b-capabilities-v1' if planner=='capability' else '3b-mvg-v1','epoch':7,'plan_digest':ident('complete-neutral-plan'),
            'source_input_identity':ident('neutral-full-source'),'source_policy_digest':ident('neutral-source-policy'),
            'request_policy_digest':ident(policy),'runtime_identity_digest':ident(runtime)},
        'nodes':nodes,'node_catalog_digest':ident(nodes),'candidate_labels':labels,'candidate_lineages':mapping,
        'hold':n,'base_paid_or_unknown':83,'outside_guard':181,'guard_occupancy':181+n,'campaign_limit':290,'released':0,
        'retained_profile_calls':0,'retained_lineage_calls':{v:0 for v in mapping.values()},
        'time_policy':{'supports_synthesis_budget':True,'retained_total_active_seconds':0,
                       'retained_lineage_active_seconds':{v:0 for v in mapping.values()}},'context_limit':96000}
    events=[claim];observations=[];result_hashes={}
    count=completed+int(pending)
    for i,node in enumerate(nodes[:count]):
        node_id=node['node_id'];rid='neutral-run:dispatch:'+str(i+1);prompt=('neutral-'+node_id).encode()
        request={'protocol':prefix.PROTOCOL,'request_sha256':'sha256:'+sha(prompt),
            'plan_digest':claim['binding']['plan_digest'],'node_id':node_id,'phase':node['phase'],
            'input_measurement':{'request_sha256':'sha256:'+sha(prompt),'request_chars':len(prompt),
                'request_bytes':len(prompt),'max_bytes':1024*1024,'max_input_tokens':96000,
                'reserved_continuation_tokens':26000,'truncation_allowed':False,
                'input_token_estimate':len(prompt),'token_counter':'utf8_byte_upper_bound','token_counts':{}},
            'output_reserve':26000,'source_hashes':policy,'schema_digest':ident('neutral-output-schema'),
            'request_ref':ref('work/'+node_id+'/prompt.txt','newrouge.b-route-segmented-prompt.v1',prompt),
            'schema_ref':ref('work/'+node_id+'/schema.json','newrouge.b-route-segmented-output-schema.v1'),
            'input_archive_ref':ref('work/'+node_id+'/input-archive.json','newrouge.b-route-segmented-input-archive.v1'),
            'timeout_sec':1}
        lineages=[] if node['phase']=='selection' else [mapping[node['candidate_labels'][0]]]
        reservation={'schema_version':prefix.NATIVE_CLAIM,'protocol':prefix.PROTOCOL,'number':i+1,
            'reservation_id':rid,'run_id':'neutral-run','phase':node['phase'],
            'candidate':lineages[0] if lineages else None,'generation':1,'execution':1,
            'candidate_labels':node['candidate_labels'][:],'lineage_ids':lineages,
            'reserved_at_utc':'2000-01-01T00:00:00Z','status':'reserved','request_identity':request,
            'workspace':'C:/neutral/owner/work/'+node_id,'timeout_sec':1,'model_identity':runtime}
        native={'schema_version':prefix.NATIVE_CLAIM,'protocol':prefix.PROTOCOL,'plan_digest':claim['binding']['plan_digest'],
            'node':node,'reservation':reservation,'registry_epoch':7,
            'funding_at_reserve':{'schema_version':'newrouge.story25-native-funding.v1',
                'paid_or_unknown_before_run':83,'campaign_limit':290,'subsequent_full_reservation':0,
                'maximum_native_charges':n,'released':0,'retained_profile_calls':0,
                'retained_lineage_calls':{v:0 for v in mapping.values()},'pending_encumbrances':[],'profile_evidence':[]},'parents':{d:result_hashes[d] for d in node['dependencies']},
            'native_after_digest':ident('neutral-native-'+node_id),'journal_ref':'journal/'+node_id+'.json'}
        native_raw=wire(native)+b'\n';path='work/'+node_id+'/claim.json'
        common={'allocation_id':claim['allocation_id'],'node_id':node_id,'ordinal':i,'reservation_id':rid,
                'paid_or_unknown':83+i+1,'guard_occupancy':181+n,'hold':n,'released':0}
        intent={**common,'schema_version':prefix.INTENT,'kind':'intent','node_digest':ident(node),
            'reservation':reservation,'reservation_digest':ident(reservation),'request_identity_digest':ident(request),
            'native_claim_ref':ref(path,prefix.NATIVE_CLAIM,native_raw)}
        events.append(intent)
        result_digest=ident('neutral-result-'+node_id)
        outcome={'status':'completed','completed_at_utc':'2000-01-01T00:00:01Z',
                 'output_sha256':ident('neutral-output-'+node_id),'active_elapsed_seconds':0.25,
                 'segmented_result_digest':result_digest}
        outcome_raw=wire(outcome)+b'\n'
        done=i<completed
        observations.append({'node_id':node_id,'claim_path':path,
            'claim_raw':native_raw if done or persisted else None,
            'outcome_raw':outcome_raw if done or observed_outcome else None,
            'verified_result_digest':result_digest if done or observed_outcome else None})
        if done:
            intent_hash=json.loads(chain(events)['%06d.json'%len(events)])['sha256']
            events.append({**common,'schema_version':prefix.OUTCOME,'kind':'outcome','intent_row_sha256':intent_hash,
                           'native_outcome_digest':'sha256:'+sha(outcome_raw),'verified_result_digest':result_digest})
            result_hashes[node_id]=result_digest
    members=chain(events)
    if stopped:
        last=json.loads(members['%06d.json'%len(events)])
        stop={'schema_version':prefix.STOP,'allocation_id':claim['allocation_id'],
              'claim_row_sha256':json.loads(members['000001.json'])['sha256'],'last_sequence':len(events),
              'last_row_sha256':last['sha256'],'hold':n,'paid_or_unknown':83+count,'guard_occupancy':181+n,
              'campaign_limit':290,'released':0,'retry_allowed':False,'reason_code':'neutral-unknown-retained'}
        members['STOP.json']=wire(stop)+b'\n'
    return {'members':members,'expected_inventory':inventory(members),'expected_claim':deepcopy(claim),
            'native_observations':observations,
            'expected_state':'retained-stop' if stopped else 'completed' if completed==n else 'open-prefix'}

def validate(graph):
    return prefix.validate_prefix(**graph)

def replace_events(graph, events, *, replace_expected_claim=False):
    graph['members']=chain(events);graph['expected_inventory']=inventory(graph['members'])
    if replace_expected_claim:graph['expected_claim']=deepcopy(events[0])


class FinancialPrefixTests(unittest.TestCase):
    def test_complete_eight_nodes_and_cold_replay_are_facts_only(self):
        graph=neutral_graph();before=deepcopy(graph);facts=validate(graph)
        self.assertEqual(facts,validate(deepcopy(graph)))
        self.assertEqual(graph,before)
        self.assertEqual(facts['last_sequence'],17)
        self.assertEqual(facts['intent_count'],8)
        self.assertEqual(facts['paid_or_unknown'],91)
        self.assertEqual(facts['guard_occupancy'],189)
        self.assertEqual(facts['hold'],8)
        self.assertEqual(facts['prefix_disposition'],'complete')
        self.assertIsNone(facts['next_unseen_node_id'])
        mvg=validate(neutral_graph(11,planner='mvg'))
        self.assertEqual((mvg['hold'],mvg['last_sequence'],mvg['paid_or_unknown'],mvg['guard_occupancy']),(11,23,94,192))
        self.assertIs(mvg['dispatch_authorized'],False)
        for flag in ('dispatch_authorized','append_authorized','redispatch_allowed',
                     'live_member_closure_verified','native_qualification_verified','opaque_grant'):
            self.assertIs(facts[flag],False)

    def test_every_settled_and_unsettled_prefix_retains_full_hold(self):
        for count in range(8):
            settled=validate(neutral_graph(count))
            self.assertEqual(settled['next_unseen_node_id'],neutral_graph(count)['expected_claim']['nodes'][count]['node_id'])
            for persisted in (False,True):
                with self.subTest(count=count,persisted=persisted):
                    facts=validate(neutral_graph(count,pending=True,persisted=persisted))
                    self.assertEqual(facts['hold'],8)
                    self.assertEqual(facts['guard_occupancy'],189)
                    self.assertEqual(facts['paid_or_unknown'],83+count+1)
                    self.assertEqual(facts['prefix_disposition'],'unsettled-intent')
                    self.assertIsNone(facts['next_unseen_node_id'])
                    self.assertIs(facts['redispatch_allowed'],False)
        graph=neutral_graph(2,pending=True,observed_outcome=True)
        self.assertEqual(validate(graph)['prefix_disposition'],'unsettled-intent')

    def test_duplicate_reorder_version_hash_and_sequence_reject(self):
        for kind in ('duplicate','reorder','version','hash','gap','bool_sequence','raw_noncanonical','duplicate_JSON'):
            with self.subTest(kind=kind):
                graph=neutral_graph(2);events=events_of(graph['members'])
                if kind=='duplicate':events.insert(3,deepcopy(events[1]));replace_events(graph,events)
                elif kind=='reorder':events[1],events[3]=events[3],events[1];replace_events(graph,events)
                elif kind=='version':events[1]['schema_version']='task.story29.unit-native-profile-funding.v1';replace_events(graph,events)
                elif kind=='gap':graph['members']['000099.json']=graph['members'].pop('000003.json')
                else:
                    row=json.loads(graph['members']['000002.json'])
                    if kind=='hash':row['sha256']='0'*64;raw=wire(row)+b'\n'
                    elif kind=='bool_sequence':row['sequence']=True;row['sha256']=sha(wire({k:v for k,v in row.items() if k!='sha256'}));raw=wire(row)+b'\n'
                    elif kind=='raw_noncanonical':raw=json.dumps(row,indent=2).encode()+b'\n'
                    else:raw=b'{"sequence":2,"sequence":2}'
                    graph['members']['000002.json']=raw
                graph['expected_inventory']=inventory(graph['members'])
                with self.assertRaises(prefix.PrefixError):validate(graph)

    def test_STOP_presence_hash_chain_and_fullhold_are_not_optional(self):
        for completed,pending in ((0,False),(2,True),(8,False)):
            facts=validate(neutral_graph(completed,pending=pending,stopped=True))
            self.assertEqual(facts['prefix_disposition'],'retained-stop')
            self.assertIsNone(facts['next_unseen_node_id'])
            self.assertEqual(facts['hold'],8)
        for kind in ('inventory_omission','terminal_omission','retry','refund','last_hash','hold','bool_paid'):
            graph=neutral_graph(2,pending=True,stopped=True)
            if 'omission' in kind:
                del graph['members']['STOP.json']
                if kind=='terminal_omission':graph['expected_inventory']=inventory(graph['members'])
            else:
                stop=json.loads(graph['members']['STOP.json'])
                key,value={'retry':('retry_allowed',True),'refund':('released',1),'last_hash':('last_row_sha256','0'*64),
                           'hold':('hold',1),'bool_paid':('paid_or_unknown',True)}[kind]
                stop[key]=value;graph['members']['STOP.json']=wire(stop)+b'\n';graph['expected_inventory']=inventory(graph['members'])
            with self.subTest(kind=kind):
                with self.assertRaises(prefix.PrefixError):validate(graph)

    def test_claim_bounds_catalog_and_bool_counts_reject(self):
        mutations=[('hold',1),('hold',True),('outside_guard',True),('outside_guard',285),('base_paid_or_unknown',190),
                   ('campaign_limit',True),('campaign_limit',291),('released',1),('guard_occupancy',False),
                   ('retained_profile_calls',90),('retained_profile_calls',True),('context_limit',96001),
                   ('node_catalog_digest','sha256:'+'0'*64)]
        for key,value in mutations:
            graph=neutral_graph(0);events=events_of(graph['members']);events[0][key]=value
            if key=='outside_guard' and type(value) is int:events[0]['guard_occupancy']=value+8
            replace_events(graph,events,replace_expected_claim=True)
            with self.subTest(key=key,value=value):
                with self.assertRaises(prefix.PrefixError):validate(graph)
        for key,value in [('retained_lineage_calls',{'candidate-1':63}),
                          ('time_policy',{'supports_synthesis_budget':True,'retained_total_active_seconds':13500,'retained_lineage_active_seconds':{}})]:
            graph=neutral_graph(0);events=events_of(graph['members']);events[0][key]=value;replace_events(graph,events,replace_expected_claim=True)
            with self.assertRaises(prefix.PrefixError):validate(graph)

    def test_request_reservation_and_native_binding_drift_reject(self):
        for kind in ('request_node','request_policy','schema_digest','input70k','truncation','timeout','bool_timeout','reservation_id','runtime','native_raw','native_parent','native_funding_bool'):
            graph=neutral_graph(1);events=events_of(graph['members']);intent=events[1];r=intent['reservation'];q=r['request_identity']
            if kind=='request_node':q['node_id']='foreign'
            elif kind=='request_policy':q['source_hashes']={'foreign':True}
            elif kind=='schema_digest':q['schema_digest']=ident('foreign-schema')
            elif kind=='input70k':q['input_measurement']['input_token_estimate']=70001
            elif kind=='truncation':q['input_measurement']['truncation_allowed']=True
            elif kind=='timeout':r['timeout_sec']=q['timeout_sec']=2701
            elif kind=='bool_timeout':r['timeout_sec']=q['timeout_sec']=True
            elif kind=='reservation_id':r['reservation_id']='foreign:dispatch:1'
            elif kind=='runtime':r['model_identity']={'foreign':True}
            elif kind=='native_raw':graph['native_observations'][0]['claim_raw']+=b' '
            else:
                native=json.loads(graph['native_observations'][0]['claim_raw'])
                if kind=='native_parent':native['parents']={'foreign':ident('foreign')}
                else:native['funding_at_reserve']['retained_profile_calls']=True
                raw=wire(native)+b'\n';graph['native_observations'][0]['claim_raw']=raw;intent['native_claim_ref']['raw_digest']='sha256:'+sha(raw)
            intent['reservation_digest']=ident(r);intent['request_identity_digest']=ident(q)
            # Re-sign financial chain so this reaches semantic identity checks.
            events[2]['intent_row_sha256']=json.loads(chain(events[:2])['000002.json'])['sha256']
            replace_events(graph,events)
            with self.subTest(kind=kind):
                with self.assertRaises(prefix.PrefixError):validate(graph)

    def test_unknown_or_partial_cannot_advance_or_fake_completion(self):
        graph=neutral_graph(1,pending=True,persisted=False);facts=validate(graph)
        self.assertIsNone(facts['next_unseen_node_id'])
        for kind in ('advance','missing_native_for_outcome','extra_native','observed_result_without_outcome','observed_over_time','missing_all_outcomes'):
            graph=neutral_graph(1,pending=True,persisted=False)
            if kind=='advance':
                events=events_of(neutral_graph(2,pending=True)['members']);del events[4];replace_events(graph,events)
            elif kind=='missing_native_for_outcome':graph=neutral_graph(1);graph['native_observations'][0]['claim_raw']=None
            elif kind=='extra_native':graph['native_observations'].append(deepcopy(graph['native_observations'][0]))
            elif kind=='observed_result_without_outcome':graph['native_observations'][-1]['verified_result_digest']=ident('forged-result');graph['native_observations'][-1]['claim_raw']=neutral_graph(1,pending=True)['native_observations'][-1]['claim_raw']
            elif kind=='observed_over_time':
                graph=neutral_graph(1,pending=True,observed_outcome=True)
                raw=json.loads(graph['native_observations'][-1]['outcome_raw']);raw['active_elapsed_seconds']=13501
                graph['native_observations'][-1]['outcome_raw']=wire(raw)+b'\n'
            else:graph['expected_state']='completed'
            with self.subTest(kind=kind):
                with self.assertRaises(prefix.PrefixError):validate(graph)

    def test_outcome_charges_once_and_wrong_outcome_or_old_claim_reject(self):
        graph=neutral_graph(1);facts=validate(graph)
        self.assertEqual(facts['intent_count'],1);self.assertEqual(facts['paid_or_unknown'],84)
        for kind in ('second_charge','outcome_digest','native_result','active_time','old_claim','owner_claim_drift'):
            graph=neutral_graph(1);events=events_of(graph['members'])
            if kind=='second_charge':events[2]['paid_or_unknown']=85
            elif kind=='outcome_digest':events[2]['native_outcome_digest']=ident('wrong')
            elif kind in ('native_result','active_time'):
                raw=json.loads(graph['native_observations'][0]['outcome_raw'])
                if kind=='native_result':raw['segmented_result_digest']=ident('wrong')
                else:raw['active_elapsed_seconds']=13501
                native_raw=wire(raw)+b'\n';graph['native_observations'][0]['outcome_raw']=native_raw;events[2]['native_outcome_digest']='sha256:'+sha(native_raw)
            elif kind=='old_claim':events[0]['schema_version']='task.story29.unit-native-profile-funding.v1';graph['expected_claim']=deepcopy(events[0])
            else:events[0]['binding']['source_input_identity']=ident('different-owner-input')
            replace_events(graph,events)
            with self.subTest(kind=kind):
                with self.assertRaises(prefix.PrefixError):validate(graph)
