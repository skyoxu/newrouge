"""Genuine read-only same-account repair preflight; no intent or model dispatch."""
from pathlib import Path
import json
import sys
from contextlib import nullcontext
from unittest.mock import patch

sys.dont_write_bytecode=True
sys.path.insert(0,'/workspace/newrouge/scripts/python')
import _b_route_compensation as compensation
import _b_route_adoption_review as review
import _b_route_qualified_compensation_review_v2 as qualified
import _b_route_compensation_review_repair as repair
import _b_route_compensation_segmented_execution as engine
from _b_route_compensation_review_profiles import PUBLISHED
from _b_route_operation_scope import business_guard
from _mvg_capability_checkpoint import coordinator_lock

ROOT=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
SOURCE=Path('/workspace/newrouge-tools/source-epochs/continuation20-65e75d61')
OUT=Path(__file__).resolve().parent
OP='NativeV15Origin03Compensation01'
original=repair.original(ROOT,OP,SOURCE)
with qualified.action():
    snapshot,frozen=compensation.build(ROOT,original['subject']['request'],
        allocations=original['subject']['preview']['allocations'],review_profile=PUBLISHED)
    with business_guard(ROOT,frozen['scope_ids'],operation_id=OP,review_only=True),coordinator_lock(review.path(ROOT,review.location(OP))):
        snapshot,frozen2=compensation.build(ROOT,original['subject']['request'],
            allocations=frozen['allocations'],review_profile=PUBLISHED)
        assert frozen==frozen2
        subject=compensation.make_subject(snapshot,original['subject']['request'],frozen2)
        derived=qualified.model_packet(ROOT,subject)
        reserve='--reserve-proof-buffers' in sys.argv
        streamed='--streamed-audit' in sys.argv
        referenced='--all-audit-by-ref' in sys.argv
        metadata_graphs='--metadata-graphs' in sys.argv
        data_metadata=None
        if metadata_graphs:
            old_home=review.path(ROOT,review.location(OP))
            actual_refs=[repair.ref(ROOT,p.relative_to(ROOT).as_posix()) for p in old_home.rglob('*') if p.is_file()]
            actual_refs += [{'path':review.location(OP)+'/'+repair.LANE+'/original-source/'+name,
                'schema_version':'raw.bytes.v1','raw_digest':repair.codec.raw_digest(raw)} for name,raw in original['source'].items()]
            data_metadata={'DATA_resource_probe_only':True,'actual_bound_original_and_source_refs':actual_refs,
                'actual_prior_evidence':original['prefix'][0]['evidence'],
                'future_ref_metadata_byte_reserve':'x'*12000}
        reserve_lengths=[]
        if reserve:
            old_home=review.path(ROOT,review.location(OP))
            if referenced:
                reserve_lengths=[50000]  # Proof/ref metadata; runtime/audit raw bytes are no longer retained.
            elif not streamed:
                reserve_lengths=[p.stat().st_size for p in old_home.rglob('*') if p.is_file()]
                reserve_lengths += [len(data) for data in original['source'].values()]
            if not referenced:
                reserve_lengths += [len(review.raw(subject)),len(derived.freeze_auth())]
                reserve_lengths += [len(review.raw(derived.packet[k])) for k in ('materials','roles','presentation')]
                reserve_lengths.append(300000)
                reserve_lengths.append(2*max((old_home/'segmented/nodes'/n/'execution.json').stat().st_size for n in ('000','001')))
        original_metrics=type(derived).private_metrics
        def metrics_with_reserved(self):
            metrics,buffers=original_metrics(self)
            if data_metadata is not None:
                metrics += [engine.materials.compact._json_preflight(data_metadata,self.work) for _ in range(2)]
            return metrics,[*buffers,*reserve_lengths]
        # Strictly accumulate both legacy-validation passes from proof replay
        # in the genuine current work account before deriving the new spec.
        old=repair.original(ROOT,OP,SOURCE,work=derived.work)
        repair.original(ROOT,OP,SOURCE,work=derived.work)
        repair._subject_transition(old,derived);repair._release_audit_bytes(old)
        original.clear()
        with patch.object(type(derived),'private_metrics',metrics_with_reserved) if reserve else nullcontext():
            spec=engine._spec(derived)
        repair._business_transition(old,derived,spec)
        plan=engine._plan(subject,derived.packet,spec)
        prompt,schema,request,measurement=engine._request(subject,derived.packet,plan,plan['nodes'][1],
            spec[1]['base_prompt'],old['prefix'])
        derived.recheck();snapshot.verify()
        report={'genuine_same_root_subject_and_source_transition':True,
            'same_wire_decoder_and_exact_business_body':True,'all9_checks_preserved':True,
            'complete_rpc_measurement':measurement,'source_policy':review.policy_identity(),
            'strict_work_charged':derived.work.limit-derived.work.remaining,'work_limit':derived.work.limit,
            'legacy_validation_passes_in_same_work_account':2,'model_calls':0,
            'new_intent_or_allowance_or_proof':False,'reserved_proof_buffer_bytes':sum(reserve_lengths)}
        name=('genuine-strict-metadata-proof-preflight.json' if '--strict-metadata' in sys.argv else
              'genuine-metadata-proof-preflight.json' if metadata_graphs else
              'genuine-referenced-proof-preflight.json' if referenced else
              'genuine-streamed-proof-preflight.json' if streamed else
              'genuine-reserved-proof-preflight.json' if reserve else 'genuine-pre-dispatch.json')
        (OUT/name).write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
