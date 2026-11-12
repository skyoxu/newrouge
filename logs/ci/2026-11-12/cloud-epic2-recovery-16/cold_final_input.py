"""One standalone full cold DATA read; no historical/native/model execution."""
import json
from pathlib import Path
import sys
import traceback
sys.dont_write_bytecode=True
sys.path.insert(0,'/workspace/newrouge/scripts/python')
import _b_route_compact_literal as compact
import _b_route_qualified_compensation_materials_v2 as materials
OUT=Path(__file__).absolute().parent
root=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
result=json.loads((OUT/'actual-segmented-preflight-04.json').read_text());home=(root/result['state_ref']).parent
work=compact._work(None)
try:
 prompt=(home/'nodes/000/w/prompt.txt').read_bytes().decode('utf-8')
 restored=materials.read_segment_input(prompt,work=work)
 charged=work.limit-work.remaining
 assert (materials.ordered(restored)+'\n').encode()==(home/'packet.json').read_bytes()
 report={'passed':True,'work_charged':charged,'work_limit':work.limit,'frames':len(restored['materials']['frames']),'documents':len(restored['materials']['documents']),'checks':len(restored['presentation']['required_checks']),'complete_packet_byte_exact':True,'canonical_compact_and_view_selection_verified':True}
except Exception:
 report={'passed':False,'traceback':traceback.format_exc(),'work_charged':work.limit-work.remaining,'work_limit':work.limit}
report.update(scope='standalone bounded DATA cold reader only; no genuine Derived/private graphs retained in this process',model_dispatched=False,old_owner_executed=False)
(OUT/'actual-final-cold.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
