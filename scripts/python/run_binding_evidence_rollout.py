"""Run read-only binding-evidence preflight for real consumer artifacts."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from knowledge_binding_producer import produce_binding, validate_binding_evidence

PAIRS = {
 "chapter4":"chapter4-PRD-NEWROUGE-GAME-0001-v2",
 "chapter5":"chapter5-T28-GM-0128-v4",
 "chapter6":"chapter6-T29-GM-0129-v2",
 "review":"review-T29-GM-0129-v2",
}
def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='.'); ap.add_argument('--output-dir',default='logs/ci/knowledge-context/rollout'); args=ap.parse_args()
    root=Path(args.root).resolve(); out=root/args.output_dir
    results=[]
    for consumer, stem in PAIRS.items():
        try:
            bundle=json.loads((root/'logs/ci/knowledge-context'/f'{stem}.json').read_text(encoding='utf-8'))
            decisions=json.loads((root/'logs/ci/knowledge-context'/f'{stem}.decisions.json').read_text(encoding='utf-8'))
            evidence=produce_binding(root,bundle,decisions); validate_binding_evidence(root,bundle,evidence)
            path=out/f'{consumer}.binding.json'; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
            results.append({'consumer':consumer,'status':'passed','path':path.relative_to(root).as_posix(),'evidence_count':len(evidence['evidence'])})
        except Exception as exc:
            results.append({'consumer':consumer,'status':'failed','reason':str(exc)})
    payload={'schema_version':'newrouge.binding-evidence-rollout.v1','status':'passed' if all(x['status']=='passed' for x in results) else 'failed','results':results}
    print(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)); return 0 if payload['status']=='passed' else 2
if __name__=='__main__': raise SystemExit(main())
