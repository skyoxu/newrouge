"""Root-only metadata seal, after the actual ready Request has been staged."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import types

TASK = Path(r'C:\Users\Administrator\Documents\Codex\2026-11-05\task')
HOME = TASK / 'night-handoff/story27-r52-public-review-prepare-host-followup02'
STAGE = TASK / 'logs/ci/2026-11-09/story27-r52-public-request-stage-02/result.json'
NATIVE_SEED = 'logs/ci/2026-11-09/story27-r52-v15-native-profile-seal-native02/config.json'
PROTECTION_SEED = 'logs/ci/2026-11-09/story27-r52-target-protection-seal-verify-03/config.json'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--Root-STOP', required=True)
    parser.add_argument('--Root-STOP-sha256', required=True)
    parser.add_argument('--stage-receipt-sha256', required=True)
    parser.add_argument('--request-sha256', required=True)
    parser.add_argument('--Root-stage-OS0', required=True, action='store_true')
    args = parser.parse_args()
    require = lambda ok, message: None if ok else (_ for _ in ()).throw(RuntimeError(message))
    require(Path.cwd() == TASK and os.name == 'nt' and sys.flags.dev_mode and sys.flags.isolated
            and sys.flags.no_site and sys.dont_write_bytecode and not sys.flags.optimize,
            'fixed ordinary isolated Root metadata host')
    require(datetime.now(timezone.utc).date().isoformat() == '2026-11-09', 'new day needs new reviewed scope')
    sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    require(sha(HOME / 'manifest.json') == args.manifest_sha256, 'exact reviewed manifest')
    manifest = json.loads((HOME / 'manifest.json').read_bytes())
    for name, row in manifest['files'].items():
        require(sha(HOME / name) == row['sha256'], 'reviewed control raw member')
    def no_dispatch(event, values):
        if event in {'subprocess.Popen','_winapi.CreateProcess','os.system','os.startfile','os.link','os.symlink'} or event.startswith(('socket.','os.exec','os.spawn','os.posix_spawn')):
            raise RuntimeError('metadata sealer denies child/network/link')
    sys.addaudithook(no_dispatch)
    host_path = HOME / 'review_prepare_host.draft.py'
    H = types.ModuleType('_Root_review_prepare_metadata_helpers'); H.__file__ = str(host_path)
    exec(compile(host_path.read_bytes(),str(host_path),'exec',dont_inherit=True,optimize=0),H.__dict__)
    declarations = json.loads(H.read(HOME / 'declarations.json'))
    for name, digest in declarations['prerequisite_pins'].items():
        require(H.hash_file(TASK / name) == digest, 'immutable prerequisite/control raw pin')
    stop_path = H.plain(TASK / args.Root_STOP)
    require(stop_path.is_relative_to(TASK/'logs/ci/2026-11-09')
            and H.hash_file(stop_path) == args.Root_STOP_sha256, 'actual independent new Root STOP')
    stop = json.loads(H.read(stop_path))
    require(stop['template_only_not_evidence'] is False, 'Root STOP must be a real observation, not template')
    require(all(stop[name] is True for name in ('all_source_writers_stopped','Root_normal_token',
            'original_nx_two_lock_scope_admitted','authenticated_capture_exact_reads_admitted',
            'finite_original_public_review_and_scope_lock_writes_admitted','official_CLI_public_data_only_scope_admitted')),
            'Root actual writers/normal-token/native/public finite scope admission')
    require(stop['operation_id'] == H.OPERATION and stop['request_ref'] == H.REQUEST
            and stop['model_calls_allowed'] == 0 and stop['new_financial_claim_allowed'] is False,
            'exact zero-model operation; no budget claim')
    require(stop['actual_stage_receipt_ref'] == STAGE.relative_to(TASK).as_posix()
            and stop['actual_stage_receipt_sha256'] == args.stage_receipt_sha256
            and stop['actual_request_sha256'] == args.request_sha256, 'Root actual authority binds the precise ready/staged bytes')
    require(H.hash_file(STAGE) == args.stage_receipt_sha256 and not (STAGE.parent/'STOP.json').exists(), 'actual new stage receipt and no STOP')
    staged = json.loads(H.read(STAGE))
    require(staged['passed'] is True and staged['request_staged'] is True and staged['source_closed'] is True
            and staged['schema65_closed'] is True and staged['all_old_target_Git_raw_identity_members_unchanged'] is True
            and staged['request_ref'] == staged['public_CLI_request_argument'] == H.REQUEST
            and staged['request_sha256'] == args.request_sha256 and staged['actual_subprocesses'] == staged['Git_calls'] == staged['model_calls'] == 0
            and staged['blocked_actions'] == [] and staged['formal_acceptance'] is False, 'actual complete original ready staging')
    require(H.snapshot_tree(H.TARGET) == staged['target_after'], 'actual complete staged target/Git/source closure unchanged')
    require(H.hash_file(H.TARGET/H.REQUEST) == args.request_sha256
            and len(H.read(H.TARGET/H.REQUEST)) == staged['request_bytes'], 'exact actual staged Request raw bytes')
    request = json.loads(H.read(H.TARGET/H.REQUEST))
    require(request['schema_version'] == 'newrouge.b-route-adoption-request.v2'
            and request['operation_id'] == H.OPERATION and 'host_review_ref' not in request,
            'actual initial public v2 request; no fabricated completed review')
    require(not (H.TARGET/H.REVIEW_HOME).exists(), 'fresh original review home')
    failed_close = json.loads(H.read(TASK/'logs/ci/2026-11-09/story27-r52-review-prepare01-preowner-failure-Root-close-01/result.json'))
    require(failed_close['original_exec'] == 79934 and failed_close['original_tool_OS_exit'] == 1
            and failed_close['failure_before_original_owner_reader_Git_or_locks'] is True
            and failed_close['complete_target_and_Git_raw_identity_members_unchanged'] is True
            and failed_close['source885_closed'] is True and failed_close['schema65_and_tokenizer15_closed'] is True
            and failed_close['failure_was_allowlist_model_omission_not_target_drift'] is True
            and failed_close['original_stop_preserved'] is True and failed_close['actual_model_calls_added'] == 0,
            'known original pre-owner failure and actual independent unchanged-source/target close required')
    old_failure = json.loads(H.read(TASK/failed_close['original_failure_ref']))
    require(H.hash_file(TASK/failed_close['original_failure_ref']) == failed_close['original_failure_sha256']
            and old_failure['passed'] is False and old_failure['original_owner_returncode'] is None
            and old_failure['reader_calls'] == 0 and old_failure['Git_records'] == []
            and old_failure['original_lock_rows'] == [] and old_failure['Job_observations']['assign_success'] == 0
            and old_failure['model_calls'] == 0, 'preserve old failed result; no original owner or child was started')
    native = json.loads(H.read(TASK/NATIVE_SEED))
    protection = json.loads(H.read(TASK/PROTECTION_SEED))
    config = {name:native[name] for name in ('source_files','source_directories','dependency_files','dependency_metadata_roots',
        'parent_import_paths','source_support','run_digest','fixed_original_reads','lock_paths','metadata_ancestor_paths',
        'official_CLI_binding','source_full_members','dependency_members','isolated_startup_paths','stdlib_search_metadata','program_file_identities')}
    config.update(schema_dependency_files=protection['schema_dependency_files'],schema_import_roots=protection['schema_import_roots'],
        source_directory_views=protection['source_directory_views'],source_full_directories=protection['source_full_directories'],
        import_metadata=protection['import_metadata'],program_identities=protection['program_identities'],
        protection_stdlib_search_metadata=protection['stdlib_search_metadata'])
    require(set(config['schema_dependency_files']) <= set(config['dependency_files']), 'schema dependency domain included in native80 seed')
    for name, digest in config['source_files'].items():
        require(H.hash_file(H.SOURCE/name) == digest, 'fresh full R52 raw source closure')
    for name, row in config['dependency_files'].items():
        require(H.hash_file(name) == row['sha256'], 'fresh complete schema/tokenizer dependency raw closure')
    for name, digest in config['fixed_original_reads'].items():
        require(H.hash_file(name) == digest, 'fixed original native / CLI DATA bytes unchanged')
    for name, row in config['official_CLI_binding']['files'].items():
        require(H.file_identity(name) == row['file_identity'], 'original public CLI five-file identities unchanged')
    for name, expected in config['program_file_identities'].items():
        require(H.file_identity(name) == expected, 'actual program identity unchanged')
    source_now = {name:H.members(H.SOURCE/name) for name in config['source_full_members']}
    require(source_now == config['source_full_members'], 'fresh full R52 directory membership')
    dependency_now = {name:H.members(name,validate_children=False) for name in config['dependency_members']}
    require(dependency_now == config['dependency_members'], 'fresh dependency directory metadata')
    metadata = {}
    for name in native['metadata_ancestor_members']:
        path = H.plain(name,missing=True)
        metadata[name] = None if not path.exists() else {'identity':[path.stat().st_dev,path.stat().st_ino],
                                                       'members':H.members(path,validate_children=False)}
    config['metadata_ancestor_members'] = metadata
    for name, expected in config['import_metadata'].items():
        path = H.plain(name,missing=True)
        observed = H.metadata_names(path)
        require(observed == expected, 'fixed schema import metadata unchanged')
    require(H.startup_metadata() == config['protection_stdlib_search_metadata'], 'actual official isolated stdlib metadata')
    config.update(target=str(H.TARGET),target_before=staged['target_after'],
        target_files=staged['target_after']['files'],target_directories={name:row['members'] for name,row in staged['target_after']['directories'].items()},
        target_write_paths=list(H.REVIEW_FILES),operation_id=H.OPERATION,request_ref=H.REQUEST,request_sha256=args.request_sha256,
        stage_receipt_ref=STAGE.relative_to(TASK).as_posix(),stage_receipt_sha256=args.stage_receipt_sha256,
        Root_STOP_ref=args.Root_STOP,Root_STOP_sha256=args.Root_STOP_sha256,model_calls_allowed=0,new_financial_claim_allowed=False,
        prerequisite_pins=declarations['prerequisite_pins'],
        Root_public_review_prepare_admitted=True,Root_request_actual_ready_staged=True,Root_fresh_source_closed=True,
        Root_normal_token=True,original_nx_two_lock_scope_admitted=True,authenticated_capture_exact_reads_admitted=True,
        official_CLI_public_data_only_scope_admitted=True,formal_acceptance=False,automatic_retry=False,
        actual_counts={'source':len(config['source_files']),'schema':len(config['schema_dependency_files']),
                       'tokenizer':len(set(config['dependency_files'])-set(config['schema_dependency_files'])),
                       'CLI_public_data':len(config['official_CLI_binding']['files'])},
        paid_or_unknown=80,guard_occupancy=178,campaign_limit=290,released=0)
    absent_files = ('docs/planning/b-route/catalog.v1.json','docs/planning/b-route/policy.v1.json',
                    'docs/planning/b-route/task-origins.v1.json','logs/ci/b-route-operations/pending.json')
    config['absent_target_files'] = [name for name in absent_files if not (H.TARGET/name).exists()]
    config['absent_target_directories'] = [name for name in ('docs/planning/b-route','docs/planning/b-route/plans',
        'logs/ci/b-route-operations/operations','logs/ci/capability-planning','logs/ci/mvg-planning') if not (H.TARGET/name).exists()]
    require(len(config['absent_target_files']) == len(absent_files), 'fresh unpublished target, preserve any existing governance')
    H.source_close(config)
    require(H.snapshot_tree(H.TARGET) == staged['target_after'], 'post-metadata staged target unchanged')
    output = H.plain(TASK/'logs/ci/2026-11-09/story27-r52-public-review-prepare-seal-02',missing=True)
    require(not output.exists(), 'new seal namespace; no retry')
    output.mkdir(exist_ok=False)
    H.write_new(output/'config.json',H.raw_json(config))
    print(json.dumps({'config':(output/'config.json').relative_to(TASK).as_posix(),
        'sha256':H.hash_file(output/'config.json'),'actual_counts':config['actual_counts'],'model_calls':0,'formal_acceptance':False}),flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
