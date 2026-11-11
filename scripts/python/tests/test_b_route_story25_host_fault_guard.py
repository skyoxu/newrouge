"""Portable source-only guard tests; no host helper, project import or Git runs.

Only the actual guard's stdlib AST definitions are loaded into a small namespace.
The approved host files and the checked-in base fixture are parsed as data, never
compiled or executed. Root owns execution; this author only parsed this test.
"""
from copy import deepcopy
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest


PYTHON = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).with_name("fixtures") / "story25_host_fault_base_sources.json"
COMMON = "scripts/python/_planning_skill_common.py"
SERVER = "scripts/python/_codex_app_server.py"
TRANSITION = "scripts/python/_b_route_execution_transition.py"


def guard_namespace():
    source = (PYTHON / "_b_route_execution_transition.py").read_text(encoding="utf-8")
    syntax = ast.parse(source)
    constants = {"_ALLOWED", "_HOST_FAULT_MODULE", "_APP_SERVER_HOST_MODULE", "_HOST_FAULT_MODULES",
                 "_HOST_FAULT_POLICY", "_HOST_REVIEWED_AST", "_HOST_BASE_AST", "_WORKER_LIFETIME_MODULE",
                 "_INPUT_RESOURCE_MODULE", "_INPUT_RESOURCE_BASE_RAW", "_INPUT_RESOURCE_REVIEWED_AST",
                 "_ISSUE_ACCOUNT_MODULE", "_ISSUE_ACCOUNT_REVIEWED_RAW"}
    functions = {"_require", "_allowed_delta", "_semantic_closure", "_semantic_unchanged"}
    nodes = []
    for node in syntax.body:
        if isinstance(node, ast.ClassDef) and node.name == "TransitionError":
            nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and (node.name in functions or node.name.startswith("_host_")):
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in node.targets):
            nodes.append(node)
    namespace = {"ast": ast, "hashlib": hashlib, "deepcopy": deepcopy}
    # No module imports or host owner bodies occur in this selected AST.
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                 "<actual-host-source-guard>", "exec"), namespace)
    return namespace


def owner(tree, name):
    return next(node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name)


def changed(source, edit):
    tree = ast.parse(source)
    edit(tree)
    return ast.unparse(ast.fix_missing_locations(tree))


class HostFaultSourceGuardTests(unittest.TestCase):
    def setUp(self):
        self.guard = guard_namespace()
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(fixture["schema_version"], "newrouge.story25-host-fault-base-sources.v1")
        self.assertEqual(fixture["base_commit"], "10398b4179cd15342b2c0db02111136180654025")
        self.old = {}
        for name, row in fixture["sources"].items():
            self.assertEqual(hashlib.sha256(row["text"].encode("utf-8")).hexdigest(), row["sha256"])
            self.old[name] = row["text"]
        self.current = {COMMON: (PYTHON / "_planning_skill_common.py").read_text(encoding="utf-8"),
                        SERVER: (PYTHON / "_codex_app_server.py").read_text(encoding="utf-8")}

    def check(self, *, common=None, server=None):
        return self.guard["_host_fault_sources"](self.old[COMMON], self.current[COMMON] if common is None else common,
            self.old[SERVER], self.current[SERVER] if server is None else server)

    def test_frozen_real_host_delta_has_only_reviewed_fault_slots(self):
        result = self.check()
        self.assertEqual(result, {"policy": "newrouge.b-route-host-fault-source-boundaries.v3", "profile": "reviewed-loop3"})
        self.assertEqual(hashlib.sha256((PYTHON / "_planning_skill_common.py").read_bytes()).hexdigest(),
                         "0190d35946e087c34c71301a8a771670087d8ef7808786263b5d5bac1755a9e2")
        self.assertEqual(hashlib.sha256((PYTHON / "_codex_app_server.py").read_bytes()).hexdigest(),
                         "598eb7d9e4e2dccec5a1a0ba31cf3b8e9fa0cd1df1d9d5b9263564cef1bdc022")
        # Projections are not publication data: actual full current source still differs.
        self.assertNotEqual(self.current[COMMON], self.old[COMMON])
        self.assertNotEqual(self.current[SERVER], self.old[SERVER])

    def test_historical_r25_minimal_runner_exception_remains_exactly_local(self):
        original = "def canonical_sha(value):\n    return value\ndef run_isolated_model():\n    return 1\n"
        result = self.guard["_host_fault_sources"](original, original.replace("return 1", "return 2"))
        self.assertEqual(result["profile"], "historical-runner-only")
        with self.assertRaisesRegex(ValueError, "outside_failure_boundary"):
            self.guard["_host_fault_sources"](original, original.replace("return value", "return None"))
        with self.assertRaisesRegex(ValueError, "outside_cleanup_boundary"):
            self.guard["_host_fault_sources"](original, original, "def replay():\n return 1\n", "def replay():\n return 2\n")

    def test_reviewed_common_bodies_and_new_helper_cannot_be_modified(self):
        edits = []
        for method in ("__init__", "_read", "cancel"):
            def edit(tree, method=method):
                owner(owner(tree, "_WindowsRunnerOutput"), method).body = [ast.Return(value=ast.Constant(value=None))]
            edits.append((method, edit))
        for name in ("_stop_owned_pipe_workers", "run_isolated_model"):
            def edit(tree, name=name):
                owner(tree, name).body = [ast.Return(value=ast.Constant(value=None))]
            edits.append((name, edit))
        for name, edit in edits:
            with self.subTest(owner=name), self.assertRaisesRegex(ValueError, "unreviewed_fault_owner"):
                self.check(common=changed(self.current[COMMON], edit))

    def test_unmasked_common_communicate_primitives_and_pure_helpers_remain_bound(self):
        for name in ("communicate", "_cancel_owned_pipe_io", "_terminate_process_tree", "canonical_sha",
                     "_runner_prefix", "validate_runner_description"):
            def edit(tree, name=name):
                parent = owner(tree, "_WindowsRunnerOutput") if name == "communicate" else tree
                owner(parent, name).body = [ast.Return(value=ast.Constant(value=None))]
            with self.subTest(owner=name), self.assertRaisesRegex(ValueError, "outside_failure_boundary"):
                self.check(common=changed(self.current[COMMON], edit))

    def test_app_server_replay_identity_high_tools_and_normal_protocol_remain_bound(self):
        for name in ("replay", "_replay", "thread_config", "check_reasoning_effort", "_no_mcp_tools", "command"):
            def edit(tree, name=name):
                owner(tree, name).body = [ast.Return(value=ast.Constant(value=None))]
            with self.subTest(owner=name), self.assertRaisesRegex(ValueError, "outside_cleanup_boundary"):
                self.check(server=changed(self.current[SERVER], edit))
        for name in ("record", "read_stdout", "send", "receive", "rpc"):
            def edit(tree, name=name):
                owner(owner(tree, "run_request"), name).body = [ast.Return(value=ast.Constant(value=None))]
            with self.subTest(owner=name), self.assertRaisesRegex(ValueError, "outside_cleanup_boundary"):
                self.check(server=changed(self.current[SERVER], edit))
        def bypass_protocol(tree):
            request = owner(tree, "run_request")
            protocol = next(node for node in request.body if type(node) is ast.Try and node.finalbody)
            protocol.body.insert(0, ast.Return(value=ast.Tuple(elts=[ast.Constant(value="forged success"), ast.Dict(keys=[], values=[])], ctx=ast.Load())))
        with self.assertRaisesRegex(ValueError, "outside_cleanup_boundary"):
            self.check(server=changed(self.current[SERVER], bypass_protocol))

    def test_app_server_cleanup_stderr_finally_and_import_slots_are_not_free_masks(self):
        def cleanup(tree):
            owner(tree, "_cleanup_request").body = [ast.Return(value=ast.Constant(value=None))]
        def stderr(tree):
            owner(owner(tree, "run_request"), "read_stderr").body = [ast.Return(value=ast.Constant(value=None))]
        def finally_return(tree):
            request = owner(tree, "run_request")
            next(n for n in request.body if type(n) is ast.Try and n.finalbody).finalbody.append(ast.Return(value=ast.Constant(value="success")))
        def wrong_exception(tree):
            request = owner(tree, "run_request")
            protocol = next(n for n in request.body if type(n) is ast.Try and n.finalbody)
            subscript = next(n for n in ast.walk(protocol.finalbody[0]) if isinstance(n, ast.Subscript))
            subscript.slice = ast.Constant(value=0)
        def sys_alias(tree):
            node = next(n for n in tree.body if isinstance(n, ast.Import) and any(a.name == "sys" for a in n.names))
            node.names[0].asname = "other_sys"
        def cleanup_import_alias(tree):
            node = next(n for n in owner(tree, "run_request").body if isinstance(n, ast.ImportFrom) and n.module == "_planning_skill_common")
            node.names[-1].asname = "other_stop"
        for name, edit, reason in (("helper", cleanup, "unreviewed_fault_owner"), ("stderr", stderr, "unreviewed_fault_owner"),
            ("extra_return", finally_return, "unreviewed_fault_owner"), ("exception_slot", wrong_exception, "unreviewed_fault_owner"),
            ("sys_alias", sys_alias, "sys_import"), ("cleanup_alias", cleanup_import_alias, "cleanup_import")):
            with self.subTest(owner=name), self.assertRaisesRegex(ValueError, reason):
                self.check(server=changed(self.current[SERVER], edit))

    def test_unknown_duplicate_and_missing_host_definitions_are_rejected(self):
        def duplicate_method(tree):
            reader = owner(tree, "_WindowsRunnerOutput")
            reader.body.append(deepcopy(owner(reader, "communicate")))
        def unknown_helper(tree):
            tree.body.append(ast.parse("def _cleanup_arbitrary():\n    return True\n").body[0])
        def missing_stop(tree):
            tree.body.remove(owner(tree, "_stop_owned_pipe_workers"))
        for name, edit in (("duplicate", duplicate_method), ("unknown", unknown_helper), ("missing", missing_stop)):
            with self.subTest(owner=name), self.assertRaises(ValueError):
                self.check(common=changed(self.current[COMMON], edit))
        with self.assertRaisesRegex(ValueError, "module_membership_changed"):
            self.guard["_host_fault_sources"](self.old[COMMON], self.current[COMMON], self.old[SERVER], None)

    def test_early_source_delta_is_finite_and_never_waives_removal(self):
        original = {COMMON: "old-common", SERVER: "old-server"}
        current = {COMMON: "new-common", SERVER: "new-server", TRANSITION: "new-guard"}
        self.assertEqual(set(self.guard["_allowed_delta"](original, current)), set(current))
        with self.assertRaisesRegex(ValueError, "outside_allowlist"):
            self.guard["_allowed_delta"](original, {**current, "scripts/python/_arbitrary_host.py": "new"})
        with self.assertRaisesRegex(ValueError, "source_removal_forbidden"):
            self.guard["_allowed_delta"](original, {key: value for key, value in current.items() if key != SERVER})
        with self.assertRaisesRegex(ValueError, "new_module_not_committed"):
            self.guard["_allowed_delta"]({**original, TRANSITION: "old-guard"}, current)

    def test_host_projection_is_not_reused_for_semantic_import_closure(self):
        names = ("review_schema", "review_issues", "machine", "generation_schema", "generation_schemas", "generation_target")
        runtime = ("import _codex_app_server as server\n"
            "def obligations():\n    return server.semantic_helper()\n"
            "def qualified_sources():\n    return server.semantic_helper()\n" +
            "\n".join("def " + name + "():\n    return 'original'\n" for name in names))
        module = "scripts/python/_b_route_planning_runtime.py"
        sources = {("old", module): runtime, ("new", module): runtime,
                   ("old", SERVER): "def semantic_helper():\n    return ['all flows']\n",
                   ("new", SERVER): "def semantic_helper():\n    return []\n"}
        self.guard["_path"] = lambda root, name: SimpleNamespace(read_text=lambda encoding: sources[(root, name)])
        self.guard["_same"] = lambda left, right: json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)
        with self.assertRaisesRegex(ValueError, "canonical_semantics_changed"):
            self.guard["_semantic_unchanged"]("old", "new")

    def test_loop3_input_resource_delta_pins_all_six_owners_and_immutable_remainder(self):
        fixture = FIXTURE.with_name("story25_loop3_planning_input_base.py.txt")
        raw = fixture.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
            "e66f9dfd17815f3038570678354d1e0f2735131bfb6e454b73a6a1fe415d4340")
        original = raw.decode("utf-8")
        current = (PYTHON / "_b_route_planning_input.py").read_text(encoding="utf-8")
        check = self.guard["_host_input_resource_sources"]
        check(original, current)
        for name in self.guard["_INPUT_RESOURCE_REVIEWED_AST"]:
            def edit(tree, name=name):
                owner(tree, name).body = [ast.Return(value=ast.Constant(value=None))]
            with self.subTest(owner=name), self.assertRaisesRegex(ValueError, "unreviewed_owner"):
                check(original, changed(current, edit))
        def change_validator(tree):
            owner(tree, "validate_draft_chain").body = [ast.Return(value=ast.Constant(value=None))]
        with self.assertRaisesRegex(ValueError, "outside_resource_boundary"):
            check(original, changed(current, change_validator))
        with self.assertRaisesRegex(ValueError, "original_not_frozen"):
            check(original + "\n# unreviewed original\n", current)

    def test_loop3_input_resource_imports_do_not_create_free_module_slots(self):
        original = FIXTURE.with_name("story25_loop3_planning_input_base.py.txt").read_text(encoding="utf-8")
        current = (PYTHON / "_b_route_planning_input.py").read_text(encoding="utf-8")
        def alias(tree):
            node = next(node for node in tree.body if isinstance(node, ast.Import)
                and any(value.name == "_b_route_planning_wire" for value in node.names))
            node.names[0].asname = "other_wire"
        def transport(tree):
            node = next(node for node in tree.body if isinstance(node, ast.ImportFrom)
                and node.module == "_mvg_evidence_transport")
            node.names.append(ast.alias(name="lossless_context", asname=None))
        for name, edit in (("wire-alias", alias), ("unguarded-factor", transport)):
            with self.subTest(import_name=name), self.assertRaisesRegex(ValueError, "import_changed"):
                self.guard["_host_input_resource_sources"](original, changed(current, edit))

    def test_loop3_lifetime_exact_fault_owners_and_other_job_behavior_remain_bound(self):
        original = FIXTURE.with_name("story25_loop3_worker_lifetime_base.py.txt").read_text(encoding="utf-8")
        self.assertEqual(hashlib.sha256(original.encode("utf-8")).hexdigest(),
            "6fab381945228f180b3646c7f0c84e7f778e25017f7b3b7d8b7efa543588fbf6")
        current = (PYTHON / "_mvg_worker_lifetime.py").read_text(encoding="utf-8")
        check = self.guard["_host_lifetime_sources"]
        check(original, current)
        for name in ("__init__", "close", "worker_lifetime"):
            def edit(tree, name=name):
                target = tree if name == "worker_lifetime" else owner(tree, "WindowsWorkerJob")
                owner(target, name).body = [ast.Return(value=ast.Constant(value=None))]
            with self.subTest(owner=name), self.assertRaisesRegex(ValueError, "unreviewed_fault_owner"):
                check(original, changed(current, edit))
        def assign(tree):
            owner(owner(tree, "WindowsWorkerJob"), "assign").body = [ast.Return(value=ast.Constant(value=None))]
        with self.assertRaisesRegex(ValueError, "outside_cleanup_boundary"):
            check(original, changed(current, assign))

    def test_loop3_worker_cleanup_helper_and_finally_are_exactly_pinned(self):
        current = (PYTHON / "_mvg_capability_worker.py").read_text(encoding="utf-8")
        check = self.guard["_host_worker_cleanup_source"]
        check(current)
        def helper(tree):
            owner(tree, "_cleanup_candidate").body = [ast.Return(value=ast.Constant(value=None))]
        def final(tree):
            runner = owner(tree, "run_candidate")
            context = next(node for node in runner.body if type(node) is ast.With)
            protocol = next(node for node in context.body if type(node) is ast.Try and node.finalbody)
            protocol.finalbody = [ast.Pass()]
        for name, edit in (("helper", helper), ("finally", final)):
            with self.subTest(owner=name), self.assertRaisesRegex(ValueError, "unreviewed_fault_owner"):
                check(changed(current, edit))

    def test_loop3_issue_account_adapter_addition_is_bound_to_exact_reviewed_bytes(self):
        raw = (PYTHON / "_b_route_issue_accounts.py").read_bytes()
        self.guard["_host_added_account_source"](raw)
        with self.assertRaisesRegex(ValueError, "source_not_reviewed"):
            self.guard["_host_added_account_source"](raw + b"\n# unreviewed account policy\n")


if __name__ == "__main__":
    unittest.main()
