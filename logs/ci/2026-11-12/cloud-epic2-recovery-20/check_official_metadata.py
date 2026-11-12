"""Bounded official metadata RPCs only; never thread/start or turn/start."""
import subprocess,sys,json,queue,threading,time,datetime,os,re
from pathlib import Path
sys.dont_write_bytecode=True;sys.path.insert(0,'/workspace/newrouge/scripts/python')
import _codex_app_server as runner
home=Path('/workspace/newrouge-tools/codex-login-20261112-JtqMz6')
out=Path(__file__).absolute().parent
env=dict(os.environ);env['CODEX_HOME']=str(home)
report={'kind':'official metadata only','model_turns':0,'rpc_methods':[],'cache_before':(home/'models_cache.json').is_file()}
proc=subprocess.Popen(runner.command('/opt/codex/bin/codex'),env=env,cwd=home,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
q=queue.Queue();errors=[]
private=home/'metadata-rpc.jsonl';fd=os.open(private,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);capture=os.fdopen(fd,'w')
def stdout():
 for line in proc.stdout:
  capture.write(line);capture.flush()
  try:q.put(json.loads(line))
  except ValueError:pass
 q.put(None)
def stderr():
 for line in proc.stderr:errors.append(line)
t=threading.Thread(target=stdout,daemon=True);e=threading.Thread(target=stderr,daemon=True);t.start();e.start()
def send(value):proc.stdin.write(json.dumps(value)+'\n');proc.stdin.flush()
def rpc(i,method,params):
 assert method in ('initialize','model/list','config/read','account/read','account/rateLimits/read')
 report['rpc_methods'].append(method);send({'id':i,'method':method,'params':params});deadline=time.monotonic()+12
 while time.monotonic()<deadline:
  row=q.get(timeout=max(.01,deadline-time.monotonic()))
  if row is None:raise RuntimeError('official_metadata_stdout_closed')
  if row.get('id')==i:
   if 'error' in row:
    error=row['error'];return {'rpc_error_code':error.get('code'),'rpc_error_http_categories':sorted(set(re.findall(r'\b(?:401|403|429|500|502|503)\b',str(error))))}
   return row.get('result',{})
 raise TimeoutError('official_metadata_rpc_timeout')
try:
 initial=rpc(1,'initialize',{'clientInfo':{'name':'newrouge_cloud_metadata','version':'1.0'},'capabilities':{'experimentalApi':True}})
 report['initialize_ok']='rpc_error_code' not in initial
 if report['initialize_ok']:
  send({'method':'initialized'})
  models=rpc(2,'model/list',{'limit':100,'includeHidden':True})
  report['model_list_error']={k:v for k,v in models.items() if k.startswith('rpc_error')}
  report['model_list']=[{k:m[k] for k in ('id','model','isDefault') if k in m} for m in models.get('data',[])]
  config=rpc(3,'config/read',{'includeLayers':False});c=config.get('config',{})
  report['effective_nonsecret_config']={k:c[k] for k in ('model','model_provider','model_reasoning_effort','service_tier') if k in c}
  account=rpc(4,'account/read',{'refreshToken':False});a=account.get('account') or {}
  report['account_metadata']={k:a[k] for k in ('type','planType') if k in a}
  report['requires_openai_auth']=account.get('requiresOpenaiAuth')
  limits=rpc(5,'account/rateLimits/read',{})
  report['subscription_status_error']={k:v for k,v in limits.items() if k.startswith('rpc_error')}
  report['subscription_status_returned']=any(k in limits for k in ('rateLimits','rateLimitsByLimitId'))
except Exception as error:report['metadata_error_type']=type(error).__name__
finally:
 proc.stdin.close()
 try:proc.wait(timeout=3)
 except subprocess.TimeoutExpired:
  proc.terminate()
  try:proc.wait(timeout=3)
  except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=3)
 t.join(timeout=2);e.join(timeout=2);capture.close()
 stderr_text=''.join(errors);p=home/'metadata-rpc.stderr';p.write_text(stderr_text);p.chmod(0o600)
 report.update(process_exit=proc.returncode,pipe_threads_stopped=not t.is_alive() and not e.is_alive(),official_cache_created=(home/'models_cache.json').is_file(),
  stderr_http_categories=sorted(set(re.findall(r'\b(?:401|403|429|500|502|503)\b',stderr_text))),
  stderr_error_categories={k:k in stderr_text.lower() for k in ('failed to refresh','unauthorized','forbidden','sqlite','read-only','error')})
 (out/'official-app-server-metadata.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
