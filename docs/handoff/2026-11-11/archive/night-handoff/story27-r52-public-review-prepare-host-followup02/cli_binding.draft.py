"""Finite public installation DATA role. This module never dispatches a CLI."""
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil

TASK = Path(r'C:\Users\Administrator\Documents\Codex\2026-11-05\task')
NPM = Path(r'C:\Users\Administrator\AppData\Roaming\npm')
PACKAGE = NPM / 'node_modules/@openai/codex'
NATIVE_PACKAGE = PACKAGE / 'node_modules/@openai/codex-win32-x64'
NATIVE = NATIVE_PACKAGE / 'vendor/x86_64-pc-windows-msvc/bin/codex.exe'
NATIVE_SHA = '9e7c59c05cc1ce5677b1f94e835b2ac038ca3be14504e78d558eacdb0ea3f55d'
FILES = (NATIVE, NPM / 'codex.cmd', NPM / 'codex', PACKAGE / 'package.json', NATIVE_PACKAGE / 'package.json')
RECORD_REF = 'logs/ci/2026-11-09/story27-installed-Codex-metadata-Root-01/record.json'
RECORD_SHA = 'ae907930757c9e4fad5c71bc060a6d724851cf1eb679a21dcb1f0526b8a980ad'


def need(value, why):
    if not value: raise RuntimeError('official_CLI_data_binding:' + why)


def bind_environment(environment):
    """Return the exact process-local search. Do not edit any OS/user setting."""
    result = dict(environment)
    result['PATH'] = os.pathsep.join([r'C:\Program Files\Git\mingw64\bin', r'C:\Program Files\Python312', str(NPM)])
    result['PATHEXT'] = '.EXE;.CMD'
    result.pop('CODEX_MANAGED_PACKAGE_ROOT', None)
    return result


def record_contract(record):
    if type(record) is not dict or type(record.get('files')) is not dict:
        return False
    return (record.get('scope') == 'installed public package data-only; no executable dispatch'
        and record.get('npm_directory') == str(NPM) and record.get('native_executable') == str(NATIVE)
        and record.get('embedded_original_3A_CLI_tool_path') == str(NATIVE)
        and record.get('embedded_original_3A_CLI_tool_raw_digest') == 'sha256:' + NATIVE_SHA
        and record.get('installed_native_cli_matches_original_3A_tool') is True
        and record.get('full_current_3A_identity_or_eligibility_reverified') is False
        and record.get('CLI_executed') is False and record.get('credentials_or_sessions_read') is False
        and record.get('system_PATH_changed') is False and record.get('authentication_or_network_settings_changed') is False
        and set(record['files']) == {str(path) for path in FILES})


def inspect_installation(S, record_path, runner_path, expected_runner_sha):
    """Root-only fresh file/name observations; exact original resolver is data-only."""
    need(S.sha(record_path) == RECORD_SHA, 'actual Root metadata receipt raw')
    record = json.loads(record_path.read_bytes())
    need(record_contract(record),
         'only original CLI component match, never whole 3A acceptance')
    need(set(record['files']) == {str(path) for path in FILES}, 'exact five public files only')
    observations = {}
    directories = set()
    for path in FILES:
        row = record['files'][str(path)]
        need(row['path'] == str(path) and type(row['sha256']) is str and len(row['sha256']) == 64,
             'literal public file record')
        before = S.file_identity(path)
        need(before[-1] == 1 and [before[0], before[1], before[2], before[3], before[5]] == row['file_identity']
             and before[2] == row['bytes'] and S.sha(path) == row['sha256'], 'fresh exact single-link public data file')
        need(S.file_identity(path) == before, 'public data identity stable while hashing')
        observations[str(path)] = {'sha256': row['sha256'], 'bytes': row['bytes'], 'file_identity': before}
        parent = path.parent
        while parent.is_relative_to(NPM):
            directories.add(str(parent))
            if parent == NPM: break
            parent = parent.parent
    need(observations[str(NATIVE)]['sha256'] == NATIVE_SHA and observations[str(NATIVE)]['bytes'] == 326875440,
         'same native CLI path/raw identity as captured original 3A component')
    package = json.loads((PACKAGE / 'package.json').read_bytes())
    need(package['name'] == record['installed_package_name'] == '@openai/codex'
         and package['version'] == record['installed_package_version'] == '0.160.1', 'recorded public package metadata')
    # Preserve the real original path resolver, including its unique native
    # optional-package glob. No replacement/fake identity or executable call.
    need(S.sha(runner_path) == expected_runner_sha, 'original R5 resolver source pin')
    node = next(n for n in ast.parse(runner_path.read_bytes()).body
                if isinstance(n, ast.FunctionDef) and n.name == '_codex_executable')
    namespace = {'Path': Path, 'shutil': shutil, 'os': os}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(runner_path), 'exec'), namespace)
    prior_environment = dict(os.environ); prior_cwd = Path.cwd()
    try:
        environment = bind_environment(prior_environment)
        os.environ.clear(); os.environ.update(environment)
        os.chdir(S.plain(TASK / 'r5'))
        resolved = Path(namespace['_codex_executable']()).resolve(strict=True)
    finally:
        os.chdir(prior_cwd); os.environ.clear(); os.environ.update(prior_environment)
    need(str(resolved) == record['embedded_original_3A_CLI_tool_path'], 'real original resolver selects exact captured native path')
    # These original tool_identity globs are untouched. Every possible existing
    # match must stay in the five-file DATA role; unknown matches fail closed.
    for parent in list(NATIVE.parents)[:4]:
        for pattern in ('@openai/codex-*/vendor/*/codex/codex*', 'vendor/*/codex/codex*'):
            for binary in parent.glob(pattern):
                if binary.is_file(): need(str(binary.resolve(strict=True)) in observations, 'unlisted original CLI identity glob match')
        directories.update(str(parent / suffix) for suffix in ('@openai', 'vendor'))
    directories.add(str(PACKAGE / 'vendor'))
    members = {name: S.metadata_listing(name) for name in sorted(directories)}
    for path in FILES:
        need(S.sha(path) == observations[str(path)]['sha256']
             and S.file_identity(path) == observations[str(path)]['file_identity'], 'public installation final raw/identity close')
    return {'record_ref': RECORD_REF, 'record_sha256': RECORD_SHA, 'files': observations, 'metadata_members': members,
            'npm_directory': str(NPM), 'native_executable': str(NATIVE), 'native_sha256': NATIVE_SHA,
            'original_resolver_selected_same_native_path': True, 'data_read_only_no_dispatch_role': True,
            'full_current_3A_identity_or_eligibility_reverified': False,
            'process_local_PATHEXT': '.EXE;.CMD', 'CODEX_MANAGED_PACKAGE_ROOT_used': False}
