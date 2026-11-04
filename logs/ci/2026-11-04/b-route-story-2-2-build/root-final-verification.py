from pathlib import Path
import sys,os,json,subprocess,hashlib,time,ast
root=Path.cwd();base=root/'logs/ci/2026-11-04/b-route-story-2-2-build';out=base/'root-final-verification';out.mkdir(exist_ok=False)
spec=root/'_bmad-output/implementation-artifacts/b-route/spec-2-2-independent-cumulative-source-audit.md'
frozen=spec.read_text().split('<frozen-after-approval',1)[1].split('</frozen-after-approval>',1)[0]
assert hashlib.sha256(frozen.encode()).hexdigest()=='9454a00ff8d169a1f540eff43b33ed742d01249b87a78b0742ea2797ce0e5192'
import yaml
workflow=yaml.load((root/'.github/workflows/story-2-2-windows.yml').read_text(),Loader=yaml.BaseLoader)
program=workflow['jobs']['source-audit']['steps'][2]['run'];tree=ast.parse(program)
nested={node.targets[0].id:ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in {'runner','matrix_runner'}}
assert set(nested)=={'runner','matrix_runner'}
for s in nested.values():ast.parse(s)
runner=nested['runner'];start=runner.index('allowed_skips = ');stop=runner.index('actual_skips = ',start)
runner=runner[:start]+"allowed_skips = {'test_b_route_sources.SourceAccountingTests.test_windows_real_junction_and_short_path', 'test_b_route_source_audit.SourceAuditTests.test_windows_audit_real_junction_and_short_path_rejected'}\n"+runner[stop:]
runner=runner.replace('and required <= set(result.successes)','and required == actual_skips')
(out/'linux-suite-driver.py').write_text(runner,encoding='utf-8')
record={'full_diff_read':'/tmp/story22-native-step3-final-m3diburz.diff; all2711 lines read in400-line chunks (initial1200 request was truncated and reread)','diff_sha256':'ccfba6ecf960eb1a979a721e81763da25f39aa79f41a54fc04eaf1a72946187d','frozen_sha256':hashlib.sha256(frozen.encode()).hexdigest(),'synthetic_only':True,'real_model_acceptance':'blocked CONNECT403; no new attempt','steps':[]}
clean_env=dict(os.environ);clean_env.pop('PYTHONDONTWRITEBYTECODE',None);clean_env.pop('PYTHONPYCACHEPREFIX',None)
commands=[('linux-relevant-suites',[sys.executable,'-B','-c',runner],600),('independent-synthetic-cli',[sys.executable,str(base/'independent-synthetic-cli.py'),str(out/'cli')],300)]
for name,command,budget in commands:
 started=time.monotonic();p=subprocess.run(command,cwd=root,env=clean_env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=budget)
 for suffix,value in [('stdout',p.stdout),('stderr',p.stderr)]: (out/(name+'.'+suffix)).write_text(value,encoding='utf-8')
 record['steps'].append({'name':name,'returncode':p.returncode,'elapsed_seconds':time.monotonic()-started,'budget_seconds':budget,'stdout_sha256':hashlib.sha256(p.stdout.encode()).hexdigest(),'stderr_sha256':hashlib.sha256(p.stderr.encode()).hexdigest()})
 (out/'summary.json').write_text(json.dumps(record,indent=2)+'\n')
 print(json.dumps(record['steps'][-1]),flush=True)
 if p.returncode:
  print(p.stderr[-2500:],flush=True);raise SystemExit(p.returncode)
print('Relevant Linux suites and independent CLI finished; real model and Windows remain separate.')
