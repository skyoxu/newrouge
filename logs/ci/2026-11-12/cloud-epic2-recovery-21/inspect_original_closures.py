"""Decode both actual original model inputs as DATA; never dispatch or seal."""
from pathlib import Path
import hashlib
import json
import sys

sys.dont_write_bytecode=True
sys.path.insert(0,'/workspace/newrouge/scripts/python')
import _b_route_compact_literal as compact
import _b_route_compensation_partition as partition
import _b_route_qualified_compensation_materials_v2 as materials

OUT=Path(__file__).resolve().parent
HOME=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare/logs/ci/b-route-adoption-reviews/f1a3f32d5599f72cc20517a2f05b4ec5ad9acc8ca1331b727aee3fa8f99df864')
work=compact._work(None)
payloads=[]
for ordinal in ('000','001'):
    prompt=(HOME/'segmented/nodes'/ordinal/'w/prompt.txt').read_text()
    base,context=prompt.rsplit('\n\nCLI NODE CONTEXT (data):\n',1)
    header,body=base.split('\n',1)
    assert header.startswith(partition.WIRE+' ')
    payloads.append(partition.identity_spelling(compact.loads(body,work=work),decode=True,
        resources=partition._Resources(work)))
business,governance=payloads
atoms=partition.decode_business(business,governance['target_projection'],
    resources=partition._Resources(work))
envelope=partition.restore_governance(governance,atoms,resources=partition._Resources(work))
packet=materials._restore_json_views(envelope,work)
saved={'schema_version':json.loads((HOME/'presentation.json').read_bytes())['schema_version'].replace('presentation','packet'),
    **{name:json.loads((HOME/(name+'.json')).read_bytes()) for name in ('presentation','roles','materials')}}
assert materials.ordered(packet)==materials.ordered(saved)
materials.validate(packet,work=work)
report={'actual_original_input_canonical_decoding':True,
    'full_restored_packet_equals_original_saved_packet':True,
    'frame_count':len(packet['materials']['frames']),
    'literal_document_count':len(packet['materials']['documents']),
    'required_check_count':len(packet['presentation']['required_checks']),
    'original_business_atom_count':len(atoms),
    'encoding_work_charged':work.limit-work.remaining,'encoding_work_limit':work.limit,
    'model_calls':0,'proof_or_old_record_writes':False}
(OUT/'original-input-closure-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
