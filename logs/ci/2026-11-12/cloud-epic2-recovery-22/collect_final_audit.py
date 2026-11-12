"""Final read-only state, source and preservation audit; no model or transition."""
from pathlib import Path
import hashlib
import json
import sys
import traceback

sys.dont_write_bytecode=True;sys.path.insert(0,'/workspace/newrouge/scripts/python')
import _planning_apply_journal as journal
import _b_route_adoption_review as review

OUT=Path(__file__).resolve().parent
ROOT=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
OP='NativeV15Origin03Compensation01';BASE=ROOT/review.location(OP)
try:
    graph=journal.operation_state_graph(ROOT)
    summary={'operation_ids':[r['operation_id'] for r in graph['operations']],
        'terminals':sorted(graph['terminals']),'resolved_by':graph['resolved_by'],
        'active_operation_ids':[r['operation_id'] for r in graph['operations'] if
            r['operation_id'] not in graph['terminals'] and r['operation_id'] not in graph['resolved_by']]}
    assert summary['resolved_by']['NativeV15Origin03']==OP and OP in summary['terminals']
    assert summary['active_operation_ids']==[]
    (OUT/'final-operation-state-graph.json').write_text(json.dumps(summary,indent=2)+'\n')
    before=json.loads((OUT/'original-records-before.json').read_bytes())
    assert all(hashlib.sha256((BASE/name).read_bytes()).hexdigest()==r['sha256'] for name,r in before.items())
    intent=ROOT/journal._operation_ref(OP).replace('/operation.json','/commit.json')
    assert json.loads(intent.read_bytes())['phase']=='complete' and not intent.with_name('commit.pending.json').exists()
    read=json.loads((OUT/'public-compensation-read.json').read_bytes())
    assert read['formal_adoption'] is True and read['readiness'] is False and read['runtime_verified'] is False
    assert read['context']['plan_refs'][0]['revision']==2 and read['default_b_enabled'] is False
    old=json.loads((Path('/workspace/newrouge')/'logs/ci/2026-11-12/cloud-epic2-recovery-15/published-prepare-actual-02.json').read_bytes())['original_critical_files_before']
    retained={name:'sha256:'+hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in old.items()}
    assert retained['docs/planning/b-route/commits/NativeV15Origin03.json']
    assert retained[journal._operation_ref('NativeV15Origin03')]
    assert not retained['docs/planning/b-route/catalog.v1.json']
    catalog=json.loads((ROOT/'docs/planning/b-route/catalog.v1.json').read_bytes())
    assert catalog['revision']==2 and all(h['receipt_ref']['entity_id']==OP for h in catalog['scope_heads'])
    allowance=json.loads((BASE/'segmented/review-repair/allowance.json').read_bytes())
    assert allowance['additional_limit']==1 and allowance['cumulative_limit']==3
    assert json.loads((BASE/'segmented/call-limit.json').read_bytes())['model_request_budget']==2
    assert (BASE/'segmented/nodes/001/unknown.json').exists()
    policy,pins=review.policy_observations()
    assert policy==json.loads((BASE/'review.json').read_bytes())['policy_identity']
    report={'operation_id':OP,'all6_public_compensation_stages_succeeded':True,
        'proof_version':'newrouge.b-route-compensation-segmented-proof.v2','new_plan_revision':2,
        'receipt_revision':read['context']['receipt_revision'],'catalog_revision':2,
        'catalog_raw_digest':read['catalog_raw_digest'],'formal_adoption':True,
        'readiness':False,'runtime_verified':False,'default_b_enabled':False,
        'original34_review_files_unchanged':True,'old_receipt_and_operation_unchanged':True,
        'catalog_changed_only_via_authorized_publication':True,'original_limit2_retained':True,
        'old_two_intents_and_refusal_unknown_retained':True,'new_logical_calls':1,
        'cumulative_logical_calls':3,'new_model_unknown':False,'source_policy':policy,
        'current_source_pins_verified':len(pins),'resolution':summary,'commit_marker_absent':True,
        'no_financial_ledger_actions_or_historical_unknown_release':True,
        'full_suite_executed':False,'formal_Epic2_acceptance':'pending original Windows/native and Story2.9/2.10 scope'}
    (OUT/'final-state-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
except BaseException:
    (OUT/'final-audit-error.txt').write_text(traceback.format_exc())
    raise
