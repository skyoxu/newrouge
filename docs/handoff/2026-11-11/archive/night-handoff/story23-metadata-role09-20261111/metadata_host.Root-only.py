"""UNEXECUTED Task-only metadata scope over original H and metadata06.

No public review, lock, native, finance, paid or target-write role is inherited.
The in-memory H tables are consumed-file observations, not a new authority.
"""
import ast
import fnmatch
import os
from pathlib import Path
import sys

TASK = Path(r'C:\Users\Administrator\Documents\Codex\2026-11-05\task')
SOURCE = TASK / 'r59'
TARGET = TASK / 'nx'
PRESERVED = TASK / 'r5'
CONTRACT = 'logs/ci/2026-11-06/story25-post-v4-native/3b/planning-contract.json'


def need(ok, why):
    if not ok:
        raise RuntimeError('metadata_only_host:' + why)


def literal_assignments(path):
    tree = ast.parse(path.read_bytes(), filename=str(path))
    result = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                result[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
        if isinstance(node, ast.FunctionDef) and node.name == 'policy_identity':
            for item in node.body:
                if isinstance(item, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'names' for t in item.targets):
                    result['policy_names'] = ast.literal_eval(item.value)
    return result


def make_metadata_guard(H, metadata06):
    """Compose real original factory before installing its captured run hooks."""
    need(H.SOURCE == SOURCE and H.TARGET == TARGET, 'actual fixed source and artifact roots')
    Paid = metadata06.make_paid_guard(H)
    runtime_data = literal_assignments(SOURCE / 'scripts/python/_b_route_segmented_runtime.py')
    schema_data = literal_assignments(SOURCE / 'scripts/python/_b_route_schema_resources.py')
    policy_paths = {H.key(SOURCE / 'scripts/python' / n) for n in runtime_data['policy_names']}
    policy_paths.update(H.key(SOURCE / n) for n in runtime_data['_DESCRIBE_NAMES'])
    schema_paths = {H.key(SOURCE / 'docs/planning/b-route/schemas' / (n + '.schema.json'))
                    for n in schema_data['FORMAL'] + schema_data['AUXILIARY']}

    class MetadataGuard(Paid):
        def __init__(self, out, *, dependency_files, dependency_members, import_paths, control_pins):
            # H initializes FD/constructor/audit state. Its public target data
            # placeholders are NOT an assertion of target closure or a ban.
            # All target writes are forbidden by overrides below; scoped close
            # deliberately never calls H.close_inputs/target_close/source_close.
            c = dict(target=str(TARGET), source_files={}, dependency_files={},
                     source_full_members={}, dependency_members={}, fixed_original_reads={},
                     target_files={}, target_directories={}, metadata_ancestor_members={},
                     lock_paths=[], target_write_paths=[], absent_target_files=[],
                     absent_target_directories=[], isolated_startup_paths=list(H.ISOLATED_STARTUP_PATHS),
                     parent_import_paths=[str(p) for p in import_paths],
                     program_identities={'Python': H.file_identity(H.PYTHON), 'Git': H.file_identity(H.GIT)})
            H.Guard.__init__(self, c, out)
            self.available_dependencies = {H.key(p): row['sha256'] for p, row in dependency_files.items()}
            self.identities = {}
            self.admitting = None
            self.observations = {}
            self.nx_reads = set()
            self.r5_reads = set()
            self.write_events = []
            self.enumeration_refusals = []
            self.enumeration_diagnostic_errors = []
            self.import_directories = {H.key(p) for p in import_paths}
            self.dependency_directories = {H.key(p) for p in dependency_members}
            self.closing_observations = False
            self.input_owners = None
            self.workflow = None
            self.functions = {}
            self.runner_rows, self.describe_rows, self.cleanup_rows = [], [], []
            self.closed_child_rows = None
            # Explicitly no public authorization. Overrides, not these empty
            # collections, enforce the ban even if an inherited method mutates them.
            self.public_directories = set()
            self.review_files = set()
            self.locks = self.write_targets = self.lock_parents = set()
            self.startup_before = H.startup_metadata()
            for path, pin in control_pins.items():
                self._pin(path, expected=pin)
            self._pin(H.PYTHON, expected=H.PYTHON_SHA)
            self._pin(H.GIT, expected=H.GIT_SHA)

        def _pin(self, path, *, expected=None, code=False):
            name = H.key(path)
            before = self.admitting
            self.admitting = name
            try:
                raw = H.hash_file(name)
                identity = H.file_identity(name)
            finally:
                self.admitting = before
            need(expected is None or raw == expected, 'original exact input pin:' + name)
            need(name not in self.files or self.files[name] == raw, 'consumed input changed:' + name)
            need(name not in self.identities or self.identities[name] == identity, 'consumed identity changed:' + name)
            self.files[name], self.identities[name] = raw, identity
            if code:
                self.code_files.add(name)

        def frame(self, module, function):
            if module is None or not isinstance(getattr(module, '__loader__', None), H.Loader):
                return None
            original = self.functions.get((module.__name__, function))
            value = module
            for part in function.split('.'):
                value = getattr(value, part)
            body = getattr(value, '__wrapped__', value)
            if original is not None:
                need((value, body.__code__) == original, 'original input owner unchanged')
            frame = sys._getframe(1)
            while frame:
                if (frame.f_code is body.__code__ and frame.f_globals is module.__dict__
                        and H.key(frame.f_code.co_filename) == H.key(module.__file__)):
                    return frame
                frame = frame.f_back
            return None

        def bind_input_owners(self, sources, native, inventory, codec, schemas, workflow):
            owners = (sources, native, inventory, codec, schemas, workflow)
            need(self.input_owners is None, 'input owners bound once')
            for module in owners:
                need(isinstance(module.__loader__, H.Loader) and module.__loader__.guard is self
                     and Path(module.__file__).absolute().parent == SOURCE / 'scripts/python',
                     'actual current SourceOnly input owner')
            self.input_owners = owners
            self.workflow = workflow
            for module, names in ((sources, ('Observations.read', 'Observations.members', 'Observations.verify', 'checked_path')),
                                  (native, ('resolve_sources',)), (inventory, ('safe_source_pattern', 'safe_input')),
                                  (codec, ('read_reference_bytes',)), (schemas, ('resources',)),
                                  (workflow, ('freeze_manifest', '_read')),
                                  (self.runtime_owner, ('capture_source', 'verify_candidate_context', 'policy_identity', '_derived_catalog', '_preserved_owner', 'value', 'raw')),
                                  (self.runtime_owner.planning, ('read_contract',)),
                                  (self.transition, ('_source_manifest',))):
                for name in names:
                    value = module
                    for part in name.split('.'):
                        value = getattr(value, part)
                    self.functions[(module.__name__, name)] = (value, getattr(value, '__wrapped__', value).__code__)

        def observation(self):
            if self.input_owners is None:
                return None
            sources = self.input_owners[0]
            for method in ('read', 'members', 'verify'):
                active = self.frame(sources, 'Observations.' + method)
                if active is None:
                    continue
                obs = active.f_locals.get('self')
                need(type(obs) is sources.Observations and Path(obs.root).absolute() == TARGET,
                     'actual target Observations instance and root')
                capture = self.frame(self.runtime_owner, 'capture_source')
                verify = self.frame(self.runtime_owner, 'verify_candidate_context')
                accepted = False
                if capture is not None:
                    accepted = (capture.f_locals.get('obs') is obs
                        and Path(capture.f_locals['root']).absolute() == TARGET
                        and {k: capture.f_locals[k] for k in ('run_id', 'planner', 'planning_contract')} == self.metadata_request)
                if verify is not None:
                    token = verify.f_locals.get('token')
                    accepted = accepted or (verify.f_locals.get('obs') is obs
                        and type(token) is self.runtime_owner._SourceCapture
                        and token in self.runtime_owner._SOURCES and token._seal is self.runtime_owner._SEAL
                        and token._root == TARGET and token['run_id'] == self.metadata_request['run_id']
                        and token['planner'] == self.metadata_request['planner']
                        and token['source_identity']['planning_contract_ref'] == CONTRACT)
                if self.closing_observations:
                    accepted = accepted or self.observations.get(id(obs)) is obs
                need(accepted, 'original capture/issued verify/known close input owner')
                self.observations[id(obs)] = obs
                return obs, active
            return None

        def material_read(self):
            """Original freeze rereads only actual already observed material bytes."""
            if self.workflow is None:
                return None
            original = self.frame(self.workflow, '_read')
            freeze = self.frame(self.workflow, 'freeze_manifest')
            derived = self.frame(self.runtime_owner, '_derived_catalog')
            capture = self.frame(self.runtime_owner, 'capture_source')
            if not all((original, freeze, derived, capture)):
                return None
            obs = derived.f_locals['obs']
            value = original.f_locals['value']
            need(capture.f_locals.get('obs') is obs and self.observations.get(id(obs)) is obs
                 and freeze.f_locals['materials'] is derived.f_locals['declarations']
                 and Path(original.f_locals['root']).absolute() == TARGET
                 and Path(freeze.f_locals['root']).absolute() == TARGET
                 and freeze.f_locals['run_id'] == self.metadata_request['run_id']
                 and value in obs.files and obs.files[value] is not None,
                 'actual original manifest material is an already observed complete input')
            self.runtime_owner.role(value)
            return obs, value

        def preserved_identity_read(self, name):
            owner = self.frame(self.runtime_owner, '_preserved_owner')
            capture = self.frame(self.runtime_owner, 'capture_source')
            value = self.frame(self.runtime_owner, 'value')
            raw = self.frame(self.runtime_owner, 'raw')
            if not all((owner, capture, value, raw)):
                return None
            contract = owner.f_locals.get('contract')
            if contract is not capture.f_locals.get('contract') or type(contract) is not dict:
                return None
            expected = Path(contract['audit_ref']).parent.as_posix() + '/identity.json'
            if (owner.f_locals.get('identity_name') != expected
                    or value.f_locals.get('name') != expected
                    or raw.f_locals.get('name') != expected
                    or any(Path(f.f_locals['root']).absolute() != TARGET for f in (owner,capture,value,raw))
                    or H.key(TARGET / expected) != name):
                return None
            # This is unverified verifier-selection metadata, never authority.
            # Original complete preserved proof/currentness checks still follow.
            self.runtime_owner.role(expected)
            return expected

        def check_code_path(self, path):
            name = H.key(path)
            if name.endswith(('.pyc', '.pyo')):
                self.deny('no sourceless code', name)
            if name in self.code_files or self.runtime(name):
                return
            finder = sys._getframe(1)
            while finder and not (finder.f_code is H.Finder.find_spec.__code__ and finder.f_globals is H.__dict__):
                finder = finder.f_back
            need(finder is not None and finder.f_locals['self'].guard is self
                 and H.key(finder.f_locals['spec'].origin) == name, 'real original Finder-selected import')
            p = Path(name)
            current = any(p.is_relative_to(Path(H.key(SOURCE / sub))) for sub in ('scripts/python', 'scripts/sc'))
            need(not any(x.casefold() == 'tests' for x in p.parts) and not p.name.startswith('test_'), 'no test code role')
            if current:
                need(p.suffix == '.py', 'current source import is Python source')
                self._pin(name, code=True)
            else:
                need(name in self.available_dependencies and p.suffix in ('.py', '.pyd'),
                     'missing exact dependency code DATA:' + name)
                self._pin(name, expected=self.available_dependencies[name], code=True)

        def allowed_read(self, path):
            name = H.key(path)
            need('s2' not in {p.casefold() for p in Path(name).parts}, 'no S2')
            if name == self.admitting or name in self.files or self.runtime(name) or Path(name).is_relative_to(self.out):
                return
            if name in self.available_dependencies:
                self._pin(name, expected=self.available_dependencies[name])
                return
            if name in policy_paths and self.frame(getattr(self, 'runtime_owner', None), 'policy_identity') is not None:
                self._pin(name)
                return
            schemas = self.input_owners[4] if self.input_owners else None
            if name in schema_paths and self.frame(schemas, 'resources') is not None:
                self._pin(name)
                return
            transition = getattr(self, 'transition', None)
            original = self.frame(transition, '_source_manifest')
            if original is not None:
                local = original.f_locals
                if (Path(local['root']).absolute() == PRESERVED
                        and local['commit'] == self.runtime_owner._PRESERVED_COMMIT
                        and local.get('source') is not None and H.key(local['source']) == name
                        and local['name'] in local['tracked']):
                    self._pin(name)
                    self.r5_reads.add(name)
                    return
            identity = self.preserved_identity_read(name)
            if identity is not None:
                self._pin(name)
                self.nx_reads.add(identity)
                return
            observation = self.observation()
            if observation:
                obs, active = observation
                read = self.frame(self.input_owners[0], 'Observations.read')
                if read is not None and read.f_locals['self'] is obs:
                    value = read.f_locals['value']
                    self.runtime_owner.role(value)
                    need(H.key(TARGET / value) == name, 'exact actual observation locator, not target prefix')
                    self.nx_reads.add(value)
                    return
            material = self.material_read()
            if material is not None and H.key(TARGET / material[1]) == name:
                self.nx_reads.add(material[1])
                return
            self.deny('metadata read outside consumed code/dependency/original input role', name)

        def allowed_write(self, path, mkdir=False, flags=None):
            name = H.key(path)
            need(Path(name).is_relative_to(self.out), 'no nx/source/finance/old-log/lock write')
            H.plain(path, missing=True)
            if not mkdir:
                need(type(flags) is int and flags & os.O_EXCL and flags & os.O_CREAT,
                     'only new exclusive output files')
            self.write_events.append({'path': name, 'mkdir': mkdir})

        def role(self, frame, event, arg):
            if event != 'call':
                return
            filename = frame.f_code.co_filename
            if filename and not filename.startswith('<'):
                p = Path(filename)
                module, name = p.name, frame.f_code.co_name
                prohibited = (
                    module in {'_b_route_segmented_funding.py', '_b_route_segmented_journal.py'} and name != '<module>'
                    or module == '_b_route_inventory.py' and name == 'git'
                    or name in {'scope_guard', 'coordinator_lock', 'operation_lock', 'run_isolated_model',
                                'capture_plan_authority', 'prepare_run', '_prepare_run_fiscal', 'financial_repair_birth',
                                'execute_workflow', 'publish_born', 'commit_checkpoint', 'prepare_review', 'complete_review'})
                if prohibited and p.is_relative_to(SOURCE):
                    self.deny('no public/lock/paid/native/finance owner in metadata lane', [module, name])
            return H.Guard.role(self, frame, event, arg)

        @staticmethod
        def pattern_directory(parts, wanted):
            if not parts:
                return True
            if not wanted:
                return False
            if wanted[0] == '**':
                return (MetadataGuard.pattern_directory(parts, wanted[1:])
                        or MetadataGuard.pattern_directory(parts[1:], wanted))
            return (fnmatch.fnmatchcase(parts[0].casefold(), wanted[0].casefold())
                    and MetadataGuard.pattern_directory(parts[1:], wanted[1:]))

        def enumeration(self, path):
            name = H.key(path)
            if Path(name).is_relative_to(self.out) or self.runtime(name):
                return True
            finder = sys._getframe(1)
            while finder and not (finder.f_code is H.Finder.find_spec.__code__ and finder.f_globals is H.__dict__):
                finder = finder.f_back
            if finder is not None and finder.f_locals['self'].guard is self:
                if name in self.import_directories:
                    return True
                # Genuine package search only, from an already admitted source
                # package __path__; no arbitrary filesystem prefix permission.
                for module in tuple(sys.modules.values()):
                    if isinstance(getattr(module, '__loader__', None), H.Loader) and module.__loader__.guard is self:
                        if any(H.key(p) == name for p in getattr(module, '__path__', ())):
                            return True
            # Namespace/plugin/resource enumeration retains its original finite
            # names-only directory role, while actual payload needs its own pin.
            if name in self.dependency_directories:
                caller = sys._getframe(1)
                while caller:
                    loader = caller.f_globals.get('__loader__')
                    if (isinstance(loader, H.Loader) and loader.guard is self
                            and H.key(caller.f_code.co_filename) in self.code_files):
                        return True
                    caller = caller.f_back
            observation = self.observation()
            material = self.material_read()
            contract_path = None
            contract = self.frame(self.runtime_owner.planning, 'read_contract')
            checked = self.frame(self.input_owners[0], 'checked_path')
            if not observation and not material:
                # read_contract validates declared paths after its own obs.read
                # has returned. This is the witnessed names-only owner chain.
                capture = self.frame(self.runtime_owner, 'capture_source')
                if contract is None or checked is None or capture is None:
                    return False
                obs = contract.f_locals.get('obs')
                if (type(obs) is not self.input_owners[0].Observations
                        or capture.f_locals.get('obs') is not obs
                        or self.observations.get(id(obs)) is not obs
                        or Path(obs.root).absolute() != TARGET
                        or contract.f_locals.get('reference') != CONTRACT):
                    return False
                value = contract.f_locals.get('value')
                if type(value) is not dict:
                    return False
                declared = {value.get('audit_ref')}
                for kind in ('constraints','contexts'):
                    for row in value.get(kind,()):
                        if type(row) is dict and type(row.get('path')) is str:
                            declared.add(row['path'])
                contract_path = checked.f_locals.get('value')
                if (type(contract_path) is not str or contract_path not in declared
                        or Path(checked.f_locals['root']).absolute() != TARGET):
                    return False
            else:
                obs, active = observation if observation else (material[0], None)
            checked = self.frame(self.input_owners[0], 'checked_path')
            if checked is not None:
                local = checked.f_locals
                if (Path(local['root']).absolute() == TARGET and 'current' in local
                        and H.key(local['current']) == name
                        and (TARGET / local['value']).is_relative_to(Path(local['current']))):
                    return True
            members = self.frame(self.input_owners[0], 'Observations.members')
            safe_input = self.frame(self.input_owners[2], 'safe_input')
            if safe_input is not None:
                local = safe_input.f_locals
                read = self.frame(self.input_owners[0], 'Observations.read')
                permitted = {read.f_locals['value']} if read is not None and read.f_locals['self'] is obs else set()
                if contract_path is not None:
                    permitted.add(contract_path)
                if material:
                    permitted.add(material[1])
                if members is not None and members.f_locals['self'] is obs:
                    for pattern in members.f_locals['patterns']:
                        parts = pattern.split('/')
                        wildcard = next((i for i, part in enumerate(parts) if any(c in part for c in '*?[')), len(parts))
                        permitted.add('/'.join(parts[:wildcard]))
                if (Path(local['root']).absolute() == TARGET and local.get('value') in permitted
                        and 'current' in local and H.key(local['current']) == name
                        and (TARGET / local['value']).is_relative_to(Path(local['current']))):
                    return True
            safe_pattern = self.frame(self.input_owners[2], 'safe_source_pattern')
            if (members is not None and members.f_locals['self'] is obs and safe_pattern is not None
                    and Path(safe_pattern.f_locals['root']).absolute() == TARGET
                    and safe_pattern.f_locals['pattern'] in members.f_locals['patterns']
                    and safe_pattern.f_locals.get('base') is not None
                    and Path(name).is_relative_to(Path(H.key(safe_pattern.f_locals['base'])))):
                return True  # original no-reparse source-pattern walk, names only
            resolve = self.frame(self.input_owners[1], 'resolve_sources')
            if (members is not None and members.f_locals['self'] is obs and resolve is not None
                    and Path(resolve.f_locals['root']).absolute() == TARGET
                    and resolve.f_locals['patterns'] is members.f_locals['patterns']
                    and Path(name).is_relative_to(Path(H.key(TARGET)))):
                relative = Path(name).relative_to(Path(H.key(TARGET))).parts
                return any(self.pattern_directory(relative, Path(pattern).parts) for pattern in members.f_locals['patterns'])
            return False

        def enumeration_diagnostic(self, path):
            """Observation only. No admission, source lookup, payload or repr."""
            records = []
            frame = sys._getframe(1)
            source_modules = {'_b_route_sources', '_b_route_codec', '_b_route_inventory'}
            while frame is not None and len(records) < 48:
                code = frame.f_code
                module_name = frame.f_globals.get('__name__')
                loader = frame.f_globals.get('__loader__')
                source_only = isinstance(loader, H.Loader) and loader.guard is self
                row = {'module': module_name if type(module_name) is str else None,
                       'function': code.co_name, 'filename': code.co_filename,
                       'line': frame.f_lineno, 'actual_H_SourceOnly_loader': source_only}
                # Only path operands of the explicitly reviewed original path
                # owners, plus the stdlib iterdir operand. No complete locals,
                # input bytes, source text, dictionaries, globs or emitted names.
                names = ()
                if source_only and module_name in source_modules:
                    names = ('root', 'value', 'path', 'current', 'candidate', 'base', 'part', 'resolved')
                elif module_name == 'pathlib' and code.co_name == 'iterdir':
                    names = ('self',)
                operands = {}
                for key in names:
                    value = frame.f_locals.get(key)
                    if type(value) is str:
                        operands[key] = value[:512]
                    elif type(value) is type(TARGET):
                        operands[key] = str(value)[:512]
                if operands:
                    row['path_operands'] = operands
                instance = frame.f_locals.get('self')
                if source_only and module_name == '_b_route_sources':
                    row['same_known_observation_instance'] = instance is not None and self.observations.get(id(instance)) is instance
                records.append(row)
                frame = frame.f_back
            return {'event': 'os.listdir/os.scandir refusal', 'directory': H.key(path),
                    'admitted': False, 'input_owners_bound': self.input_owners is not None,
                    'metadata_request_bound': hasattr(self, 'metadata_request'),
                    'closing_original_observations': self.closing_observations,
                    'known_observation_count': len(self.observations),
                    'frames': records, 'stack_truncated': frame is not None,
                    'permission_changed': False}

        def audit_checked(self, event, values):
            if event == 'msvcrt.locking':
                self.deny('no byte-lock operation in metadata lane', event)
            if event in {'os.remove', 'os.rmdir', 'os.rename', 'os.replace', 'os.chmod', 'os.chown', 'os.utime',
                         'os.truncate', 'shutil.rmtree', 'shutil.copyfile', 'os.link', 'os.symlink'}:
                self.deny('no destructive/copy/link operation, including outputs', event)
            if event in ('os.scandir', 'os.listdir'):
                admitted = self.enumeration(values[0])
                if not admitted and len(self.enumeration_refusals) < 4:
                    try:
                        observation = self.enumeration_diagnostic(values[0])
                        observation['event'] = event
                        self.enumeration_refusals.append(observation)
                        H.write_new(self.out / ('enumeration-refusal-%s.json' % len(self.enumeration_refusals)),
                                    H.raw_json(observation))
                    except BaseException as diagnostic_error:
                        # Keep the original denial primary even if diagnostics
                        # cannot close their own exclusive output observation.
                        self.enumeration_diagnostic_errors.append(type(diagnostic_error).__name__)
                need(admitted, 'no enumeration outside original import or Observations member role:' + str(values[0]))
                return
            return Paid.audit_checked(self, event, values)

        def close_inputs(self):
            """Metadata close, explicitly replacing H's full target/public close."""
            self.assert_active()
            need(not self.codec_fds, 'all real original codec descriptors closed')
            returned = [row for row in self.codec_fd_events if row['event'] == 'original codec returned']
            need(returned and all(row['actual_closed'] is True and row['fdopen_admitted'] for row in returned),
                 'actual original codec FD return/close evidence, not an empty observer')
            need(not self.runner_rows and not self.cleanup_rows, 'no paid runner or cleanup created')
            need(not self.lock_events and not self.lock_descriptors, 'no inherited lock activity')
            need(H.startup_metadata() == self.startup_before, 'actual isolated startup metadata unchanged')
            self.closing_observations = True
            try:
                for obs in tuple(self.observations.values()):
                    obs.verify()  # original actual raw/absence/watch membership owner
            finally:
                self.closing_observations = False
            for name, expected in tuple(self.files.items()):
                need(H.hash_file(name) == expected and H.file_identity(name) == self.identities[name],
                     'consumed source/control/dependency/original bytes changed:' + name)
            need(not self.blocked and not self.codec_fds, 'no earlier denial or unclosed codec FD')
            need(len(self.r5_reads) == 486, 'original preserved full production domain is still 486')
            need(all(Path(row['path']).is_relative_to(self.out) for row in self.write_events),
                 'all actual write roles confined to fresh output')
            return {'scope': 'consumed sources/controls/dependencies; actual original Observations and r5 manifest',
                    'consumed_file_count': len(self.files), 'original_r5_production_count': len(self.r5_reads),
                    'nx_observed_paths': sorted(self.nx_reads), 'actual_observation_count': len(self.observations),
                    'codec_fd_events': self.codec_fd_events, 'blocked': self.blocked,
                    'write_events': self.write_events, 'full_nx_snapshot_claimed': False,
                    'paid_guard_or_financial_execution_verified': False}

    return MetadataGuard
