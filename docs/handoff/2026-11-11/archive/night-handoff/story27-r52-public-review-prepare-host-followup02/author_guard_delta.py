"""AST input for author metadata assembly; not a runtime import or test."""


class GuardDelta:
    def allowed_read(self, path):
        name = key(path)
        if name.endswith(('.pyc', '.pyo')):
            self.deny('bytecode read', name)
        if (name in self.files or name in self.extra_files or name in self.write_targets
                or self.runtime(name) or Path(name).is_relative_to(self.out)):
            return
        if name in self.absent_target_files and not Path(name).exists():
            return
        if name in self.locks and self.coordinator_frame('coordinator_lock'):
            return
        self.deny('read outside fixed or authenticated positive closure', name)

    def original_frame(self, module_name, function_name):
        module = sys.modules.get(module_name)
        function = getattr(module, function_name, None)
        function = getattr(function, '__wrapped__', function)
        if not isinstance(getattr(module, '__loader__', None), Loader):
            return None
        code = getattr(function, '__code__', None)
        frame = sys._getframe(1)
        while frame:
            if (frame.f_code is code and frame.f_globals is module.__dict__
                    and key(frame.f_code.co_filename) == key(SOURCE / 'scripts/python' / (module_name + '.py'))):
                return frame
            frame = frame.f_back
        return None

    def allowed_write(self, path, mkdir=False, flags=None):
        name = key(plain(path, missing=True))
        if Path(name).is_relative_to(self.out):
            return
        frame = self.coordinator_frame('coordinator_lock')
        if name in self.locks and frame and key(frame.f_locals['path']) == name:
            self.lock_events.append({'path': name, 'role': 'original coordinator_lock open/write', 'thread': threading.get_ident()})
            return
        frame = self.coordinator_frame('operation_lock')
        if mkdir and name in self.lock_parents and frame and key(frame.f_locals['directory']) == name:
            self.lock_events.append({'path': name, 'role': 'original operation_lock activity directory'})
            return
        if mkdir and name in self.public_directories:
            scope = self.original_frame('_b_route_operation_scope', '_directory')
            review = self.original_frame('_b_route_adoption_review', 'write_once')
            require(scope is not None or review is not None, 'public mkdir only original finite namespace owner')
            return
        if name in self.review_files:
            frame = self.original_frame('_b_route_adoption_review', 'write_once')
            require(frame is not None and key(frame.f_locals['target']) == name
                    and not Path(name).exists() and type(flags) is int
                    and bool(flags & os.O_EXCL) and bool(flags & os.O_CREAT), 'exact four original create-once review files')
            return
        self.deny('write outside new review files / original nx or source-derived scope locks', name)

    def audit(self, event, values):
        try:
            return self.audit_checked(event, values)
        except BaseException as error:
            if len(self.blocked) < 256:
                self.blocked.append({'event': event, 'type': type(error).__name__, 'reason': str(error)[:512]})
            raise

    def audit_checked(self, event, values):
        if event == 'Root.native.reader.guard':
            if values == (self.nonce,):
                self.ack = self.nonce
            return
        if event in ('subprocess.Popen', '_winapi.CreateProcess'):
            if self.token is not None and self.token.get('kind') == 'git':
                return self.audit_git_process(event, values)
            return self.audit_native(event, values)
        if event.startswith(('socket.', 'os.exec', 'os.spawn', 'os.posix_spawn')) or event in {
                'os.system', 'os.startfile', 'os.fork', 'os.forkpty', 'os.link', 'os.symlink'}:
            self.deny('no network/model/other process/link', event)
        if event == 'exec' and values and hasattr(values[0], 'co_filename'):
            filename = values[0].co_filename
            if filename and not filename.startswith('<') and Path(key(filename)).is_relative_to(TARGET):
                self.deny('target locator is data only', filename)
        if event == 'open':
            path, mode, flags = values[0], values[1] or '', values[2] or 0
            if type(path) is int:
                if not self.pipe_open(path):
                    self.codec_fd_open(path, mode, flags)
                return
            writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing:
                self.allowed_write(path, flags=flags)
            else:
                self.allowed_read(path)
                if key(path) == key(GIT):
                    git_program_metadata()
                else:
                    plain(path, missing=True)
        elif event in ('os.scandir', 'os.listdir'):
            path = plain(values[0], missing=True)
            name = key(path)
            if (name in self.directories or name in self.metadata_directories or name in self.extra_dirs
                    or name in self.public_directories or self.runtime(name) or path.is_relative_to(self.out)):
                return
            if name in self.absent_target_directories and not path.exists():
                return
            self.deny('enumeration outside fixed or authenticated metadata', name)
        elif event == 'os.mkdir':
            self.allowed_write(values[0], mkdir=True)
        elif event in {'os.remove', 'os.rmdir', 'os.rename', 'os.replace', 'os.chmod', 'os.chown', 'os.utime',
                       'os.truncate', 'shutil.rmtree', 'shutil.copyfile'}:
            if not Path(key(values[0])).is_relative_to(self.out):
                self.deny('no old target / lock destructive or copying role', event)

    def role(self, frame, event, arg):
        if event != 'call' or frame.f_code.co_filename.startswith('<'):
            return
        if not Path(key(frame.f_code.co_filename)).is_relative_to(SOURCE):
            return
        module, name = Path(frame.f_code.co_filename).name, frame.f_code.co_name
        if module == '_b_route_operation_scope.py' and name == 'scope_guard':
            if frame is self.public_scope_frame:
                return  # Resume of this exact original context-manager frame.
            owner = sys.modules.get('_b_route_operation_scope')
            function = getattr(getattr(owner, 'scope_guard', None), '__wrapped__', None)
            require(isinstance(getattr(owner, '__loader__', None), Loader) and function is not None
                    and frame.f_code is function.__code__ and frame.f_globals is owner.__dict__, 'original scope_guard binding')
            require(key(frame.f_locals['root']) == key(TARGET)
                    and frame.f_locals['operation_id'] == 'NativeV15Origin02'
                    and frame.f_locals['legacy_owner'] is None, 'same actual public review scope call')
            parent = frame.f_back
            module_owner = sys.modules.get('_b_route_adoption')
            while parent and not (parent.f_globals is module_owner.__dict__
                                 and parent.f_code is module_owner._review_preview.__code__):
                parent = parent.f_back
            require(parent is not None and parent.f_locals['seal'] is False, 'actual review-prepare preview parent')
            scopes = frame.f_locals['scope_ids']
            require(scopes == parent.f_locals['frozen']['scope_ids']
                    and isinstance(scopes, (list, tuple)) and scopes
                    and all(type(value) is str and re.fullmatch(r'[a-z0-9][a-z0-9._:-]{0,127}', value)
                            and value != 'writer:planning' for value in scopes), 'actual frozen portable scope denominator')
            paths = {TARGET / 'logs/ci/b-route-operations/locks/metadata/capability-coordinator.lock'}
            for scope in (*scopes, 'writer:planning'):
                paths.add(TARGET / 'logs/ci/b-route-operations/locks/scopes' /
                          hashlib.sha256(scope.encode('utf-8')).hexdigest() / 'capability-coordinator.lock')
            require(not self.public_scope_admitted, 'one original public scope_guard invocation')
            self.public_scope_admitted = True
            self.public_scope_frame = frame
            self.public_scope_ids = list(scopes)
            for path in paths:
                name = key(path)
                require(not path.exists(), 'new original public lock; do not reuse old namespace')
                self.target_scope_locks.add(name)
                self.locks.add(name)
                self.write_targets.add(name)
                self.public_directories.add(key(path.parent))
            return
        if module in {'_codex_app_server.py', '_llm_backend.py'} and name in {'run_request', 'call_llm', 'chat'}:
            self.deny('actual model dispatch', [module, name])
        if name == 'prepare_review' and module == '_b_route_adoption.py':
            owner = sys.modules.get('_b_route_adoption')
            function = getattr(getattr(owner, name, None), '__wrapped__', None)
            require(isinstance(getattr(owner, '__loader__', None), Loader) and function is not None
                    and frame.f_code is function.__code__ and frame.f_globals is owner.__dict__
                    and key(frame.f_locals['root']) == key(TARGET)
                    and frame.f_locals['operation_id'] == 'NativeV15Origin02'
                    and frame.f_locals['request_ref'] == REQUEST, 'one actual original public prepare_review call')
            return
        if name in {'run_candidate', 'prepare_review', 'complete_review', 'run_native', 'produce_proof', 'prepare_origin'}:
            self.deny('other planning/model/commit/origin stage', [module, name])

