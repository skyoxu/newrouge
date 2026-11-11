"""Thin Root-only finite execution ABI candidate; UNEXECUTED.

Uses the existing issuer/lease, original source factory/native/workflow and their
original official runner. It is not a process/Guard/ledger framework. Root's
existing real paid host must supply its source-only/FD/Job/IO supervision. No
config/grant/model/namespace is created at import or from a serialized authority.
"""
import os
from pathlib import Path


def run_once(owner, *, mode, plan_ref=None, planning_contract=None, semantic_catalog_ref=None):
    import _b_route_segmented_funding as funding
    funding.require_original_owner(owner)
    runtime = owner.owners['runtime']
    workflow = owner.owners['workflow']
    if mode == 'inspect':
        return owner.inspect_archived_fiscal_proof()
    if mode == 'repair-native-birth':
        return owner.repair_native_birth(planning_contract=planning_contract,semantic_catalog_ref=semantic_catalog_ref)
    if mode == 'reconcile-completed-intent':
        value = owner.reconcile_completed_intent()
        return {'facts':value['facts'],'redispatch_authorized':False,'released':0}
    if mode != 'execute':
        raise ValueError('unknown_finite_fiscal_action')
    existing = os.path.lexists(owner.config_path.parent/'ledger') or os.path.lexists(owner.config_path.parent/'prefix-init.json')
    if existing:
        # No new financial claim, even for empty/partial/corrupt/STOP namespace.
        # Partial data raises at the original reader; never falls back to fresh.
        run = owner._existing_prefix()
        view = owner.inspect_archived_fiscal_proof()
        if view['facts']['prefix_disposition'] == 'complete':
            return view  # Completed cold replay adds no intent or publication.
        scope = owner.resume_segmented_claim(planning_contract=planning_contract,
                                             semantic_catalog_ref=semantic_catalog_ref)
    else:
        if plan_ref is None or planning_contract is None:
            raise ValueError('original_plan_input_and_source_request_required')
        # Actual admitted full CLI plan input, not a caller plan dictionary or
        # a new carrier. This also preserves it if interrupted before birth.
        path = Path(plan_ref).absolute()
        refs = [r for r in owner.c['input_files'] if Path(r['path']).absolute()==path]
        if len(refs) != 1:
            raise ValueError('plan_not_original_config_input')
        plan = runtime.codec.strict_json_loads(owner.h.pinned(refs[0],metadata=False))
        workflow.validate_plan(plan)
        b = owner.c['binding']
        if plan['run_id'] != b['run_id'] or plan['planner'] != b['planner']:
            raise ValueError('plan_not_original_config_run_profile')
        authority = runtime.capture_plan_authority(owner.root,run_id=b['run_id'],planner=b['planner'],
                    planning_contract=planning_contract,semantic_catalog_ref=semantic_catalog_ref)
        scope = owner.hold_segmented_plan(owner.root,authority,plan)
        run = runtime._homes(owner.root,plan['planner'],plan['run_id'])
    with scope as grant:
        plan = owner.plan
        if not os.path.lexists(run):
            runtime.prepare_run(owner.root,run_id=plan['run_id'],planner=plan['planner'],plan=plan,
                planning_contract=planning_contract,semantic_catalog_ref=semantic_catalog_ref,schedule_grant=grant)
        # Same original source/full request/native/high/runner/result pipeline.
        # No dispatcher, model API, budget loop, auto retry or fallback is added.
        return workflow.execute_workflow(owner.root,run_dir=run,plan=plan)
