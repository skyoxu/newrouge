"""Exact native worker adapter; never call the original owner from the launcher."""
import argparse,hashlib,json,types
from pathlib import Path
HOME=Path(__file__).absolute().parent
TASK=HOME.parents[1]
PROFILE={
 'profile_id':'atomic-review-prepare-persist01',
 'worker_ref':'night-handoff/story27-r52-atomic-review-prepare-thin-controls-01/run_review_prepare.Root-only.py',
 'worker_sha256':'71e7f9241ae4485a525868060bff75db537fff15e1a6c2d4ce82f5c3fd4916c8',
 'worker_arguments':['--manifest-sha256','88a551e4a57a09a621990758ae6355d0de70651824a36faabc01ec991810fa25',
  '--config','logs/ci/2026-11-09/story27-r52-atomic-review-prepare-seal-01/config.json',
  '--config-sha256','d6f1eec3a9e9bf7dc5b94608db02d069c4f84404625587bfe9ebd7e64658067d'],
 'supervision_out_ref':'logs/ci/2026-11-09/story27-r52-atomic-review-prepare-supervision-01',
 'result_ref':'logs/ci/2026-11-09/story27-r52-atomic-review-prepare-01/result.json',
 'input_pins':{
  'night-handoff/story27-r52-atomic-review-prepare-thin-controls-01/manifest.json':'88a551e4a57a09a621990758ae6355d0de70651824a36faabc01ec991810fa25',
  'logs/ci/2026-11-09/story27-r52-atomic-review-prepare-seal-01/config.json':'d6f1eec3a9e9bf7dc5b94608db02d069c4f84404625587bfe9ebd7e64658067d'}}

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest-sha256',required=True);a=p.parse_args()
    mraw=(HOME/'manifest.json').read_bytes()
    if hashlib.sha256(mraw).hexdigest()!=a.manifest_sha256:raise RuntimeError('reviewed supervisor manifest')
    manifest=json.loads(mraw)
    for name,row in manifest['files'].items():
        if '/' in name or '\\' in name or hashlib.sha256((HOME/name).read_bytes()).hexdigest()!=row['sha256']:raise RuntimeError('reviewed control member')
    raw=(HOME/'held_supervisor_core.py').read_bytes()
    core=types.ModuleType('_Root_exact_held_worker_core');core.__file__=str(HOME/'held_supervisor_core.py')
    exec(compile(raw,core.__file__,'exec',dont_inherit=True,optimize=0),core.__dict__)
    return core.supervise_exact(PROFILE)

if __name__=='__main__':raise SystemExit(main())
