"""Offline short-path routing only; no native worker or admission executes."""
import ast
from copy import deepcopy
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

import _b_route_planning_runtime as runtime


class StopBeforeDispatch(Exception):
    pass


class InputPathRuntimeTests(unittest.TestCase):
    def test_stage_cost_short_path_overrides_old_names_without_budget_changes(self):
        import _mvg_capability_append as append
        import _mvg_capability_generation as generation
        workspace = Path("C:/fixture/candidates/candidate-2/scope-1")
        frozen = {"transport": {"batches": [{}, {}]}}
        partial = types.ModuleType("_b_route_partial_generation_recovery")
        partial.resume_propose_attempt = Mock(side_effect=AssertionError("No recovery claim in routing test"))
        budget = {"remaining_requests": 7, "remaining_seconds": 300}
        cases = (({}, "5-inspect.json"),
                 ({"b_route_review_worker_attempt": 2}, "recovery-2/5-inspect.json"),
                 ({"b_route_synthesis_recovery": {"old": True}}, "synthesis-recovery-1/5-inspect.json"),
                 ({"b_route_partial_generation_recovery": {"old": True}}, "input-budget-recovery-1/5-inspect.json"),
                 ({"b_route_input_path_recovery": {"typed": True}, "b_route_partial_generation_recovery": {"old": True},
                   "b_route_synthesis_recovery": {"old": True}, "b_route_review_worker_attempt": 2}, "p1/5-inspect.json"))
        def run(_directory, **kwargs):
            return kwargs["propose"]({}, {}, None, None, 1, Mock())
        for state, relative in cases:
            state = {"runtime_identity": "synthetic-routing", **state}
            cost_budget, invoke = Mock(return_value=budget), Mock(side_effect=AssertionError("No runner in routing test"))
            original = deepcopy(state)
            with self.subTest(relative=relative), patch.dict(sys.modules, {partial.__name__: partial}), \
                    patch.object(runtime, "frozen_input", return_value=frozen), \
                    patch.object(runtime, "scopes", return_value=[{}]), \
                    patch.object(runtime, "load_json", return_value={"total_invocations": 4}), \
                    patch.object(append, "run_capability_append", side_effect=run), \
                    patch.object(generation, "stage_cost_preflight", side_effect=StopBeforeDispatch) as preflight:
                with self.assertRaises(StopBeforeDispatch):
                    runtime.generate_append(workspace, state, workspace, invoke_factory=invoke, before_call=Mock(),
                                            checkpoint=Mock(), accepted_seed={}, cost_budget=cost_budget)
                cost_budget.assert_called_once_with("inspect", known_evidence_calls=2)
                preflight.assert_called_once_with(workspace / "capability-append/stage-costs" / relative,
                                                  phase="inspect", evidence_calls=2, **budget)
                invoke.assert_not_called()
                self.assertEqual(state, original)
        partial.resume_propose_attempt.assert_not_called()

    @staticmethod
    def selection_routing():
        # Execute the actual small routing block, not the native state machine.
        # No copy of its branch implementation appears in this fixture.
        source = Path(runtime.__file__).with_name("_mvg_capability_selection.py")
        tree = ast.parse(source.read_bytes())
        blocks = []
        for node in ast.walk(tree):
            for _name, value in ast.iter_fields(node):
                if not isinstance(value, list):
                    continue
                for index, item in enumerate(value):
                    if (isinstance(item, ast.Assign) and len(item.targets) == 1
                            and isinstance(item.targets[0], ast.Name) and item.targets[0].id == "lifecycle_name"):
                        statements = []
                        for statement in value[index:]:
                            if (isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Call)
                                    and isinstance(statement.value.func, ast.Name) and statement.value.func.id == "run_candidate"):
                                break
                            statements.append(statement)
                        if len(statements) > 1:
                            blocks.append(statements)
        if len(blocks) != 1:
            raise AssertionError("Expected exactly the native lifecycle routing block")
        return compile(ast.fix_missing_locations(ast.Module(body=blocks[0], type_ignores=[])), str(source), "exec")

    def test_lifecycle_short_path_is_scoped_and_historical_fallbacks_remain(self):
        routing = self.selection_routing()
        combined = {"b_route_review_recovery": {"old": True}, "b_route_review_worker_attempt": 2,
                    "b_route_synthesis_recovery": {"old": True}, "b_route_partial_generation_recovery": {"old": True},
                    "b_route_input_path_recovery": {"typed": True}}
        cases = ((combined, "candidate-2", 0, "lifecycle-p1"),
                 (combined, "candidate-1", 0, "lifecycle-review-recovery-2"),
                 (combined, "candidate-2", 1, "lifecycle"),
                 (combined, "candidate-3", 0, "lifecycle"),
                 ({key: value for key, value in combined.items() if key != "b_route_input_path_recovery"},
                  "candidate-2", 0, "lifecycle-input-budget-recovery-1"),
                 ({"b_route_synthesis_recovery": {"old": True}}, "candidate-2", 0, "lifecycle-synthesis-recovery-1"),
                 ({}, "candidate-2", 0, "lifecycle"))
        for state, label, index, expected in cases:
            original = deepcopy(state)
            namespace = {"state": state, "label": label, "index": index}
            with self.subTest(label=label, index=index, expected=expected):
                exec(routing, {"__builtins__": {"str": str}}, namespace)
                self.assertEqual(namespace["lifecycle_name"], expected)
                self.assertEqual(state, original)


if __name__ == "__main__":
    unittest.main()
