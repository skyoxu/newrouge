"""Observe the genuine offline preparation; never waive its capacity gate."""
import hashlib
import json
from pathlib import Path
import sys
import traceback
from unittest.mock import patch

sys.dont_write_bytecode = True
REPO = Path('/workspace/newrouge')
sys.path.insert(0,str(REPO/'scripts/python'))
import _b_route_adoption as adoption
import _b_route_codec as codec
import _b_route_adoption_review as review
import _b_route_qualified_compensation_materials_v2 as materials
import _capability_input_integrity as integrity
from _b_route_compensation_review_profiles import PUBLISHED

OUT = Path(__file__).absolute().parent
ROOT = Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
REPORT = OUT/'published-prepare-actual-02.json'
assert not REPORT.exists()
original_measure, original_render = integrity.measure_request, materials.render
captures, renders = [], []
policy,pins = review.policy_observations()
critical = ['docs/planning/b-route/catalog.v1.json','docs/planning/b-route/commits/NativeV15Origin03.json',
            __import__('_planning_apply_journal')._operation_ref('NativeV15Origin03')]
before = {name:codec.raw_digest(codec.read_reference_bytes(ROOT,name)) for name in critical}

def observe_render(derived):
    text = original_render(derived)
    renders.append({'frame_bytes':len(text.encode()),'work_limit':derived.work.limit,
                    'work_charged':derived.work.limit-derived.work.remaining,
                    'packet_schema':derived.packet['schema_version'],'claim':derived.packet['presentation']['claim']})
    return text


def observe_measure(payload,**kwargs):
    data = payload.encode('utf-8')
    path = OUT/'published-complete-request-02.txt'
    assert not path.exists()
    path.write_bytes(data)
    captures.append({'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'policy':kwargs})
    return original_measure(payload,**kwargs)

try:
    with patch.object(integrity,'measure_request',side_effect=observe_measure), \
         patch.object(materials,'render',side_effect=observe_render):
        result = adoption.prepare_review(ROOT,operation_id='NativeV15Origin03Compensation01',
            request_ref='logs/ci/b-route-requests/native-v15-origin03-compensation-01/request.json',
            compensation_delivery=PUBLISHED.name('delivery'))
    value = {'passed':True,'result':result}
except Exception as error:
    value = {'passed':False,'error_type':type(error).__name__,'traceback':traceback.format_exc()}
after = {name:codec.raw_digest(codec.read_reference_bytes(ROOT,name)) for name in critical}
value.update(source_policy=policy,source_pins=pins,genuine_render_observations=renders,captured_requests=captures,
    original_critical_files_before=before,original_critical_files_after=after,original_critical_files_unchanged=before==after,
    saved_new_subject_exists=(ROOT/review.location('NativeV15Origin03Compensation01')/'subject.json').exists(),
    observation_only=True,capacity_gate_unchanged=True,old_owner_executed=False,
    model_dispatched=False,reserve_or_apply=False)
REPORT.write_text(json.dumps(value,indent=2)+'\n')
print(json.dumps({k:value[k] for k in ('passed','error_type','genuine_render_observations','captured_requests',
    'original_critical_files_unchanged','saved_new_subject_exists','model_dispatched')},indent=2))
