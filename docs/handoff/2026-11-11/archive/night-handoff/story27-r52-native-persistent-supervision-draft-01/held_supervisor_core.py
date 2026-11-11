"""Two exact Root worker transports. No outer timeout/kill or business acceptance."""
import ctypes
from ctypes import wintypes
from datetime import datetime,timezone
import hashlib,json,os,stat,subprocess,sys
from pathlib import Path
TASK=Path(__file__).absolute().parents[2]
PYTHON=Path(r'C:\Program Files\Python312\python.exe')
PYTHON_SHA='4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a'
NATIVE_ARGS=['--manifest-sha256','88a551e4a57a09a621990758ae6355d0de70651824a36faabc01ec991810fa25',
 '--config','logs/ci/2026-11-09/story27-r52-atomic-review-prepare-seal-01/config.json',
 '--config-sha256','d6f1eec3a9e9bf7dc5b94608db02d069c4f84404625587bfe9ebd7e64658067d']
LANES={
 'atomic-review-prepare-persist01':{
  'worker_ref':'night-handoff/story27-r52-atomic-review-prepare-thin-controls-01/run_review_prepare.Root-only.py',
  'worker_sha256':'71e7f9241ae4485a525868060bff75db537fff15e1a6c2d4ce82f5c3fd4916c8',
  'worker_arguments':NATIVE_ARGS,
  'supervision_out_ref':'logs/ci/2026-11-09/story27-r52-atomic-review-prepare-supervision-01',
  'result_ref':'logs/ci/2026-11-09/story27-r52-atomic-review-prepare-01/result.json'},
 'owner-failed13-detached-attempt03':{
  'worker_ref':'night-handoff/story28-r55-owner-failed13-detached-attempt03-draft/run_failed13.draft.py',
  'worker_sha256':'34f41636a934a7d85aeb3d80508a39c882081d4b1f36ad0e8d182b37d60a362c',
  'worker_arguments':['--install-ref','logs/ci/2026-11-09/story28-r55-owner-install-Root-01/result.json',
   '--install-sha256','039784e7176db774772ef78b5c413ad525aba25e4fed7a9fdcd88358c4288bd9'],
  'supervision_out_ref':'logs/ci/2026-11-09/story28-r55-owner-failed13-supervision-03',
  'result_ref':'logs/ci/2026-11-09/story28-r55-owner-failed13-Root-03/result.json'}}

def need(ok,why):
    if not ok:raise RuntimeError('held_supervisor:'+why)
def utc():return datetime.now(timezone.utc).isoformat()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def plain(path,missing=False):
    p=Path(path).absolute()
    for a in reversed((p,*p.parents)):
        try:s=a.lstat()
        except FileNotFoundError:
            need(missing,'missing exact path');continue
        need(not stat.S_ISLNK(s.st_mode) and not s.st_file_attributes&0x400,'no reparse')
        need(stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode) and s.st_nlink==1,'ordinary single-link path')
    return p
def relative(ref,missing=False):
    need(type(ref) is str and ref and '\\' not in ref and ':' not in ref,'Task relative ref')
    parts=ref.split('/');need(all(x not in ('','.','..') and x.rstrip(' .')==x for x in parts),'unambiguous ref')
    need(not any(x.casefold() in {'.codex','.aws','.ssh','sessions','credentials'} or x.casefold().startswith('.env') for x in parts),'no private ref')
    p=plain(TASK/ref,missing);need(p.is_relative_to(TASK),'fixed Task boundary');return p
def read(path):
    p=plain(path);a=p.stat();raw=p.read_bytes();b=p.stat()
    need((a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns,a.st_nlink)==(b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns,b.st_ctime_ns,b.st_nlink),'raw input stable')
    return raw
def write(path,value):
    raw=(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf8')
    with plain(path,True).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())

def identity(handle,pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    times=kernel.GetProcessTimes;times.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)];times.restype=wintypes.BOOL
    created,ended,kernel_time,user=[wintypes.FILETIME() for _ in range(4)]
    need(times(wintypes.HANDLE(handle),ctypes.byref(created),ctypes.byref(ended),ctypes.byref(kernel_time),ctypes.byref(user)),'original held birth query')
    image=ctypes.create_unicode_buffer(32768);length=wintypes.DWORD(len(image))
    query=kernel.QueryFullProcessImageNameW;query.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)];query.restype=wintypes.BOOL
    okay=query(wintypes.HANDLE(handle),0,image,ctypes.byref(length))
    return {'pid':pid,'held_handle':handle,'birth_filetime':(created.dwHighDateTime<<32)|created.dwLowDateTime,
      'image':image.value if okay else None,'image_error':None if okay else ctypes.get_last_error()}
def exit_value(handle):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);fn=kernel.GetExitCodeProcess
    fn.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)];fn.restype=wintypes.BOOL
    value=wintypes.DWORD();need(fn(wintypes.HANDLE(handle),ctypes.byref(value)),'original held OS exit query');return value.value

def supervise_exact(profile):
    need(os.name=='nt' and Path.cwd()==TASK and Path(sys.executable).absolute()==PYTHON
      and sys.flags.dev_mode and sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and not sys.flags.optimize,'fixed normal isolated Root Python/cwd')
    need(set(profile)=={'profile_id','worker_ref','worker_sha256','worker_arguments','supervision_out_ref','result_ref','input_pins'},'exact transport profile shape')
    need(profile['profile_id'] in LANES,'two explicit original worker lanes only')
    expected=LANES[profile['profile_id']]
    need(all(profile[k]==v for k,v in expected.items()),'literal original worker pin/argv/output')
    need(type(profile['input_pins']) is dict and profile['input_pins'],'real pinned inputs')
    for ref,pin in profile['input_pins'].items():need(sha(read(relative(ref)))==pin,'actual input raw pin')
    need(sha(read(PYTHON))==PYTHON_SHA,'fixed Python raw')
    worker=relative(profile['worker_ref']);need(sha(read(worker))==profile['worker_sha256'],'fixed worker raw')
    result_path=relative(profile['result_ref'],True);out=relative(profile['supervision_out_ref'],True)
    need(not out.exists() and not result_path.parent.exists(),'new supervision and worker-out domains; never duplicate')
    out.mkdir(parents=True,exist_ok=False)
    argv=[str(PYTHON),'-X','dev','-I','-S','-B',str(worker),*profile['worker_arguments']]
    input_limit=os.environ.get('SC_CAPABILITY_MAX_INPUT_TOKENS')
    need(input_limit in (None,'70000','96000'),'preserve original finite caller input limit')
    env={k:os.environ[k] for k in ('SystemRoot','WINDIR','SystemDrive','TEMP','TMP','PROCESSOR_ARCHITECTURE','NUMBER_OF_PROCESSORS') if k in os.environ}
    env.update(PATH=str(PYTHON.parent),PATHEXT='.EXE',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',
      NEWROGUE_CODEX_REASONING_EFFORT='high')
    if input_limit is not None:env['SC_CAPABILITY_MAX_INPUT_TOKENS']=input_limit
    write(out/'supervisor-started.json',{'utc':utc(),'supervisor_pid':os.getpid(),'profile':profile,'argv':argv,
      'outer_timeout_seconds':None,'kill_on_timeout':False,'automatic_retry':False,'business_or_native_PASS_claimed':False})
    process=None;pre=post=None;code=raw_exit=None;error=None;identity_error=post_error=close_error=None
    closed=False;close_attempted=False;known=False
    with (out/'worker-stdout.bin').open('xb') as stdout,(out/'worker-stderr.bin').open('xb') as stderr:
        try:
            process=subprocess.Popen(argv,cwd=TASK,stdout=stdout,stderr=stderr,stdin=subprocess.DEVNULL,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                pre=identity(int(process._handle),process.pid)
                need(pre['image'] is not None and Path(pre['image'])==PYTHON and pre['birth_filetime']>0,'actual original worker image/birth')
            except BaseException as exc:identity_error=type(exc).__name__+':'+str(exc)
            write(out/'child-started.json',{'utc':utc(),'pid':process.pid,'held_handle':int(process._handle),'identity':pre,'identity_error':identity_error,'argv':argv})
            code=process.wait()  # Original worker keeps its own3600 reader/Job/locks. No outer deadline or kill.
        except BaseException as exc:
            error=type(exc).__name__+':'+str(exc)
        finally:
            if process is not None:
                if process.returncode is None:
                    try:code=process.wait()
                    except BaseException as exc:error=(error or '')+';wait:'+type(exc).__name__+':'+str(exc)
                try:post=identity(int(process._handle),process.pid)
                except BaseException as exc:post_error=type(exc).__name__+':'+str(exc)
                try:
                    raw_exit=exit_value(int(process._handle))
                    known=type(code) is int and raw_exit!=259 and code==raw_exit
                except BaseException as exc:error=(error or '')+';exit:'+type(exc).__name__+':'+str(exc)
                close_attempted=True
                try:process._handle.Close();closed=True
                except BaseException as exc:close_error=type(exc).__name__+':'+str(exc)
            stdout.flush();os.fsync(stdout.fileno());stderr.flush();os.fsync(stderr.fileno())
    post_same=pre is not None and post is not None and all(pre[k]==post[k] for k in ('pid','held_handle','birth_filetime'))
    if post is not None and post['image'] is not None:post_same=post_same and Path(post['image'])==PYTHON
    # Missing post-exit image is preserved as metadata, not confused with unknown OS exit.
    write(out/'child-terminal.json',{'utc':utc(),'child_pid':None if process is None else process.pid,
      'pre_identity':pre,'identity_error':identity_error,'post_identity':post,'post_identity_error':post_error,
      'python_returncode':code,'raw_GetExitCodeProcess_value':raw_exit,'terminal_known':known,
      'actual_original_held_child_exit_code':raw_exit if known else None,
      'handle_close_attempted':close_attempted,'actual_handle_closed':closed,'handle_close_error':close_error,'error':error})
    # Retain the known original terminal even if a later metadata/raw close fails.
    program_same=pins_same=False;result_raw=None
    try:
        program_same=sha(read(PYTHON))==PYTHON_SHA and sha(read(worker))==profile['worker_sha256']
        pins_same=all(sha(read(relative(ref)))==pin for ref,pin in profile['input_pins'].items())
        result_raw=read(result_path) if result_path.exists() else None
    except BaseException as exc:error=(error or '')+';metadata_close:'+type(exc).__name__+':'+str(exc)
    reported=None
    if result_raw is not None:
        try:reported=json.loads(result_raw).get('passed')
        except (ValueError,UnicodeError):pass
    complete=known and closed and identity_error is None and post_error is None and post_same and close_error is None and error is None and program_same and pins_same
    record={'utc':utc(),'profile_id':profile['profile_id'],'transport_complete':complete,'child_pid':None if process is None else process.pid,
      'pre_identity':pre,'identity_error':identity_error,'post_identity':post,'post_identity_error':post_error,
      'python_returncode':code,'raw_GetExitCodeProcess_value':raw_exit,'terminal_known':known,
      'actual_original_held_child_exit_code':raw_exit if known else None,
      'handle_close_attempted':close_attempted,'actual_handle_closed':closed,'handle_close_error':close_error,'error':error,
      'stdout_sha256':sha(read(out/'worker-stdout.bin')),'stderr_sha256':sha(read(out/'worker-stderr.bin')),
      'worker_result_ref':profile['result_ref'],'worker_result_sha256':None if result_raw is None else sha(result_raw),
      'test_result_ref':profile['result_ref'],'test_result_sha256':None if result_raw is None else sha(result_raw),
      'worker_reported_passed':reported,'worker_STOP_exists':result_path.with_name('STOP.json').exists(),
      'original_program_and_control_pins_unchanged':program_same and pins_same,
      'wait_returned_without_supervisor_timeout_or_kill':type(code) is int,
      'automatic_retry':False,'business_or_native_PASS_claimed':False,'formal_acceptance':False,
      'actual_project_model_calls_added_by_supervisor':0,'financial_claim_created':False,
      'paid_or_unknown':80,'guard_occupancy':178,'campaign_limit':290,'released':0}
    write(out/'result.json',record);print(json.dumps(record),flush=True)
    return 0 if complete and raw_exit==0 else 1
