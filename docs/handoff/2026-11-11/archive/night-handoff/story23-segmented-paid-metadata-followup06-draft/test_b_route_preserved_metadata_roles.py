"""UNEXECUTED DATA/negative/role-mechanism source checks, not genuine proof.

No child/model/Git is started. No fake module is accepted as a genuine owner.
Root source-loads the real candidate runtime and the Task adapter module under
`_Root_story23_paid_metadata` through its existing test host.
"""
import ast
import inspect
from pathlib import Path
import unittest

import _b_route_segmented_runtime as runtime
import _Root_story23_paid_metadata as consumer


class PreservedMetadataRoleTests(unittest.TestCase):
    def test_finite_manifest_query_data_domain(self):
        commit=runtime._PRESERVED_COMMIT
        for arguments in (('rev-parse','--verify',commit+'^{commit}'),
                ('ls-tree','-rz','--full-tree',commit),('ls-tree','-rz','--full-tree','HEAD'),
                ('ls-files','--others','-z')):
            self.assertTrue(runtime._manifest_query_matches(arguments,None))

    def test_arbitrary_git_or_commit_is_outside_data_domain(self):
        for arguments in (('status',),('show','HEAD:secret'),('ls-tree','-rz','--full-tree','other'),
                ('rev-parse','--verify','0'*40+'^{commit}'),('ls-files','--others','-z','extra')):
            self.assertFalse(runtime._manifest_query_matches(arguments,None))
        self.assertFalse(runtime._manifest_query_matches(['ls-files','--others','-z'],None))

    def test_attributes_stdin_requires_exact_owned_names_data(self):
        arguments=('check-attr','--source='+runtime._PRESERVED_COMMIT,'--stdin','-z',
                   'text','eol','filter','working-tree-encoding','ident')
        names=['scripts/a.py','scripts/b.py']
        self.assertTrue(runtime._manifest_query_matches(arguments,b'scripts/a.py\0scripts/b.py\0',tracked_names=names))
        self.assertFalse(runtime._manifest_query_matches(arguments,b'scripts/b.py\0scripts/a.py\0',tracked_names=names))
        self.assertFalse(runtime._manifest_query_matches(arguments,b'scripts/a.py\0extra.py\0',tracked_names=names))
        self.assertFalse(runtime._manifest_query_matches(arguments,None,tracked_names=names))

    def test_matching_command_without_original_chain_has_no_role(self):
        self.assertIsNone(runtime._original_metadata_call())
        self.assertIs(runtime._is_original_source_metadata(
            [runtime.sys.executable,'-I','-S','-B','-c',runtime._BRIDGE],(),{}),False)

    def test_source_wrapper_metadata_precedes_paid_launch_record(self):
        tree=ast.parse(inspect.getsource(runtime._source_runner_scope.__wrapped__))
        launch=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='launch')
        metadata=next(n for n in ast.walk(launch) if isinstance(n,ast.Call)
                      and isinstance(n.func,ast.Name) and n.func.id=='_is_original_source_metadata')
        append=next(n for n in ast.walk(launch) if isinstance(n,ast.Call)
                    and isinstance(n.func,ast.Attribute) and n.func.attr=='append')
        self.assertLess(metadata.lineno,append.lineno)
        self.assertTrue(any(isinstance(n,ast.Assign) and any(isinstance(t,ast.Subscript)
            and isinstance(t.slice,ast.Constant) and t.slice.value=='launch' for t in n.targets)
            for n in ast.walk(tree)))

    def test_dispatcher_origin_precedes_describe_without_super_forwarding(self):
        tree=ast.parse(Path(consumer.__file__).read_text(encoding='utf-8'))
        cls=next(n for n in ast.walk(tree) if isinstance(n,ast.ClassDef) and n.name=='PaidGuard')
        dispatch=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='run_git')
        metadata=next(n for n in ast.walk(dispatch) if isinstance(n,ast.Call)
            and isinstance(n.func,ast.Attribute) and n.func.attr=='metadata_call')
        describe=next(n for n in ast.walk(dispatch) if isinstance(n,ast.Call)
            and isinstance(n.func,ast.Attribute) and n.func.attr=='describe_frame')
        self.assertLess(metadata.lineno,describe.lineno)
        direct_roles={n.left.id for n in ast.walk(dispatch) if isinstance(n,ast.Compare)
            and isinstance(n.left,ast.Name) and len(n.ops)==1 and isinstance(n.ops[0],ast.Is)
            and len(n.comparators)==1 and isinstance(n.comparators[0],ast.Name)
            and n.comparators[0].id=='caller'}
        self.assertTrue({'describe','cleanup'} <= direct_roles)
        self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
            and n.func.attr=='run_git' and isinstance(n.func.value,ast.Call)
            and isinstance(n.func.value.func,ast.Name) and n.func.value.func.id=='super'
            for n in ast.walk(dispatch)))
