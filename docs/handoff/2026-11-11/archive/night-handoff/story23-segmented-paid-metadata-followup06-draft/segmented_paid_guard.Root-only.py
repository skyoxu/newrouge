"""Task-only paid metadata followup06; UNEXECUTED source composition.

Original SourceOnly/codec-FD Guard remains owner; the paid supervisor evidence
shows held wait only. This factory adapts finite/native/source-transport roles.
Frozen-reader Job coverage is not paid-runner proof.
No config/authority/namespace/lease/grant/model is created at import.
"""
import hashlib
import os
from pathlib import Path
import re
import stat
import sys
from copy import deepcopy

TASK=Path(r'C:\Users\Administrator\Documents\Codex\2026-11-05\task')


def need(ok,why):
    if not ok:raise RuntimeError('segmented_paid_consumer:'+why)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def make_paid_guard(H):
    Base=H.Guard
    standard_run=H.subprocess.run
    # Original inventory dispatcher implementation is copied below, retaining
    # its existing mechanism while its real direct caller remains visible.
    require,key,hash_file,file_identity=H.require,H.key,H.hash_file,H.file_identity
    GIT,GIT_SHA,TARGET,POPEN=H.GIT,H.GIT_SHA,H.TARGET,H.POPEN
    subprocess,write_new,raw_json,held=H.subprocess,H.write_new,H.raw_json,H.held
    ctypes,wintypes,digest=H.ctypes,H.wintypes,H.digest

    class PaidGuard(Base):
        cleanup_program=Path(r'C:\Windows\System32\taskkill.exe')

        def bind_metadata_sources(self,runtime,transition,common,*,root,run_id,planner,planning_contract):
            """Bind existing actual source request DATA, never fiscal authority."""
            need(not hasattr(self,'metadata_request'),'one actual source-metadata binding')
            for module,name in ((runtime,'_b_route_segmented_runtime.py'),
                                (transition,'_b_route_execution_transition.py'),
                                (common,'_planning_skill_common.py')):
                need(isinstance(module.__loader__,H.Loader) and module.__loader__.guard is self
                     and Path(module.__file__).absolute()==H.SOURCE/'scripts/python'/name,
                     'actual SourceOnly metadata owners')
            need(Path(root).absolute()==self.target==H.TARGET and planner in runtime.PROFILE,
                 'same existing actual metadata root and profile')
            if hasattr(self,'owner'):
                need(self.owner.root==Path(root).absolute() and self.plan['run_id']==run_id
                     and self.plan['planner']==planner and self.owner.owners['runtime'] is runtime,
                     'same existing owner and actual metadata source request')
            runtime.codec.validate_business_id(run_id);runtime.role(planning_contract)
            self.metadata_request={'run_id':run_id,'planner':planner,'planning_contract':planning_contract}
            self.metadata_root=Path(root).absolute()
            self.runtime_owner,self.transition,self.common=runtime,transition,common
            self.run_function=common.run_isolated_model;self.run_code=self.run_function.__code__
            self.cleanup_function=common._terminate_process_tree;self.cleanup_code=self.cleanup_function.__code__
            self.metadata_functions=[]
            for module,names in ((runtime,('_original_metadata_call','_original_assemble','capture_source',
                         'verify_candidate_context','_source_runner_scope')),
                         (transition,('_git','_source_manifest','_tracked_tree'))):
                for name in names:
                    fn=getattr(module,name);body=getattr(fn,'__wrapped__',fn)
                    need(body.__globals__ is module.__dict__ and Path(body.__code__.co_filename).absolute()
                         ==Path(module.__file__).absolute(),'original metadata code globals file')
                    self.metadata_functions.append((module,name,fn,body.__code__))
            self.metadata_rows=[];self.metadata_records=[]
            if not hasattr(self,'runner_rows'):
                self.runner_rows=[];self.describe_rows=[];self.cleanup_rows=[]
                self.closed_child_rows=None

        def installed_source_launch(self):
            current=H.subprocess.Popen
            if current is H.POPEN:return None
            module=getattr(self,'runtime_owner',None)
            need(module is not None and callable(current) and getattr(current,'__globals__',None) is module.__dict__,
                 'only actual installed original source wrapper')
            outer=getattr(module._source_runner_scope,'__wrapped__',module._source_runner_scope)
            codes=[c for c in outer.__code__.co_consts if hasattr(c,'co_name') and c.co_name=='launch']
            need(len(codes)==1 and getattr(current,'__code__',None) is codes[0],
                 'actual original launch code')
            cells=dict(zip(current.__code__.co_freevars,(c.cell_contents for c in current.__closure__)))
            facts=cells.get('facts');source=cells.get('source')
            issued=[token for token,value in module._TRANSPORTS.items() if value is facts]
            need(len(issued)==1 and type(issued[0]) is module._RunnerTransport and issued[0].seal is module._SEAL
                 and facts['closed'] is False and facts.get('launch') is current and facts['source'] is source
                 and cells.get('prior') is H.POPEN and type(source) is module._SourceCapture
                 and source in module._SOURCES and source._seal is module._SEAL
                 and source._root==self.metadata_root and Path(source._policy['source_root'])==H.SOURCE
                 and source['run_id']==self.metadata_request['run_id'] and source['planner']==self.metadata_request['planner']
                 and source['source_identity']['planning_contract_ref']==self.metadata_request['planning_contract'],
                 'same live issued source wrapper prior facts and original source')
            return current

        def assert_active(self):
            # Original invariant, with only its Popen-reference clause extended
            # to the exact currently installed factory output. Never restore it.
            self.ack=None
            sys.audit('Root.native.reader.guard',self.nonce)
            wrapper=self.installed_source_launch()
            need(self.ack==self.nonce and self.finder in sys.meta_path and sys.getprofile() is self.profile_role
                 and H.POPEN.__init__ is self.guarded_init and H.POPEN._get_handles is self.guarded_handles
                 and H.POPEN._execute_child is H.EXECUTE
                 and (H.subprocess.Popen is H.POPEN or H.subprocess.Popen is wrapper)
                 and os.open is self.guarded_os_open and os.fdopen is H._FDOPEN,
                 'installed actual guard source constructor handles FD references')
            need(not self.blocked and H.subprocess.run==self.run_git,'same actual dispatcher and no prior refusal')

        def metadata_call(self,caller,argv,options):
            if not hasattr(self,'metadata_request'):return None
            for module,name,fn,code in self.metadata_functions:
                actual=getattr(module,name);body=getattr(actual,'__wrapped__',actual)
                need(actual is fn and body.__code__ is code and body.__globals__ is module.__dict__,
                     'original bound metadata functions unchanged')
            call=self.runtime_owner._original_metadata_call()
            if call is None:return None
            need(call['caller'] is caller and call['request']==self.metadata_request
                 and Path(call['assemble'].f_locals['root']).absolute()==self.metadata_root
                 and argv==call['argv'] and options==call['options'],
                 'actual direct original metadata owner request and IO')
            need(H.key(call['assemble'].f_locals['owner'])==H.key(TASK/'r5')
                 and H.key(call['assemble'].f_locals.get('git',H.GIT))==H.key(H.GIT),
                 'existing selected preserved owner and fixed original Git')
            wanted=H.GIT if call['kind']=='metadata-git' else H.PYTHON
            need(H.key(call['image'])==H.key(wanted),'same existing actual metadata executable')
            program='Git' if call['kind']=='metadata-git' else 'Python'
            pin=H.GIT_SHA if program=='Git' else H.PYTHON_SHA
            need(H.hash_file(wanted)==pin and H.file_identity(wanted)==self.c['program_identities'][program],
                 'original fixed metadata program before dispatch')
            return call

        def metadata_constructor(self,args,kwargs):
            dispatch=self.own_frame('run_git')
            if dispatch is None or dispatch.f_locals.get('metadata') is None:return None
            local=dispatch.f_locals
            need(local['self'] is self and dispatch.f_back is local['caller'],
                 'known actual metadata dispatcher and its real direct caller')
            call=self.metadata_call(local['caller'],local['argv'],local['kwargs'])
            options=call['options']
            expected={k:options[k] for k in ('stdout','stderr','creationflags')}
            if options['input'] is not None:expected['stdin']=H.subprocess.PIPE
            if 'cwd' in options:expected['cwd']=options['cwd']
            need(list(args)==[call['argv']] and kwargs==expected,
                 'unchanged original metadata stdlib constructor IO')
            return dispatch,call,local['metadata_row']

        def close_metadata_child(self,row,completed,error):
            """Original held identity/OS terminal, pipe and handle close mechanism."""
            process=row.get('process');record={k:v for k,v in row.items() if k!='process'}
            record.update(model_calls=0,terminal_known=False,actual_handle_closed=False,terminal_errors=[])
            try:
                need(process is not None and row['start_identity_error'] is None,
                     'actual metadata constructor and held start identity')
                post=H.held(process);record['post_identity']=post
                need(post['pid']==row['pid'] and post['held_handle']==row['held_handle']
                     and post['birth_filetime']==row['birth_filetime'],'same held metadata PID handle birth')
                if post['image'] is not None:need(H.key(post['image'])==H.key(row['image']),'same available metadata image')
                kernel=H.ctypes.WinDLL('kernel32',use_last_error=True)
                query=kernel.GetExitCodeProcess
                query.argtypes=[H.wintypes.HANDLE,H.ctypes.POINTER(H.wintypes.DWORD)];query.restype=H.wintypes.BOOL
                value=H.wintypes.DWORD()
                need(query(H.wintypes.HANDLE(int(process._handle)),H.ctypes.byref(value)), 'actual held metadata exit query')
                record['raw_GetExitCodeProcess_value']=value.value
                need(value.value!=259 and process.poll()==value.value,'actual known held metadata terminal')
                record.update(terminal_known=True,actual_original_held_OS_exit=value.value)
                record['original_pipes_closed']=all(stream is None or stream.closed
                    for stream in (process.stdin,process.stdout,process.stderr))
                record['original_pipe_workers_closed']=all(worker is None or not worker.is_alive()
                    for worker in (getattr(process,'_stdout_thread',None),getattr(process,'_stderr_thread',None)))
                need(record['original_pipes_closed'] and record['original_pipe_workers_closed'],
                     'original metadata stdin stdout stderr and reader threads closed')
                if completed is not None:need(completed.returncode==value.value,'same original metadata return code')
                wanted=H.GIT if row['kind']=='metadata-git' else H.PYTHON
                program='Git' if row['kind']=='metadata-git' else 'Python'
                pin=H.GIT_SHA if program=='Git' else H.PYTHON_SHA
                need(H.hash_file(wanted)==pin and H.file_identity(wanted)==self.c['program_identities'][program],
                     'original fixed metadata program at close')
            except BaseException as close_error:
                record['terminal_errors'].append(repr(close_error))
            finally:
                if process is not None:
                    try:process._handle.Close();record['actual_handle_closed']=True
                    except BaseException as close_error:record['terminal_errors'].append('Close:'+repr(close_error))
                record['error']=None if error is None else repr(error)
                if completed is not None:
                    record.update(stdout_sha256=sha(completed.stdout),stderr_sha256=sha(completed.stderr),
                                  stdout_bytes=len(completed.stdout),stderr_bytes=len(completed.stderr))
                self.metadata_records.append(record)
                H.write_new(self.out/('metadata/%s-terminal.json'%row['number']),H.raw_json(record))
            need(record['terminal_known'] and record['actual_handle_closed'] and not record['terminal_errors'],
                 'actual metadata held terminal pipe handle closure')

        def own_frame(self, name):
            wanted = getattr(PaidGuard, name).__code__
            frame = sys._getframe(1)
            while frame:
                if frame.f_code is wanted and frame.f_globals is globals() and (frame.f_locals.get('self') is self):
                    return frame
                frame = frame.f_back
            return None

        def cleanup_fact(self):
            path = self.cleanup_program
            for parent in reversed(path.parents):
                H.plain(parent)
            need(path.resolve(strict=True) == path, 'fixed original cleanup program path')
            first = H._LSTAT(path)
            need(stat.S_ISREG(first.st_mode) and (not first.st_file_attributes & 1024), 'ordinary installed cleanup program')
            identity = lambda i: [i.st_dev, i.st_ino, i.st_size, i.st_mtime_ns, i.st_ctime_ns, i.st_nlink]
            with H._OPEN(path, 'rb') as stream:
                raw = stream.read()
            after = H._LSTAT(path)
            need(identity(first) == identity(after), 'cleanup program stable while hashing')
            return {'path': str(path), 'sha256': sha(raw), 'identity': identity(after)}

        def real_frame(self, module, function, code=None):
            fn = getattr(module, function)
            wanted = code or getattr(fn, '__wrapped__', fn).__code__
            frame = sys._getframe(1)
            while frame:
                if frame.f_code is wanted and frame.f_globals is module.__dict__:
                    return frame
                frame = frame.f_back
            return None

        def bind_owner(self,owner,plan,*,runtime,workflow,journal,requests,common):
            owner.facade.require_original_owner(owner)
            need(all(isinstance(m.__loader__,H.Loader) for m in (runtime,workflow,journal,requests,common)),
                 'actual existing SourceOnly project owners')
            need(owner.owners['runtime'] is runtime and owner.owners['workflow'] is workflow,
                 'same source-bound fiscal/native owners')
            if hasattr(self,'metadata_request'):
                need(runtime is self.runtime_owner and common is self.common and owner.root==self.metadata_root
                     and plan['run_id']==self.metadata_request['run_id'] and plan['planner']==self.metadata_request['planner'],
                     'same original metadata and fiscal source binding')
            self.owner=owner;self.plan=workflow.validate_plan(plan)
            self.runtime_owner,self.workflow,self.journal,self.requests,self.common=runtime,workflow,journal,requests,common
            self.run_function=common.run_isolated_model;self.run_code=self.run_function.__code__
            self.cleanup_function=common._terminate_process_tree;self.cleanup_code=self.cleanup_function.__code__
            self.run=runtime._homes(owner.root,plan['planner'],plan['run_id'])
            self.finance=owner.config_path.parent
            self.runner_rows=[];self.describe_rows=[];self.cleanup_rows=[];self.funding_locks=[]
            self.funding_lock_returns=[];self.paid_lock_observer=None
            self.closed_coord_locks=None;self.closed_child_rows=None
            self.paid_outputs_started=False;self.paid_output_rows=None
            self.cleanup_initial=self.cleanup_fact()
            self.authorized=set();self.native_dirs=set();self.observed_writes=set();self.dynamic_outputs=set()
            self.finance_files={H.key(self.finance/'funding.lock'),H.key(self.finance/'prefix-init.json'),H.key(self.finance/'ledger/STOP.json')}
            self.finance_files|={H.key(self.finance/'ledger'/('%06d.json'%n)) for n in range(1,2*len(plan['nodes'])+2)}
            self.finance_dirs={H.key(self.finance),H.key(self.finance/'ledger')}
            store=owner.root/'logs/ci/mvg-recovery'
            self.authorized.update(H.key(p) for p in (store/'registry.json',store/'activity/segmented-active.json'))
            for name in ('initial-run.json','born.json','host.json','plan.json','claim.json'):
                self.authorized.add(H.key(self.run/'b'/name))
            self.authorized.update(H.key(self.run/n) for n in ('run.json','q/state.json','q/plan.json','q/completion.json'))
            stem=hashlib.sha256((str(self.run.resolve())+'\0'+plan['plan_digest']).encode()).hexdigest()[:24]
            publications=store/'activity/segmented-journals'
            self.authorized.add(H.key(publications/(stem+'-000-born.json')))
            for verb in ('init','finalize'):self.authorized.add(H.key(publications/(stem+'-000-'+verb+'.json')))
            for node in plan['nodes']:
                slot=self.run/'q'/('n'+str(node['ordinal']))
                for name in ('claim.json','complete-claim.json','result.json','failure.json','input-archive.json','m-execution.json'):
                    self.authorized.add(H.key(slot/name))
                for directory in (slot/'m',slot/'i'):
                    for name in ('prompt.txt','input.json','output-schema.json'):self.authorized.add(H.key(directory/name))
                self.authorized.update(H.key(slot/'m'/n) for n in ('output.json','runner-input-integrity.json'))
                for verb in ('reserve','complete','fail'):
                    self.authorized.add(H.key(publications/(stem+'-%03d-'%node['ordinal']+verb+'.json')))
            for name in self.authorized:
                parent=Path(name).parent
                while parent.is_relative_to(owner.root):
                    self.native_dirs.add(H.key(parent))
                    if parent==owner.root:break
                    parent=parent.parent
            self.locks.update(H.key(p) for p in (self.run/'capability-coordinator.lock',store/'capability-coordinator.lock',
                              store/'activity/capability-coordinator.lock'))
            self.lock_parents.update(H.key(Path(n).parent) for n in self.locks)
            # These exact mutable before images remain closed by original
            # native journal/source CAS, not by a stale generic immutable pin.
            for name in self.authorized:self.files.pop(name,None)
            self.original_target_before=deepcopy(self.c['target_before'])
            self.original_finance_before=H.snapshot_tree(self.finance)

        def observe_paid_locks(self):
            """Reuse the original NX observer and Host3 funding return wrapper."""
            import msvcrt
            need(self.paid_lock_observer is None and not self.funding_locks,
                 'install original lock observers once before financial work')
            underlying_locking=msvcrt.locking
            self.observe_original_locks()
            nx_locking=msvcrt.locking
            guard=self
            body=getattr(self.owner.h.Controller.locked,'__wrapped__',self.owner.h.Controller.locked)

            def locking(fd,mode,count):
                frame=guard.finance_frame()
                if frame is None:return nx_locking(fd,mode,count)
                need(frame.f_code is body.__code__ and frame.f_globals is guard.owner.h.__dict__
                     and frame.f_locals.get('self') is guard.owner.store,
                     'actual original store Controller.locked frame')
                stream=frame.f_locals.get('stream')
                need(stream is not None and stream.fileno()==fd and count==1
                     and mode in (msvcrt.LK_NBLCK,msvcrt.LK_UNLCK)
                     and H.key(stream.name)==H.key(guard.finance/'funding.lock'),
                     'actual original store funding byte-lock fd')
                audit_index=len(guard.funding_locks)
                value=underlying_locking(fd,mode,count)
                # The inherited audit entry records an attempted operation.
                # This separate entry exists only after its real return.
                guard.funding_lock_returns.append({'fd':fd,'mode':mode,'count':count,
                    'returned':True,'stream':stream,'audit_index':audit_index})
                return value

            self.paid_lock_observer=locking
            msvcrt.locking=locking

        def close_paid_locks(self):
            """Observe actual returns/closed streams; never infer them from audits."""
            import msvcrt
            need(self.paid_lock_observer is not None and msvcrt.locking is self.paid_lock_observer,
                 'same installed original paid lock observer')
            audits=self.funding_locks;returned=self.funding_lock_returns
            need(len(audits)==len(returned) and len(returned)%2==0,
                 'each original funding audit has its actual return')
            for index,row in enumerate(returned):
                audit=audits[index]
                need(row['audit_index']==index and row['returned'] is True
                     and all(row[k]==audit[k] for k in ('fd','mode','count'))
                     and row['stream'] is audit['stream'] and row['stream'].closed,
                     'same original funding audit return and closed stream')
            for index in range(0,len(returned),2):
                acquire,release=returned[index:index+2]
                need(acquire['mode']==msvcrt.LK_NBLCK and release['mode']==msvcrt.LK_UNLCK
                     and acquire['stream'] is release['stream'] and acquire['fd']==release['fd'],
                     'original funding acquire unlock pair')
            coordination=[*self.completed_lock_rows,*self.lock_descriptors.values()]
            fresh=set()
            for row in coordination:
                need(row['path'] in self.locks and row['acquire_returned'] and row['unlock_returned']
                     and row['close_returned'] and not row['errors'],
                     'original coordinator acquire unlock close returned')
                target=Path(row['path'])
                if target.is_relative_to(self.target):
                    need(H.plain(target).stat().st_size==1,'original one-byte coordinator lock')
                    name=target.relative_to(self.target).as_posix()
                    if name not in self.original_target_before['files']:fresh.add(H.key(target))
            self.closed_coord_locks=fresh
            return {'funding_audit_count':len(audits),'funding_return_count':len(returned),
                'funding_closed_stream_pairs':len(returned)//2,
                'funding_returns':[{k:r[k] for k in ('fd','mode','count','returned','audit_index')}
                    |{'path':H.key(r['stream'].name),'stream_closed':r['stream'].closed} for r in returned],
                'original_coordination_scopes':deepcopy(coordination),'fresh_original_locks':sorted(fresh)}

        def producer_frame(self):
            if not hasattr(self,'owner'):return None
            for module,names in ((self.runtime_owner,('_prepare_run_fiscal','financial_repair_birth')),
                    (self.requests,('render_request','archive_request_inputs'))):
                for name in names:
                    frame=self.real_frame(module,name)
                    if frame is not None:return frame
            module=self.journal
            for name in ('publish_born','_publish_born_fiscal'):
                frame=self.real_frame(module,name)
                if frame is not None:return frame
            for name in ('_transaction','workspace'):
                fn=getattr(module._Session,name)
                frame=sys._getframe(1)
                while frame:
                    if frame.f_code is fn.__code__ and frame.f_globals is module.__dict__:
                        session=frame.f_locals.get('self')
                        if type(session) is module._Session and session._seal is module._SEAL and session.root==self.owner.root and session.plan==self.plan:
                            session._live();return frame
                    frame=frame.f_back
            return None

        def finance_frame(self):
            if not hasattr(self,'owner') or self.owner.store is None:return None
            store=self.owner.store;module=self.owner.store_module
            candidates=[(module,getattr(module.FinitePrefixStore,n),store) for n in ('create_claim','append_event','retain_stop')]
            candidates.append((self.owner.h,self.owner.h.Controller.locked,store))
            frame=sys._getframe(1)
            while frame:
                for owner,fn,instance in candidates:
                    body=getattr(fn,'__wrapped__',fn)
                    if frame.f_code is body.__code__ and frame.f_globals is owner.__dict__ and frame.f_locals.get('self') is instance:return frame
                frame=frame.f_back
            return None

        def atomic_target(self):
            frame=self.real_frame(self.common,'atomic_json') if hasattr(self,'common') else None
            if frame is None:return None
            target=frame.f_locals.get('path');temp=frame.f_locals.get('tmp')
            if target is None:return None
            name=H.key(target)
            if name not in self.authorized:return None
            if self.producer_frame() is None and self.real_frame(self.common,'run_isolated_model',self.run_code) is None:return None
            return frame,Path(target),None if temp is None else Path(temp)

        def allowed_read(self,path):
            name=H.key(path)
            if name in (getattr(self,'finance_files',set())|getattr(self,'authorized',set())
                        |getattr(self,'dynamic_outputs',set())|(getattr(self,'closed_coord_locks',None) or set())):return
            return super().allowed_read(path)

        def allowed_write(self,path,mkdir=False,flags=None):
            if Path(H.key(path)).is_relative_to(self.out):return
            if self.token and self.token.get('kind')=='paid-cleanup' and os.fspath(path)==os.devnull:
                need(not mkdir,'original cleanup stdio null');return
            name=H.key(H.plain(path,missing=True))
            if hasattr(self,'owner') and (name in self.finance_files or mkdir and name in self.finance_dirs):
                frame=self.finance_frame();need(frame is not None,'actual original store/lease financial writer')
                if not mkdir and Path(name).name!='funding.lock':
                    need(type(flags) is int and flags&H.os.O_EXCL and flags&H.os.O_CREAT and not Path(name).exists(),
                         'original exclusive financial event/STOP/init')
                self.observed_writes.add(name);return
            atomic=self.atomic_target()
            if atomic is not None:
                frame,target,temp=atomic
                if mkdir and H.key(path)==H.key(target.parent) and Path(path).is_dir():return
                if not mkdir and temp is not None and name==H.key(temp):return
            if self.producer_frame() is not None and ((mkdir and name in self.native_dirs) or not mkdir and name in self.authorized):
                self.observed_writes.add(name);return
            return super().allowed_write(path,mkdir=mkdir,flags=flags)

        def source_transport(self):
            module=getattr(self,'runtime_owner',None)
            if module is None:return None
            outer=getattr(module._source_runner_scope,'__wrapped__',module._source_runner_scope)
            launch=[c for c in outer.__code__.co_consts if hasattr(c,'co_name') and c.co_name=='launch']
            need(len(launch)==1,'one original source transport launch code')
            frame=sys._getframe(1)
            while frame:
                if frame.f_code is launch[0] and frame.f_globals is module.__dict__:
                    if 'record' not in frame.f_locals:return None
                    facts=frame.f_locals['facts'];record=frame.f_locals['record']
                    tokens=[token for token,value in module._TRANSPORTS.items() if value is facts]
                    need(len(tokens)==1 and type(tokens[0]) is module._RunnerTransport and tokens[0].seal is module._SEAL
                         and facts['closed'] is False and facts['launches']==[record], 'actual original opaque source transport')
                    source=facts['source'];self.installed_source_launch()
                    module.verify_candidate_context(self.metadata_root,source)
                    need(source['run_id']==self.metadata_request['run_id'] and source['planner']==self.metadata_request['planner']
                         and Path(source._policy['source_root'])==H.SOURCE,'same original source input/run/profile')
                    logical=record['logical_argv'];actual=record['transport_argv']
                    need(actual==frame.f_locals['actual'] and logical==frame.f_locals['logical']
                         and record['bootstrap_raw_digest']==module.codec.raw_digest(frame.f_locals['bootstrap'].encode()),
                         'exact original actual/logical/bootstrap binding')
                    return frame,logical,actual,record
                frame=frame.f_back
            return None

        def describe_frame(self):
            return self.real_frame(self.common,'inspect_isolated_runner') if hasattr(self,'common') else None

        def audit_checked(self,event,values):
            if event=='msvcrt.locking' and self.finance_frame() is not None:
                frame=self.finance_frame();stream=frame.f_locals.get('stream')
                need(stream is not None and values==(stream.fileno(),values[1],1)
                     and H.key(stream.name)==H.key(self.finance/'funding.lock'),'actual original funding lock fd')
                self.funding_locks.append({'fd':values[0],'mode':values[1],'count':values[2],'stream':stream});return
            token=self.token
            if event=='open' and not isinstance(values[0],int) and os.fspath(values[0])==os.devnull:
                need(token and token.get('constructing') and token.get('kind')=='paid-cleanup',
                     'only original owned cleanup stdio null');return
            if event in ('subprocess.Popen','_winapi.CreateProcess') and token and token.get('kind') in ('paid-runner','describe-runner','paid-cleanup','metadata-git','metadata-bridge'):
                command=H.subprocess.list2cmdline(token['argv'])
                if event=='subprocess.Popen':
                    need(len(values)==4 and values[0]==token['executable'] and values[1]==command
                         and values[2]==token.get('cwd') and values[3] is None and not token['popen'],'exact actual consumer Popen audit')
                    token['popen']=True
                else:
                    need(token['popen'] and not token['create'] and len(values)==3 and values[0]==token['executable']
                         and values[2]==token.get('cwd'),'actual consumer CreateProcess order')
                    frame=sys._getframe(1)
                    while frame and frame.f_code is not H.EXECUTE.__code__:frame=frame.f_back
                    actual={} if frame is None else frame.f_locals
                    need(frame is not None and actual['self'] is token['process'] and actual['args']==command
                         and actual['executable']==token['executable'] and actual['cwd']==token.get('cwd') and actual['env'] is None
                         and actual['creationflags']==token['creationflags'] and actual['shell'] is False,'actual unchanged _execute_child fields')
                    token['create']=True
                return
            if event in ('os.listdir','os.scandir') and H.key(values[0]) in getattr(self,'finance_dirs',set())|getattr(self,'native_dirs',set()):return
            if event in ('os.rename','os.replace'):
                atomic=self.atomic_target()
                if atomic is not None:
                    frame,target,temp=atomic
                    need(temp is not None and H.key(values[0])==H.key(temp) and H.key(values[1])==H.key(target),
                         'only original authorized atomic replacement')
                    self.observed_writes.add(H.key(target));return
            if event in ('os.remove',) and self.atomic_target() is not None:
                frame,target,temp=self.atomic_target()
                need(temp is not None and H.key(values[0])==H.key(temp) and frame.f_locals.get('owned') is True,
                     'only original owned temporary cleanup');return
            if event=='open' and not isinstance(values[0],int) and H.key(values[0])==H.key(self.cleanup_program):
                need(not values[2]&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)
                     and self.own_frame('cleanup_fact') is not None,'only actual fixed cleanup read');return
            return super().audit_checked(event,values)

        def run_git(self,argv,**kwargs):
            caller=sys._getframe(1)
            metadata=self.metadata_call(caller,argv,kwargs)
            if metadata is not None:
                self.assert_active()
                number=len(self.metadata_rows)+1
                metadata_row={'number':number,'kind':metadata['kind'],'process':None,
                              'start_identity_error':None}
                self.metadata_rows.append(metadata_row)
                completed=None;error=None
                try:
                    completed=standard_run(argv,**kwargs)
                    return completed
                except BaseException as primary:
                    error=primary
                    raise
                finally:
                    try:self.close_metadata_child(metadata_row,completed,error)
                    except BaseException as closing:
                        if error is None:raise
                        error.add_note('original_metadata_close_unproven:'+repr(closing))
            args=(argv,)
            describe=self.describe_frame()
            if describe is caller:
                need(args==([*self.common._runner_prefix(H.SOURCE/'scripts/python/codex_isolated_model_runner.py',suppress_bytecode=True),'--describe'],)
                     and kwargs=={'text':True,'encoding':'utf-8','errors':'replace','stdout':H.subprocess.PIPE,'stderr':H.subprocess.STDOUT,'timeout':30},
                     'unchanged original zero-model describe run')
                return standard_run(*args,**kwargs)
            cleanup=self.real_frame(self.common,'_terminate_process_tree',self.cleanup_code) if hasattr(self,'common') else None
            if cleanup is caller:
                matches=[row for row in self.runner_rows if row['process'] is cleanup.f_locals['proc']]
                need(len(matches)==1 and args==(['taskkill','/PID',str(matches[0]['process'].pid),'/T','/F'],)
                     and kwargs=={'stdout':H.subprocess.DEVNULL,'stderr':H.subprocess.DEVNULL,'timeout':15,'check':False},
                     'unchanged original owned runner cleanup')
                return standard_run(*args,**kwargs)
            # Copied original inventory mechanism; the direct caller is the
            # genuine owner, not a forwarding adapter pretending to be it.
            self.assert_active()
            caller=sys._getframe(1)
            owner=self.inventory.git
            require(caller.f_code is owner.__code__ and caller.f_globals is self.inventory.__dict__
                    and isinstance(self.inventory.__loader__,H.Loader) and key(caller.f_locals['root'])==key(TARGET),
                    'original inventory.git caller/root')
            prefix = ['git','--no-optional-locks','--no-replace-objects','-c','protocol.allow=never',
                '-c','core.hooksPath=' + os.devnull,'-c','commit.gpgSign=false','-c','tag.gpgSign=false','-C',str(TARGET)]
            require(type(argv) is list and argv == prefix + list(caller.f_locals['args'])
                    and set(kwargs) == {'capture_output','timeout','env'} and kwargs['capture_output'] is True
                    and type(kwargs['timeout']) is int and kwargs['timeout'] == 30
                    and kwargs['env'] is caller.f_locals['child_env'], 'unchanged original argv/30s/capture_output/env object')
            self.git_shape(argv[len(prefix):])
            require(hash_file(GIT) == GIT_SHA and file_identity(GIT) == self.c['program_identities']['Git'], 'fixed Git before dispatch')
            number = len(self.git_intents) + 1
            require(number <= 4096, 'finite original Git read calls')
            stem = 'git/' + str(number) + '-'
            self.git_intents.append({'number':number, 'argv':argv})
            write_new(self.out / (stem+'intent.json'), raw_json({'argv':argv, 'executable':str(GIT),
                'timeout':30, 'capture_output':True, 'environment':kwargs['env'], 'original_optional':caller.f_locals['optional'], 'automatic_retry':False}))
            process = None; stdout = stderr = b''; error = None; timed_out = False; row = None
            try:
                process = POPEN(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(TASK),
                    env=kwargs['env'], executable=str(GIT), close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW)
                row = self.git_children[-1]
                try:
                    stdout, stderr = process.communicate(timeout=30)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    process.kill()  # Same newly-owned-child timeout cleanup as stdlib subprocess.run.
                    stdout, stderr = process.communicate(timeout=30)
            except BaseException as exc:
                error = exc
                if process is None and self.git_children and self.git_children[-1].get('number') == number:
                    row = self.git_children[-1]; process = row['process']
                if process is not None and process.poll() is None:
                    try:
                        process.wait(timeout=30)
                    except BaseException as wait_error:
                        if row is not None:
                            row['finite_wait_error'] = type(wait_error).__name__ + ':' + str(wait_error)
            finally:
                actual = None; raw_exit_query = None; closed = False
                post_identity = None; post_identity_error = None; exit_query_error = None
                handle_close_error = None; handle_close_attempted = False
                pre_identity_verified = False; terminal_birth_verified = False
                if process is not None:
                    try:
                        try:
                            pre_identity_verified = bool(row is not None and row['identity_error'] is None
                                and row['Popen_audit'] and row['CreateProcess_audit'] and row.get('image') is not None
                                and key(row['image']) == key(GIT) and row.get('birth_filetime',0) > 0)
                            post_identity = held(process)
                            require(pre_identity_verified, 'actual original pre-image/audits/birth fixed Git')
                            require(post_identity['pid'] == row['pid'] and post_identity['held_handle'] == row['held_handle']
                                    and post_identity['birth_filetime'] == row['birth_filetime'], 'same original Git held handle/PID/birth at terminal')
                            terminal_birth_verified = True
                            # Windows can deny image lookup after a known process exit.
                            # Preserve the actual error; a returned image must still match.
                            if post_identity['image'] is not None:
                                require(key(post_identity['image']) == key(GIT), 'available post-image must remain fixed Git')
                        except BaseException as identity_error:
                            post_identity_error = type(identity_error).__name__ + ':' + str(identity_error)
                        try:
                            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                            query = kernel.GetExitCodeProcess
                            query.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]; query.restype = wintypes.BOOL
                            value = wintypes.DWORD()
                            require(query(wintypes.HANDLE(int(process._handle)), ctypes.byref(value)), 'actual Git held exit query')
                            raw_exit_query = value.value
                            require(raw_exit_query != 259 and process.poll() == raw_exit_query, 'actual known original held Git terminal')
                            actual = raw_exit_query
                        except BaseException as query_error:
                            exit_query_error = type(query_error).__name__ + ':' + str(query_error)
                    finally:
                        # The original owned handle gets a close attempt even when
                        # post-identity or exit-query validation failed. No PID reopen.
                        handle_close_attempted = True
                        try:
                            process._handle.Close()
                            closed = True
                        except BaseException as close_error:
                            handle_close_error = type(close_error).__name__ + ':' + str(close_error)
                closing_errors = [value for value in (post_identity_error, exit_query_error, handle_close_error) if value is not None]
                closing_error = ';'.join(closing_errors) if closing_errors else None
                write_new(self.out / (stem+'stdout.bin'), stdout)
                write_new(self.out / (stem+'stderr.bin'), stderr)
                evidence = {k:v for k,v in (row or {}).items() if k != 'process'}
                evidence.update(number=number, argv=argv, actual_original_held_OS_exit=actual,
                    raw_GetExitCodeProcess_value=raw_exit_query, terminal_known=actual is not None,
                    python_returncode=None if process is None else process.returncode, timeout=timed_out,
                    error=None if error is None else type(error).__name__ + ':' + str(error),
                    post_identity=post_identity, post_identity_error=post_identity_error,
                    pre_identity_verified=pre_identity_verified, terminal_birth_verified=terminal_birth_verified,
                    exit_query_error=exit_query_error, handle_close_attempted=handle_close_attempted, handle_close_error=handle_close_error,
                    closing_error=closing_error, actual_handle_closed=closed,
                    stdout_sha256=digest(stdout), stderr_sha256=digest(stderr), stdout_bytes=len(stdout), stderr_bytes=len(stderr))
                write_new(self.out / (stem+'terminal.json'), raw_json(evidence))
                self.git_records.append(evidence)
            require(row is not None and row['identity_error'] is None and row['Popen_audit'] and row['CreateProcess_audit']
                    and pre_identity_verified and terminal_birth_verified and actual is not None
                    and closing_error is None and closed and hash_file(GIT) == GIT_SHA
                    and file_identity(GIT) == self.c['program_identities']['Git'], 'actual held Git audits/identity/program close')
            if error is not None:
                raise error
            if timed_out:
                raise subprocess.TimeoutExpired(argv, 30, stdout, stderr)
            self.observe_git_output(argv[len(prefix):], stdout, actual)
            return subprocess.CompletedProcess(argv, actual, stdout, stderr)

        def install(self):
            H.Guard.install(self)
            original_initialize=self.guarded_init
            guard=self
            def initialize(process,*args,**kwargs):
                metadata=guard.metadata_constructor(args,kwargs)
                direct=sys._getframe(1)
                inventory=(direct.f_code is PaidGuard.run_git.__code__ and direct.f_globals is globals()
                           and direct.f_locals.get('self') is guard and direct.f_locals.get('metadata') is None)
                if metadata is not None:
                    dispatch,call,row=metadata
                    need(guard.token is None,'one original metadata constructor')
                    token={'process':process,'argv':args[0],'kind':call['kind'],'executable':None,
                           'cwd':kwargs.get('cwd'),'creationflags':H.subprocess.CREATE_NO_WINDOW,
                           'constructing':True,'popen':False,'create':False,
                           'fresh_pipe_handles':set(),'used_pipe_handles':set()}
                    guard.token=token;row['process']=process
                    try:return H.INIT(process,*args,**kwargs)
                    finally:
                        token['constructing']=False;guard.token=None
                        row.update(Popen_audit=token['popen'],CreateProcess_audit=token['create'])
                        if getattr(process,'_child_created',False) and getattr(process,'_handle',None) is not None:
                            try:
                                row.update(H.held(process))
                                wanted=H.GIT if call['kind']=='metadata-git' else H.PYTHON
                                need(row['birth_filetime']>0 and row['image'] is not None
                                     and H.key(row['image'])==H.key(wanted) and token['popen'] and token['create'],
                                     'actual metadata held identity and dual audits')
                            except BaseException as error:
                                # Match the original H Git constructor: retain
                                # the identity failure but let original run own
                                # communicate/wait/timeout cleanup before close.
                                row['start_identity_error']=repr(error)
                if inventory:
                    need(guard.token is None and len(args)==1 and args[0]==guard.git_intents[-1]['argv']
                         and set(kwargs)=={'stdout','stderr','cwd','env','executable','close_fds','creationflags'}
                         and kwargs['stdout']==kwargs['stderr']==H.subprocess.PIPE and kwargs['cwd']==str(TASK)
                         and kwargs['executable']==str(H.GIT) and kwargs['close_fds'] is True
                         and kwargs['creationflags']==H.subprocess.CREATE_NO_WINDOW,
                         'exact original inventory query capture constructor')
                    token={'process':process,'argv':args[0],'env':kwargs['env'],'constructing':True,'kind':'git',
                           'popen':False,'create':False,'fresh_pipe_handles':set(),'used_pipe_handles':set()}
                    guard.token=token
                    try:return H.INIT(process,*args,**kwargs)
                    finally:
                        token['constructing']=False;guard.token=None
                        if getattr(process,'_child_created',False) and getattr(process,'_handle',None) is not None:
                            row={'number':guard.git_intents[-1]['number'],'process':process,'pid':process.pid,
                                 'held_handle':int(process._handle),'Popen_audit':token['popen'],
                                 'CreateProcess_audit':token['create'],'identity_error':None}
                            guard.git_children.append(row)
                            try:
                                row.update(H.held(process))
                                need(row['birth_filetime']>0 and row['image'] is not None
                                     and H.key(row['image'])==H.key(H.GIT) and token['popen'] and token['create'],
                                     'original inventory dual audits held birth image')
                            except BaseException as error:row['identity_error']=type(error).__name__+':'+str(error)
                            H.write_new(guard.out/('git/%s-started.json'%row['number']),
                                        H.raw_json({k:v for k,v in row.items() if k!='process'}))
                transport=guard.source_transport()
                cleanup=guard.real_frame(guard.common,'_terminate_process_tree',guard.cleanup_code) if hasattr(guard,'common') else None
                if transport is None and cleanup is None:return original_initialize(process,*args,**kwargs)
                need(guard.token is None,'one original constructor at a time')
                run=guard.real_frame(guard.common,'run_isolated_model',guard.run_code) if hasattr(guard,'common') else None
                describe=guard.describe_frame();contract=None
                if transport is not None:
                    frame,logical,actual,record=transport
                    need(frame.f_locals['prior'] is H.POPEN and list(args)==[actual], 'actual source transport to original Popen')
                    if run is not None:
                        contract=guard.owner.facade.current_schedule_grant().paid_dispatch_contract()
                        need(logical==contract['logical_command'] and contract['model_request_budget']==1
                             and not any(r.get('reservation_id')==contract['reservation_id'] for r in guard.runner_rows),
                             'one paid constructor per original reservation')
                        need(kwargs=={'text':False,'stdout':H.subprocess.PIPE,'stderr':H.subprocess.STDOUT,
                                      'creationflags':H.subprocess.CREATE_NEW_PROCESS_GROUP},'original paid IO/flags')
                        need(len(guard.runner_rows)<len(guard.plan['nodes']),'finite N actual constructor bound')
                        kind='paid-runner';flags=H.subprocess.CREATE_NEW_PROCESS_GROUP;held_frame=run
                    else:
                        need(describe is not None and logical==[*guard.common._runner_prefix(
                            H.SOURCE/'scripts/python/codex_isolated_model_runner.py',suppress_bytecode=True),'--describe'],
                            'actual original zero-model describe source')
                        need(kwargs=={'text':True,'encoding':'utf-8','errors':'replace',
                                      'stdout':H.subprocess.PIPE,'stderr':H.subprocess.STDOUT},'original describe IO')
                        kind='describe-runner';flags=0;held_frame=describe
                    executable=None
                else:
                    matches=[r for r in guard.runner_rows if r['process'] is cleanup.f_locals['proc']]
                    need(len(matches)==1 and list(args)==[['taskkill','/PID',str(matches[0]['process'].pid),'/T','/F']]
                         and kwargs=={'stdout':H.subprocess.DEVNULL,'stderr':H.subprocess.DEVNULL},'original owned cleanup constructor')
                    need(guard.cleanup_fact()==guard.cleanup_initial,'same original cleanup program')
                    kind='paid-cleanup';flags=0;held_frame=cleanup;executable=str(guard.cleanup_program)
                    kwargs={**kwargs,'executable':executable}
                token={'process':process,'argv':args[0],'kind':kind,'executable':executable,'creationflags':flags,
                       'constructing':True,'popen':False,'create':False,'fresh_pipe_handles':set(),'used_pipe_handles':set()}
                guard.token=token
                try:return H.INIT(process,*args,**kwargs)
                finally:
                    token['constructing']=False;guard.token=None
                    if getattr(process,'_child_created',False) and getattr(process,'_handle',None) is not None:
                        row={'process':process,'frame':held_frame,'kind':kind,'Popen_audit':token['popen'],
                             'CreateProcess_audit':token['create'],'start_identity_error':None}
                        if contract is not None:row.update(reservation_id=contract['reservation_id'],node_id=contract['node_id'])
                        rows=guard.runner_rows if kind=='paid-runner' else guard.describe_rows if kind=='describe-runner' else guard.cleanup_rows
                        rows.append(row)
                        try:
                            row.update(H.held(process));wanted=guard.cleanup_program if kind=='paid-cleanup' else H.PYTHON
                            need(row['birth_filetime']>0 and row['image'] is not None and H.key(row['image'])==H.key(wanted)
                                 and token['popen'] and token['create'],'actual held identity and dual audits')
                        except BaseException as error:
                            row['start_identity_error']=repr(error);raise
                        finally:H.write_new(guard.out/(kind+'-started-%s.json'%len(rows)),
                            H.raw_json({k:v for k,v in row.items() if k not in ('process','frame')}))
            self.guarded_init=initialize
            H.POPEN.__init__=initialize

        def close_finite_inputs(self):
            need(self.closed_coord_locks is not None and self.paid_output_rows is not None,
                 'original paid lock and exact output closure before finite after-pin')
            after=H.snapshot_tree(self.target);before=self.original_target_before
            old=set(before['files']);new=set(after['files'])-old
            changed={n for n in old if after['files'].get(n)!=before['files'][n]}
            need(set(before['files'])<=set(after['files']),'no old target removal')
            permitted=self.authorized|self.dynamic_outputs|self.closed_coord_locks
            need(all(H.key(self.target/n) in permitted for n in changed|new),'finite source-derived target writes only')
            for n,row in before['directories'].items():
                need(n in after['directories'] and row['identity']==after['directories'][n]['identity'],'old directory identity retained')
            for n in set(after['directories'])-set(before['directories']):
                need(H.key(self.target/n) in self.native_dirs,'finite native directories only')
            self.files.update({H.key(self.target/n):row['sha256'] for n,row in after['files'].items()})
            self.write_targets={H.key(self.target/n) for n in changed|new}
            self.c['target_before']=after;self.c['target_files']=after['files']
            self.c['target_directories']={n:row['members'] for n,row in after['directories'].items()}
            self.directories.update({H.key(self.target/n):row['members'] for n,row in after['directories'].items()})
            self.target_complete=True
            finance=H.snapshot_tree(self.finance);old_fin=self.original_finance_before
            need(set(old_fin['files'])<=set(finance['files']),'no original financial record removal')
            for n,row in old_fin['files'].items():need(finance['files'][n]==row,'old financial raw/identity retained')
            for n in set(finance['files'])-set(old_fin['files']):
                need(H.key(self.finance/n) in self.finance_files,'finite original financial rows/init/STOP/lock')
            for n,row in old_fin['directories'].items():
                need(n in finance['directories'] and row['identity']==finance['directories'][n]['identity'],'old finance directory identity')
            for n in set(finance['directories'])-set(old_fin['directories']):
                need(H.key(self.finance/n) in self.finance_dirs,'finite finance directories only')
            for n,row in finance['files'].items():self.files[H.key(self.finance/n)]=row['sha256']
            for n,row in finance['directories'].items():
                self.directories[H.key(self.finance/n)]=row['members']
                if H.key(self.finance/n) in self.metadata_directories:
                    self.metadata_directories[H.key(self.finance/n)]={'identity':row['identity'],'members':row['members']}
            H.Guard.close_inputs(self)
            return {'target_after':after,'finance_after':finance,'child_OS_sandbox_claimed':False}

        def close_paid_outputs(self):
            """Reuse Host3's exact output discovery/launch check and after-pin.

            Only this attempt's actually held runners select workspaces. No
            unstarted node, caller-supplied output list or receipt grants a role.
            """
            need(not self.paid_outputs_started,'one exact paid output closing observation')
            self.paid_outputs_started=True
            need(self.closed_coord_locks is not None,'original lock closing observation before target output snapshot')
            closed=self.closed_child_rows
            need(closed is not None and len(closed)==len(self.runner_rows+self.describe_rows+self.cleanup_rows)
                 and all(r['terminal_known'] and r['actual_handle_closed'] and not r['terminal_errors'] for r in closed),
                 'original held children closed before output observation')
            official=[Path(name) for name in self.c['official_CLI_binding']['files']
                      if Path(name).name=='codex.exe']
            need(len(official)==1,'one existing original official CLI binding')
            observed=[]
            for index,original in enumerate(self.runner_rows):
                terminal=closed[index]
                need(original['start_identity_error'] is None and terminal['actual_original_held_OS_exit']==0
                     and terminal['original_output_reader_closed']
                     and terminal['reservation_id']==original['reservation_id']
                     and terminal['node_id']==original['node_id'],'same actual successful closed paid node')
                nodes=[n for n in self.plan['nodes'] if n['node_id']==original['node_id']]
                need(len(nodes)==1,'one originally bound paid plan node')
                workspace=self.run/'q'/('n'+str(nodes[0]['ordinal']))/'m'
                frame=original['frame']
                need(frame.f_code is self.run_code and frame.f_globals is self.common.__dict__
                     and frame.f_locals.get('proc') is original['process']
                     and Path(frame.f_locals['workspace']).absolute()==workspace
                     and Path(frame.f_locals['output_path']).absolute()==workspace/'output.json'
                     and Path(frame.f_locals['execution_log']).absolute()==workspace.parent/'m-execution.json',
                     'same original common runner workspace output execution paths')
                names=H.members(workspace)
                journals=[name for name in names if re.fullmatch(r'output\.json\.[0-9a-f]{32}\.app-server\.jsonl',name)]
                need(len(journals)==1,'one original runner App Server journal per actual node')
                journal_path=workspace/journals[0]
                stderr_path=journal_path.with_suffix('.stderr.txt')
                need(set(names)=={'prompt.txt','input.json','output-schema.json','output.json',
                     'runner-input-integrity.json',journal_path.name,stderr_path.name},
                     'exact original paid workspace request output integrity journal stderr members')
                self.dynamic_outputs.update((H.key(journal_path),H.key(stderr_path)))
                launch=self.owner.h.parse(H.read(journal_path).splitlines()[0])
                need(launch['direction']=='host' and launch['message']['event']=='launch'
                     and H.key(launch['message']['executable'])==H.key(official[0]),
                     'actual original backend launch uses existing fixed official CLI')
                observed.append({'node_id':original['node_id'],'reservation_id':original['reservation_id'],
                    'journal':journal_path.relative_to(self.target).as_posix(),
                    'stderr':stderr_path.relative_to(self.target).as_posix()})
            # As in Host3, pin actual observed after-images before the original
            # Guard's full close. Finite native writes are closed separately.
            after=H.snapshot_tree(self.target)
            for row in observed:
                for role in ('journal','stderr'):
                    name=row[role];fact=after['files'][name]
                    self.files[H.key(self.target/name)]=fact['sha256']
                    self.write_targets.add(H.key(self.target/name))
                    row[role+'_after']=deepcopy(fact)
            self.paid_output_rows=observed
            return observed

        def close_children(self):
            rows = []
            for original in self.runner_rows + self.describe_rows + self.cleanup_rows:
                process = original['process']
                row = {k: v for k, v in original.items() if k not in {'process', 'frame'}}
                row.update(terminal_known=False, actual_original_held_OS_exit=None, actual_handle_closed=False, terminal_errors=[])
                try:
                    post = H.held(process)
                    row['post_identity'] = post
                    need(post['pid'] == row['pid'] and post['held_handle'] == row['held_handle'] and (post['birth_filetime'] == row['birth_filetime']), 'same original held child')
                    if post['image'] is not None:
                        need(H.key(post['image']) == H.key(row['image']), 'available post-exit image unchanged')
                    kernel = H.ctypes.WinDLL('kernel32', use_last_error=True)
                    query = kernel.GetExitCodeProcess
                    query.argtypes = [H.wintypes.HANDLE, H.ctypes.POINTER(H.wintypes.DWORD)]
                    query.restype = H.wintypes.BOOL
                    value = H.wintypes.DWORD()
                    need(query(H.wintypes.HANDLE(int(process._handle)), H.ctypes.byref(value)), 'actual original exit query')
                    row['raw_GetExitCodeProcess_value'] = value.value
                    need(value.value != 259 and type(process.returncode) is int and (process.returncode == value.value), 'original runner wait returned known OS terminal')
                    row.update(terminal_known=True, actual_original_held_OS_exit=value.value)
                    if row['kind'] == 'paid-runner':
                        capture = original['frame'].f_locals.get('capture')
                        row['original_output_reader_closed'] = bool(capture is not None and capture.done.is_set() and (not capture.worker.is_alive()) and process.stdout.closed)
                        need(row['original_output_reader_closed'], 'original WindowsRunnerOutput EOF/worker/pipe closed')
                    elif row['kind'] == 'describe-runner':
                        row['original_output_reader_closed'] = bool(process.stdout.closed and (getattr(process,'_stdout_thread',None) is None or not process._stdout_thread.is_alive()))
                        need(row['original_output_reader_closed'], 'original stdlib describe pipe/thread closed')
                except BaseException as error:
                    row['terminal_errors'].append(repr(error))
                finally:
                    try:
                        process._handle.Close()
                        row['actual_handle_closed'] = True
                    except BaseException as error:
                        row['terminal_errors'].append('Close:' + repr(error))
                rows.append(row)
            H.write_new(self.out / 'actual-owned-child-close.json', H.raw_json(rows))
            self.closed_child_rows=rows
            return rows

    return PaidGuard
