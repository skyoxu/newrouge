"""Root-invoked read-only actual-artifact diagnostic; never formal acceptance.

Actual final original owner authority and real completed original v2 tickets are
inputs. No template/synthetic dictionary can stand in for them. This code does
not create a fresh native target, re-render old tickets, write model evidence,
call a model, change ACLs, modify original archives or re-sign old proofs.
"""
from pathlib import Path
import base64
import _b_route_codec as codec
import _planning_apply_journal as journal
import _b_route_adoption as adoption
import _b_route_adoption_review as review
import _b_route_compensation as compensation
import _b_route_qualified_compensation_review as qualified
import _b_route_qualified_compensation_materials as materials


def inspect_existing_history(root, *, original_operation_id):
    root=Path(root).absolute()
    original=journal.read_operation(root,operation_id=original_operation_id)
    with qualified.action():
        value=qualified.history(root,original)
        value.recheck()
        return {'diagnostic_only':True,'formal_adoption':False,'native_qualification':False,
            'new_model_calls':0,'target_writes':0,'original_proof_rewritten':False,
            'original_operation_id':original_operation_id,'original_operation_schema':original['schema_version'],
            'historical_subject_digest':value.identity(),'new_history_auth_digest':codec.canonical_digest(value.binding())}


def complete_memory_only_request(root, *, request_ref, require_later_task_done=False):
    root=Path(root).absolute()
    request=journal.validate_operation_request(adoption.safe_path(root,request_ref).read_bytes())
    with qualified.action():
        snapshot,frozen=compensation.build(root,request)
        subject=compensation.make_subject(snapshot,request,frozen)
        qualified.need(subject['schema_version']==qualified.SUBJECT,'actual verified qualified original family')
        if require_later_task_done:
            master=codec.strict_json_loads(snapshot.read('.taskmaster/tasks/tasks.json'))
            qualified.need(any(row.get('status')=='done' for row in master['master']['tasks']),
                           'this specific diagnostic fixture actually has a later completed Task')
        derived=qualified.model_packet(root,subject)
        values=qualified.artifacts(root,subject,packet=derived,delivery=qualified.DELIVERY)
        qualified.bind_action(snapshot)
        snapshot.verify()
        captured=set(subject['current_files'])|set(subject['private_files'])
        qualified.need(captured=={n for n,d in snapshot.files.items() if d is not None},
                       'complete disjoint exact original capture identities after private factoring')
        # An independent complete cold action, not added to the warm account or
        # presented as a warm/private native proof. Each keeps original caps.
        cold=materials.read_prompt(values['w/prompt.txt'].decode('utf-8'))
        qualified.need(materials.ordered(cold)==materials.ordered(derived.packet),'complete exact independent cold packet')
        from _capability_input_integrity import CODEX_MAX_TURN_BYTES,configured_input_limit,measure_request
        capacity=measure_request(values['request.txt'].decode('utf-8'),max_bytes=CODEX_MAX_TURN_BYTES,
            max_input_tokens=min(70000,configured_input_limit()),reserved_tokens=qualified.OUTPUT_RESERVE_TOKENS)
        snapshot.verify()
        return {'diagnostic_only':True,'formal_adoption':False,'native_qualification':False,
            'new_model_calls':0,'target_writes':0,'original_proof_rewritten':False,
            'operation_id':subject['operation_id'],'subject_schema':subject['schema_version'],
            'review_delivery':qualified.DELIVERY,'review_claim':qualified.CLAIM,
            'actual_frame_count':len(cold['materials']['frames']),
            'inline_capture_count':len(subject['current_files']),'private_exact_reference_count':len(subject['private_files']),
            'private_subject_digest':codec.canonical_digest(subject),
            'public_materials_digest':cold['presentation']['materials_digest'],
            'historical_auth_digest':cold['presentation']['historical_auth_digest'],
            'actual_request_raw_digest':codec.raw_digest(values['request.txt']),
            'actual_request_bytes':len(values['request.txt']),'capacity':capacity,
            'warm_account_limit':derived.work.limit,'warm_account_remaining':derived.work.remaining}
