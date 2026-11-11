"""AST assembly tail; no author execution. The assembled host is the entry."""


def target_close(config, guard):
    actual = snapshot_tree(TARGET)
    before = config['target_before']
    new_files = {Path(name).relative_to(Path(key(TARGET))).as_posix()
                 for name in guard.review_files | guard.target_scope_locks}
    require(set(actual['files']) == set(before['files']) | new_files, 'only actual four review files and original new scope locks')
    for name, row in before['files'].items():
        require(actual['files'][name] == row, 'all original target/Git/capsule/request raw and identities unchanged')
    allowed_dirs = {Path(name).relative_to(Path(key(TARGET))).as_posix() for name in guard.public_directories}
    for name in new_files:
        parent = Path(name).parent
        while str(parent) != '.':
            allowed_dirs.add(parent.as_posix())
            parent = parent.parent
    require(set(actual['directories']) <= set(before['directories']) | allowed_dirs, 'only finite original namespace directories')
    for name, row in before['directories'].items():
        now = actual['directories'][name]
        require(now['identity'] == row['identity'], 'old target directory identity unchanged')
        additions = {Path(path).name for path in new_files | allowed_dirs
                     if Path(path).parent.as_posix() == (name or '.')}
        require(set(now['members']) == set(row['members']) | additions.intersection(now['members']), 'old target directory membership unchanged except admitted children')
    return actual


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--config-sha256', required=True)
    args = parser.parse_args()
    require(os.name == 'nt' and sys.flags.dev_mode and sys.flags.isolated and sys.flags.no_site
            and sys.dont_write_bytecode and not sys.flags.optimize and Path.cwd() == TASK
            and Path(sys.executable).absolute() == PYTHON and Path(__file__).absolute() == HOME / 'review_prepare_host.draft.py', 'fixed isolated Root entry')
    require(datetime.now(timezone.utc).date().isoformat() == '2026-11-09', 'new day requires new reviewed namespace')
    require(hash_file(HOME / 'manifest.json') == args.manifest_sha256, 'exact reviewed manifest')
    manifest = json.loads(read(HOME / 'manifest.json'))
    for name, row in manifest['files'].items():
        require(hash_file(HOME / name) == row['sha256'], 'all reviewed control bytes')
    config_path = plain(TASK / args.config)
    require(config_path.is_relative_to(TASK / 'logs/ci/2026-11-09') and hash_file(config_path) == args.config_sha256, 'actual Root config pin')
    config = json.loads(read(config_path))
    require(all(config[name] is True for name in ('Root_public_review_prepare_admitted','Root_request_actual_ready_staged',
            'Root_fresh_source_closed','Root_normal_token','original_nx_two_lock_scope_admitted',
            'authenticated_capture_exact_reads_admitted','official_CLI_public_data_only_scope_admitted')),
            'actual Root admission and source/request seal required')
    require(config['target'] == str(TARGET) and config['operation_id'] == OPERATION
            and config['request_ref'] == REQUEST and config['model_calls_allowed'] == 0, 'only exact original public review-prepare')
    out = plain(TASK / 'logs/ci/2026-11-09/story27-r52-public-review-prepare-02', missing=True)
    require(not out.exists(), 'fresh output; preserve any attempt')
    source_close(config)
    require(snapshot_tree(TARGET) == config['target_before'], 'fresh staged target/Git equals actual seal')
    require(hash_file(TARGET / REQUEST) == config['request_sha256'] and not (TARGET / REVIEW_HOME).exists(), 'actual new request and review namespace')
    out.mkdir(exist_ok=False)
    write_new(out / 'offline-codex-home/models_cache.json', MODEL_CATALOG)
    inherited_limit = os.environ.get('SC_CAPABILITY_MAX_INPUT_TOKENS')
    require(inherited_limit in (None,'70000','96000'), 'same finite native04 inherited input limit')
    safe_env = {name: os.environ[name] for name in ('SystemRoot','WINDIR','SystemDrive','TEMP','TMP',
                'PROCESSOR_ARCHITECTURE','NUMBER_OF_PROCESSORS') if name in os.environ}
    safe_env.update(CODEX_HOME=str(out / 'offline-codex-home'), NEWROGUE_CODEX_REASONING_EFFORT='high',
        PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', TIKTOKEN_CACHE_DIR=str(TASK / 'story22-tokenizer-cache'),
        PATH=str(GIT.parent)+os.pathsep+str(PYTHON.parent), PATHEXT='.EXE',
        GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_COUNT='0',
        GIT_TERMINAL_PROMPT='0',GIT_OPTIONAL_LOCKS='0')
    cli_path = HOME / 'cli_binding.draft.py'
    require(hash_file(cli_path) == '13e51ca6a806505b68b8bc73b216530809f09d438c6d94b9ada30f7ae7fc6fbd', 'same validated CLI DATA helper')
    cli = types.ModuleType('_Root_review_prepare_CLI_environment'); cli.__file__ = str(cli_path)
    exec(compile(read(cli_path), str(cli_path), 'exec'), cli.__dict__)
    safe_env = cli.bind_environment(safe_env)
    if inherited_limit is not None:
        safe_env['SC_CAPABILITY_MAX_INPUT_TOKENS'] = inherited_limit
    os.environ.clear(); os.environ.update(safe_env)
    guard = Guard(config, out)
    guard.files.update({key(config_path):args.config_sha256,key(PYTHON):PYTHON_SHA,key(GIT):GIT_SHA,
        key(out/'offline-codex-home/models_cache.json'):digest(MODEL_CATALOG),key(HOME/'manifest.json'):args.manifest_sha256})
    guard.files.update({key(HOME/name):row['sha256'] for name,row in manifest['files'].items()})
    guard.files.update({key(TASK/name):pin for name,pin in config['prerequisite_pins'].items()})
    guard.files[key(TASK/config['Root_STOP_ref'])] = config['Root_STOP_sha256']
    guard.files[key(TASK/config['stage_receipt_ref'])] = config['stage_receipt_sha256']
    stdout, stderr = io.StringIO(), io.StringIO()
    outcome = {'passed':False,'operation_id':OPERATION,'stage':'review-prepare','model_calls':0,
        'formal_acceptance':False,'automatic_retry':False,'paid_or_unknown':80,'guard_occupancy':178,'campaign_limit':290,'released':0,
        'offline_catalog_is_current_model_or_high_evidence':False}
    write_new(out/'intent.json',raw_json(outcome))
    code = None
    try:
        guard.install(); guard.close_inputs(); guard.observe_original_locks()
        lifetime = importlib.import_module('_b_route_reader_lifetime')
        guard.wrap_transport(lifetime)
        guard.inventory = importlib.import_module('_b_route_inventory')
        owner = importlib.import_module('b_route_adoption')
        require(owner.__file__ == str(SOURCE/'scripts/python/b_route_adoption.py') and isinstance(owner.__loader__,Loader), 'original public SourceOnly CLI owner')
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = owner.main(['--root',str(TARGET),'--stage','review-prepare','--operation-id',OPERATION,'--request',REQUEST])
        write_new(out/'owner-stdout.bin',stdout.getvalue().encode('utf-8'))
        write_new(out/'owner-stderr.bin',stderr.getvalue().encode('utf-8'))
        result = json.loads(stdout.getvalue())
        require(type(code) is int and code == 0 and result['status'] == 'review_prepared'
                and result['operation_id'] == OPERATION and result['model_dispatched'] is False
                and result['semantic_execution_required'] is True and result['machine_preservation'] is None
                and all(result[name] is False for name in ('formal_adoption','readiness','runtime_verified')), 'actual complete public review-prepare result')
        require(guard.transport_calls == 1 and len(guard.children) == 1
                and guard.job_observations['assign_success'] == 1 and guard.job_observations['last_active'] == 0
                and guard.job_observations['close_success'] == 1, 'actual original full reader/Job completed')
        require(guard.public_scope_admitted and guard.target_scope_locks, 'actual original scope denominator and locks')
        lock_rows = guard.completed_lock_rows + list(guard.lock_descriptors.values())
        require({row['path'] for row in lock_rows} == guard.locks
                and all(row['acquire_returned'] and row['unlock_returned'] and row['close_returned'] and not row['errors'] for row in lock_rows), 'all actual original nx and target scope locks acquired/unlocked/closed')
        require(len(guard.git_intents) == len(guard.git_records) > 0 and all(row['actual_original_held_OS_exit'] is not None
                and row['actual_handle_closed'] and row['closing_error'] is None and not row['timeout']
                and row['Popen_audit'] and row['CreateProcess_audit'] for row in guard.git_records), 'all original readonly Git held terminals closed')
        guard.target_complete = True
        guard.close_inputs(); source_close(config)
        after = target_close(config, guard)
        review_pins = {name:hash_file(TARGET/name) for name in REVIEW_FILES}
        require(result['subject_ref'] == REVIEW_HOME+'/subject.json' and result['workspace'] == REVIEW_HOME+'/w'
                and result['execution_capture_ref'] == REVIEW_HOME+'/execution.json'
                and result['required_environment'] == {'NEWROGUE_CODEX_REASONING_EFFORT':'high'}, 'actual exact original review outputs and command description')
        write_new(out/'owner-result.json',raw_json(result))
        write_new(out/'lock-events.json',raw_json({'path_events':guard.lock_events,'actual_byte_lock_and_close':lock_rows}))
        write_new(out/'codec-fd-events.json',raw_json(guard.codec_fd_events))
        outcome.update(passed=True,original_owner_returncode=code,owner_result=result,review_files=review_pins,
            actual_native_capture_sha256=hash_file(out/'actual-native-capture.json'),Job_observations=guard.job_observations,
            actual_held_Git=guard.git_records,all_scope_lock_rows=lock_rows,target_after=after,source_closed=True,
            request_ref=REQUEST,request_sha256=config['request_sha256'],stage_receipt_ref=config['stage_receipt_ref'],
            stage_receipt_sha256=config['stage_receipt_sha256'],actual_counts=config['actual_counts'])
        write_new(out/'result.json',raw_json(outcome))
        guard.close_inputs(); source_close(config)
        require(snapshot_tree(TARGET) == after,'post-result original target/member closure')
        print(json.dumps({'passed':True,'stage':'review-prepare','result_sha256':hash_file(out/'result.json'),
                          'model_calls':0,'formal_acceptance':False}),flush=True)
        return 0
    except BaseException as error:
        for name,value in (('owner-stdout.bin',stdout.getvalue()),('owner-stderr.bin',stderr.getvalue())):
            if not (out/name).exists():write_new(out/name,value.encode('utf-8'))
        outcome.update(passed=False,error_type=type(error).__name__,reason=str(error)[:2048],original_owner_returncode=code,
            blocked_actions=guard.blocked,Git_records=guard.git_records,reader_calls=guard.transport_calls,
            Job_observations=guard.job_observations,original_lock_rows=guard.completed_lock_rows+list(guard.lock_descriptors.values()))
        write_new(out/'STOP.json',raw_json(outcome));traceback.print_exc();return 1


if __name__ == '__main__':
    raise SystemExit(main())
