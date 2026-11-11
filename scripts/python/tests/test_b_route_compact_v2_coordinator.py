"""Offline OS-transport coverage for the explicit new compact input policy."""
import ast
import os
import unittest
from unittest.mock import patch

import _b_route_planning_runtime as runtime
import _planning_skill_common as common
import test_b_route_planning_runtime as fixtures


class CompactV2CoordinatorTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp

    def create(self, profile="3b-mvg-v1", run_id="runtime", *, complete_wire=False):
        directory, state = fixtures.RuntimeTests.create(self, profile, run_id,
            complete_wire=True, wire_delivery=runtime.wire.CURRENT_SCHEMA)
        state["b_route_input_compact_policy"] = runtime.compact.CURRENT_SCHEMA
        common.atomic_json(directory / "run.json", state)
        return directory, state

    def check_coordinator(self, profile):
        observed = []
        render = runtime.wire.render

        def checked_render(instruction, materials, delivery=None, *, compact_schema=None):
            self.assertEqual(compact_schema, runtime.compact.CURRENT_SCHEMA)
            prompt = render(instruction, materials, delivery, compact_schema=compact_schema)
            self.assertEqual(ast.literal_eval(prompt.split("\n", 1)[1])["schema_version"],
                runtime.compact.CURRENT_SCHEMA)
            self.assertEqual(runtime.wire.text(runtime.wire.read_prompt(prompt, delivery)),
                runtime.wire.text(materials))
            observed.append(materials["phase"])
            return prompt

        with patch.dict(os.environ, {"NEWROGUE_CODEX_REASONING_EFFORT": "high",
                "NEWROGUE_B_ROUTE_FIXTURE_REASONING_EFFORT": "high"}), \
                patch.object(runtime.wire, "render", side_effect=checked_render):
            fixtures.ReviewFixTests.complete_offline_transport_coordinator(self, profile, complete_wire=True)
        self.assertTrue({"generation", "independent_admission", "selection"} <= set(observed))

    def test_two_capability_candidates_use_new_codec_through_native_transport(self):
        self.check_coordinator("3b-capabilities-v1")

    def test_three_mvg_candidates_use_new_codec_through_native_transport(self):
        self.check_coordinator("3b-mvg-v1")


if __name__ == "__main__":
    unittest.main()
