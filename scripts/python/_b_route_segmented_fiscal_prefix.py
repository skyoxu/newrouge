"""Pure DATA validation of a separately versioned finite financial prefix.

No IO, lock, clock, claim writer, namespace, opaque mint, model or dispatch API.
Inputs must later come from genuine Root/native owners. Successful validation
proves consistency of supplied bytes only, never completeness of a live graph.
"""
import hashlib
import json
import math
import re

CLAIM = 'task.segmented-schedule-financial-claim.v1'
INTENT = 'task.segmented-schedule-financial-intent.v1'
OUTCOME = 'task.segmented-schedule-financial-outcome.v1'
STOP = 'task.segmented-schedule-financial-stop.v1'
FACTS = 'task.segmented-schedule-financial-prefix-facts.v1'
PROTOCOL = 'newrouge.b-route-segmented-workflow.v1'
NATIVE_CLAIM = 'newrouge.b-route-segmented-claim.v1'
PHASES = ('generation', 'synthesis', 'independent-review', 'selection')
PROFILES = {'capability': ('3b-capabilities-v1', 96, 2), 'mvg': ('3b-mvg-v1', 192, 3)}
NODE_FIELDS = set('node_id phase ordinal candidate_labels segment_ids obligation_ids dependencies output_reserve final'.split())
RESERVATION_FIELDS = set('schema_version protocol number reservation_id run_id phase candidate generation execution candidate_labels lineage_ids reserved_at_utc status request_identity workspace timeout_sec model_identity'.split())
REQUEST_FIELDS = set('protocol request_sha256 plan_digest node_id phase input_measurement output_reserve source_hashes schema_digest request_ref schema_ref timeout_sec input_archive_ref'.split())
NATIVE_FIELDS = set('schema_version protocol plan_digest node reservation registry_epoch funding_at_reserve parents native_after_digest journal_ref'.split())

class PrefixError(ValueError):
    pass

def need(value, reason):
    if not value:
        raise PrefixError('segmented_financial_prefix:' + reason)

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def identity(value):
    return 'sha256:' + digest(canonical(value))

def parse(raw):
    need(type(raw) is bytes, 'raw_bytes_required')
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate_JSON_key')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _x: (_ for _ in ()).throw(PrefixError('segmented_financial_prefix:JSON_nonfinite')))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise PrefixError('segmented_financial_prefix:invalid_JSON') from error

def keys(value, names, reason):
    need(type(value) is dict and set(value) == set(names), reason)

def integer(value, minimum=0, maximum=290):
    return type(value) is int and minimum <= value <= maximum

def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0

def hashed(value, prefixed=True):
    return type(value) is str and re.fullmatch(('sha256:' if prefixed else '') + '[0-9a-f]{64}', value) is not None

def text(value):
    return type(value) is str and bool(value) and '\x00' not in value

def strings(value, *, empty=False):
    return type(value) is list and (empty or bool(value)) and all(text(x) for x in value) and len(set(value)) == len(value)

def relative(value):
    return (text(value) and '\\' not in value and ':' not in value and not value.startswith('/')
            and all(p not in ('', '.', '..') for p in value.split('/')))

def reference(value, schema=None):
    keys(value, ('path', 'schema_version', 'raw_digest'), 'reference_shape')
    need(relative(value['path']) and text(value['schema_version']) and hashed(value['raw_digest']), 'reference_identity')
    need(schema is None or value['schema_version'] == schema, 'reference_version')

def _claim(claim):
    keys(claim, ('schema_version', 'kind', 'allocation_id', 'binding', 'nodes', 'node_catalog_digest',
                 'candidate_labels', 'candidate_lineages', 'hold', 'base_paid_or_unknown', 'outside_guard',
                 'guard_occupancy', 'campaign_limit', 'released', 'retained_profile_calls',
                 'retained_lineage_calls', 'time_policy', 'context_limit'), 'claim_shape')
    need(claim['schema_version'] == CLAIM and claim['kind'] == 'claim', 'claim_version')
    need(text(claim['allocation_id']) and len(claim['allocation_id']) <= 128, 'allocation_identity')
    b = claim['binding']
    keys(b, ('root', 'source_root', 'run_id', 'planner', 'profile', 'epoch', 'plan_digest',
             'source_input_identity', 'source_policy_digest', 'request_policy_digest', 'runtime_identity_digest'), 'binding_shape')
    need(all(text(b[k]) for k in ('root', 'source_root', 'run_id')) and b['planner'] in PROFILES
         and integer(b['epoch'], maximum=2**63-1), 'binding_identity')
    profile, limit, candidate_count = PROFILES[b['planner']]
    need(b['profile'] == profile and all(hashed(b[k]) for k in
         ('plan_digest', 'source_input_identity', 'source_policy_digest', 'request_policy_digest', 'runtime_identity_digest')),
         'binding_profile_digests')
    nodes, labels, mapping = claim['nodes'], claim['candidate_labels'], claim['candidate_lineages']
    need(type(nodes) is list and integer(len(nodes), 1, limit) and integer(claim['hold'], 1, limit)
         and len(nodes) == claim['hold'] and identity(nodes) == claim['node_catalog_digest'], 'complete_catalog_hold')
    need(strings(labels) and len(labels) == candidate_count and type(mapping) is dict and set(mapping) == set(labels)
         and all(text(v) for v in mapping.values()) and len(set(mapping.values())) == candidate_count, 'original_candidate_lineages')
    seen, phase, finals, panels = set(), -1, [], []
    coverage = {(p, label): 0 for p in PHASES[:3] for label in labels}
    costs = {lineage: 0 for lineage in mapping.values()}
    for ordinal, node in enumerate(nodes):
        keys(node, NODE_FIELDS, 'node_shape')
        need(text(node['node_id']) and node['node_id'] not in seen and type(node['ordinal']) is int
             and node['ordinal'] == ordinal and node['phase'] in PHASES and type(node['final']) is bool,
             'node_order_identity')
        current = PHASES.index(node['phase'])
        need(current >= phase and strings(node['candidate_labels']) and set(node['candidate_labels']) <= set(labels)
             and strings(node['segment_ids'], empty=True) and strings(node['obligation_ids'])
             and strings(node['dependencies'], empty=True) and set(node['dependencies']) <= seen
             and integer(node['output_reserve'], 1, 26000), 'node_complete_schedule_shape')
        phase = current
        if node['phase'] != 'selection':
            need(len(node['candidate_labels']) == 1 and not node['final'], 'native_single_candidate')
            label = node['candidate_labels'][0]
            coverage[node['phase'], label] += 1
            costs[mapping[label]] += 1
        else:
            need(node['candidate_labels'] == labels, 'equal_selection_candidates')
            (finals if node['final'] else panels).append(node['node_id'])
            if node['final']:
                need(ordinal == len(nodes)-1 and set(node['dependencies']) == set(panels), 'last_final_all_panels')
        seen.add(node['node_id'])
    need(all(coverage.values()) and panels and len(finals) == 1, 'all_phases_candidates_and_final')
    paid, guard, n = claim['base_paid_or_unknown'], claim['outside_guard'], claim['hold']
    need(integer(paid) and integer(guard) and paid <= guard and integer(claim['guard_occupancy'])
         and claim['guard_occupancy'] == guard+n <= 290 and type(claim['campaign_limit']) is int
         and claim['campaign_limit'] == 290 and type(claim['released']) is int and claim['released'] == 0,
         'fullhold_no_refund_or_paid_guard_double_count')
    retained = claim['retained_lineage_calls']
    need(integer(claim['retained_profile_calls'], maximum=limit) and claim['retained_profile_calls']+n <= limit
         and type(retained) is dict and all(text(k) and integer(v, maximum=64) for k,v in retained.items())
         and all(retained.get(k,0)+v <= 64 for k,v in costs.items()), 'original_profile_and_lineage_limits')
    time = claim['time_policy']
    keys(time, ('supports_synthesis_budget', 'retained_total_active_seconds', 'retained_lineage_active_seconds'), 'time_policy_shape')
    need(type(time['supports_synthesis_budget']) is bool and number(time['retained_total_active_seconds'])
         and type(time['retained_lineage_active_seconds']) is dict
         and all(text(k) and number(v) for k,v in time['retained_lineage_active_seconds'].items()), 'original_time_data')
    if b['planner'] == 'capability':
        maximum = 3900 if time['supports_synthesis_budget'] else 2700
        need(time['retained_total_active_seconds']+n <= 13500
             and all(time['retained_lineage_active_seconds'].get(k,0)+v <= maximum for k,v in costs.items()),
             'original_retained_time_bound')
    need(integer(claim['context_limit'], 1, 96000), 'configured_context_not_expanded')
    return b

def _reservation(event, claim, node):
    r = event['reservation']
    keys(r, RESERVATION_FIELDS, 'reservation_shape')
    b, number_ = claim['binding'], node['ordinal']+1
    lineages = [] if node['phase'] == 'selection' else sorted(claim['candidate_lineages'][x] for x in node['candidate_labels'])
    need(r['schema_version'] == NATIVE_CLAIM and r['protocol'] == PROTOCOL and type(r['number']) is int
         and r['number'] == number_ and r['run_id'] == b['run_id']
         and r['reservation_id'] == b['run_id']+':dispatch:'+str(number_)
         and r['phase'] == node['phase'] and r['candidate_labels'] == node['candidate_labels']
         and r['lineage_ids'] == lineages and r['candidate'] == (lineages[0] if len(lineages)==1 else None)
         and type(r['generation']) is int and r['generation'] == 1 and type(r['execution']) is int and r['execution'] == 1
         and r['status'] == 'reserved' and text(r['reserved_at_utc']) and text(r['workspace'])
         and identity(r['model_identity']) == b['runtime_identity_digest'], 'actual_native_reservation_identity')
    q = r['request_identity']
    keys(q, REQUEST_FIELDS, 'actual_request_shape')
    need(q['protocol'] == PROTOCOL and q['plan_digest'] == b['plan_digest'] and q['node_id'] == node['node_id']
         and q['phase'] == node['phase'] and hashed(q['request_sha256']) and hashed(q['schema_digest'])
         and identity(q['source_hashes']) == b['request_policy_digest']
         and type(q['output_reserve']) is int and q['output_reserve'] == node['output_reserve']
         and type(r['timeout_sec']) is int and r['timeout_sec'] >= 1 and q['timeout_sec'] == r['timeout_sec']
         and type(q['timeout_sec']) is int, 'full_request_plan_policy_identity')
    maximum = 1800 if b['planner']=='mvg' else (1200 if node['phase']=='synthesis' and claim['time_policy']['supports_synthesis_budget'] else 2700)
    need(r['timeout_sec'] <= maximum, 'original_timeout_bound')
    for key, schema in (('request_ref', 'newrouge.b-route-segmented-prompt.v1'),
                        ('schema_ref', 'newrouge.b-route-segmented-output-schema.v1'),
                        ('input_archive_ref', 'newrouge.b-route-segmented-input-archive.v1')):
        reference(q[key], schema)
    m = q['input_measurement']
    need(type(m) is dict and integer(m.get('input_token_estimate'), maximum=70000)
         and type(m.get('reserved_continuation_tokens')) is int and m['reserved_continuation_tokens']==node['output_reserve']
         and m['input_token_estimate']+node['output_reserve'] <= claim['context_limit']
         and m.get('truncation_allowed') is False and m.get('request_sha256') == q['request_sha256'],
         'input70k_plus_original_output_total_no_truncation')
    reference(event['native_claim_ref'], NATIVE_CLAIM)
    need(identity(r)==event['reservation_digest'] and identity(q)==event['request_identity_digest']
         and event['reservation_id']==r['reservation_id'], 'whole_reservation_request_digest')
    return r

def _native_funding(value, claim):
    required = {'schema_version', 'paid_or_unknown_before_run', 'campaign_limit',
                'subsequent_full_reservation', 'maximum_native_charges', 'released',
                'retained_profile_calls', 'retained_lineage_calls'}
    need(type(value) is dict and required <= set(value)
         and value['schema_version']=='newrouge.story25-native-funding.v1', 'native_funding_family')
    for key in required-{'schema_version','retained_lineage_calls'}:
        need(integer(value[key]), 'native_funding_strict_integer')
    need(value['campaign_limit']==290 and value['released']==0
         and value['paid_or_unknown_before_run']>=claim['base_paid_or_unknown']
         and value['retained_profile_calls']>=claim['retained_profile_calls']
         and type(value['retained_lineage_calls']) is dict
         and all(text(k) and integer(v,maximum=64) for k,v in value['retained_lineage_calls'].items()),
         'native_funding_no_refund_or_bool_counts')
    limit=PROFILES[claim['binding']['planner']][1]
    need(value['retained_profile_calls']+claim['hold']<=limit
         and value['maximum_native_charges']>=claim['hold']
         and value['paid_or_unknown_before_run']+value['subsequent_full_reservation']+claim['hold']<=290,
         'native_funding_whole_schedule_ceiling')
    for lineage in claim['candidate_lineages'].values():
        costs=sum(node['phase']!='selection' and lineage in {claim['candidate_lineages'][label]
                  for label in node['candidate_labels']} for node in claim['nodes'])
        need(value['retained_lineage_calls'].get(lineage,0)+costs<=64, 'native_retained_lineage_ceiling')

def validate_prefix(members, *, expected_inventory, expected_claim, native_observations, expected_state):
    """Return DATA facts only. expected_* must later be genuine owner observations.

    expected_state: open-prefix, retained-stop or completed. A pending intent is
    valid data but always blocked. This routine never authorizes any append or
    dispatch, even when a next unseen node can be named.
    """
    need(expected_state in ('open-prefix','retained-stop','completed'), 'explicit_terminal_expectation')
    need(type(members) is dict and type(expected_inventory) is dict and set(members)==set(expected_inventory),
         'exact_supplied_member_inventory_including_STOP')
    need(all(text(k) and type(v) is bytes for k,v in members.items())
         and all(hashed(v, False) for v in expected_inventory.values()), 'raw_member_inventory_shape')
    need(all(digest(raw)==expected_inventory[k] for k,raw in members.items()), 'raw_member_hash')
    names = sorted(set(members)-{'STOP.json'})
    _claim(expected_claim)
    n = expected_claim['hold']
    need(1 <= len(names) <= 1+2*n and names==['%06d.json'%i for i in range(1,len(names)+1)],
         'bounded_contiguous_financial_rows')
    rows=[]
    for name in names:
        row=parse(members[name]);keys(row, ('sequence','previous','event','sha256'), 'financial_row_shape')
        need(type(row['sequence']) is int and row['sequence']==len(rows)+1
             and row['previous']==(rows[-1]['sha256'] if rows else None)
             and hashed(row['sha256'], False) and row['sha256']==digest(canonical({k:v for k,v in row.items() if k!='sha256'}))
             and members[name]==canonical(row)+b'\n', 'original_canonical_hash_chain')
        rows.append(row)
    claim=rows[0]['event']
    need(canonical(claim)==canonical(expected_claim), 'same_complete_owner_supplied_claim')
    b=_claim(claim)
    need(type(native_observations) is list, 'native_observation_list')
    intent_count=0;completed=[];pending=None;intents=[];seen_reservations=set();outcome_digests={}
    elapsed_total=claim['time_policy']['retained_total_active_seconds']
    elapsed_lineages=dict(claim['time_policy']['retained_lineage_active_seconds'])
    for row in rows[1:]:
        e=row['event'];need(type(e) is dict, 'financial_event_mapping')
        common={'schema_version','kind','allocation_id','node_id','ordinal','reservation_id','paid_or_unknown','guard_occupancy','hold','released'}
        need(e.get('allocation_id')==claim['allocation_id'] and type(e.get('paid_or_unknown')) is int
             and type(e.get('guard_occupancy')) is int and e['guard_occupancy']==claim['guard_occupancy']
             and type(e.get('hold')) is int and e['hold']==n and type(e.get('released')) is int and e['released']==0,
             'fullhold_at_every_event')
        if e.get('kind')=='intent':
            keys(e, common|{'node_digest','reservation','reservation_digest','request_identity_digest','native_claim_ref'}, 'intent_shape')
            need(e['schema_version']==INTENT and pending is None and intent_count==len(completed) and intent_count<n,
                 'no_second_intent_or_advance_past_unknown')
            node=claim['nodes'][intent_count]
            need(type(e['ordinal']) is int and e['ordinal']==intent_count and e['node_id']==node['node_id']
                 and e['node_digest']==identity(node) and e['paid_or_unknown']==claim['base_paid_or_unknown']+intent_count+1,
                 'ordered_node_unique_intent_paid_once')
            r=_reservation(e,claim,node)
            need(r['reservation_id'] not in seen_reservations, 'reservation_never_repeated')
            seen_reservations.add(r['reservation_id']);intents.append(e);intent_count+=1;pending=e
        elif e.get('kind')=='outcome':
            keys(e, common|{'intent_row_sha256','native_outcome_digest','verified_result_digest'}, 'outcome_shape')
            need(e['schema_version']==OUTCOME and pending is not None and e['node_id']==pending['node_id']
                 and type(e['ordinal']) is int and e['ordinal']==pending['ordinal'] and e['reservation_id']==pending['reservation_id']
                 and e['intent_row_sha256']==rows[row['sequence']-2]['sha256']
                 and hashed(e['native_outcome_digest']) and hashed(e['verified_result_digest'])
                 and e['paid_or_unknown']==claim['base_paid_or_unknown']+intent_count,
                 'same_pending_native_outcome_no_second_charge')
            outcome_digests[e['node_id']]=(e['native_outcome_digest'], e['verified_result_digest'])
            completed.append(e['node_id']);pending=None
        else:
            raise PrefixError('segmented_financial_prefix:unknown_or_mixed_event_version')
    need(len(native_observations)==intent_count, 'one_native_observation_per_actual_intent')
    for index,(event,observation) in enumerate(zip(intents,native_observations)):
        keys(observation, ('node_id','claim_path','claim_raw','outcome_raw','verified_result_digest'), 'native_observation_shape')
        need(observation['node_id']==event['node_id'] and observation['claim_path']==event['native_claim_ref']['path'],
             'same_node_claim_observation')
        native_raw=observation['claim_raw'];outcome_raw=observation['outcome_raw']
        need(native_raw is None or type(native_raw) is bytes, 'native_claim_bytes_or_explicit_absence')
        if native_raw is None:
            need(index==intent_count-1 and pending is event and outcome_raw is None
                 and observation['verified_result_digest'] is None, 'partial_native_persist_blocks_progress')
            continue
        need('sha256:'+digest(native_raw)==event['native_claim_ref']['raw_digest'], 'actual_native_claim_raw_digest')
        native=parse(native_raw);keys(native,NATIVE_FIELDS,'native_claim_shape')
        need(native['schema_version']==NATIVE_CLAIM and native['protocol']==PROTOCOL and native['plan_digest']==b['plan_digest']
             and type(native['registry_epoch']) is int and native['registry_epoch']==b['epoch']
             and canonical(native['node'])==canonical(claim['nodes'][index])
             and canonical(native['reservation'])==canonical(event['reservation'])
             and hashed(native['native_after_digest']) and type(native['funding_at_reserve']) is dict
             and type(native['parents']) is dict and native['parents']=={dep:outcome_digests[dep][1] for dep in claim['nodes'][index]['dependencies']}
             and relative(native['journal_ref']), 'exact_original_native_claim')
        _native_funding(native['funding_at_reserve'],claim)
        if event['node_id'] not in outcome_digests:
            need(pending is event and index==intent_count-1, 'native_observation_without_financial_outcome')
            # A native outcome may predate a lost fiscal append. It remains
            # unknown here; only genuine owner roll-forward may reconcile it.
            if outcome_raw is not None:
                need(type(outcome_raw) is bytes and hashed(observation['verified_result_digest']), 'pending_observed_outcome_bytes')
                observed=parse(outcome_raw)
                keys(observed, ('status','completed_at_utc','output_sha256','active_elapsed_seconds','segmented_result_digest'), 'pending_native_outcome_shape')
                need(observed['status']=='completed' and text(observed['completed_at_utc']) and hashed(observed['output_sha256'])
                     and number(observed['active_elapsed_seconds'])
                     and observed['segmented_result_digest']==observation['verified_result_digest'], 'pending_native_outcome_binding')
                elapsed=observed['active_elapsed_seconds'];elapsed_total+=elapsed
                for lineage in event['reservation']['lineage_ids']:
                    elapsed_lineages[lineage]=elapsed_lineages.get(lineage,0)+elapsed
                if b['planner']=='capability':
                    maximum=3900 if claim['time_policy']['supports_synthesis_budget'] else 2700
                    need(elapsed_total<=13500 and all(v<=maximum for v in elapsed_lineages.values()), 'original_active_time_ceiling')
            else:
                need(observation['verified_result_digest'] is None, 'no_result_without_native_outcome')
            continue
        need(type(outcome_raw) is bytes, 'completed_native_outcome_required')
        outcome=parse(outcome_raw)
        keys(outcome, ('status','completed_at_utc','output_sha256','active_elapsed_seconds','segmented_result_digest'), 'native_outcome_shape')
        out_digest,result_digest=outcome_digests[event['node_id']]
        need('sha256:'+digest(outcome_raw)==out_digest and observation['verified_result_digest']==result_digest
             and outcome['segmented_result_digest']==result_digest and outcome['status']=='completed'
             and text(outcome['completed_at_utc']) and hashed(outcome['output_sha256'])
             and number(outcome['active_elapsed_seconds']), 'same_actual_native_outcome_result')
        elapsed=outcome['active_elapsed_seconds'];elapsed_total+=elapsed
        for lineage in event['reservation']['lineage_ids']:
            elapsed_lineages[lineage]=elapsed_lineages.get(lineage,0)+elapsed
        if b['planner']=='capability':
            maximum=3900 if claim['time_policy']['supports_synthesis_budget'] else 2700
            need(elapsed_total<=13500 and all(v<=maximum for v in elapsed_lineages.values()), 'original_active_time_ceiling')
    stopped='STOP.json' in members
    need((expected_state=='retained-stop')==stopped, 'STOP_required_and_never_silently_omitted')
    if stopped:
        stop=parse(members['STOP.json'])
        keys(stop, ('schema_version','allocation_id','claim_row_sha256','last_sequence','last_row_sha256',
                    'hold','paid_or_unknown','guard_occupancy','campaign_limit','released','retry_allowed','reason_code'), 'STOP_shape')
        need(stop['schema_version']==STOP and stop['allocation_id']==claim['allocation_id']
             and stop['claim_row_sha256']==rows[0]['sha256'] and type(stop['last_sequence']) is int
             and stop['last_sequence']==len(rows) and stop['last_row_sha256']==rows[-1]['sha256']
             and type(stop['hold']) is int and stop['hold']==n and type(stop['paid_or_unknown']) is int
             and stop['paid_or_unknown']==claim['base_paid_or_unknown']+intent_count
             and type(stop['guard_occupancy']) is int and stop['guard_occupancy']==claim['guard_occupancy']
             and type(stop['campaign_limit']) is int and stop['campaign_limit']==290
             and type(stop['released']) is int and stop['released']==0 and stop['retry_allowed'] is False
             and text(stop['reason_code']) and members['STOP.json']==canonical(stop)+b'\n', 'STOP_retains_complete_hold_and_prefix')
    if expected_state=='completed':
        need(pending is None and len(completed)==n, 'completed_requires_whole_schedule_outcomes')
    disposition=('retained-stop' if stopped else 'unsettled-intent' if pending else
                 'complete' if len(completed)==n else 'open-settled-prefix')
    return {'schema_version':FACTS,'allocation_id':claim['allocation_id'],'plan_digest':b['plan_digest'],
            'node_catalog_digest':claim['node_catalog_digest'],'hold':n,'intent_count':intent_count,
            'paid_or_unknown':claim['base_paid_or_unknown']+intent_count,'guard_occupancy':claim['guard_occupancy'],
            'released':0,'completed_node_ids':completed,'unsettled_node_id':pending['node_id'] if pending else None,
            'next_unseen_node_id':claim['nodes'][intent_count]['node_id'] if not stopped and pending is None and intent_count<n else None,
            'prefix_disposition':disposition,'last_sequence':len(rows),'last_row_sha256':rows[-1]['sha256'],
            'member_inventory_digest':identity(expected_inventory),'dispatch_authorized':False,
            'append_authorized':False,'redispatch_allowed':False,'live_member_closure_verified':False,
            'native_qualification_verified':False,'opaque_grant':False}
