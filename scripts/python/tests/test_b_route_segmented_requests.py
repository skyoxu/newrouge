"""Synthetic final-request storage/size tests, never native/model qualification.

The payload builder, token counter and post-execution owner are explicit local
fakes. Real official-wrapper/tokenizer/receipt composition belongs to Root.
"""
import copy
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


_SPEC = importlib.util.spec_from_file_location("segmented_requests_under_test",
    Path(__file__).resolve().parents[1] / "_b_route_segmented_requests.py")
requests = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(requests)


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def envelope(phase="generation", reserve=2000):
    original = "Original \u4e2d\u6587 e\u0301\r\nsource bytes.\x00"
    global_text = "Complete indivisible GLOBAL constraint.\r\n"
    value = {"schema_version": requests.ENVELOPE, "protocol": requests.PROTOCOL,
        "run_id": "synthetic-run", "plan_digest": digest(b"plan"), "manifest_digest": digest(b"manifest"),
        "node_id": "synthetic-node", "phase": phase, "ordinal": 0,
        "candidate_labels": ["A", "B", "C"], "dimensions": ["coverage", "interactions"],
        "segment_refs": [{"segment_id": "segment-1", "material_id": "source-1", "start": 0,
            "end": len(original.encode()), "raw_digest": digest(original.encode()), "order": 0,
            "parent_digest": digest(original.encode())}],
        "global_constraints": [{"material_id": "global-1", "raw_digest": digest(global_text.encode()), "text": global_text}],
        "original_segments": [{"segment_id": "segment-1", "text": original}],
        "predecessors": [{"node_id": "previous-node", "result_digest": digest(b"derived"),
            "output": {"derived_not_lossless": "DERIVED findings"}}],
        "obligations": [{"obligation_id": "obligation-1", "segment_ids": ["segment-1"],
            "dependency_ids": [], "kind": "atomic"}], "dependency_edges": [],
        "output_reserve": reserve, "final": False, "candidate_contract": None, "candidate_products": []}
    value["citation_catalog"] = copy.deepcopy(value["segment_refs"]) + [{"segment_id": "global-segment",
        "material_id": "global-1", "start": 0, "end": len(global_text.encode()),
        "raw_digest": digest(global_text.encode()), "order": 0, "parent_digest": digest(global_text.encode())}]
    return value


class SegmentedRequestTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="sr23-")).absolute()
        self.addCleanup(self.cleanup_owned_temp)
        self.root = self.temp / "project"
        self.root.mkdir()
        self.serial = 0
        self.payload_patch = patch.object(requests, "_model_prompt", side_effect=self.visible_workspace)
        self.payload = self.payload_patch.start()
        self.addCleanup(self.payload_patch.stop)
        self.counter_patch = patch.object(requests, "_measure", side_effect=self.report)
        self.counter = self.counter_patch.start()
        self.addCleanup(self.counter_patch.stop)

    def cleanup_owned_temp(self):
        outcome = getattr(self, "_outcome", None)
        result = getattr(outcome, "result", None)
        if result is not None and any(test is self for test, _ in result.failures + result.errors):
            return
        base = Path(tempfile.gettempdir()).resolve()
        target = self.temp.resolve()
        if target.parent != base or not target.name.startswith("sr23-"):
            raise AssertionError("Unexpected owned TEMP cleanup target")
        shutil.rmtree(target)

    def workspace(self):
        self.serial += 1
        return self.root / "logs" / "ci" / "synthetic-run" / "q" / str(self.serial)

    def visible_workspace(self, workspace, prompt_path, output_path):
        self.assertEqual(prompt_path, workspace / "prompt.txt")
        self.assertEqual(output_path, workspace / "output.json")
        return "SYNTHETIC WORKSPACE BUILDER\n" + "\n".join(
            (workspace / name).read_text(encoding="utf-8") for name in
            ("prompt.txt", "input.json", "output-schema.json"))

    def report(self, request, reserve, *, tokens=None):
        raw = request.encode("utf-8")
        counter, counts = "utf8_byte_upper_bound", {}
        if tokens is None:
            tokens = len(raw)
        else:
            count = tokens * 10 // 11
            while (count * 11 + 9) // 10 < tokens:
                count += 1
            self.assertEqual((count * 11 + 9) // 10, tokens)
            counts = {"o200k_base": count, "cl100k_base": count}
            counter = "max(o200k_base,cl100k_base)+10_percent"
        return {"request_sha256": digest(raw), "request_chars": len(request), "request_bytes": len(raw),
            "input_token_estimate": tokens, "token_counts": counts, "token_counter": counter,
            "max_bytes": requests.MAX_REQUEST_BYTES, "max_input_tokens": 96000,
            "reserved_continuation_tokens": reserve, "truncation_allowed": False}

    def render(self, value=None, *, workspace=None, reserve=2000):
        return requests.render_request(self.root, envelope=envelope(reserve=reserve) if value is None else value,
            schema={"type": "object", "description": "Complete SCHEMA text", "properties": {}},
            instruction="Complete INSTRUCTION text", workspace=self.workspace() if workspace is None else workspace,
            output_reserve=reserve)

    def archive(self):
        request = self.render(workspace=self.workspace() / "m")
        reference = requests.archive_request_inputs(self.root, request)
        value = requests.read_input_envelope(self.root, request["workspace"])
        identity = {"protocol": requests.PROTOCOL, "plan_digest": value["plan_digest"],
            "node_id": value["node_id"], "phase": value["phase"], "request_sha256": request["request_sha256"],
            "input_measurement": request["measurement"], "output_reserve": value["output_reserve"],
            "source_hashes": {"fixture": "SYNTHETIC OWNER, NOT QUALIFICATION"},
            "schema_digest": request["schema_digest"], "timeout_sec": 120, "input_archive_ref": reference,
            "request_ref": {"path": request["prompt_path"].relative_to(self.root).as_posix(),
                "schema_version": "newrouge.b-route-segmented-prompt.v1", "raw_digest": digest(request["prompt_path"].read_bytes())},
            "schema_ref": {"path": request["schema_path"].relative_to(self.root).as_posix(),
                "schema_version": "newrouge.b-route-segmented-output-schema.v1", "raw_digest": digest(request["schema_path"].read_bytes())}}
        return request, reference, identity

    def test_all_four_phases_measure_complete_final_wrapper_and_original_bytes(self):
        for phase in ("generation", "synthesis", "independent-review", "selection"):
            with self.subTest(phase=phase):
                before = self.counter.call_count
                value = envelope(phase)
                request = self.render(value)
                self.assertEqual(self.counter.call_count, before + 1)
                final = json.loads(request["full_request"])
                self.assertEqual(final["prompt"], request["model_prompt"])
                self.assertEqual(final["output_schema"]["description"], "Complete SCHEMA text")
                for marker in ("INSTRUCTION", "SCHEMA", "GLOBAL", "DERIVED", phase):
                    self.assertIn(marker, request["full_request"])
                self.assertEqual(requests.read_input_envelope(self.root, request["workspace"]), value)
                self.assertEqual(request["request_sha256"], digest(request["full_request"].encode()))
                self.assertIsNone(requests.verify_rendered_request(self.root, request))

    def test_input_70000_and_total_96000_are_separate_exact_limits(self):
        for tokens, reserve, accepted, diagnostic in [(70000, 26000, True, ""),
                (70001, 2000, False, "input_over_70000"),
                (70000, 26001, False, "input_plus_output_over_96000")]:
            with self.subTest(tokens=tokens, reserve=reserve):
                self.counter.side_effect = lambda text, out, count=tokens: self.report(text, out, tokens=count)
                if accepted:
                    request = self.render(reserve=reserve)
                    self.assertEqual(request["measurement"]["input_token_estimate"], 70000)
                else:
                    with self.assertRaisesRegex(ValueError, diagnostic):
                        self.render(reserve=reserve)

    def test_wrong_measurement_identity_types_counts_and_reserve_are_rejected(self):
        for mutation in ("request_sha256", "input_token_estimate", "reserved_continuation_tokens", "token_counts"):
            def measure(text, reserve, field=mutation):
                report = self.report(text, reserve)
                report[field] = {"request_sha256": digest(b"other"), "input_token_estimate": True,
                    "reserved_continuation_tokens": reserve + 1, "token_counts": {"unexpected": 1}}[field]
                return report
            self.counter.side_effect = measure
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "measurement"):
                self.render()

    def test_range_digest_type_order_and_unknown_fields_fail_before_io(self):
        for mutation in ("range", "digest", "ordinal-bool", "final-phase", "unknown-field", "missing-original"):
            value = envelope()
            if mutation == "range":
                value["segment_refs"][0]["end"] -= 1
            elif mutation == "digest":
                value["global_constraints"][0]["text"] += "changed"
            elif mutation == "ordinal-bool":
                value["ordinal"] = False
            elif mutation == "final-phase":
                value["final"] = True
            elif mutation == "unknown-field":
                value["unbound"] = "extra"
            else:
                value["original_segments"] = []
            before = self.counter.call_count
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.render(value)
            self.assertEqual(self.counter.call_count, before)

    def test_foreign_and_sensitive_locators_reject_before_filesystem_io(self):
        locations = [self.temp / "foreign", self.root / "logs" / "ci" / ".env" / "request",
            self.root / "logs" / "ci" / "auth.json" / "request",
            self.root / "logs" / "ci" / "archived_sessions" / "request"]
        for location in locations:
            with self.subTest(location=location), patch.object(Path, "lstat", side_effect=AssertionError("Unexpected filesystem IO")):
                with self.assertRaises(ValueError):
                    self.render(workspace=location)

    def test_existing_workspace_is_never_overwritten_or_implicitly_resumed(self):
        workspace = self.workspace()
        workspace.mkdir(parents=True)
        sentinel = workspace / "sentinel.txt"
        sentinel.write_bytes(b"existing evidence")
        with self.assertRaisesRegex(ValueError, "workspace_already_exists"):
            self.render(workspace=workspace)
        self.assertEqual(sentinel.read_bytes(), b"existing evidence")
        self.assertEqual(self.counter.call_count, 0)

    def test_unknown_member_is_rejected_before_any_content_read(self):
        request = self.render()
        (request["workspace"] / "unknown.bin").write_bytes(b"synthetic unknown evidence")
        with patch.object(requests, "_read_plain", side_effect=AssertionError("Unknown content was opened")):
            with self.assertRaisesRegex(ValueError, "unexpected_workspace_member"):
                requests.verify_rendered_request(self.root, request)

    def test_input_content_and_same_byte_file_replacement_invalidate_token(self):
        request = self.render()
        path = request["schema_path"]
        raw = path.read_bytes()
        replacement = path.with_name("replacement.tmp")
        replacement.write_bytes(raw)
        replacement.replace(path)
        with self.assertRaisesRegex(ValueError, "input_changed"):
            requests.verify_rendered_request(self.root, request)
        request = self.render()
        request["prompt_path"].write_bytes(b"changed instruction")
        with self.assertRaisesRegex(ValueError, "input_changed"):
            requests.verify_rendered_request(self.root, request)

    def test_opaque_token_cannot_be_reconstructed_from_public_mapping(self):
        request = self.render()
        for fake in (dict(request), object.__new__(requests.RenderedRequest)):
            with self.subTest(fake_type=type(fake)), self.assertRaisesRegex(ValueError, "request_not_issued"):
                requests.verify_rendered_request(self.root, fake)
        changed = request["measurement"]
        changed["input_token_estimate"] = 0
        self.assertNotEqual(request["measurement"]["input_token_estimate"], 0)
        self.assertIsNone(requests.verify_rendered_request(self.root, request))

    def test_final_is_derived_conclusion_not_an_original_source_exemption(self):
        value = envelope("selection")
        value["final"] = True
        # The core, not this storage boundary, must prove whether this closure is sufficient.
        request = self.render(value)
        self.assertIn("Complete indivisible GLOBAL", request["full_request"])
        self.assertIn("segment-1", request["full_request"])
        value["segment_refs"] = []
        with self.assertRaisesRegex(ValueError, "segment_order_or_coverage"):
            self.render(value)

    def test_post_execution_closing_consumes_only_typed_fixed_owner_grant(self):
        request = self.render()
        workspace = request["workspace"]
        names = {"output.json": b'{"synthetic":true}', "runner-input-integrity.json": b'{"synthetic":true}',
            "output.json.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.app-server.jsonl": b'{"synthetic":true}\r\n',
            "output.json.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.app-server.stderr.txt": b"synthetic diagnostics"}
        for name, raw in names.items():
            (workspace / name).write_bytes(raw)
        class FakeAlreadyVerifiedClose:
            pass
        grant = FakeAlreadyVerifiedClose()
        def verify(root, value, *, workspace):
            if type(value) is not FakeAlreadyVerifiedClose:
                raise ValueError("synthetic owner rejects forged close")
            return {"files": {name: digest(raw) for name, raw in names.items()},
                "request_sha256": request["request_sha256"], "binding_digest": digest(b"synthetic binding"),
                "output_digest": digest(names["output.json"]), "receipt_digest": digest(b"synthetic receipt")}
        fake_owner = types.SimpleNamespace(verify_execution_close=verify)
        # This stub tests the renderer's storage seam, never official execution authority.
        with patch.dict(sys.modules, {"_b_route_segmented_workflow": fake_owner}):
            closed = requests.verify_rendered_request(self.root, request, execution_close=grant)
            self.assertEqual(set(closed["files"]), set(names))
            with self.assertRaisesRegex(ValueError, "rejects forged close"):
                requests.verify_rendered_request(self.root, request, execution_close={})
            (workspace / "unknown-sidecar.txt").write_bytes(b"ungranted")
            with self.assertRaisesRegex(ValueError, "unexpected_workspace_member"):
                requests.verify_rendered_request(self.root, request, execution_close=grant)

    def test_citation_catalog_is_metadata_not_a_missing_source_exemption(self):
        for mutation in ("duplicate", "missing-ref", "different-ref", "split-global", "bool-range"):
            value = envelope()
            if mutation == "duplicate":
                value["citation_catalog"].append(copy.deepcopy(value["citation_catalog"][0]))
            elif mutation == "missing-ref":
                value["citation_catalog"].pop(0)
            elif mutation == "different-ref":
                value["citation_catalog"][0]["parent_digest"] = digest(b"other parent")
            elif mutation == "split-global":
                value["citation_catalog"][1]["end"] -= 1
            else:
                value["citation_catalog"][0]["start"] = False
            before = self.counter.call_count
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.render(value)
            self.assertEqual(self.counter.call_count, before)

    def test_generated_candidate_slot_originals_are_carried_without_normalizing_raw_json(self):
        value = envelope("independent-review")
        raw = ' [ {"id":"generated-1", "types":[true,1,1.0], "text":"original candidate"} ]\r\n'
        value["candidate_contract"] = {"slots": ["slot-1"], "host_metadata_only": True}
        value["candidate_products"] = [{"candidate_label": "A",
            "candidate_id": requests._identity({"plan_digest": value["plan_digest"], "blind_label": "A"}), "stage": "assembled-original",
            "content_digest": digest(b"synthetic complete candidate"),
            "slots": [{"slot_id": "slot-1", "target": "definitions.flows", "value_json": raw,
                "raw_digest": digest(raw.encode()), "generation_value_json": None,
                "generation_raw_digest": digest(raw.encode()), "generation_result_digest": digest(b"synthetic G"),
                "synthesis_result_digest": digest(b"synthetic S")}],
            "object_domain": {"ids": ["generated-1"], "edges": []}, "review_result_digests": []}]
        request = self.render(value)
        restored = requests.read_input_envelope(self.root, request["workspace"])
        self.assertEqual(restored, value)
        self.assertEqual(restored["candidate_products"][0]["slots"][0]["value_json"], raw)
        self.assertIn("definitions.flows", request["full_request"])
        self.assertIn("original candidate", request["full_request"])
        fragments = copy.deepcopy(value)
        fragments["phase"] = "generation"
        fragments["candidate_products"][0]["stage"] = "generation-fragments"
        fragments["candidate_products"][0]["content_digest"] = None
        fragments["candidate_products"][0]["slots"][0]["synthesis_result_digest"] = None
        fragment_request = self.render(fragments)
        self.assertEqual(requests.read_input_envelope(self.root, fragment_request["workspace"]), fragments)
        synthesis = copy.deepcopy(fragments)
        synthesis["phase"] = "synthesis"
        synthesis["candidate_products"][0]["stage"] = "synthesis-inputs"
        original_g = ' [ {"id":"dependency-G", "complete":true} ]\r\n'
        current_s = '[{"id":"dependency-S","complete":true}]'
        synthesis["candidate_products"][0]["slots"].append({"slot_id": "dependency-slot", "target": "definitions.flows",
            "value_json": current_s, "raw_digest": digest(current_s.encode()),
            "generation_value_json": original_g, "generation_raw_digest": digest(original_g.encode()),
            "generation_result_digest": digest(b"dependency G"), "synthesis_result_digest": digest(b"accepted dependency S")})
        synthesis_request = self.render(synthesis)
        self.assertEqual(requests.read_input_envelope(self.root, synthesis_request["workspace"]), synthesis)
        self.assertIn("dependency-G", synthesis_request["full_request"])
        self.assertIn("dependency-S", synthesis_request["full_request"])

    def test_candidate_product_metadata_raw_digest_and_strict_json_are_closed(self):
        baseline = envelope("independent-review")
        baseline["candidate_products"] = [{"candidate_label": "A",
            "candidate_id": requests._identity({"plan_digest": baseline["plan_digest"], "blind_label": "A"}),
            "stage": "assembled-original", "content_digest": digest(b"candidate"),
            "slots": [{"slot_id": "slot-1", "target": "definitions.flows", "value_json": '[{"id":"x"}]',
                "raw_digest": digest(b'[{"id":"x"}]'), "generation_value_json": None,
                "generation_raw_digest": digest(b'[{"id":"x"}]'), "generation_result_digest": digest(b"G"),
                "synthesis_result_digest": digest(b"S")}], "object_domain": {}, "review_result_digests": []}]
        # Establish a valid full literal baseline before testing each rejection.
        self.render(baseline)
        for mutation in ("candidate-duplicate", "slot-duplicate", "raw-drift", "duplicate-json-key",
                         "truncated-json", "nonfinite-json", "slot-extra", "foreign-label", "assembled-null-digest"):
            value = copy.deepcopy(baseline)
            row = value["candidate_products"][0]
            slot = row["slots"][0]
            if mutation == "candidate-duplicate":
                value["candidate_products"].append(copy.deepcopy(row))
            elif mutation == "slot-duplicate":
                row["slots"].append(copy.deepcopy(slot))
            elif mutation == "raw-drift":
                slot["value_json"] += " "
            elif mutation in ("duplicate-json-key", "truncated-json", "nonfinite-json"):
                slot["value_json"] = {"duplicate-json-key": '{"id":1,"id":2}',
                    "truncated-json": "[", "nonfinite-json": "NaN"}[mutation]
                slot["raw_digest"] = digest(slot["value_json"].encode())
            elif mutation == "slot-extra":
                slot["unbound"] = True
            elif mutation == "foreign-label":
                row["candidate_label"] = "not-a-blind-candidate"
            else:
                row["content_digest"] = None
            before = self.counter.call_count
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.render(value)
            self.assertEqual(self.counter.call_count, before)

    def test_changed_synthesis_preserves_exact_full_generation_json(self):
        original = ' [ {"id":"G", "types":[true,1,1.0]} ]\r\n'
        current = '[{"id":"S","types":[true,1,1.0]}]'
        value = envelope("independent-review")
        value["candidate_products"] = [{"candidate_label": "A",
            "candidate_id": requests._identity({"plan_digest": value["plan_digest"], "blind_label": "A"}),
            "stage": "assembled-original", "content_digest": digest(b"assembled candidate"),
            "slots": [{"slot_id": "slot-1", "target": "definitions.flows", "value_json": current,
                "raw_digest": digest(current.encode()), "generation_value_json": original,
                "generation_raw_digest": digest(original.encode()), "generation_result_digest": digest(b"G result"),
                "synthesis_result_digest": digest(b"S result")}], "object_domain": {}, "review_result_digests": []}]
        request = self.render(value)
        observed = requests.read_input_envelope(self.root, request["workspace"])
        slot = observed["candidate_products"][0]["slots"][0]
        self.assertEqual(slot["generation_value_json"], original)
        self.assertEqual(slot["value_json"], current)
        self.assertEqual(slot["generation_raw_digest"], digest(original.encode()))
        self.assertEqual(slot["raw_digest"], digest(current.encode()))

    def test_missing_mixed_or_tampered_generation_and_synthesis_carriage_rejected(self):
        original, current = '[{"id":"G"}]\r\n', '[{"id":"S"}]'
        baseline = envelope("synthesis")
        baseline["candidate_products"] = [{"candidate_label": "A",
            "candidate_id": requests._identity({"plan_digest": baseline["plan_digest"], "blind_label": "A"}),
            "stage": "synthesis-inputs", "content_digest": None,
            "slots": [{"slot_id": "slot-1", "target": "definitions.flows", "value_json": current,
                "raw_digest": digest(current.encode()), "generation_value_json": original,
                "generation_raw_digest": digest(original.encode()), "generation_result_digest": digest(b"G result"),
                "synthesis_result_digest": digest(b"S result")}], "object_domain": {}, "review_result_digests": []}]
        self.render(baseline)
        cases = {"missing-field": "candidate_slot_fields", "missing-original": "changed_slot_missing_generation_json",
            "original-tamper": "candidate_generation_raw_binding", "current-tamper": "candidate_slot_raw_binding",
            "unknown-generation-digest": "candidate_generation_raw_binding", "unsynthesized-change": "unsynthesized_slot_changed_generation",
            "generation-with-synthesis": "generation_fragment_has_synthesis", "phase-stage-mix": "candidate_product_stage",
            "unassembled-has-content": "unassembled_candidate_content_digest", "blind-candidate-mix": "candidate_product_identity"}
        for mutation, diagnostic in cases.items():
            value = copy.deepcopy(baseline)
            row = value["candidate_products"][0]
            slot = row["slots"][0]
            if mutation == "missing-field":
                slot.pop("generation_value_json")
            elif mutation == "missing-original":
                slot["generation_value_json"] = None
            elif mutation == "original-tamper":
                slot["generation_value_json"] += " "
            elif mutation == "current-tamper":
                slot["value_json"] += " "
            elif mutation == "unknown-generation-digest":
                slot["generation_raw_digest"] = digest(b"another G")
            elif mutation == "unsynthesized-change":
                slot["synthesis_result_digest"] = None
            elif mutation == "generation-with-synthesis":
                value["phase"] = "generation"
                row["stage"] = "generation-fragments"
            elif mutation == "phase-stage-mix":
                value["phase"] = "independent-review"
            elif mutation == "unassembled-has-content":
                row["content_digest"] = digest(b"not assembled")
            else:
                row["candidate_label"] = "B"
            before = self.counter.call_count
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, diagnostic):
                self.render(value)
            self.assertEqual(self.counter.call_count, before)

    def test_permanent_archive_cold_rebuilds_exact_request_without_render_token(self):
        request, reference, identity = self.archive()
        workspace = request["workspace"]
        expected = request["full_request"]
        archive = workspace.parent / "i"
        self.assertEqual({p.name for p in archive.iterdir()}, set(requests._INPUT_NAMES))
        self.assertEqual({p.name for p in workspace.iterdir()}, set(requests._INPUT_NAMES))
        self.assertEqual(reference["path"], (workspace.parent / "input-archive.json").relative_to(self.root).as_posix())
        for name in requests._INPUT_NAMES:
            self.assertEqual((archive / name).read_bytes(), (workspace / name).read_bytes())
        del request
        gc.collect()
        observed = requests.verify_request_archive(self.root, archive_ref=reference,
            workspace=workspace, request_identity=identity)
        self.assertEqual(observed["full_request"], expected)
        self.assertEqual(observed["request_sha256"], identity["request_sha256"])
        self.assertEqual(observed["paths"], {"workspace": workspace, "prompt_path": workspace / "prompt.txt",
            "schema_path": workspace / "output-schema.json", "output_path": workspace / "output.json"})
        self.assertEqual(self.counter.call_count, 1)  # No new model call or token estimate on cold reconstruction.

    def test_archive_never_overwrites_and_rejects_extra_archive_members(self):
        request, reference, identity = self.archive()
        manifest = self.root / reference["path"]
        raw = manifest.read_bytes()
        with self.assertRaisesRegex(ValueError, "input_archive_already_exists"):
            requests.archive_request_inputs(self.root, request)
        self.assertEqual(manifest.read_bytes(), raw)
        (request["workspace"].parent / "i" / "unknown.txt").write_bytes(b"synthetic unexpected content")
        with self.assertRaisesRegex(ValueError, "archive_not_input_only"):
            requests.verify_request_archive(self.root, archive_ref=reference,
                workspace=request["workspace"], request_identity=identity)

    def test_archive_leaves_real_sidecars_in_place_and_never_feeds_them_to_model(self):
        request, reference, identity = self.archive()
        workspace = request["workspace"]
        files = {"output.json": b'{"synthetic":true}', "runner-input-integrity.json": b'{"synthetic":true}',
            "output.json.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.app-server.jsonl": b"HOST_ONLY_SYNTHETIC_PROTOCOL\r\n",
            "output.json.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.app-server.stderr.txt": b"HOST_ONLY_DIAGNOSTICS"}
        for name, raw in files.items():
            (workspace / name).write_bytes(raw)
        before = {name: (workspace / name).read_bytes() for name in files}
        observed = requests.verify_request_archive(self.root, archive_ref=reference,
            workspace=workspace, request_identity=identity)
        self.assertEqual(observed["full_request"], request["full_request"])
        self.assertFalse("HOST_ONLY" in observed["model_prompt"])
        self.assertEqual(set(observed["workspace_members"]), set(requests._INPUT_NAMES) | set(files))
        self.assertEqual(before, {name: (workspace / name).read_bytes() for name in files})
        # Input observation is deliberately not an output authorization.
        with self.assertRaisesRegex(ValueError, "unexpected_workspace_member"):
            requests.verify_rendered_request(self.root, request)

    def test_archive_rejects_original_claim_wrapper_schema_measurement_and_path_substitution(self):
        request, reference, original = self.archive()
        requests.verify_request_archive(self.root, archive_ref=reference,
            workspace=request["workspace"], request_identity=original)
        for mutation in ("wrapper", "schema", "measurement", "prompt-path", "schema-raw", "reserve", "archive-ref"):
            identity = copy.deepcopy(original)
            if mutation == "wrapper":
                identity["request_sha256"] = digest(b"other actual wrapper")
            elif mutation == "schema":
                identity["schema_digest"] = digest(b"other schema")
            elif mutation == "measurement":
                identity["input_measurement"]["request_sha256"] = digest(b"other measurement")
            elif mutation == "prompt-path":
                identity["request_ref"]["path"] = "logs/ci/other/prompt.txt"
            elif mutation == "schema-raw":
                identity["schema_ref"]["raw_digest"] = digest(b"other bytes")
            elif mutation == "reserve":
                identity["output_reserve"] += 1
            else:
                identity["input_archive_ref"]["raw_digest"] = digest(b"other archive")
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "archive_claim"):
                requests.verify_request_archive(self.root, archive_ref=reference,
                    workspace=request["workspace"], request_identity=identity)
        other = request["workspace"].with_name("other-m")
        other.mkdir()
        for name in requests._INPUT_NAMES:
            (other / name).write_bytes((request["workspace"] / name).read_bytes())
        with self.assertRaisesRegex(ValueError, "archive_claim_input_path_or_bytes"):
            requests.verify_request_archive(self.root, archive_ref=reference,
                workspace=other, request_identity=original)

    def test_archive_and_actual_input_tampering_cannot_be_rebound_after_claim(self):
        request, reference, identity = self.archive()
        workspace = request["workspace"]
        targets = [workspace / "input.json", workspace.parent / "i" / "input.json"]
        for target in targets:
            old = target.read_bytes()
            target.write_bytes(old + b" ")
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "archive_original_input_bytes_changed"):
                requests.verify_request_archive(self.root, archive_ref=reference,
                    workspace=workspace, request_identity=identity)
            target.write_bytes(old)
        manifest = self.root / reference["path"]
        old = manifest.read_bytes()
        manifest.write_bytes(old + b" ")
        with self.assertRaisesRegex(ValueError, "archive_manifest_raw_binding"):
            requests.verify_request_archive(self.root, archive_ref=reference,
                workspace=workspace, request_identity=identity)

    def test_archive_wrong_sensitive_locator_rejects_before_metadata_or_content_io(self):
        request, reference, identity = self.archive()
        wrong = {**reference, "path": "logs/ci/archived_sessions/auth.json"}
        identity["input_archive_ref"] = wrong
        with patch.object(Path, "lstat", side_effect=AssertionError("Unexpected filesystem IO")):
            with self.assertRaisesRegex(ValueError, "archive_reference_locator"):
                requests.verify_request_archive(self.root, archive_ref=wrong,
                    workspace=request["workspace"], request_identity=identity)


    def test_fixed_v2_wire_preserves_order_types_unicode_and_exact_full_wrapper(self):
        value = envelope()
        value["candidate_contract"] = {"ordered": {"z": [True, 1, 1.0, -0.0], "a": "\u4e2d\u6587\r\n\x00e\u0301"},
            "complete_original": "Repeated original body. " * 8}
        encoded = requests.encode_input_envelope(value)
        self.assertEqual(set(encoded), {"schema_version", "codec", "original_json_raw_digest", "literal"})
        self.assertEqual(encoded["schema_version"], requests.INPUT_WIRE)
        self.assertEqual(encoded["codec"], "newrouge.b-route-compact-literal.v2")
        self.assertEqual(encoded["original_json_raw_digest"], digest(requests._json_text(value).encode("utf-8")))
        restored = requests.decode_input_envelope(encoded)
        self.assertEqual(requests._json_text(restored), requests._json_text(value))
        request = self.render(value)
        workspace = request["workspace"]
        self.assertEqual((workspace / "input.json").read_bytes(), (requests._json_text(encoded) + "\n").encode("utf-8"))
        self.assertEqual((workspace / "prompt.txt").read_bytes(),
            requests.wire_instruction("Complete INSTRUCTION text").encode("utf-8"))
        self.assertEqual((workspace / "prompt.txt").read_text(encoding="utf-8").count("Complete INSTRUCTION text"), 1)
        self.assertIn(requests._input_codec().instruction(requests.INPUT_CODEC), request["model_prompt"])
        self.assertEqual(self.counter.call_args.args[0], request["full_request"])
        self.assertEqual(requests._json_text(requests.read_input_envelope(self.root, workspace)), requests._json_text(value))

    def test_wire_rejects_other_codecs_raw_fallback_missing_fields_and_executable_literal(self):
        valid = requests.encode_input_envelope(envelope())
        codec = requests._input_codec()
        attacks = []
        for version in ("newrouge.b-route-compact-literal.v1", "newrouge.b-route-compact-literal.v3"):
            declared = copy.deepcopy(valid)
            declared["codec"] = version
            attacks.append((declared, "input_wire_identity"))
            hidden = copy.deepcopy(valid)
            hidden["literal"] = hidden["literal"].replace(requests.INPUT_CODEC, version, 1)
            attacks.append((hidden, "input_literal_version"))
        for field in valid:
            missing = copy.deepcopy(valid)
            del missing[field]
            attacks.append((missing, "input_wire_fields"))
        extra = {**valid, "raw_fallback": envelope()}
        attacks += [(extra, "input_wire_fields"), (envelope(), "input_wire_fields"),
            (dict(reversed(list(valid.items()))), "input_wire_order"),
            ({**valid, "literal": "__import__('must_never_import')"}, "input_literal_version")]
        for value, error in attacks:
            with self.subTest(error=error), patch.object(codec, "loads", side_effect=AssertionError("wrong codec entered")) as load:
                with self.assertRaisesRegex(ValueError, error):
                    requests.decode_input_envelope(value)
                load.assert_not_called()

    def test_wire_requires_exact_ordered_logical_digest_and_canonical_literal(self):
        value = envelope()
        valid = requests.encode_input_envelope(value)
        changed = requests.encode_input_envelope(dict(reversed(list(value.items()))))
        changed["original_json_raw_digest"] = valid["original_json_raw_digest"]
        with self.assertRaisesRegex(ValueError, "input_original_json_binding"):
            requests.decode_input_envelope(changed)
        with self.assertRaisesRegex(ValueError, "Noncanonical compact literal packet"):
            requests.decode_input_envelope({**valid, "literal": valid["literal"] + " "})
        with self.assertRaisesRegex(ValueError, "input_original_json_binding"):
            requests.decode_input_envelope({**valid, "original_json_raw_digest": digest(b"wrong original")})
        # A self-consistent transport still cannot waive the existing logical
        # envelope's complete original segment/body binding.
        broken = copy.deepcopy(value)
        broken["original_segments"][0]["text"] += "hidden change"
        literal = requests._input_codec().dumps(broken, schema=requests.INPUT_CODEC)
        with self.assertRaisesRegex(ValueError, "segment_bytes_binding"):
            requests.decode_input_envelope({**valid, "literal": literal,
                "original_json_raw_digest": digest(requests._json_text(broken).encode("utf-8"))})

    def test_fixed_input_reader_rejects_duplicate_nonfinite_extra_and_noncanonical_json(self):
        request = self.render()
        path = request["workspace"] / "input.json"
        raw = path.read_bytes()
        value = json.loads(raw)
        attacks = [(raw[:-2] + b',"codec":"duplicate"}\n', "duplicate_input_json_key"),
            (requests._json_text({**value, "extra": 1}).encode() + b"\n", "input_wire_fields"),
            (b'{"schema_version":NaN}\n', "nonfinite_input_json"),
            (raw[:-1], "input_wire_noncanonical_json"),
            (raw + b"\n", "input_wire_noncanonical_json"),
            (json.dumps(value, ensure_ascii=False, indent=2).encode() + b"\n", "input_wire_noncanonical_json")]
        for data, error in attacks:
            path.write_bytes(data)
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                requests.read_input_envelope(self.root, request["workspace"])
        path.write_bytes(raw)
        self.assertEqual(requests.read_input_envelope(self.root, request["workspace"]), envelope())

    def test_fixed_input_reader_never_reads_sidecars_and_closes_actual_input_bytes(self):
        request = self.render()
        workspace = request["workspace"]
        sidecar = workspace / "auth.json"
        sidecar.write_text("SYNTHETIC UNREAD SENTINEL", encoding="utf-8")
        original = requests._read_plain
        with patch.object(requests, "_read_plain", wraps=original) as observed:
            self.assertEqual(requests.read_input_envelope(self.root, workspace), envelope())
        self.assertEqual([call.args[0] for call in observed.call_args_list], [workspace / "input.json"] * 2)
        raw = (workspace / "input.json").read_bytes()
        reads = []
        def drift(path):
            answer = original(path)
            reads.append(path)
            if len(reads) == 1:
                path.write_bytes(raw + b" ")
            return answer
        with patch.object(requests, "_read_plain", side_effect=drift), self.assertRaisesRegex(ValueError, "input_changed_during_read"):
            requests.read_input_envelope(self.root, workspace)
        with patch.object(Path, "lstat", side_effect=AssertionError("unsafe locator touched")), \
             patch.object(Path, "read_bytes", side_effect=AssertionError("unsafe content touched")):
            with self.assertRaisesRegex(ValueError, "sensitive_or_invalid_path_role"):
                requests.read_input_envelope(self.root, self.root / "logs/ci/archived_sessions")


if __name__ == "__main__":
    unittest.main()
