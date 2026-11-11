from pathlib import Path
import sys, json, time, datetime, subprocess, hashlib, unittest, contextlib
root=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(root/'scripts/python'),str(root/'scripts/python/tests'),str(root/'scripts/sc'),str(root)]
label,*selectors=sys.argv[1:]
home=Path(__file__).parent/label
home.mkdir(exist_ok=False)
files=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=root,text=True).splitlines()
metadata={'label':label,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'selectors':selectors,'baseline_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
 'changed_files_sha256':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in files if (root/n).is_file()},
 'qualification':'Focused offline unit/CLI checks only; no provider, Windows durability or formal Story acceptance claim.'}
(home/'invocation.json').write_text(json.dumps(metadata,indent=2)+'\n')
started=time.monotonic()
with (home/'unittest.log').open('w',encoding='utf-8') as output,contextlib.redirect_stdout(output),contextlib.redirect_stderr(output):
 suite=unittest.defaultTestLoader.loadTestsFromNames(selectors)
 result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
report={'label':label,'tests_run':result.testsRun,'passed':result.testsRun-len({getattr(t,'test_case',t).id() for t,_ in result.failures+result.errors})-len(result.skipped),
 'failures':[str(t) for t,_ in result.failures],'errors':[str(t) for t,_ in result.errors],
 'skipped':[(str(t),why) for t,why in result.skipped],'successful':result.wasSuccessful(),
 'elapsed_seconds':time.monotonic()-started,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'new_provider_calls':0,'qualification':metadata['qualification']}
(home/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
sys.exit(0 if result.wasSuccessful() else 1)
