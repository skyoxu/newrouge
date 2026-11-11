"""Stdlib AST/text assembly only; never executes any imported project/control."""
from pathlib import Path
import ast
import difflib
import json

HOME = Path(__file__).absolute().parent
TASK = HOME.parents[1]
NATIVE = TASK / 'night-handoff/story27-r52-v15-native-origin-controls-followup04/native_host.draft.py'
PROTECTION = TASK / 'night-handoff/story27-r52-target-protection-host-followup03/protection_host.draft.py'


def functions(text):
    tree = ast.parse(text)
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Guard')
    lines = text.splitlines(True)
    return {node.name: ''.join(lines[min([node.lineno] + [item.lineno for item in node.decorator_list])-1:node.end_lineno]) + '\n'
            for node in cls.body if isinstance(node, ast.FunctionDef)}, tree, lines


native = NATIVE.read_text(encoding='utf-8')
assert not (HOME / 'STOP.json').exists(), 'Frozen author package must not be reassembled'
protection = PROTECTION.read_text(encoding='utf-8')
methods, tree, lines = functions(native)
pm, pt, pl = functions(protection)
delta = (HOME / 'author_guard_delta.py').read_text(encoding='utf-8')
dt = ast.parse(delta)
dl = delta.splitlines(True)
dc = next(node for node in dt.body if isinstance(node, ast.ClassDef))
custom = {node.name: ''.join(dl[node.lineno-1:node.end_lineno]) + '\n'
          for node in dc.body if isinstance(node, ast.FunctionDef)}
methods['audit_native'] = methods.pop('audit').replace('def audit(', 'def audit_native(', 1)
methods.update(custom)
methods['__init__'] += '''        self.git_children, self.git_records, self.git_intents = [], [], []
        self.known_commits = {HEAD, BASELINE}
        self.known_objects = {HEAD: 'commit', BASELINE: 'commit'}
        self.inventory = None
        self.original_nx_locks = set(self.locks)
        self.target_scope_locks = set()
        self.public_scope_ids, self.completed_lock_rows = [], []
        self.public_scope_frame = None
        self.public_scope_admitted = False
        self.review_files = {key(self.target / name) for name in REVIEW_FILES}
        self.public_directories = {key(self.target / name) for name in PUBLIC_DIRECTORIES}
        self.absent_target_files = {key(self.target / name) for name in config['absent_target_files']}
        self.absent_target_directories = {key(self.target / name) for name in config['absent_target_directories']}
'''
methods['assert_active'] += "        require(subprocess.run == self.run_git, 'same original typed Git dispatcher')\n"
for name in ('git_shape', 'observe_git_output', 'run_git'):
    methods[name] = pm[name].replace('self.children', 'self.git_children')
audit = pm['audit_raw']
start = audit.index("        if event in ('subprocess.Popen', '_winapi.CreateProcess'):")
end = audit.index("        if event.startswith(('socket.'", start)
methods['audit_git_process'] = '    def audit_git_process(self, event, values):\n' + audit[start:end]

# Retain the native SourceOnly/codec/pipe wrappers; add one exact Git constructor
# branch, using the already verified protection03 constructor body.
install = methods['install']
start = install.index('        def initialize(process, *args, **kwargs):')
end = install.index('        self.guarded_init, self.guarded_handles', start)
native_init = install[start:end]
pi = pm['install']; ps = pi.index('        def initialize(process, *args, **kwargs):')
pe = pi.index('        self.profile_role, self.guarded_os_open', ps)
git_body = pi[ps:pe].split('\n', 1)[1].rstrip()
git_body = git_body.replace('guard.children.append(row)', 'guard.git_children.append(row)')
git_body = git_body.replace("'constructing': True,", "'constructing': True, 'kind': 'git',")
git_branch = '        def initialize(process, *args, **kwargs):\n'
git_branch += '            if sys._getframe(1).f_code is Guard.run_git.__code__:\n'
git_branch += '\n'.join('    ' + line if line else line for line in git_body.splitlines()) + '\n'
git_branch += native_init.split('\n', 1)[1]
install = install[:start] + git_branch + install[end:]
install = install.replace('        sys.addaudithook(self.audit)', '        subprocess.run = self.run_git\n        sys.addaudithook(self.audit)')
methods['install'] = install

# The byte-lock calls remain original. Preserve distinct observations if a later
# original coordinator reuses a closed integer descriptor for another scope.
locks = methods['observe_original_locks']
needle = "            row = guard.lock_descriptors.setdefault(fd,"
locks = locks.replace(needle, "            if fd in guard.lock_descriptors and guard.lock_descriptors[fd]['close_returned']:\n"
                            "                guard.completed_lock_rows.append(guard.lock_descriptors.pop(fd))\n" + needle)
methods['observe_original_locks'] = locks
# Existing target membership remains exact; only the fixed original namespace
# directories can exist empty before or after the four review files are written.
methods['close_inputs'] = methods['close_inputs'].replace('        expected_dirs = {key(self.target)}',
    "        expected_dirs = {key(self.target)} | self.public_directories | {key(self.target / name) for name in self.c['target_before']['directories']}")
methods['close_inputs'] = methods['close_inputs'].replace(
    "            observed_writes = {key(row['path']) for row in self.lock_events}",
    "            observed_writes = {key(row['path']) for row in self.lock_events}\n"
    "            observed_writes |= {name for name in self.public_directories | self.write_targets if Path(name).exists()}")

cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Guard')
main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
prefix = ''.join(lines[:cls.lineno-1])
prefix = prefix.replace('Root-only finite nx/m4 original-reader replay; author never executes this draft.',
                        'Root-only original public review-prepare with real original reader and readonly target Git.')
prefix = prefix.replace("HOME = TASK / 'night-handoff/story27-r52-v15-native-origin-controls-followup04'",
                        "HOME = TASK / 'night-handoff/story27-r52-public-review-prepare-host-followup02'")
prefix = prefix.replace('import argparse\n', 'import argparse\nimport contextlib\nimport io\n', 1)
constants = []
for node in pt.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ('HEAD', 'BASELINE') for t in node.targets):
        constants.append(''.join(pl[node.lineno-1:node.end_lineno]))
prefix += '\n' + '\n'.join(constants) + '\n'
prefix += "TARGET = TASK / 'story27-r52-v15-empty-target-native01'\n"
prefix += "REQUEST = 'logs/ci/2026-11-09/b-route-requests/native-v15-origin02-request-01/request.json'\n"
prefix += "OPERATION = 'NativeV15Origin02'\n"
prefix += "REVIEW_HOME = 'logs/ci/b-route-adoption-reviews/' + hashlib.sha256(OPERATION.encode()).hexdigest()\n"
prefix += "REVIEW_FILES = tuple(REVIEW_HOME + '/' + name for name in ('subject.json','w/prompt.txt','w/schema.json','request.txt'))\n"
prefix += "PUBLIC_DIRECTORIES = ('logs','logs/ci','logs/ci/b-route-operations','logs/ci/b-route-operations/locks','logs/ci/b-route-operations/locks/metadata','logs/ci/b-route-operations/locks/scopes','logs/ci/b-route-adoption-reviews',REVIEW_HOME,REVIEW_HOME+'/w')\n"
for name in ('original_frame', 'snapshot_tree', 'metadata_names', 'startup_metadata', 'source_close'):
    node = next(n for n in pt.body if isinstance(n, ast.FunctionDef) and n.name == name)
    helper = ''.join(pl[node.lineno-1:node.end_lineno])
    if name == 'source_close':
        helper = helper.replace("config['stdlib_search_metadata']", "config['protection_stdlib_search_metadata']")
    prefix += '\n' + helper + '\n'
host = prefix + '\nclass Guard:\n' + '\n'.join(methods.values())
host += '\n' + (HOME / 'author_host_tail.py').read_text(encoding='utf-8')
ast.parse(host)
with (HOME / 'review_prepare_host.draft.py').open('w', encoding='utf-8', newline='\n') as stream:
    stream.write(host)
with (HOME / 'native04-to-review.diff').open('w', encoding='utf-8', newline='\n') as stream:
    stream.writelines(difflib.unified_diff(native.splitlines(True), host.splitlines(True), fromfile='native04/native_host.draft.py', tofile='review_prepare_host.draft.py'))
print(json.dumps({'AST_only': True, 'host_written': True, 'project_or_controls_executed': False}))
