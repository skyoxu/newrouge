"""Synthetic native/OS observations; actual segmented business product owners.

No fixture setUp, model, subprocess, registry writer or legacy admission runs.
Root runs these new cases only after the common source barrier. Complete
protocol/schema/source/owner/graph/accounting predicates are not patched.
"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _b_route_candidate as original
import _b_route_codec as codec
import _b_route_segmented_candidates as products
import _b_route_segmented_workflow as core
import _b_route_segmented_requests as requests
import _b_route_segmented_runtime as native
import _b_route_planning_input as planning
import test_b_route_candidate as candidate_data
import test_b_route_segmented_workflow as analysis


def business_fixture(root):
    """Reuse existing valid data methods, never their TemporaryDirectory setup."""
    fixture = candidate_data.CandidateTests()
    fixture.root = root
    fixture.manifest = {"source_revision": "revision  1 ", "manifest_sha256": "sha256:" + "1" * 64,
                        "sources": [{"path": "docs/source.md"}, {"path": "docs/empty.md"}]}
    fixture.ledger = {"source_revision": "revision  1 ", "source_manifest_sha256": "sha256:" + "1" * 64,
        "blocks": [{"block_id": "B1", "source_path": "docs/source.md", "text": "Rule"},
                   {"block_id": "B2", "source_path": "docs/empty.md", "text": ""}]}
    fixture.proposal = {"proposal_id": "proposal:keep-original", "source_block_ids": ["B1"],
        "acceptance_intent": "Keep original  \r\n", "prior_requirement_ids": ["FR-EXISTING"], "non_task_sinks": ["SINK"]}
    store = {"native-manifest.json": analysis.json_bytes(fixture.manifest),
             "native-ledger.json": analysis.json_bytes(fixture.ledger),
             "docs/source.md": b"# Rule\r\n\r\nPreserve order.  \r\n",
             "docs/empty.md": b"", "docs/constraint.md": b"Keep original identities and audit provenance.\r\n"}
    for name, raw in store.items():
        analysis.write(root, name, raw)
    contract = {"schema_version": planning.CONTRACT, "input_stage": "3b", "audit_ref": "logs/ci/fixture/report.json",
                "scope": {"scope_id": "scope", "kind": "all", "ids": []},
                "constraints": [{"path": "docs/constraint.md", "format": "text"}], "contexts": [],
                "limits": {"max_bytes": 1048576, "max_input_tokens": 96000, "reserved_tokens": 200}}
    inputs = {"global_proof": {"manifest": deepcopy(fixture.manifest), "ledger": deepcopy(fixture.ledger),
                              "proposals": {"proposals": [deepcopy(fixture.proposal)]}},
              "contract": contract, "closure": {"source_paths": ["docs/source.md", "docs/empty.md"]},
              "source_inventory": [{"path": "docs/source.md", "raw_digest": codec.raw_digest(store["docs/source.md"])}]}
    fixture.frozen = {"input_identity": codec.canonical_digest(inputs), "inputs": inputs}
    # This is the explicit unavailable full-native observation boundary. It is
    # not a real prepared proof, and never reaches a real native writer.
    context = {"frozen": fixture.frozen, "byte_store": store,
               "fixture_notice": "SYNTHETIC ORIGINAL NATIVE OBSERVATION; NOT QUALIFICATION"}
    return fixture.envelope()["content"], context


def paired_business_fixture(root, content, context, *, shared):
    """Two separate source/Requirement/Flow owners; optionally one shared C.

    This changes only the explicit synthetic native observation, not a real
    prepared record. The original full business predicates still consume every
    source reference, body, route and owner without mocking.
    """
    content, context = deepcopy(content), deepcopy(context)
    inputs = context["frozen"]["inputs"]
    manifest, ledger = inputs["global_proof"]["manifest"], inputs["global_proof"]["ledger"]
    manifest["sources"][1]["path"] = "docs/second.md"
    ledger["blocks"][1] = {"block_id": "B2", "source_path": "docs/second.md", "text": "Second independent rule"}
    original_req = deepcopy(content["requirements"][0])
    second_req = {**deepcopy(original_req), "requirement_id": "proposal:second-rule", "source_block_ids": ["B2"],
                  "acceptance_intent": "Preserve the second Rule", "prior_requirement_ids": [], "non_task_sinks": ["SINK-SECOND"]}
    inputs["global_proof"]["proposals"]["proposals"].append({"proposal_id": second_req["requirement_id"],
        **{key: deepcopy(second_req[key]) for key in ("source_block_ids", "acceptance_intent", "prior_requirement_ids", "non_task_sinks")}})
    inputs["closure"]["source_paths"] = ["docs/source.md", "docs/second.md"]
    context["byte_store"]["docs/second.md"] = b"Second independent rule; preserve its own Flow and evidence.\n"
    context["byte_store"].pop("docs/empty.md", None)
    for path, value in (("native-manifest.json", manifest), ("native-ledger.json", ledger)):
        context["byte_store"][path] = analysis.json_bytes(value)
        (root / path).write_bytes(context["byte_store"][path])
    analysis.write(root, "docs/second.md", context["byte_store"]["docs/second.md"])
    inputs["source_inventory"] = [{"path": path, "raw_digest": codec.raw_digest(context["byte_store"][path])}
                                  for path in inputs["closure"]["source_paths"]]
    context["frozen"]["input_identity"] = codec.canonical_digest(inputs)
    for key, path in (("manifest_ref", "native-manifest.json"), ("ledger_ref", "native-ledger.json")):
        content["source_identity"][key]["files"][0]["raw_digest"] = codec.raw_digest(context["byte_store"][path])
    content["requirements"].append(second_req)
    fixture = candidate_data.CandidateTests()
    fixture.proposal = inputs["global_proof"]["proposals"]["proposals"][1]
    second = fixture.flow("FLOW-SECOND")
    second["proposed_owner_key"] = "flow-owner-second"
    second["source_block_ids"] = ["B2"]
    second["capability_ids"] = ["proposal:capability-second"]
    for obj in original.walk(second):
        if obj.get("kind") == "flow" and obj.get("definition_id") == "FLOW-SECOND":
            obj["proposed_owner_key"] = "flow-owner-second"
    content["definitions"]["flows"].append(second)
    for field in ("requirement_verification", "coverage_table", "applicability"):
        row = deepcopy(content[field][0])
        row["requirement_id"] = second_req["requirement_id"]
        if "flow_id" in row:
            row["flow_id"] = "FLOW-SECOND"
        content[field].append(row)
    content["requirement_route_memberships"].append({"requirement_id": second_req["requirement_id"],
        "flow_id": "FLOW-SECOND", "observable_role": "Independent second result"})
    command_ids = ["COMMON-C", "COMMON-C"] if shared else ["FIRST-C", "SECOND-C"]
    commands = []
    for index, (flow, command_id) in enumerate(zip(content["definitions"]["flows"], command_ids)):
        # A complete acyclic entry/action/success graph keeps this two-consumer
        # fixture small. The unchanged Cap positive retains its original SCC.
        flow["graph"]["nodes"] = flow["graph"]["nodes"][:3]
        flow["graph"]["edges"] = flow["graph"]["edges"][:2]
        flow["graph"]["loops"] = []
        owner = "common-command-owner" if shared else "command-owner-" + str(index)
        use = {"kind": "command", "definition_id": command_id, "proposed_owner_key": owner}
        flow["graph"]["nodes"][1]["command_uses"] = [deepcopy(use)]
        if not any(command["id"] == command_id for command in commands):
            commands.append({"id": command_id, "proposed_owner_key": owner, "requirement_ids": [],
                             "responsibility": "Preserve the declared Rule at each exact consumer", "uses": []})
    content["definitions"]["commands"] = commands
    return content, context


def product_plan(root, context, *, planner="mvg", content=None):
    labels = list("AB" if planner == "capability" else "ABC")
    source_raw = (root / "docs/source.md").read_bytes()
    global_raw = (root / "docs/constraint.md").read_bytes()
    materials = [{"material_id": "source", "path": "docs/source.md", "version": "source-v1", "role": "source",
                  "candidate_label": None, "boundaries": [0, len(source_raw)]},
                 {"material_id": "global", "path": "docs/constraint.md", "version": "global-v1", "role": "global",
                  "candidate_label": None, "boundaries": [0, len(global_raw)]}]
    source_ids = ["source.0"]
    if "docs/second.md" in context["frozen"]["inputs"]["closure"]["source_paths"]:
        second_raw = (root / "docs/second.md").read_bytes()
        materials.insert(1, {"material_id": "second", "path": "docs/second.md", "version": "source-v1", "role": "source",
                             "candidate_label": None, "boundaries": [0, len(second_raw)]})
        source_ids.append("second.0")
    candidates = [{"label": label, "candidate_id": "private-original-" + planner + "-" + label, "material_ids": []} for label in labels]
    manifest = core.freeze_manifest(root, run_id="new-products-" + planner, materials=materials, candidates=candidates)
    obligations = [{"obligation_id": "source-rule", "kind": "requirement", "segment_ids": source_ids + ["global.0"], "dependency_ids": []},
                   {"obligation_id": "graph-rule", "kind": "edge", "segment_ids": source_ids[:], "dependency_ids": ["source-rule"]}]
    oids = [r["obligation_id"] for r in obligations]
    edges = [["graph-rule", "source-rule"]]
    nodes = []
    by_phase = {}
    for phase in core.PHASES[:3]:
        for label in labels:
            previous = [] if phase == "generation" else [by_phase[(core.PHASES[core.PHASES.index(phase)-1], label)]]
            node_id = phase.replace("independent-", "") + "-" + label
            nodes.append({"node_id": node_id, "phase": phase, "ordinal": len(nodes), "candidate_labels": [label],
                          "segment_ids": [] if phase == "synthesis" else source_ids[:], "obligation_ids": oids[:],
                          "dependencies": previous, "output_reserve": 26000, "final": False})
            by_phase[phase, label] = node_id
    nodes.append({"node_id": "joint-panel", "phase": "selection", "ordinal": len(nodes), "candidate_labels": labels[:],
                  "segment_ids": source_ids[:], "obligation_ids": oids[:],
                  "dependencies": [by_phase["independent-review", label] for label in labels], "output_reserve": 26000, "final": False})
    nodes.append({"node_id": "global-choice", "phase": "selection", "ordinal": len(nodes), "candidate_labels": labels[:],
                  "segment_ids": [], "obligation_ids": oids[:], "dependencies": ["joint-panel"], "output_reserve": 26000, "final": True})
    slots = []
    for label in labels:
        for target in products.TARGETS:
            values = None
            if content is not None and target in {"definitions.flows", "definitions.commands"}:
                values = content["definitions"][target.split(".")[1]]
            for suffix in (["/" + row["id"] for row in values] if values else [""]):
                slots.append({"slot_id": label + ":" + target + suffix, "candidate_label": label, "target": target,
                              "generation_node": by_phase["generation", label], "synthesis_node": by_phase["synthesis", label],
                              "obligation_ids": oids[:], "dependency_slot_ids": []})
    contract = {"schema_version": products.CONTRACT, "source_input_identity": context["frozen"]["input_identity"],
                "slots": slots, "final_required_slot_ids": []}
    return core.build_plan(manifest, planner=planner, dimensions=["source", "graph-and-preservation"],
                           obligations=obligations, dependency_edges=edges, nodes=nodes, candidate_contract=contract)


def fine_body_values(content):
    """Complete object-per-slot data for pure closure checks, never a prefix."""
    values = {}
    for target in products.TARGETS:
        value = content
        for key in target.split("."):
            value = value[key]
        groups = [[row] for row in value] if isinstance(value, list) and value else [value]
        for ordinal, group in enumerate(groups):
            sid = "A:" + target + "/" + str(ordinal)
            second = any(obj.get("requirement_id") == "proposal:second-rule" or obj.get("id") in {"FLOW-SECOND", "SECOND-C"}
                         or obj.get("definition_id") in {"FLOW-SECOND", "SECOND-C"} for obj in original.walk(group))
            values[sid] = {"slot": {"slot_id": sid, "candidate_label": "A", "target": target, "dependency_slot_ids": [],
                                     "obligation_ids": ["second" if second else "first"]},
                           "value": deepcopy(group), "piece": {"slot_id": sid,
                               "value_json": json.dumps(group, ensure_ascii=False, separators=(",", ":")),
                               "parent_piece_refs": [], "change_reason": "", "citations": []}}
    return values


class SegmentedCandidateTests(unittest.TestCase):
    # Method reuse only; this creates a unique short owned TEMP tree and never
    # calls CandidateTests.setUp or any original native preparation.
    cleanup_owned = analysis.SegmentedWorkflowTests.cleanup_owned
    blocked = analysis.SegmentedWorkflowTests.blocked
    fake_os_turn = analysis.SegmentedWorkflowTests.fake_os_turn

    def setUp(self):
        analysis.SegmentedWorkflowTests.setUp(self)
        self.content, self.context = business_fixture(self.root)
        self.plan = product_plan(self.root, self.context)
        self.run_dir = self.root / "logs/ci/native"
        self.response_factory = self.business_response

    def close_fake_original_context(self, root, context):
        if context is not self.context:
            raise AssertionError("No caller dictionary may replace synthetic original owner token")
        for path, raw in context["byte_store"].items():
            if (Path(root) / path).read_bytes() != raw:
                raise ValueError("synthetic_native_observation_raw_changed")

    @contextmanager
    def composition(self, plan=None, session=None):
        with analysis.SegmentedWorkflowTests.composition(self, plan=plan, session=session) as active:
            with patch.object(native, "candidate_context", side_effect=lambda *args: self.context), \
                 patch.object(native, "verify_candidate_context", side_effect=self.close_fake_original_context):
                yield active

    def business_response(self, plan, node, envelope):
        citations = [analysis.citation(plan, row["segment_id"]) for row in plan["manifest"]["segments"]]
        oids = node["obligation_ids"]
        obligations = {r["obligation_id"]: r for r in plan["obligations"]}
        coverage = [{"obligation_id": oid, "citations": [analysis.citation(plan, sid) for sid in obligations[oid]["segment_ids"]]} for oid in oids]
        decisions = [{"decision_id": node["node_id"] + "/" + oid, "obligation_ids": [oid],
                      "depends_on": obligations[oid]["dependency_ids"][:], "citations": coverage[index]["citations"],
                      "statement": "Preserve the original Rule and complete declared Flow graph: " + oid} for index, oid in enumerate(oids)]
        comparisons = []
        if node["phase"] == "selection":
            for label in node["candidate_labels"]:
                for dimension in plan["dimensions"]:
                    comparisons.append({"candidate_label": label, "dimension": dimension, "obligation_ids": oids[:],
                        "assessment": "Complete declared Rule and graph for blind candidate " + label, "citations": citations,
                        "cross_impacts": [{"from": edge[0], "to": edge[1], "explanation": "Graph obligations preserve source Rule", "citations": citations} for edge in plan["dependency_edges"]]})
        pieces = []
        parents = [{"slot_id": slot["slot_id"], "raw_digest": slot["raw_digest"]}
                   for product in envelope["candidate_products"] for slot in product["slots"]]
        for slot in products.expected_slots(plan, node):
            value = self.content
            for key in slot["target"].split("."):
                value = value[key]
            value = deepcopy(value)
            object_id = slot["slot_id"].partition("/")[2]
            if object_id:
                value = [row for row in value if row["id"] == object_id]
            reason = ""
            if node["phase"] == "synthesis" and slot["target"] == "definitions.flows":
                value[0]["observable_result"] += "; same Rule clarified during synthesis"
                reason = "Clarify the visible result while preserving the complete original generation object"
            piece = {"slot_id": slot["slot_id"], "value_json": json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                     "citations": deepcopy(citations), "parent_piece_refs": deepcopy(parents), "change_reason": reason}
            if getattr(self, "alter_piece", None):
                self.alter_piece(node, slot, piece)
            pieces.append(piece)
        checks = [{"candidate_label": product["candidate_label"], "slot_id": slot["slot_id"], "raw_digest": slot["raw_digest"],
                   "verdict": "supported", "citations": deepcopy(citations)}
                  for product in envelope["candidate_products"] for slot in product["slots"]]
        if node["phase"] not in {"independent-review", "selection"}:
            checks = []
        joint_checks = []
        if node["phase"] in {"independent-review", "selection"}:
            for product in envelope["candidate_products"]:
                provided = {slot["slot_id"] for slot in product["slots"]}
                for domain in product["object_domain"]["interaction_domains"]:
                    if set(domain["member_slot_ids"]) & provided:
                        joint_checks.append({**{key: deepcopy(domain[key]) for key in (
                            "candidate_label", "domain_digest", "member_digests", "interaction_edges", "source_obligation_ids")},
                            "verdict": "supported", "citations": deepcopy(citations)})
        return {"schema_version": core.RESPONSE, "protocol": core.PROTOCOL, "run_id": plan["run_id"],
            "plan_digest": plan["plan_digest"], "node_id": node["node_id"], "phase": node["phase"],
            "coverage": coverage, "decisions": decisions, "dependency_edges": deepcopy(plan["dependency_edges"]),
            "unresolved": [], "findings": [],
            "checks": [{"obligation_id": oid, "verdict": "supported", "citations": deepcopy(citations)} for oid in oids] if node["phase"] == "independent-review" else [],
            "comparisons": comparisons, "candidate_pieces": pieces, "product_checks": checks, "joint_checks": joint_checks,
            "selected_label": "A" if node["final"] else None,
            "rationale": "Complete Rule and graph preserved; choose original blind A" if node["final"] else "",
            "derived_not_lossless": True}

    def prefix_before(self, node):
        tokens = {}
        for previous_node, item in zip(self.active_plan["nodes"][:node["ordinal"]], self.session.completed):
            tokens[previous_node["node_id"]] = core.replay_verified_result(self.root, self.active_plan, previous_node,
                                                                         item["reservation"], item["result"])
        return tokens, core.capture_completed_prefix(self.root, self.active_plan, tokens)

    def assert_complete_product_chain(self, planner):
        self.plan = product_plan(self.root, self.context, planner=planner,
                                 content=self.content if getattr(self, "paired", False) else None)
        with self.composition():
            result = core.execute_workflow(self.root, run_dir=self.run_dir, plan=self.plan)
            proof = products.verify_proof(self.root, run_dir=self.run_dir, plan=self.plan, proof=result["candidate_proof"])
        self.assertEqual(len(self.dispatched), len(self.plan["nodes"]))
        self.assertEqual(len(proof["products"]), 2 if planner == "capability" else 3)
        self.assertTrue(proof["new_segmented_candidate_qualified"])
        for key in ("legacy_native_admission", "formal_adoption", "readiness", "b_default_active"):
            self.assertIs(proof[key], False)
        self.assertIs(result["native_qualified"], False)
        self.assertEqual(self.session.finalized, result)
        for call in self.dispatched:
            envelope = requests.read_input_envelope(self.root, Path(call["workspace"]))
            for candidate in self.plan["manifest"]["candidates"]:
                self.assertNotIn(candidate["candidate_id"], requests._model_prompt(Path(call["workspace"]), Path(call["prompt_path"]), Path(call["output_path"])))
            if envelope["phase"] == "independent-review":
                self.assertEqual([p["candidate_label"] for p in envelope["candidate_products"]], envelope["candidate_labels"])
                body = envelope["candidate_products"][0]
                self.assertEqual(body["stage"], "assembled-original")
                self.assertEqual(body["object_domain"]["accounting"]["unique_requirement_count"], len(self.content["requirements"]))
                self.assertEqual(len(body["slots"]), len([slot for slot in self.plan["candidate_contract"]["slots"]
                                                         if slot["candidate_label"] == body["candidate_label"]]))
                flow = next(s for s in body["slots"] if s["target"] == "definitions.flows")
                object_id = flow["slot_id"].partition("/")[2]
                expected_flows = [row for row in self.content["definitions"]["flows"] if not object_id or row["id"] == object_id]
                self.assertEqual(json.loads(flow["generation_value_json"]), expected_flows)
                self.assertNotEqual(flow["value_json"], flow["generation_value_json"])
                self.assertEqual(flow["generation_raw_digest"], analysis.raw_sha(flow["generation_value_json"].encode()))
                self.assertEqual(json.loads(flow["value_json"])[0]["graph"], self.content["definitions"]["flows"][0]["graph"])
        return result

    def test_complete_capability_generation_synthesis_original_business_and_protocol(self):
        self.assert_complete_product_chain("capability")

    def test_complete_mvg_three_candidates_private_review_and_original_generation_preserved(self):
        self.content, self.context = paired_business_fixture(self.root, self.content, self.context, shared=True)
        self.paired = True
        self.assert_complete_product_chain("mvg")
        session = self.session
        with self.composition(session=session):
            review = next(n for n in self.plan["nodes"] if n["node_id"] == "review-A")
            tokens, prefix = self.prefix_before(review)
            facts = core.verify_completed_prefix(self.root, self.plan, prefix)
            values = products._values(self.plan, facts, "A", "synthesis")
            shared = "A:definitions.commands/COMMON-C"
            first, second = "A:definitions.flows/FLOW", "A:definitions.flows/FLOW-SECOND"
            domains = products.derive_review_domains(self.plan, values, context=self.context)
            related = products.review_interaction_closure(values, [shared], domains)
            self.assertTrue({shared, first, second} <= set(related))
            joint = next(d for d in domains if shared in d["member_slot_ids"])
            self.assertTrue({shared, first, second} <= set(joint["member_slot_ids"]))
            self.assertTrue({"source.0", "second.0"} <= set(joint["required_original_segments"]))
            envelope = core._envelope(self.root, self.plan, review, tokens, run_dir=self.run_dir)
            actual_slots = {row["slot_id"]: row for row in envelope["candidate_products"][0]["slots"]}
            self.assertTrue({shared, first, second} <= set(actual_slots))
            self.assertEqual(json.loads(actual_slots[shared]["value_json"]), self.content["definitions"]["commands"])
            # A semantic joint domain is not discharged by two independent
            # consumer-only source/draft views, even though each looks forward-
            # closed. The real related-closure owner supplies the missing peer.
            self.assertIn(second, products.review_interaction_closure(values, [first], domains))
            self.assertIn(first, products.review_interaction_closure(values, [second], domains))
            item = next(i for i in self.session.completed if i["node_id"] == review["node_id"])
            response = item["result"]["response"]
            actual_products = item["result"]["candidate_products"]
            products.verify_joint_checks(self.plan, review, response, actual_products)
            missing_body = deepcopy(actual_products)
            missing_body[0]["slots"] = [slot for slot in missing_body[0]["slots"] if slot["slot_id"] != second]
            self.blocked("joint_review.complete_body_and_originals_required", lambda: products.verify_joint_checks(
                self.plan, review, response, missing_body))
            missing_original = deepcopy(review)
            missing_original["segment_ids"].remove("second.0")
            self.blocked("joint_review.complete_body_and_originals_required", lambda: products.verify_joint_checks(
                self.plan, missing_original, response, actual_products))
            slotwise_only = deepcopy(response)
            slotwise_only["joint_checks"] = []
            self.assertTrue(slotwise_only["product_checks"])
            self.blocked("joint_review.complete_domain_denominator", lambda: products.verify_joint_checks(
                self.plan, review, slotwise_only, actual_products))
            partial_joint = deepcopy(response)
            check = next(row for row in partial_joint["joint_checks"] if row["domain_digest"] == joint["domain_digest"])
            check["member_digests"] = [row for row in check["member_digests"] if row["slot_id"] != second]
            self.blocked("joint_review.mixed_stale_partial_or_unsupported", lambda: products.verify_joint_checks(
                self.plan, review, partial_joint, actual_products))
            self.assertFalse(self.dispatched)  # All attacks reuse captured immutable turns, with no new request.

    def test_independent_commands_and_requirements_remain_separate_review_domains(self):
        content, context = paired_business_fixture(self.root, self.content, self.context, shared=False)
        products._business_check(content, context)
        plan = product_plan(self.root, context, content=content)
        plan["obligations"] = [
            {"obligation_id": "first", "kind": "requirement", "segment_ids": ["source.0", "global.0"], "dependency_ids": []},
            {"obligation_id": "second", "kind": "requirement", "segment_ids": ["second.0", "global.0"], "dependency_ids": []}]
        plan["dependency_edges"] = []
        for node in plan["nodes"]:
            node["obligation_ids"] = ["first", "second"]
        for slot in plan["candidate_contract"]["slots"]:
            slot["obligation_ids"] = ["first", "second"]
        analysis.resign(plan, "plan_digest")
        core.validate_plan(plan)
        values = fine_body_values(content)
        domains = products.derive_review_domains(plan, values, context=context)
        def sid(target, identity):
            return next(key for key, row in values.items() if row["slot"]["target"] == target
                        and row["value"] and row["value"][0].get("id") == identity)
        c1, c2 = sid("definitions.commands", "FIRST-C"), sid("definitions.commands", "SECOND-C")
        f1, f2 = sid("definitions.flows", "FLOW"), sid("definitions.flows", "FLOW-SECOND")
        first = set(products.review_interaction_closure(values, [c1], domains))
        second = set(products.review_interaction_closure(values, [c2], domains))
        self.assertTrue({c1, f1} <= first)
        self.assertTrue({c2, f2} <= second)
        self.assertFalse({c2, f2} & first)
        self.assertFalse({c1, f1} & second)
        # Pure body/domain data is deliberately not an authentic paid prefix.
        self.blocked("prefix.genuine_factory_token", lambda: core.verify_completed_prefix(self.root, plan,
            {"results": values, "verified": True}))

    def test_missing_duplicate_slots_and_same_definition_id_different_body_reject(self):
        node = self.plan["nodes"][0]
        with self.composition():
            envelope = core._envelope(self.root, self.plan, node, {}, run_dir=self.run_dir)
        # The complete schema/source frame comes through the explicit fake
        # original-native observation; verify_pieces itself is never mocked.
        response = self.business_response(self.plan, node, envelope)
        products.verify_pieces(self.plan, node, response["candidate_pieces"])
        long_pieces = deepcopy(response["candidate_pieces"])
        flow_piece = next(piece for piece in long_pieces if piece["slot_id"] == "A:definitions.flows")
        full_original_flow = json.loads(flow_piece["value_json"])
        full_original_flow[0]["graph"]["nodes"][0]["responsibility"] += " Full original responsibility." * 1000
        flow_piece["value_json"] = json.dumps(full_original_flow, ensure_ascii=False, separators=(",", ":"))
        self.assertGreater(len(flow_piece["value_json"]), 16000)
        products.verify_pieces(self.plan, node, long_pieces)  # Actual original business schema, no value/body trimming.
        from jsonschema import Draft202012Validator
        value_schema = core.output_schema(envelope)["properties"]["result"]["properties"]["candidate_pieces"]["items"]["properties"]["value_json"]
        self.assertEqual(value_schema["maxLength"], 1024 * 1024)
        Draft202012Validator(value_schema).validate(flow_piece["value_json"])
        for changed in (response["candidate_pieces"][:-1], response["candidate_pieces"] + [deepcopy(response["candidate_pieces"][0])]):
            self.blocked("candidate_pieces.complete_ordered_slots", lambda: products.verify_pieces(self.plan, node, changed))
        products._business_check(deepcopy(self.content), self.context)
        bad = deepcopy(self.content)
        duplicate = deepcopy(bad["definitions"]["flows"][0])
        duplicate["observable_result"] = "Different body for the same formal kind and ID"
        bad["definitions"]["flows"].append(duplicate)
        with self.assertRaises(codec.CodecError) as caught:
            products._business_check(bad, self.context)
        self.assertIn("one proposed or selected effective owner", str(caught.exception.diagnostic.expected))

    def test_foreign_private_parent_and_foreign_piece_parent_reject(self):
        for phase, own, foreign in (("generation", "generation-B", "generation-A"),
                                    ("synthesis", "synthesis-A", "generation-B"),
                                    ("independent-review", "review-A", "synthesis-B")):
            changed = deepcopy(self.plan)
            node = next(n for n in changed["nodes"] if n["node_id"] == own)
            node["dependencies"].append(foreign)
            analysis.resign(changed, "plan_digest")
            self.blocked("candidate_view.foreign_private_parent", lambda: core.validate_plan(changed))
        with self.composition():
            core.execute_workflow(self.root, run_dir=self.run_dir, plan=self.plan)
            item = next(i for i in self.session.completed if i["node_id"] == "synthesis-A")
            node = next(n for n in self.plan["nodes"] if n["node_id"] == "synthesis-A")
            changed = deepcopy(item["result"]["response"])
            changed["candidate_pieces"][0]["parent_piece_refs"][0]["slot_id"] = "B:source_identity"
            view = requests.read_input_envelope(self.root, Path(item["result"]["binding"]["workspace"]))["candidate_contract"]
            self.blocked("candidate_piece.complete_actual_generation_parents", lambda: core.verify_response(
                self.plan, node, changed, candidate_products=item["result"]["candidate_products"], candidate_contract=view))

    def test_synthesis_revision_requires_reason_and_cannot_hide_generation_in_payload(self):
        with self.composition():
            core.execute_workflow(self.root, run_dir=self.run_dir, plan=self.plan)
            item = next(i for i in self.session.completed if i["node_id"] == "synthesis-A")
            node = next(n for n in self.plan["nodes"] if n["node_id"] == "synthesis-A")
            changed = deepcopy(item["result"]["response"])
            flow = next(p for p in changed["candidate_pieces"] if p["slot_id"] == "A:definitions.flows")
            flow["change_reason"] = ""
            view = requests.read_input_envelope(self.root, Path(item["result"]["binding"]["workspace"]))["candidate_contract"]
            self.blocked("candidate_piece.unexplained_revision", lambda: core.verify_response(
                self.plan, node, changed, candidate_products=item["result"]["candidate_products"], candidate_contract=view))
            review = next(n for n in self.plan["nodes"] if n["node_id"] == "review-A")
            tokens, prefix = self.prefix_before(review)
            envelope = core._envelope(self.root, self.plan, review, tokens, run_dir=self.run_dir)
            flow = next(s for s in envelope["candidate_products"][0]["slots"] if s["target"] == "definitions.flows")
            self.assertIsNotNone(flow["generation_value_json"])
            flow["generation_value_json"] = None
            # Re-sign internally coherent literal metadata to pretend G equalled
            # S. H can check carriage, but only the actual opaque paid prefix can
            # prove which full G text existed. The core must reject this forgery.
            flow["generation_raw_digest"] = flow["raw_digest"]
            request = requests.render_request(self.root, envelope=envelope, schema=core.output_schema(envelope),
                instruction=core.phase_instruction(review["phase"]), workspace=self.root / "logs/ci/tampered-review",
                output_reserve=review["output_reserve"])
            identity = {"protocol": core.PROTOCOL, "request_sha256": request["request_sha256"], "plan_digest": self.plan["plan_digest"],
                "node_id": review["node_id"], "phase": review["phase"], "input_measurement": request["measurement"],
                "output_reserve": review["output_reserve"], "source_hashes": core.policy_identity(self.root),
                "schema_digest": request["schema_digest"], "timeout_sec": 30,
                "input_archive_ref": requests.archive_request_inputs(self.root, request),
                "request_ref": {"path": request["prompt_path"].relative_to(self.root).as_posix(), "schema_version": "newrouge.b-route-segmented-prompt.v1", "raw_digest": analysis.raw_sha(request["prompt_path"].read_bytes())},
                "schema_ref": {"path": request["schema_path"].relative_to(self.root).as_posix(), "schema_version": "newrouge.b-route-segmented-output-schema.v1", "raw_digest": analysis.raw_sha(request["schema_path"].read_bytes())}}
            self.blocked("request_identity.full_current_envelope", lambda: core.validate_request_identity(
                self.root, self.plan, review, identity, request["workspace"],
                {"run_id": self.plan["run_id"], "plan_digest": self.plan["plan_digest"], "run_path": "logs/ci/native/run.json"},
                rendered_request=request, completed_prefix=prefix))

    def test_source_closure_owned_reference_and_graph_error_use_original_predicates(self):
        products._business_check(deepcopy(self.content), self.context)
        mutations = [
            (lambda c: c["requirements"][0].update(acceptance_intent="Weakened original meaning"), "preserved original acceptance_intent"),
            (lambda c: c["source_identity"]["manifest_ref"]["files"][0].update(raw_digest="sha256:" + "0" * 64), None),
            (lambda c: c["definitions"]["flows"][0]["graph"]["edges"][0]["to"].update(node_id="undeclared"), "fully resolved graph endpoint"),
            (lambda c: c["logical_references"].append({"kind": "flow", "definition_id": "FLOW", "proposed_owner_key": "foreign-owner"}), "exact selected owner identity"),
        ]
        for mutate, expected in mutations:
            bad = deepcopy(self.content)
            mutate(bad)
            with self.subTest(expected=expected), self.assertRaises(codec.CodecError) as caught:
                products._business_check(bad, self.context)
            if expected:
                self.assertIn(expected, str(caught.exception.diagnostic.expected))

    def test_bad_synthesis_graph_blocks_before_review_request_or_new_reservation(self):
        def corrupt(node, slot, piece):
            if node["phase"] == "synthesis" and slot["target"] == "definitions.flows":
                value = json.loads(piece["value_json"])
                value[0]["graph"]["edges"][0]["to"]["node_id"] = "missing-graph-node"
                piece["value_json"] = json.dumps(value, separators=(",", ":"))
                piece["change_reason"] = "Explicit attempted graph revision, not an unrecorded edit"
        self.alter_piece = corrupt
        with self.composition(), self.assertRaises(codec.CodecError) as caught:
            core.execute_workflow(self.root, run_dir=self.run_dir, plan=self.plan)
        self.assertIn("fully resolved graph endpoint", str(caught.exception.diagnostic.expected))
        self.assertEqual(len(self.session.completed), 6)
        self.assertEqual(len(self.session.reservations), 6)
        self.assertEqual(len(self.dispatched), 6)
        self.assertFalse(any(requests.read_input_envelope(self.root, Path(c["workspace"]))["phase"] == "independent-review" for c in self.dispatched))

    def test_frozen_proof_raw_order_and_dictionary_prefix_cannot_be_resigned(self):
        with self.composition():
            result = core.execute_workflow(self.root, run_dir=self.run_dir, plan=self.plan)
            proof = result["candidate_proof"]
            products.verify_proof(self.root, run_dir=self.run_dir, plan=self.plan, proof=proof)
            final = self.plan["nodes"][-1]
            _, prefix = self.prefix_before(final)
            self.blocked("prefix.genuine_factory_token", lambda: products.materials_for_node(
                self.root, self.run_dir, self.plan, final, prefix.as_dict()))
            altered = deepcopy(self.plan)
            altered["nodes"][0]["ordinal"] = 1
            analysis.resign(altered, "plan_digest")
            self.blocked("node.identity_order", lambda: products.verify_proof(self.root,
                run_dir=self.run_dir, plan=altered, proof=proof))
            first = self.session.completed[0]["result"]
            path = Path(first["binding"]["output_path"])
            path.write_bytes(path.read_bytes() + b" ")
            self.blocked("b_route_execution_output_changed", lambda: products.verify_proof(self.root,
                run_dir=self.run_dir, plan=self.plan, proof=proof))
            self.assertEqual(len(self.session.reservations), len(self.plan["nodes"]))


if __name__ == "__main__":
    unittest.main()
