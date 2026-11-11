"""NEW historical host factory DRAFT; never accepts a caller result dictionary.

All methods are read-only. The sole mint uses a real owned Job reader completion.
Imported only by integrated owner; original modules run in a separate real R56
source namespace. Installer must pin these sources + fixed adjacent authority in
policy_observations; old source/proof bytes are never rewritten.
"""
from copy import deepcopy
from pathlib import Path
import base64
import json
import os
import sys
import _b_route_codec as codec
from _b_route_frozen_native_reader import _safe, _dependencies
from _b_route_reader_lifetime import GATE, run_reader

AUTH = 'newrouge.b-route-qualified-historical-auth.v2'
TRANSPORT = 'newrouge.b-route-qualified-historical-worker-result.v2'
_MINT = object()


def need(ok, expected):
    if not ok:
        raise ValueError(expected)


def raw(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')


class AuthenticatedHistory:
    __slots__ = ('_binding', '_files', '_roles', '_public', '_capsule', '_operation', '_root')
    def __init__(self, key, value):
        need(key is _MINT, 'history must come from the actual held worker factory')
        self._binding = value['binding']
        self._files = {k: base64.b64decode(v, validate=True) for k, v in value['files_base64'].items()}
        self._roles, self._public = value['roles'], value['public_subject']
        self._capsule, self._operation, self._root = value['capsule'], value['operation'], value['root_identity']

    def binding(self):
        return deepcopy(self._binding)

    def public_subject(self):
        return deepcopy(self._public)

    def checked_original(self, root, operation):
        root = _safe(Path(root).absolute(), directory=True)
        st = root.stat()
        need(self._root == {'path': str(root), 'device': st.st_dev, 'inode': st.st_ino}
             and operation == self._operation, 'exact actual root/operation/frozen identity')
        op_ref = __import__('_planning_apply_journal')._operation_ref(operation['operation_id'])
        need(codec.raw_digest(_safe(root / op_ref).read_bytes()) == self._binding['operation_raw_digest'],
             'exact current journal operation raw binding')
        return self

    def identity(self):
        return self._binding['private_subject_digest']

    def subject(self):
        import _b_route_adoption_review as owner
        name=owner.location(self._operation['operation_id'])+'/subject.json'
        return codec.strict_json_loads(self._files[name])

    def operation(self):return deepcopy(self._operation)

    def operation_raw(self):
        import _planning_apply_journal as journal
        data=_safe(Path(self._root['path'])/journal._operation_ref(self._operation['operation_id'])).read_bytes()
        need(codec.raw_digest(data)==self._binding['operation_raw_digest'],'exact authenticated original operation raw')
        return data

    def files(self):return dict(self._files)

    def roles(self):return dict(self._roles)

    def operation_view(self):
        import _b_route_qualified_public_history_v2 as public
        return public.operation_view(self._root['path'],self._operation,self)

    def retained_graphs(self):
        return [self._binding,self._roles,self._public,self._capsule,self._operation,self._root]

    def retained_buffers(self):return list(self._files.values())

    def recheck(self):
        # The derived v3 token also closes its own actual worker/authority bytes.
        # This is a source/raw recheck only; never fresh target eligibility.
        for name, expected in self._binding['worker_transport']['worker_sources'].items():
            need(codec.raw_digest(_safe(Path(name)).read_bytes())==expected,
                 'unchanged actual historical worker/authority resource')
        # Place only this same-read pin closure at the original short writer;
        # native replay, protocol replay and model rendering stay outside it.
        for name, expected in {**self._binding['private_raw_pins'], **self._binding['native_file_pins']}.items():
            path = _safe(Path(name), missing=True)
            actual = codec.raw_digest(path.read_bytes()) if path.is_file() else None
            need(actual == expected, 'unchanged authenticated private/native raw pin')
        for name, expected in self._binding['native_directory_pins'].items():
            path = _safe(Path(name), directory=True)
            need(sorted(item.name for item in path.iterdir()) == expected,
                 'original exact immediate native directory membership')



def authenticate(root, operation_id):
    """One genuine read-only worker, no capture_completed or model dispatch."""
    directory = Path(__file__).absolute().parent
    authority_path = directory / 'qualified-historical-owner-authority.v2.json'
    authority_raw = _safe(authority_path).read_bytes()
    authority = codec.strict_json_loads(authority_raw)
    need(type(authority) is dict and authority.get('schema_version') == 'newrouge.b-route-qualified-historical-owner-authority.v2'
         and set(authority) == {'schema_version','original_owner_root','source_schema_pins','python_version',
             'python_executable','python_executable_raw_digest','scope','dependency_authority','producer_reader'}
         and type(authority.get('original_owner_root')) is str
         and type(authority.get('source_schema_pins')) is dict and bool(authority['source_schema_pins'])
         and all(type(authority.get(k)) is str and authority[k] for k in
                 ('python_version','python_executable','python_executable_raw_digest')),
         'Root must install actual FINAL original owner authority; null is not an observed or approved epoch')
    original = Path(authority['original_owner_root']) / 'scripts' / 'python'
    need(original == directory.parents[2] / 'r56' / 'scripts' / 'python',
         'fixed real retained R56 v3 consumer authority, not an arbitrary module root')
    resources = {str(authority_path): codec.raw_digest(authority_raw)}
    for name in ('_b_route_qualified_historical_auth_v3.py', '_b_route_qualified_historical_archive.py',
                 '_b_route_qualified_historical_v3_protocol.py'):
        path = _safe(directory / name)
        resources[str(path)] = codec.raw_digest(path.read_bytes())
    producer = authority['producer_reader']
    expected_reader = directory.parents[2] / 'r52/scripts/python/_b_route_frozen_native_reader.py'
    need(type(producer) is dict and set(producer)=={'path','raw_digest'}
         and producer['path']==str(expected_reader)
         and producer['raw_digest']=='sha256:3c2b2c614082c3dcd04f5ac4866e0152fa93e4dc19ac5487853cef6731f41548',
         'real old producer reader, separate actual R56 consumer; no alias')
    original_reader = _safe(expected_reader)
    reader_pin = producer['raw_digest']
    need(codec.raw_digest(original_reader.read_bytes()) == reader_pin, 'original reader source authority')
    # Paths originate in the existing trusted host dependency resolver, never
    # in the caller input. Preserve original resolver semantics and pin closure.
    request = {'root': str(_safe(Path(root).absolute(), directory=True)), 'operation_id': operation_id,
        'original': str(original), 'directory': str(directory), 'resources': resources,
        'reader': str(original_reader), 'reader_pin': reader_pin, 'dependencies': _dependencies()}
    codec.validate_business_id(operation_id)
    bootstrap = r"""
import sys,json,pathlib,hashlib,types,base64,importlib.util,importlib.machinery
req=json.loads(sys.stdin.buffer.read())
def check(path,pin):
    p=pathlib.Path(path)
    # Bootstrap path checks intentionally use only stdlib, then the original
    # reader repeats its full plain/no-reparse identity validation.
    b=p.read_bytes()
    if 'sha256:'+hashlib.sha256(b).hexdigest()!=pin: raise ValueError('worker source changed')
    return b
for name,pin in req['resources'].items(): check(name,pin)
b=check(req['reader'],req['reader_pin'])
m=types.ModuleType('_qualified_original_source_reader');m.__file__=req['reader'];m.__package__=''
exec(compile(b,req['reader'],'exec'),m.__dict__)
m._install_source_only()
sys.path[:0]=[req['original'],req['directory'],*req['dependencies']]
sys.dont_write_bytecode=True
class CheckedSource(importlib.machinery.SourceFileLoader):
    def get_code(self,fullname):
        m._safe(pathlib.Path(self.path))
        source=check(self.path,req['resources'][self.path])
        return compile(source,self.path,'exec')
def load_new(name):
    path=str(pathlib.Path(req['directory'])/(name+'.py'))
    loader=CheckedSource(name,path)
    spec=importlib.util.spec_from_file_location(name,path,loader=loader)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    loader.exec_module(module)
    if pathlib.Path(module.__file__).absolute()!=pathlib.Path(path): raise ValueError('historical module origin changed')
    return module
archive=load_new('_b_route_qualified_historical_archive')
protocol=load_new('_b_route_qualified_historical_v3_protocol')
auth=load_new('_b_route_qualified_historical_auth_v3')
try:
    v=auth.authenticate(req['root'],req['operation_id'])
except Exception as error:
    diagnostic=getattr(error,'diagnostic',None)
    detail=diagnostic.to_dict() if diagnostic is not None else {'error_type':type(error).__name__,'reason':str(error)}
    sys.stdout.buffer.write((json.dumps({'schema_version':'newrouge.b-route-qualified-historical-worker-error.v2',
        'diagnostic':detail},ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8'))
    raise SystemExit(3)
result={'schema_version':'newrouge.b-route-qualified-historical-worker-result.v2',
 'binding':v._value,'files_base64':{k:base64.b64encode(x).decode('ascii') for k,x in v._files.items()},
 'roles':v._roles,'public_subject':v._public,'capsule':v._capsule,'operation':v._operation,'root_identity':v._root}
for name,pin in req['resources'].items(): check(name,pin)
sys.stdout.buffer.write((json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode('utf-8'))
"""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', GIT_OPTIONAL_LOCKS='0')
    original_python = _safe(Path(authority['python_executable']))
    need(codec.raw_digest(original_python.read_bytes()) == authority['python_executable_raw_digest'],
         'actual pinned original interpreter before worker release')
    completed = run_reader([str(original_python), '-I', '-S', '-B', '-c', GATE + bootstrap],
        input=raw(request), cwd=original.parents[1], env=env)
    # run_reader returns only after confirmed owned Job quiescence. No caller
    # CompletedProcess or raw dictionary seam authorizes this result.
    if completed.returncode != 0:
        try:failure=codec.strict_json_loads(completed.stdout)
        except (ValueError,codec.CodecError):failure={'diagnostic':{'error_type':'unstructured_original_worker_failure'}}
        error=codec.CodecError(codec.Diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE,codec.Stage.BUNDLE,
            expected='exact original v3 bytes and required archive preimages',actual={
                'returncode':completed.returncode,'cleanup':'confirmed_empty','failure':failure.get('diagnostic'),
                'stdout_raw_digest':codec.raw_digest(completed.stdout),'stderr_raw_digest':codec.raw_digest(completed.stderr)}))
        error.stdout,error.stderr,error.returncode,error.cleanup=completed.stdout,completed.stderr,completed.returncode,'confirmed_empty'
        raise error
    value = codec.strict_json_loads(completed.stdout)
    need(type(value) is dict and set(value) == {'schema_version','binding','files_base64','roles',
        'public_subject','capsule','operation','root_identity'} and value['schema_version'] == TRANSPORT,
        'closed genuine historical worker result')
    need(value['binding']['schema_version'] == AUTH and value['operation']['operation_id'] == operation_id
         and value['binding']['authority_raw_digest'] == codec.raw_digest(authority_raw),
         'actual held worker input/source authority binding')
    need(_safe(authority_path).read_bytes() == authority_raw, 'same installed authority after worker close')
    for name, expected in resources.items():
        need(codec.raw_digest(_safe(Path(name)).read_bytes()) == expected, 'same executed new worker sources')
    value['binding']['worker_transport'] = {'schema_version': TRANSPORT,
        'stdout_raw_digest': codec.raw_digest(completed.stdout), 'input_raw_digest': codec.raw_digest(raw(request)),
        'owned_job_returned': True, 'reader_source_digest': reader_pin, 'worker_sources': resources}
    result = AuthenticatedHistory(_MINT, value)
    result.checked_original(root, value['operation'])
    return result
