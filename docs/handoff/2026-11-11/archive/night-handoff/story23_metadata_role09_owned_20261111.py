"""One existing-owner, bounded metadata-only composition; never paid."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,sys
sys.dont_write_bytecode=True
task=Path(__file__).resolve().parents[1]
home=task/'night-handoff/story23-metadata-role09-20261111'
out=task/'logs/ci/2026-11-11/story23-r59-metadata-role-09'
def now():return datetime.now(timezone.utc).isoformat()
def save(name,value):
    with (out/name).open('x',encoding='utf-8') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
if '--worker' not in sys.argv:
    assert not (home/'out').exists()
    out.mkdir(exist_ok=False)
    save('started.json',{'utc':now(),'supervisor_pid':os.getpid(),'timeout_seconds':3600,
        'source_commit':'fe175b49e668551b175f8d5c53a91d6c53ef59f2',
        'scope':'Actual original source-capture/describe/context verification under narrow Task-only metadata host',
        'new_project_model_calls_allowed':0,'paid_or_financial_call_allowed':False})
    sys.path.insert(0,str(task/'r59/scripts/python'))
    from _b_route_reader_lifetime import run_reader,ReaderTransportError
    try:
        done=run_reader([sys.executable,'-X','dev','-I','-S','-B',str(Path(__file__).resolve()),'--worker'],
            input=b'',cwd=task,env=dict(os.environ),timeout=3600)
        (out/'stdout.bin').write_bytes(done.stdout);(out/'stderr.bin').write_bytes(done.stderr)
        native=home/'out/result.json'
        result=json.loads(native.read_bytes()) if native.exists() else None
        save('result.json',{'utc':now(),'actual_owned_reader_OS_exit':done.returncode,
            'owned_job_quiescence_returned':True,'metadata_result_present':result is not None,
            'passed':done.returncode==0 and result is not None and result['passed'],
            'actual_composition_result':str(native),'new_project_model_calls':0,
            'formal_segmented_acceptance':False,'paid_guard_composition_verified':False})
        raise SystemExit(done.returncode)
    except ReaderTransportError as exc:
        (out/'stdout.bin').write_bytes(exc.stdout);(out/'stderr.bin').write_bytes(exc.stderr)
        save('result.json',{'utc':now(),'passed':False,'reader_outcome':exc.outcome,
            'cleanup':exc.cleanup,'cause_type':exc.cause_type,'new_project_model_calls':0,
            'formal_segmented_acceptance':False})
        raise
if sys.stdin.buffer.readline()!=b'start\n':raise SystemExit(2)
sys.stdin.buffer.read()
save('worker-started.json',{'utc':now(),'pid':os.getpid()})
driver=home/'run_metadata.Root-only.py'
host=home/'metadata_host.Root-only.py'
# These are the original host's reviewed executable control pins, not a new
# business-input fingerprint or Story admission system.
args=[str(driver),'--host-sha256',hashlib.sha256(host.read_bytes()).hexdigest(),
    '--driver-sha256',hashlib.sha256(driver.read_bytes()).hexdigest(),
    '--run-id','r23-metadata-role-09','--planner','mvg']
sys.argv=args
import runpy
runpy.run_path(str(driver),run_name='__main__')
