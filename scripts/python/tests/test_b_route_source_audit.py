"""Synthetic orchestration contracts; these tests do not prove model semantics."""
import contextlib
import ctypes
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import concurrent.futures
import base64
import hashlib
from types import SimpleNamespace
from copy import deepcopy
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_source_audit as audit
import _b_route_sources as sources
import _b_route_codec as codec
from test_b_route_sources import SourceAccountingTests


class SourceAuditTests(SourceAccountingTests):
    # Inherit fixture helpers only; inherited Story 2.1 methods run in their own suite.
    def setUp(self):
        super().setUp()
        fixture = Path(__file__).parent / "fixtures/b_route_audit_synthetic_runner.py"
        self.fixture = fixture.read_text(encoding="utf-8").replace("CODE_ROOT = None",
            "CODE_ROOT = " + repr(str(Path(audit.__file__).parent)))
        self.runner = "runner.py"
        self.put(self.runner, self.fixture.encode("utf-8"))

    def mode(self, value):
        self.put(self.runner, self.fixture.replace('MODE = "clean"', 'MODE = ' + repr(value)).encode("utf-8"))

    def accounted(self, attempt="base", disposition=None):
        prepared = self.prepare(attempt)
        self.candidate(prepared, disposition=disposition)
        code, report = self.account(prepared, attempt)
        self.assertEqual(code, 1 if disposition == "unresolved" else 0, report)
        return report, prepared

    def audit(self, report, attempt="audit", extras=(), **kwargs):
        return self.invoke("audit", attempt, ["--accounted", report["output_ref"] + "/report.json",
            "--runner", self.runner, "--expected-model", "synthetic/source-audit-v1", *extras], **kwargs)

    def verify(self, report, attempt="verify", extras=(), **kwargs):
        return self.invoke("verify", attempt, ["--audit-ref", report["output_ref"] + "/report.json",
            "--runner", self.runner, "--expected-model", "synthetic/source-audit-v1", *extras], **kwargs)

    def test_complete_zero_task_os_lifecycle_verify_and_exact_replay(self):
        account, _ = self.accounted()
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        code, report = self.audit(account)
        self.assertEqual(code, 0, report)
        self.assertTrue(report["execution_complete"])
        self.assertFalse(report["planning_eligible"], "Synthetic evidence cannot grant real planning eligibility")
        self.assertEqual(report["evidence_class"], "synthetic")
        self.assertEqual(report["runner_dispatch_count"], 2)
        self.assertEqual(report["model_dispatch_count"], 0)
        self.assertEqual(report["synthetic_dispatch_count"], 2)
        self.assertFalse((self.root / ".taskmaster").exists())
        for path, raw in before.items():
            self.assertEqual((self.root / path).read_bytes(), raw)
        code, verified = self.verify(report)
        self.assertEqual(code, 0, verified)
        self.assertEqual(verified["runner_dispatch_count"], 0)
        code, replay = self.audit(account)
        self.assertEqual(code, 0, replay)
        self.assertEqual(report, replay)

    def test_default_citation_guidance_preserves_historical_prompt_and_request_bytes(self):
        expected_hashes = {"extract": "d296e2145ee39267fd7c1a10a23df4e27d98fd338638fef65d9bb80588bf6973",
                           "compare": "e267dcfa3c6510c01ae016d0f645e560bdfbafb60a4a727be5e64f0fb4a3739d"}
        account, _ = self.accounted()
        code, report = self.audit(account)
        self.assertEqual(code, 0, report)
        prefix = report["output_ref"]
        self.assertNotIn("citation_guidance", self.json(prefix + "/request.json"))
        identity = self.json(prefix + "/identity.json")
        self.assertNotIn("citation_guidance", identity)
        self.assertNotIn("producer_schema_policy", identity)
        self.assertEqual(identity["prompt_identity"], audit.canonical_sha(audit.PROMPTS))
        for phase, step in (("extract", "extract-000001"), ("compare", "compare")):
            workspace = self.root / prefix / "steps" / step / "workspace"
            raw = (workspace / "prompt.txt").read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected_hashes[phase])
            self.assertEqual(raw, (audit.PROMPTS[phase] + "\n").encode())
            request = json.loads((workspace / "input.json").read_bytes())
            self.assertEqual(set(request), {"phase", "input_identity", "payload"})
            self.assertEqual(request["input_identity"], audit.canonical_sha(request["payload"]))
            for filename in ("input.json", "schema.json"):
                value = json.loads((workspace / filename).read_bytes())
                self.assertEqual((workspace / filename).read_bytes(),
                    (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode())
        proof = audit.validate_proof(sources.Observations(self.root), prefix + "/report.json")
        self.assertTrue(proof["report"]["execution_complete"])
        self.assertEqual(self.audit(account), (code, report))

    def test_full_block_guidance_native_cli_binds_lossless_compact_payload_and_replay(self):
        raw = '# Rule\r\n\r\nKeep \"reward\" order: \u4e2d\u6587 \\ paths.  \r\n'.encode("utf-8")
        self.put("docs/source.md", raw)
        account, _ = self.accounted()
        entry = Path(__file__).resolve().parents[1] / "dev_cli.py"
        options = ["--citation-guidance", "full-block"]
        code, report = self.audit(account, extras=options, entry=entry)
        self.assertEqual(code, 0, report)
        prefix = report["output_ref"]
        self.assertEqual(self.json(prefix + "/request.json")["citation_guidance"], "full-block")
        identity = self.json(prefix + "/identity.json")
        self.assertEqual(identity["citation_guidance"], "full-block")
        self.assertEqual(identity["producer_schema_policy"], audit.PRODUCER_SCHEMA_POLICY)
        self.assertEqual(identity["producer_input_delivery"], audit.SOURCE_INPUT_CARRIER)
        self.assertEqual(report["citation_provenance"], audit.SPAN_REF_PROVENANCE)
        self.assertEqual(report["runner_dispatch_count"], 2)
        self.assertEqual(report["model_dispatch_count"], 0)
        self.assertEqual(identity["prompt_identity"], audit.producer_prompt_identity("full-block", audit.PRODUCER_SCHEMA_POLICY))
        self.assertNotEqual(identity["prompt_identity"], audit.prompt_identity())
        for phase, step in (("extract", "extract-000001"), ("compare", "compare")):
            workspace = self.root / prefix / "steps" / step / "workspace"
            actual_input = json.loads((workspace / "input.json").read_bytes())
            request = audit.decode_producer_input(actual_input, audit.PRODUCER_SCHEMA_POLICY)
            canonical_request = deepcopy(request)
            transport = canonical_request.pop("producer_transport")
            self.assertEqual(actual_input, audit.producer_input(canonical_request, audit.PRODUCER_SCHEMA_POLICY))
            self.assertEqual(transport["schema_version"], audit.SPAN_REF_COMPAT_POLICY)
            wire = json.loads((workspace / "output.json").read_bytes())
            decoded = self.json(str(workspace.parent.relative_to(self.root)) + "/canonical-output.json")
            self.assertEqual(decoded, audit.decode_producer_output(canonical_request, wire, audit.PRODUCER_SCHEMA_POLICY))
            if phase == "extract":
                self.assertEqual(set(wire["obligations"][0]["citations"][0]), {"span_ref"})
                self.assertIn("quote", decoded["obligations"][0]["citations"][0])
            self.assertEqual(request["citation_guidance"], "full-block")
            self.assertEqual(request["input_identity"], audit.canonical_sha({"payload": request["payload"], "citation_guidance": "full-block"}))
            self.assertNotEqual(request["input_identity"], audit.canonical_sha(request["payload"]))
            self.assertEqual((workspace / "prompt.txt").read_bytes(), (audit.producer_prompt(phase, "full-block", audit.PRODUCER_SCHEMA_POLICY) + "\n").encode())
            for filename in ("input.json", "schema.json"):
                visible = (workspace / filename).read_bytes()
                value = json.loads(visible)
                self.assertEqual(visible, audit.compact_model_json(value))
                pretty = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
                self.assertLess(len(visible), len(pretty))
                self.assertEqual(json.loads(visible, object_pairs_hook=list), json.loads(pretty, object_pairs_hook=list))
            files = [request["payload"]["file"]] if phase == "extract" else request["payload"]["files"]
            self.assertEqual(files[0]["text"].encode(), raw)
            self.assertEqual(base64.b64decode(files[0]["raw_base64"]), raw)
            for block in files[0]["blocks"]:
                span = block["citation_span"]
                self.assertEqual(span["quote"].encode(), raw[span["byte_start"]:span["byte_end"]])
        audit.validate_proof(sources.Observations(self.root), prefix + "/report.json")
        before = {p: p.read_bytes() for p in (self.root / prefix).rglob("*") if p.is_file()}
        self.assertEqual(self.audit(account, extras=options, entry=entry), (code, report))
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertEqual(self.verify(report, entry=entry)[0], 0, "Verification derives guidance from the audited request")
        self.assertEqual(self.audit(account)[0], 2, "An existing event cannot silently change producer mode")
        code, reused = self.audit(account, "guided-reuse", [*options, "--audit-ref", prefix + "/report.json"], entry=entry)
        self.assertEqual(code, 0, reused)
        self.assertEqual(reused["runner_dispatch_count"], 0)
        code, mismatch = self.audit(account, "default-reuse", ["--audit-ref", prefix + "/report.json"], entry=entry)
        self.assertEqual(code, 1, mismatch)
        self.assertEqual(mismatch["runner_dispatch_count"], 0)

    def v5_request(self):
        account, _ = self.accounted()
        obs = sources.Observations(self.root)
        state, _ = sources.load_accounted(obs, account["output_ref"] + "/report.json")
        bundle = audit.make_input(obs, state)
        request = audit.phase_input("extract", bundle, file=bundle["files"][0], citation_guidance="full-block")
        request["payload"]["file"]["blocks"][0]["unknown_nested"] = {
            "typed": [False, 0, 0.0, None], "text": "\u4e2d\u6587\r\n\u00e9\r", "$mvg_ref": 99,
            "literal": {"$mvg_object": [["unknown", "literal"]]},
            "nested_wire": audit.complete_wire.encode({"values": ["complete original " * 100] * 4})}
        request["input_identity"] = audit.canonical_sha({"payload": request["payload"], "citation_guidance": "full-block"})
        return request

    def test_v5_complete_input_restores_types_order_unknown_values_and_rejects_rehashed_tampering(self):
        request = self.v5_request()
        before = audit.compact_model_json(request)
        carrier = audit.producer_input(request, audit.SHARED_INPUT_POLICY)
        decoded = audit.decode_producer_input(carrier, audit.SHARED_INPUT_POLICY, expected=request)
        canonical = deepcopy(decoded)
        canonical.pop("producer_transport")
        self.assertEqual(audit.compact_model_json(canonical), before)
        self.assertEqual(audit.compact_model_json(decoded), audit.compact_model_json(audit.producer_input(request, audit.SPAN_REF_COMPAT_POLICY)))
        self.assertEqual(audit.compact_model_json(request), before)
        self.assertEqual(audit.producer_schema(request, audit.SHARED_INPUT_POLICY), audit.producer_schema(request, audit.SPAN_REF_COMPAT_POLICY))
        for mutation in ("outer-version", "policy", "codec-version", "digest", "ref", "cycle", "span", "mapping", "mixed-map", "input", "typed"):
            broken = deepcopy(carrier)
            if mutation == "outer-version": broken["schema_version"] += ".unknown"
            elif mutation == "policy": broken["producer_schema_policy"] = audit.SPAN_REF_COMPAT_POLICY
            elif mutation == "codec-version": broken["complete_materials"]["schema_version"] = "unknown"
            elif mutation == "digest": broken["complete_materials"]["materials_bytes_sha256"] = "foreign"
            elif mutation == "ref": broken["complete_materials"]["encoded"]["value"] = {"$mvg_ref": 999999}
            elif mutation == "cycle":
                broken["complete_materials"]["encoded"]["shared"] = [{"$mvg_ref": 0}]
                broken["complete_materials"]["encoded"]["value"] = {"$mvg_ref": 0}
            else:
                inner = deepcopy(decoded)
                if mutation == "span": inner["producer_transport"]["spans"][0]["byte_start"] = False
                elif mutation == "mapping": inner["producer_transport"]["mapping_identity"] = "foreign"
                elif mutation == "mixed-map": inner["producer_transport"]["schema_version"] = audit.SPAN_REF_POLICY
                elif mutation == "input": inner["payload"]["file"]["text"] += "changed"
                else: inner["payload"]["file"]["blocks"][0]["unknown_nested"]["typed"][0] = 0
                if mutation in {"input", "typed"}:
                    inner["input_identity"] = audit.canonical_sha({"payload": inner["payload"], "citation_guidance": "full-block"})
                    broken["input_identity"] = inner["input_identity"]
                broken["complete_materials"] = audit.complete_wire.encode(inner)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                audit.decode_producer_input(broken, audit.SHARED_INPUT_POLICY, expected=request)
        with self.assertRaises(ValueError): audit.decode_producer_input(carrier, audit.SPAN_REF_COMPAT_POLICY)
        with self.assertRaises(ValueError): audit.decode_producer_input(decoded, audit.SHARED_INPUT_POLICY)

    def test_historical_plain_input_semantics_keep_valid_root_key_reordering(self):
        request = {"phase": "extract", "input_identity": "original", "payload": {"file": {"unknown": [False, 0, "\u4e2d\u6587"]}}}
        reordered = {key: request[key] for key in reversed(request)}
        self.assertNotEqual(audit.compact_model_json(reordered), audit.compact_model_json(request))
        self.assertEqual(audit.decode_producer_input(reordered, None, expected=request), request)
        self.assertEqual(audit.decode_producer_input(request, None, expected=request), request)

    def test_v5_keeps_strict_canonical_empty_quote_and_partial_citation_rules(self):
        from fixtures import b_route_audit_synthetic_runner as fixture
        request = self.v5_request()
        restored = audit.decode_producer_input(audit.producer_input(request, audit.SHARED_INPUT_POLICY), audit.SHARED_INPUT_POLICY, expected=request)
        literal = fixture.execute(restored)
        wire = fixture.wire_output(restored, deepcopy(literal))
        self.assertEqual(audit.decode_producer_output(request, wire, audit.SHARED_INPUT_POLICY), literal)
        empty = deepcopy(wire)
        empty["file_review"] = " \t\r\n"
        audit.schema_check(empty, audit.producer_schema(request, audit.SHARED_INPUT_POLICY))
        with self.assertRaises(codec.CodecError): audit.validate_output(request, audit.decode_producer_output(request, empty, audit.SHARED_INPUT_POLICY))
        cite = literal["obligations"][-1]["citations"][0]
        cite["quote"] = cite["quote"][:-1]
        self.assertEqual(audit.decode_producer_output(request, literal, audit.SHARED_INPUT_POLICY), literal)
        with self.assertRaises(codec.CodecError): audit.validate_output(request, literal)
        cite["byte_end"] -= 1
        audit.validate_output(request, literal)

    def test_v5_final_actual_wrapper_capacity_failure_precedes_reservation(self):
        request = self.v5_request()
        for name, byte_limit, token_limit in (("bytes", 80, 30000), ("tokens", 1048576, 1)):
            output = self.root / "logs" / ("v5-capacity-" + name)
            args = SimpleNamespace(transport_max_bytes=byte_limit, transport_max_input_tokens=token_limit)
            with patch.object(audit, "PRODUCER_SCHEMA_POLICY", audit.SHARED_INPUT_POLICY), \
                    patch.object(audit, "reserve", side_effect=AssertionError("No reservation before actual wrapper fits")), \
                    patch.object(audit, "run_isolated_model", side_effect=AssertionError("No runner dispatch")):
                with self.assertRaises(audit.AuditStop) as stopped:
                    audit.dispatch(sources.Observations(self.root), self.root / "unused-budget", output, args,
                        "extract", request, {}, {"producer_schema_policy": audit.SHARED_INPUT_POLICY,
                            "producer_input_delivery": audit.SOURCE_INPUT_CARRIER})
            self.assertEqual(stopped.exception.category, "capacity")
            actual = json.loads((output / "steps/extract/workspace/input.json").read_bytes())
            self.assertEqual(actual["schema_version"], audit.SOURCE_INPUT_CARRIER)

    def test_v5_mixed_fresh_policy_or_delivery_refused_before_preparation_and_reservation(self):
        request = {"citation_guidance": "full-block"}
        for identity in ({"producer_schema_policy": audit.SPAN_REF_COMPAT_POLICY},
                {"producer_schema_policy": audit.SHARED_INPUT_POLICY},
                {"producer_schema_policy": audit.SHARED_INPUT_POLICY, "producer_input_delivery": "unknown"}):
            with self.subTest(identity=identity), \
                    patch.object(audit, "prepare_step", side_effect=AssertionError("No mismatched preparation")), \
                    patch.object(audit, "reserve", side_effect=AssertionError("No mismatched reservation")), \
                    self.assertRaises(codec.CodecError):
                audit.dispatch(None, None, None, None, "extract", request, {}, identity)

    def test_v4_full_proof_wire_bytes_remain_historical_and_cannot_be_reused_as_v5(self):
        account, _ = self.accounted()
        options = ["--citation-guidance", "full-block"]
        with patch.object(audit, "PRODUCER_SCHEMA_POLICY", audit.SPAN_REF_COMPAT_POLICY):
            code, original = self.audit(account, "v4-history", options)
        self.assertEqual(code, 0, original)
        prefix = original["output_ref"]
        before = {path: path.read_bytes() for path in (self.root / prefix).rglob("*") if path.is_file()}
        proof = audit.validate_proof(sources.Observations(self.root), prefix + "/report.json")
        self.assertEqual(proof["identity"]["producer_schema_policy"], "input-identity-span-ref.v4")
        for name in ("extract-000001", "compare"):
            base = prefix + "/steps/" + name + "/workspace/"
            request = self.json(base + "input.json")
            self.assertNotIn("complete_materials", request)
            request.pop("producer_transport")
            self.assertEqual((self.root / (base + "input.json")).read_bytes(), audit.compact_model_json(audit.producer_input(request, audit.SPAN_REF_COMPAT_POLICY)))
        code, blocked = self.audit(account, "v5-reuse", [*options, "--audit-ref", prefix + "/report.json"])
        self.assertEqual(code, 1, blocked)
        self.assertEqual(blocked["runner_dispatch_count"], 0)
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_v5_full_high_synthetic_protocol_execution_and_original_binding_replay(self):
        with patch.object(audit, "PRODUCER_SCHEMA_POLICY", audit.SHARED_INPUT_POLICY):
            self.high_synthetic_protocol_roundtrip(audit.SHARED_INPUT_POLICY)

    def test_v6_full_high_synthetic_protocol_execution_and_original_binding_replay(self):
        self.high_synthetic_protocol_roundtrip(audit.SEMANTIC_GUIDANCE_POLICY)

    def high_synthetic_protocol_roundtrip(self, policy):
        """Synthetic stdio transport only; every production execution validator stays live."""
        account, _ = self.accounted()
        code_root = Path(audit.__file__).parent
        fixtures = Path(__file__).parent / "fixtures"
        adapter = (fixtures / "b_route_bound_protocol_runner.py").read_text(encoding="utf-8")
        adapter = adapter.replace("import subprocess", "import subprocess\nimport json")
        adapter = adapter.replace("sys.path.insert(0, str(Path(__file__).resolve().parents[2]))",
            "sys.path[:0] = " + repr([str(code_root), str(code_root / "tests")]))
        hook = '            workspace = Path(sys.argv[sys.argv.index("--workspace") + 1])'
        self.assertEqual(adapter.count(hook), 1)
        adapter = adapter.replace(hook, hook + '\n'
            '            from _b_route_source_audit import decode_producer_input\n'
            '            from fixtures import b_route_audit_synthetic_runner as fixture\n'
            '            fixture.MODE = "omission"\n'
            '            value = json.loads((workspace / "input.json").read_bytes())\n'
            '            request = decode_producer_input(value, value["producer_schema_policy"])\n'
            '            response = fixture.wire_output(request, fixture.execute(request))\n'
            '            (workspace.parents[2] / "fixture-response.json").write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")')
        self.put("b_route_protocol_child.py", (fixtures / "b_route_protocol_child.py").read_text(encoding="utf-8")
            .replace('"reasoningEffort": "medium"', '"reasoningEffort": "high"').encode("utf-8"))
        self.put("protocol-runner.py", adapter.encode("utf-8"))
        self.put("offline-metadata/models_cache.json", {"models": [{"slug": "fixture-model"}]})
        with patch.dict(os.environ, {"CODEX_HOME": str(self.root / "offline-metadata"),
                "NEWROGUE_CODEX_REASONING_EFFORT": "high", "NEWROGUE_B_ROUTE_FIXTURE_REASONING_EFFORT": "high"}):
            code, report = self.invoke("audit", "v5-protocol", ["--accounted", account["output_ref"] + "/report.json",
                "--runner", "protocol-runner.py", "--expected-model", "fixture/fixture-model", "--citation-guidance", "full-block"])
        self.assertEqual(code, 1, report)
        self.assertTrue(report["execution_complete"], report)
        self.assertFalse(report["planning_eligible"], "Retained synthetic omission never grants real semantic acceptance")
        self.assertEqual(report["runner_dispatch_count"], 2)
        prefix = report["output_ref"]
        with patch.dict(os.environ, {"NEWROGUE_CODEX_REASONING_EFFORT": "invalid-current-environment"}):
            proof = audit.validate_proof(sources.Observations(self.root), prefix + "/report.json")
        self.assertEqual(proof["identity"]["producer_schema_policy"], policy)
        self.assertEqual(proof["identity"]["expected_reasoning_effort"], "high")
        for name in ("extract-000001", "compare"):
            base = prefix + "/steps/" + name
            receipt = self.json(base + "/receipt.json")
            self.assertEqual(receipt["model_identity_scope"], "runtime_configuration")
            self.assertFalse(receipt["provider_identity_verified"])
            evidence = receipt["model_identity_evidence"][0]
            self.assertEqual(evidence["requested_reasoning_effort"], "high")
            self.assertEqual(evidence["runtime_reasoning_effort"], "high")
            raw = base64.b64decode(evidence["protocol_jsonl_base64"])
            from _codex_app_server import replay
            output, rebuilt = replay(raw, prompt=(self.root / base / "request.txt").read_text(encoding="utf-8"),
                schema=self.json(base + "/workspace/schema.json"))
            self.assertEqual(rebuilt, evidence)
            self.assertEqual(output.encode("utf-8"), (self.root / base / "workspace/output.json").read_bytes())
            self.assertEqual(self.json(base + "/workspace/input.json")["schema_version"], audit.SOURCE_INPUT_CARRIER)
            phase = "compare" if name == "compare" else "extract"
            self.assertEqual((self.root / base / "workspace/prompt.txt").read_bytes(),
                (audit.producer_prompt(phase, "full-block", policy) + "\n").encode("utf-8"))

    def test_v6_guidance_extends_v5_without_changing_complete_materials_schema_or_canonical_identity(self):
        request = self.v5_request()
        before = audit.compact_model_json(request)
        old = audit.producer_input(request, audit.SHARED_INPUT_POLICY)
        new = audit.producer_input(request, audit.SEMANTIC_GUIDANCE_POLICY)
        self.assertEqual(new, {**old, "producer_schema_policy": audit.SEMANTIC_GUIDANCE_POLICY})
        self.assertEqual(audit.producer_schema(request, audit.SHARED_INPUT_POLICY),
            audit.producer_schema(request, audit.SEMANTIC_GUIDANCE_POLICY))
        for phase in ("extract", "compare"):
            original = audit.prompt_text(phase, "full-block") + "\n\n" + audit.SPAN_REF_GUIDANCE + "\n\n" + audit.SHARED_INPUT_GUIDANCE
            self.assertEqual(audit.producer_prompt(phase, "full-block", audit.SHARED_INPUT_POLICY), original)
            self.assertEqual(audit.producer_prompt(phase, "full-block", audit.SEMANTIC_GUIDANCE_POLICY),
                original + "\n\n" + audit.SEMANTIC_GUIDANCE[phase])
        self.assertNotEqual(audit.producer_prompt_identity("full-block", audit.SHARED_INPUT_POLICY),
            audit.producer_prompt_identity("full-block", audit.SEMANTIC_GUIDANCE_POLICY))
        self.assertIn("Do not infer delegation", audit.SEMANTIC_GUIDANCE["extract"])
        self.assertIn("even when", audit.SEMANTIC_GUIDANCE["compare"])
        for policy in audit.SHARED_INPUT_POLICIES:
            restored = audit.decode_producer_input(audit.producer_input(request, policy), policy, expected=request)
            restored.pop("producer_transport")
            self.assertEqual(audit.compact_model_json(restored), before)
        for value, policy in ((new, audit.SHARED_INPUT_POLICY), (old, audit.SEMANTIC_GUIDANCE_POLICY), (new, "unknown")):
            with self.subTest(policy=policy), self.assertRaises(codec.CodecError):
                audit.decode_producer_input(value, policy, expected=request)

    def test_v6_uncertainty_cannot_vanish_when_represented_but_valid_blocking_findings_remain_accepted(self):
        from fixtures import b_route_audit_synthetic_runner as fixture
        account, _ = self.accounted()
        obs = sources.Observations(self.root)
        state, _ = sources.load_accounted(obs, account["output_ref"] + "/report.json")
        bundle = audit.make_input(obs, state)
        extract = audit.phase_input("extract", bundle, file=bundle["files"][0], citation_guidance="full-block")
        output = fixture.execute(extract)
        for kind in ("unknown", "underspecified"):
            with self.subTest(kind=kind):
                uncertain = deepcopy(output)
                uncertain["obligations"][0]["kind"] = kind
                uncertain["coverage"][0]["disposition"] = "unknown"
                audit.validate_output(extract, uncertain)
                request = audit.phase_input("compare", bundle, [uncertain], citation_guidance="full-block")
                reviewed = fixture.execute(request)
                with self.assertRaises(codec.CodecError) as failed:
                    audit.validate_output(request, reviewed)
                self.assertEqual(failed.exception.diagnostic.entity_id, "obligation.unknown")
                reviewed["findings"] = [{"finding_id": "retained-uncertainty", "input_identity": request["input_identity"],
                    "classification": kind, "severity": "blocking", "return_owner": "source-owner",
                    "reason": "Synthetic classification disagreement retains independent uncertainty.",
                    "citations": uncertain["obligations"][0]["citations"],
                    "affected_proposal_ids": reviewed["obligation_reviews"][0]["proposal_ids"], "unprojected": False}]
                reviewed["obligation_reviews"][0]["finding_ids"] = ["retained-uncertainty"]
                with self.assertRaises(codec.CodecError) as failed:
                    audit.validate_output(request, reviewed)
                self.assertEqual(failed.exception.diagnostic.entity_id, "disposition.unknown")
                reviewed["disposition_reviews"][0]["finding_ids"] = ["retained-uncertainty"]
                restored = audit.decode_producer_input(audit.producer_input(request, audit.SEMANTIC_GUIDANCE_POLICY),
                    audit.SEMANTIC_GUIDANCE_POLICY, expected=request)
                decoded = audit.decode_producer_output(request, fixture.wire_output(restored, deepcopy(reviewed)),
                    audit.SEMANTIC_GUIDANCE_POLICY)
                audit.validate_output(request, decoded)
                self.assertEqual(decoded["findings"][0]["severity"], "blocking")

    def test_v6_fresh_policy_delivery_and_guidance_mismatch_fail_before_reservation(self):
        for identity in ({"producer_schema_policy": audit.SHARED_INPUT_POLICY, "producer_input_delivery": audit.SOURCE_INPUT_CARRIER},
                {"producer_schema_policy": audit.SEMANTIC_GUIDANCE_POLICY},
                {"producer_schema_policy": audit.SEMANTIC_GUIDANCE_POLICY, "producer_input_delivery": "unknown"},
                {"producer_schema_policy": "unknown", "producer_input_delivery": audit.SOURCE_INPUT_CARRIER}):
            with self.subTest(identity=identity), \
                    patch.object(audit, "prepare_step", side_effect=AssertionError("No mismatched preparation")), \
                    patch.object(audit, "reserve", side_effect=AssertionError("No mismatched reservation")), \
                    self.assertRaises(codec.CodecError):
                audit.dispatch(None, None, None, None, "extract", {"citation_guidance": "full-block"}, {}, identity)
        with self.assertRaises(codec.CodecError):
            audit.producer_prompt("extract", None, audit.SEMANTIC_GUIDANCE_POLICY)

    def test_v5_completed_proof_keeps_original_bytes_and_blocks_v6_current_reuse(self):
        account, _ = self.accounted()
        options = ["--citation-guidance", "full-block"]
        with patch.object(audit, "PRODUCER_SCHEMA_POLICY", audit.SHARED_INPUT_POLICY):
            code, report = self.audit(account, "v5-history", options)
        self.assertEqual(code, 0, report)
        prefix = report["output_ref"]
        before = {p: p.read_bytes() for p in (self.root / prefix).rglob("*") if p.is_file()}
        proof = audit.validate_proof(sources.Observations(self.root), prefix + "/report.json")
        self.assertEqual(proof["identity"]["producer_schema_policy"], audit.SHARED_INPUT_POLICY)
        code, blocked = self.audit(account, "v6-reuse", [*options, "--audit-ref", prefix + "/report.json"])
        self.assertEqual(code, 1, blocked)
        self.assertEqual(blocked["runner_dispatch_count"], 0)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_span_refs_preserve_qualified_utf8_crlf_bare_cr_and_literal_partials(self):
        from fixtures import b_route_audit_synthetic_runner as fixture
        files = []
        for path, text in (("a.md", "\u4e2d\u6587\r\nline\rfinal\n"), ("b.md", "other \u00e9\r\n")):
            raw = text.encode("utf-8")
            files.append({"path": path, "raw_digest": codec.raw_digest(raw), "raw_base64": base64.b64encode(raw).decode(),
                "text": text, "blocks": [{"block_id": "same-block", "source_char_start": 0,
                    "source_char_end_exclusive": len(sources.text_view(raw)), "raw_text": text,
                    "line_start": 1, "line_end": len(text.splitlines())}]})
        compare = {"phase": "compare", "input_identity": "frozen", "citation_guidance": "full-block", "payload": {"files": files}}
        rows = audit.span_table(compare)
        self.assertEqual([row["span_ref"] for row in rows], ["span-000001", "span-000002"])
        self.assertEqual([row["path"] for row in rows], ["a.md", "b.md"])
        original = deepcopy(compare)
        self.assertEqual(audit.producer_input(compare, audit.SPAN_REF_POLICY)["payload"], compare["payload"])
        self.assertEqual(compare, original)
        for file in files:
            request = {"phase": "extract", "input_identity": "frozen", "citation_guidance": "full-block", "payload": {"file": file}}
            literal = fixture.execute(request)
            wire = fixture.wire_output(audit.producer_input(request, audit.SPAN_REF_POLICY), deepcopy(literal))
            decoded = audit.decode_producer_output(request, wire, audit.SPAN_REF_POLICY)
            self.assertEqual(decoded, literal)
            audit.validate_output(request, decoded)
            cite = literal["obligations"][0]["citations"][0]
            cite["quote"] = file["text"][:1]
            cite["byte_end"] = len(cite["quote"].encode())
            self.assertEqual(audit.decode_producer_output(request, literal, audit.SPAN_REF_POLICY), literal)
            audit.validate_output(request, literal)
            cite["quote"] += "x"
            self.assertEqual(audit.decode_producer_output(request, literal, audit.SPAN_REF_POLICY), literal)
            with self.assertRaises(codec.CodecError):
                audit.validate_output(request, literal)
            for invalid in ({"span_ref": "span-999999"}, {"span_ref": "span-000001", "quote": file["text"]}):
                broken = deepcopy(wire)
                broken["obligations"][0]["citations"][0] = invalid
                with self.assertRaises(codec.CodecError):
                    audit.decode_producer_output(request, broken, audit.SPAN_REF_POLICY)

    def test_v4_schema_subset_keeps_canonical_nonempty_nonwhitespace_string_gates(self):
        from fixtures import b_route_audit_synthetic_runner as fixture
        account, _ = self.accounted()
        obs = sources.Observations(self.root)
        state, _ = sources.load_accounted(obs, account["output_ref"] + "/report.json")
        bundle = audit.make_input(obs, state)
        extractions = []
        for phase in ("extract", "compare"):
            request = audit.phase_input(phase, bundle, extractions, bundle["files"][0] if phase == "extract" else None, "full-block")
            canonical_schema = audit.output_schema(phase)
            v3 = audit.producer_schema(request, audit.SPAN_REF_POLICY)
            v4 = audit.producer_schema(request, audit.SPAN_REF_COMPAT_POLICY)
            expected = deepcopy(v3)
            removed = []
            def strip(value):
                if isinstance(value, dict):
                    for key in ("pattern", "minLength"):
                        if key in value:
                            self.assertIn("string", value["type"] if isinstance(value["type"], list) else [value["type"]])
                            removed.append(value.pop(key))
                    for child in value.values(): strip(child)
                elif isinstance(value, list):
                    for child in value: strip(child)
            strip(expected)
            self.assertTrue(removed)
            self.assertEqual(v4, expected)
            self.assertEqual(audit.output_schema(phase), canonical_schema)
            literal = fixture.execute(request)
            wire = fixture.wire_output(audit.producer_input(request, audit.SPAN_REF_COMPAT_POLICY), deepcopy(literal))
            self.assertEqual(audit.decode_producer_output(request, wire, audit.SPAN_REF_COMPAT_POLICY), literal)
            audit.validate_output(request, literal)
            if phase == "extract": extractions.append(literal)
            for text in ("", " \t\r\n"):
                broken = deepcopy(wire)
                if phase == "extract": broken["file_review"] = text
                else: broken["disposition_reviews"][0]["reason"] = text
                audit.schema_check(broken, v4)
                decoded = audit.decode_producer_output(request, broken, audit.SPAN_REF_COMPAT_POLICY)
                with self.assertRaises(codec.CodecError): audit.validate_output(request, decoded)
                with self.assertRaises(codec.CodecError): audit.schema_check(broken, v3)
            for cite in ({"span_ref": "span-999999"}, {"span_ref": "span-000001", "quote": "wrong"}):
                broken = deepcopy(wire)
                group, field = audit.citation_slots(phase)[0 if phase == "compare" else 1]
                broken[group][0][field] = [cite]
                with self.assertRaises(codec.CodecError):
                    audit.decode_producer_output(request, broken, audit.SPAN_REF_COMPAT_POLICY)

    def test_historical_v3_full_execution_replay_keeps_wire_bytes_and_blocks_v4_reuse(self):
        account, _ = self.accounted()
        options = ["--citation-guidance", "full-block"]
        with patch.object(audit, "PRODUCER_SCHEMA_POLICY", audit.SPAN_REF_POLICY):
            code, old = self.audit(account, "v3", options)
        self.assertEqual(code, 0, old)
        prefix = old["output_ref"]
        before = {p: p.read_bytes() for p in (self.root / prefix).rglob("*") if p.is_file()}
        self.assertEqual(self.json(prefix + "/identity.json")["producer_schema_policy"], audit.SPAN_REF_POLICY)
        for name in ("extract-000001", "compare"):
            request = self.json(prefix + "/steps/" + name + "/workspace/input.json")
            self.assertEqual(request.pop("producer_transport")["schema_version"], audit.SPAN_REF_POLICY)
            expected = audit.compact_model_json(audit.producer_schema(request, audit.SPAN_REF_POLICY))
            self.assertEqual((self.root / prefix / "steps" / name / "workspace/schema.json").read_bytes(), expected)
            self.assertNotEqual(expected, audit.compact_model_json(audit.producer_schema(request, audit.SPAN_REF_COMPAT_POLICY)))
        audit.validate_proof(sources.Observations(self.root), prefix + "/report.json")
        code, blocked = self.audit(account, "v4-reuse", [*options, "--audit-ref", prefix + "/report.json"])
        self.assertEqual(code, 1, blocked)
        self.assertEqual(blocked["runner_dispatch_count"], 0)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def span_ref_sizing(self):
        """Mechanical complete-fixture comparison, never a model-quality claim."""
        from fixtures import b_route_audit_synthetic_runner as fixture
        self.put("docs/source.md", ("# Rule\r\n\r\n" + "Preserve all \u4e2d\u6587 reward ordering and explicit constraints. " * 40 + "\r\n").encode())
        account, _ = self.accounted()
        obs = sources.Observations(self.root)
        state, _ = sources.load_accounted(obs, account["output_ref"] + "/report.json")
        bundle = audit.make_input(obs, state)
        extractions, measurements = [], []
        with patch.object(fixture, "MODE", "supported-deferred"):
            for phase, file in [("extract", file) for file in bundle["files"]] + [("compare", None)]:
                request = audit.phase_input(phase, bundle, extractions, file, "full-block")
                literal = fixture.execute(request)
                wire = fixture.wire_output(audit.producer_input(request, audit.SPAN_REF_POLICY), deepcopy(literal))
                decoded = audit.decode_producer_output(request, wire, audit.SPAN_REF_POLICY)
                self.assertEqual(audit.canonical_sha(decoded), audit.canonical_sha(literal))
                audit.validate_output(request, decoded)
                if phase == "extract":
                    extractions.append(decoded)
                values = {}
                for label, output in (("literal", literal), ("span_ref", wire)):
                    raw = audit.compact_model_json(output)
                    values[label] = audit.measure_request(raw.decode("utf-8"), max_bytes=1048576, max_input_tokens=96000)
                    values[label]["bytes"] = len(raw)
                measurements.append({"phase": phase, **values})
        return measurements

    def test_complete_nonempty_fixture_span_ref_sizing_preserves_all_outputs(self):
        for row in self.span_ref_sizing():
            self.assertLess(row["span_ref"]["bytes"], row["literal"]["bytes"])
            self.assertLess(row["span_ref"]["input_token_estimate"], row["literal"]["input_token_estimate"])

    def test_span_ref_input_table_and_canonical_sidecar_tampering_rejected(self):
        account, _ = self.accounted()
        code, report = self.audit(account, extras=["--citation-guidance", "full-block"])
        self.assertEqual(code, 0, report)
        prefix = report["output_ref"]
        relative = "steps/extract-000001/workspace/input.json"
        sidecar = "steps/extract-000001/canonical-output.json"
        original = {name: (self.root / prefix / name).read_bytes() for name in (relative, sidecar, "event.json")}
        for mutation in ("alias", "path", "digest", "offset", "mapping", "version", "duplicate", "canonical", "raw-substitution"):
            with self.subTest(mutation=mutation):
                for name, raw in original.items():
                    (self.root / prefix / name).write_bytes(raw)
                target, carrier = relative, self.json(prefix + "/" + relative)
                value = audit.decode_producer_input(carrier, audit.PRODUCER_SCHEMA_POLICY)
                table = value["producer_transport"]
                if mutation == "alias": table["spans"][0]["span_ref"] = "span-999999"
                elif mutation == "path": table["spans"][0]["path"] = "foreign.md"
                elif mutation == "digest": table["spans"][0]["raw_digest"] = "sha256:" + "0" * 64
                elif mutation == "offset": table["spans"][0]["byte_start"] = False
                elif mutation == "mapping": table["mapping_identity"] = "foreign"
                elif mutation == "version": table["schema_version"] = "unknown"
                elif mutation == "duplicate": table["spans"].append(deepcopy(table["spans"][0]))
                elif mutation == "canonical":
                    target, value = sidecar, self.json(prefix + "/" + sidecar)
                    value["obligations"][0]["statement"] += "changed"
                else:
                    target, value = sidecar, self.json(prefix + "/steps/extract-000001/workspace/output.json")
                if target == relative:
                    carrier["complete_materials"] = audit.complete_wire.encode(value)
                    value = carrier
                (self.root / prefix / target).write_bytes(audit.compact_model_json(value))
                event = self.json(prefix + "/event.json")
                event["artifacts"][target] = codec.raw_digest((self.root / prefix / target).read_bytes())
                self.put(prefix + "/event.json", event)
                with self.assertRaises(codec.CodecError):
                    audit.validate_proof(sources.Observations(self.root), prefix + "/report.json")
        for name, raw in original.items():
            (self.root / prefix / name).write_bytes(raw)
        audit.validate_proof(sources.Observations(self.root), prefix + "/report.json")

    def test_trusted_reasoning_expectation_binds_tool_identity_and_captured_runner(self):
        default = audit.tool_identity(self.root, self.root / self.runner, "synthetic/source-audit-v1", "full-block")
        high = audit.tool_identity(self.root, self.root / self.runner, "synthetic/source-audit-v1", "full-block",
                                   expected_reasoning_effort="high")
        self.assertEqual(high.pop("expected_reasoning_effort"), "high")
        self.assertEqual(high, default)
        account, _ = self.accounted()
        code, report = self.audit(account, extras=["--citation-guidance", "full-block"])
        self.assertEqual(code, 0, report)
        prefix = report["output_ref"]
        runner = self.json(prefix + "/runner.json")
        runner["requested_reasoning_effort"] = "high"
        self.put(prefix + "/runner.json", runner)
        event = self.json(prefix + "/event.json")
        event["artifacts"]["runner.json"] = codec.raw_digest((self.root / prefix / "runner.json").read_bytes())
        self.put(prefix + "/event.json", event)
        with self.assertRaises(codec.CodecError) as failed:
            audit.validate_proof(sources.Observations(self.root), prefix + "/report.json")
        self.assertEqual(failed.exception.diagnostic.entity_id, "proof.reasoning_effort")

    def test_guidance_still_accepts_exact_partial_and_rejects_off_by_one_citation(self):
        account, _ = self.accounted()
        code, report = self.audit(account, extras=["--citation-guidance", "full-block"])
        self.assertEqual(code, 0, report)
        step = report["output_ref"] + "/steps/extract-000001/workspace"
        request = audit.decode_producer_input(self.json(step + "/input.json"), audit.PRODUCER_SCHEMA_POLICY)
        output = self.json(str(Path(step).parent) + "/canonical-output.json")
        request.pop("producer_transport")
        cite = output["obligations"][-1]["citations"][0]
        self.assertTrue(cite["quote"].endswith("\r\n"))
        # Local validator probes never modify the captured model output.
        cite["quote"] = cite["quote"][:-1]
        with self.assertRaises(codec.CodecError) as failed:
            audit.validate_output(request, output)
        self.assertEqual(failed.exception.diagnostic.entity_id, "citation.quote")
        cite["byte_end"] -= 1
        audit.validate_output(request, output)
        self.mode("bad-quote")
        code, blocked = self.audit(account, "bad-guided", ["--citation-guidance", "full-block"])
        self.assertEqual(code, 1, blocked)
        self.assertEqual(blocked["runner_dispatch_count"], 1)
        self.assertFalse(blocked["execution_complete"])
        self.assertIn("citation.quote", json.dumps(blocked["diagnostics"]))

    def test_guided_producer_schema_consts_preserve_canonical_identity_rejection(self):
        account, _ = self.accounted(disposition="context")
        self.mode("omission")
        with patch.object(audit, "PRODUCER_SCHEMA_POLICY", "input-identity-const.v2"):
            code, report = self.audit(account, extras=["--citation-guidance", "full-block"])
        self.assertEqual(code, 1, report)
        self.assertTrue(report["execution_complete"])
        prefix = report["output_ref"]
        for phase, name in (("extract", "extract-000001"), ("compare", "compare")):
            step = prefix + "/steps/" + name + "/workspace"
            request, value = self.json(step + "/input.json"), self.json(step + "/output.json")
            schema = self.json(step + "/schema.json")
            expected = audit.output_schema(phase)
            expected["properties"]["input_identity"]["const"] = request["input_identity"]
            expected["properties"]["schema_version"]["type"] = "string"
            if phase == "compare":
                expected["properties"]["findings"]["items"]["properties"]["input_identity"]["const"] = request["input_identity"]
                self.assertTrue(value["findings"])
            self.assertEqual(schema, expected)
            self.assertNotIn("const", audit.output_schema(phase)["properties"]["input_identity"])
            audit.schema_check(value, schema)
            # Probe copies only; captured output bytes are never repaired.
            for nested in ([False, True] if phase == "compare" else [False]):
                bad = json.loads(json.dumps(value))
                row = bad["findings"][0] if nested else bad
                row["input_identity"] += "7"
                audit.schema_check(bad, audit.output_schema(phase))
                with self.assertRaises(codec.CodecError):
                    audit.schema_check(bad, schema)
                with self.assertRaises(codec.CodecError):
                    audit.validate_output(request, bad)
        audit.validate_proof(sources.Observations(self.root), prefix + "/report.json")

    def test_v2_producer_string_choices_typed_with_exact_default_and_v1_history(self):
        def rows(value):
            if isinstance(value, dict):
                yield value
                for nested in value.values():
                    yield from rows(nested)
            elif isinstance(value, list):
                for nested in value:
                    yield from rows(nested)
        for phase in ("extract", "compare"):
            request = {"phase": phase, "input_identity": "sha256:" + "1" * 64, "citation_guidance": "full-block"}
            canonical = audit.output_schema(phase)
            self.assertEqual(audit.producer_schema(request), canonical)
            legacy = json.loads(json.dumps(canonical))
            legacy["properties"]["input_identity"]["const"] = request["input_identity"]
            if phase == "compare":
                legacy["properties"]["findings"]["items"]["properties"]["input_identity"]["const"] = request["input_identity"]
            self.assertEqual(audit.producer_schema(request, "input-identity-const.v1"), legacy)
            actual = audit.producer_schema(request, "input-identity-const.v2")
            self.assertEqual(actual["properties"]["schema_version"]["type"], "string")
            for row in rows(actual):
                if row.get("type") == "object":
                    self.assertIs(row.get("additionalProperties"), False, row)
                    self.assertEqual(set(row.get("required", [])), set(row.get("properties", {})))
                if isinstance(row.get("const"), str) or ("enum" in row and all(isinstance(v, str) for v in row["enum"])):
                    self.assertEqual(row.get("type"), "string", row)
            actual["properties"]["schema_version"].pop("type")
            self.assertEqual(actual, legacy, "v2 adds only a redundant string declaration")
            self.assertNotIn("type", canonical["properties"]["schema_version"])
        account, _ = self.accounted()
        with patch.object(audit, "PRODUCER_SCHEMA_POLICY", "input-identity-const.v1"):
            code, old = self.audit(account, "v1-guided", ["--citation-guidance", "full-block"])
        self.assertEqual(code, 0, old)
        prefix = old["output_ref"]
        self.assertEqual(self.json(prefix + "/identity.json")["producer_schema_policy"], "input-identity-const.v1")
        before = {p: p.read_bytes() for p in (self.root / prefix).rglob("*") if p.is_file()}
        audit.validate_proof(sources.Observations(self.root), prefix + "/report.json")
        for name in ("extract-000001", "compare"):
            self.assertNotIn("type", self.json(prefix + "/steps/" + name + "/workspace/schema.json")["properties"]["schema_version"])
        code, blocked = self.audit(account, "v1-reuse", ["--citation-guidance", "full-block", "--audit-ref", prefix + "/report.json"])
        self.assertEqual(code, 1, blocked)
        self.assertEqual(blocked["runner_dispatch_count"], 0)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_historical_guided_generic_schema_replay_blocks_cross_policy_reuse(self):
        account, _ = self.accounted()
        options = ["--citation-guidance", "full-block"]
        current_identity = audit.tool_identity
        def historical_identity(*args, **kwargs):
            identity = current_identity(*args, **kwargs)
            identity.pop("producer_schema_policy", None)
            return identity
        # Recreate the old producer only. All canonical/proof validators run.
        with patch.object(audit, "PRODUCER_SCHEMA_POLICY", None), \
             patch.object(audit, "tool_identity", side_effect=historical_identity):
            code, old = self.audit(account, "historical-guided", options)
        self.assertEqual(code, 0, old)
        prefix = old["output_ref"]
        self.assertNotIn("producer_schema_policy", self.json(prefix + "/identity.json"))
        before = {p: p.read_bytes() for p in (self.root / prefix).rglob("*") if p.is_file()}
        proof = audit.validate_proof(sources.Observations(self.root), prefix + "/report.json")
        self.assertTrue(proof["report"]["execution_complete"])
        for phase, name in (("extract", "extract-000001"), ("compare", "compare")):
            self.assertEqual(self.json(prefix + "/steps/" + name + "/workspace/schema.json"), audit.output_schema(phase))
        with self.assertRaises(codec.CodecError) as failed:
            audit.verify_current_proof(sources.Observations(self.root), prefix + "/report.json", scope_id="scope")
        self.assertIn("producer_schema_policy", failed.exception.diagnostic.actual["changed_dependencies"])
        code, blocked = self.audit(account, "cross-policy", [*options, "--audit-ref", prefix + "/report.json"])
        self.assertEqual(code, 1, blocked)
        self.assertEqual(blocked["runner_dispatch_count"], 0)
        code, new = self.audit(account, "fresh-policy", options)
        self.assertEqual(code, 0, new)
        for name in ("extract-000001", "compare"):
            actual = audit.decode_producer_input(self.json(new["output_ref"] + "/steps/" + name + "/workspace/input.json"),
                                                 audit.PRODUCER_SCHEMA_POLICY)
            actual.pop("producer_transport")
            self.assertEqual(self.json(prefix + "/steps/" + name + "/workspace/input.json"), actual)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_producer_policy_mode_and_actual_schema_tampering_fail_closed(self):
        account, _ = self.accounted()
        code, report = self.audit(account, extras=["--citation-guidance", "full-block"])
        self.assertEqual(code, 0, report)
        prefix = report["output_ref"]
        targets = ("identity.json", "steps/extract-000001/workspace/schema.json", "event.json")
        original = {name: (self.root / prefix / name).read_bytes() for name in targets}
        for mutation in ("unknown-policy", "missing-mode", "policy-downgrade", "v1-policy-downgrade", "schema-downgrade", "missing-type", "wrong-type", "boolean-minimum", "foreign-identity"):
            with self.subTest(mutation=mutation):
                for name, raw in original.items():
                    (self.root / prefix / name).write_bytes(raw)
                identity = self.json(prefix + "/identity.json")
                schema = self.json(prefix + "/" + targets[1])
                if mutation == "unknown-policy":
                    identity["producer_schema_policy"] = "unknown-policy"
                elif mutation == "missing-mode":
                    identity.pop("citation_guidance")
                elif mutation == "policy-downgrade":
                    identity.pop("producer_schema_policy")
                elif mutation == "v1-policy-downgrade":
                    identity["producer_schema_policy"] = "input-identity-const.v1"
                elif mutation == "schema-downgrade":
                    schema["properties"]["input_identity"].pop("const")
                elif mutation == "missing-type":
                    schema["properties"]["schema_version"].pop("type")
                elif mutation == "wrong-type":
                    schema["properties"]["schema_version"]["type"] = "integer"
                elif mutation == "boolean-minimum":
                    schema["properties"]["obligations"]["items"]["properties"]["citations"]["items"]["anyOf"][1]["properties"]["byte_start"]["minimum"] = False
                else:
                    schema["properties"]["input_identity"]["const"] += "7"
                self.put(prefix + "/identity.json", identity)
                self.put(prefix + "/" + targets[1], schema)
                if mutation in {"unknown-policy", "missing-mode"}:
                    (self.root / prefix / targets[1]).write_bytes(original[targets[1]])
                event = self.json(prefix + "/event.json")
                for name in targets[:2]:
                    event["artifacts"][name] = codec.raw_digest((self.root / prefix / name).read_bytes())
                self.put(prefix + "/event.json", event)
                with self.assertRaises(codec.CodecError):
                    audit.validate_proof(sources.Observations(self.root), prefix + "/report.json")
        for policy in ("unknown-policy", audit.PRODUCER_SCHEMA_POLICY):
            with self.assertRaises(codec.CodecError):
                audit.producer_schema({"phase": "extract", "input_identity": "fixture"}, policy)
        with patch.object(audit, "reserve", side_effect=AssertionError("No reservation")), \
             patch.object(audit, "prepare_step", side_effect=AssertionError("No preparation")):
            with self.assertRaises(codec.CodecError):
                audit.dispatch(None, None, None, None, "extract", {"citation_guidance": "full-block"}, {},
                               {"producer_schema_policy": "unknown-policy"})

    def test_guided_prompt_tampering_rejected_even_with_rehashed_event(self):
        account, _ = self.accounted()
        code, report = self.audit(account, extras=["--citation-guidance", "full-block"])
        self.assertEqual(code, 0, report)
        prefix = report["output_ref"]
        relative = "steps/extract-000001/workspace/prompt.txt"
        target = self.root / prefix / relative
        target.write_bytes(target.read_bytes() + b"Changed producer guidance.\n")
        event = self.json(prefix + "/event.json")
        event["artifacts"][relative] = codec.raw_digest(target.read_bytes())
        self.put(prefix + "/event.json", event)
        with self.assertRaises(codec.CodecError) as failed:
            audit.validate_proof(sources.Observations(self.root), prefix + "/report.json")
        self.assertEqual(failed.exception.diagnostic.expected, "exact prompt rule bytes")
        code, blocked = self.audit(account, "tampered-reuse", ["--citation-guidance", "full-block", "--audit-ref", prefix + "/report.json"])
        self.assertEqual(code, 1, blocked)
        self.assertEqual(blocked["runner_dispatch_count"], 0)

    def test_citation_guidance_admission_rejects_source_stages_and_unknown_mode(self):
        account, prepared = self.accounted()
        with patch.object(audit, "reserve", side_effect=AssertionError("Admission must precede reservation")), \
             patch.object(audit, "run_isolated_model", side_effect=AssertionError("No dispatch")):
            for stage, options in (("prepare", ["--source-set", "docs/source-set.json"]),
                                   ("account", ["--prepared", prepared["prepared_ref"]["path"], "--candidate", "candidate.json"])):
                code, report = self.invoke(stage, "invalid-guidance", [*options, "--citation-guidance", "full-block"])
                self.assertEqual(code, 2, report)
                self.assertNotIn("output_ref", report)
            code, report = self.audit(account, extras=["--citation-guidance", "unknown-mode"])
            self.assertEqual(code, 2, report)
            self.assertNotIn("output_ref", report)
        self.assertEqual(list((self.root / "logs/ci").glob("*/b-route-source-audit/*")), [])

    def test_complete_reuse_zero_dispatch_and_unrelated_state(self):
        account, _ = self.accounted()
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        self.put(".taskmaster/tasks/tasks.json", {"irrelevant": "status change"})
        self.put("unrelated-head.txt", b"Unrelated HEAD provenance.\n")
        code, reused = self.audit(account, "reused", ["--audit-ref", original["output_ref"] + "/report.json"])
        self.assertEqual(code, 0, reused)
        self.assertEqual(reused["runner_dispatch_count"], 0)
        self.assertEqual(reused["reuse_reason"], "complete_identity_and_original_proof_match")
        code, verified = self.verify(reused)
        self.assertEqual(code, 0, verified)

    def test_os_runner_workspace_drift_blocks_fresh_completion_with_verify_reuse_control(self):
        account, _ = self.accounted()
        marker = "SYNTHETIC_WORKSPACE_DRIFT"
        hook = "    output = wire_output(request, execute(request))"
        self.assertEqual(self.fixture.count(hook), 1)
        mutations = {
            "input": ('    (workspace / "input.json").write_bytes(b\'{"SYNTHETIC_WORKSPACE_DRIFT":true}\\n\')\n', "input.json", 1),
            "schema": ('    changed = json.loads((workspace / "schema.json").read_bytes())\n'
                       '    changed["description"] = "SYNTHETIC_WORKSPACE_DRIFT"\n'
                       '    (workspace / "schema.json").write_bytes(json.dumps(changed).encode("utf-8"))\n', "schema.json", 1),
            "prompt": ('    target = workspace / "prompt.txt"\n'
                       '    target.write_bytes(target.read_bytes() + b"SYNTHETIC_WORKSPACE_DRIFT")\n', "prompt.txt", 1),
            "earlier-step": ('    if request["phase"] == "compare":\n'
                             '        target = workspace.parents[1] / "extract-000001/workspace/input.json"\n'
                             '        target.write_bytes(b\'{"SYNTHETIC_WORKSPACE_DRIFT":true}\\n\')\n', "input.json", 2),
        }
        for mutation, (injected, filename, dispatches) in mutations.items():
            with self.subTest(mutation=mutation):
                self.put(self.runner, self.fixture.replace(hook, injected + hook).encode("utf-8"))
                run = "workspace-" + mutation
                code, blocked = self.audit(account, run=run)
                self.assertEqual(code, 1, blocked)
                self.assertFalse(blocked["execution_complete"])
                self.assertFalse(blocked["planning_eligible"])
                self.assertEqual(blocked["runner_dispatch_count"], dispatches)
                self.assertEqual(blocked["synthetic_dispatch_count"], dispatches)
                self.assertEqual(blocked["model_dispatch_count"], 0)
                prefix = blocked["output_ref"]
                changed = "steps/extract-000001/workspace/" + filename
                event = self.json(prefix + "/event.json")
                raw = (self.root / prefix / changed).read_bytes()
                self.assertIn(marker.encode(), raw)
                self.assertEqual(event["artifacts"][changed], codec.raw_digest(raw))
                self.assertNotEqual(event["observations"][prefix + "/" + changed], codec.raw_digest(raw))
                self.assertNotIn(marker.encode(), (self.root / prefix / "steps/extract-000001/request.txt").read_bytes())
                self.assertTrue((self.root / prefix / "steps/extract-000001/execution.json").is_file())
                self.assertEqual(self.verify(blocked, "verify-blocked", run=run)[0], 1)
                code, reuse = self.audit(account, "reuse-blocked", ["--audit-ref", prefix + "/report.json"], run=run)
                self.assertEqual(code, 1, reuse)
                self.assertEqual(reuse["runner_dispatch_count"], 0)
                self.assertEqual((self.root / prefix / changed).read_bytes(), raw)
        self.put(self.runner, self.fixture.encode("utf-8"))
        code, clean = self.audit(account, run="workspace-control")
        self.assertEqual(code, 0, clean)
        self.assertTrue(clean["execution_complete"])
        self.assertEqual(self.verify(clean, run="workspace-control")[0], 0)
        code, reused = self.audit(account, "reused", ["--audit-ref", clean["output_ref"] + "/report.json"], run="workspace-control")
        self.assertEqual(code, 0, reused)
        self.assertEqual(reused["runner_dispatch_count"], 0)
        self.assertTrue(reused["execution_complete"])
        self.assertEqual(self.verify(reused, "verify-reused", run="workspace-control")[0], 0)

    def test_fresh_execution_proof_is_validated_before_completion(self):
        account, _ = self.accounted()
        invoke = audit.run_isolated_model
        def alter_captured_command(*args, **kwargs):
            receipt = invoke(*args, **kwargs)
            path = kwargs["execution_log"]
            execution = json.loads(path.read_bytes())
            execution["command"].append("--synthetic-undispatched-argument")
            path.write_bytes(json.dumps(execution).encode("utf-8"))
            return receipt
        with patch.object(audit, "run_isolated_model", side_effect=alter_captured_command):
            code, report = self.audit(account)
        self.assertEqual(code, 1, report)
        self.assertFalse(report["execution_complete"])
        self.assertEqual(report["runner_dispatch_count"], 1)
        self.assertEqual(report["synthetic_dispatch_count"], 1)
        self.assertEqual(report["model_dispatch_count"], 0)
        self.assertIn("proof.execution", json.dumps(report["diagnostics"]))
        execution = self.json(report["output_ref"] + "/steps/extract-000001/execution.json")
        self.assertEqual(execution["command"][-1], "--synthetic-undispatched-argument")

    def test_audit_python_runner_suppresses_bytecode_without_environment_override(self):
        account, _ = self.accounted()
        self.put("runner_dependency.py", b"VALUE = 42\n")
        self.put(self.runner, ("from runner_dependency import VALUE\nassert VALUE == 42\n" + self.fixture).encode("utf-8"))
        scripts = Path(__file__).resolve().parents[1]
        clean_env = dict(os.environ)
        clean_env.pop("PYTHONDONTWRITEBYTECODE", None)
        clean_env.pop("PYTHONPYCACHEPREFIX", None)
        # Actual legacy describe control proves the local dependency creates
        # bytecode without an environment guard; the helper default is unchanged.
        control = ("import sys; from pathlib import Path; "
                   "sys.path.insert(0, sys.argv[1]); "
                   "from _planning_skill_common import inspect_isolated_runner; "
                   "inspect_isolated_runner(Path(sys.argv[2]))")
        proc = subprocess.run([sys.executable, "-B", "-c", control, str(scripts), str(self.root / self.runner)],
                              env=clean_env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        cache = self.root / "__pycache__"
        self.assertTrue(list(cache.glob("runner_dependency.*.pyc")), "The legacy control must actually create dependency bytecode")
        shutil.rmtree(cache)
        entry = scripts / "account_b_route_sources.py"
        def cli(stage, attempt, extra):
            command = [sys.executable, str(entry), "--stage", stage, "--root", str(self.root), "--run-id", "bytecode",
                "--scope-id", "scope", "--attempt-id", attempt, "--runner", self.runner,
                "--expected-model", "synthetic/source-audit-v1", *extra]
            result = subprocess.run(command, env=clean_env, capture_output=True, text=True)
            self.assertEqual(result.stderr, "", result.stderr)
            return result.returncode, json.loads(result.stdout)
        accounted = account["output_ref"] + "/report.json"
        code, report = cli("audit", "fresh", ["--accounted", accounted])
        self.assertEqual(code, 0, report)
        self.assertTrue(report["execution_complete"])
        expected_runner = self.root.resolve(strict=True) / self.runner
        for step in ("extract-000001", "compare"):
            execution = self.json(report["output_ref"] + "/steps/" + step + "/execution.json")
            self.assertEqual(execution["command"][:3], [sys.executable, "-B", str(expected_runner)])
        ref = report["output_ref"] + "/report.json"
        self.assertEqual(cli("verify", "verify", ["--audit-ref", ref])[0], 0)
        code, reused = cli("audit", "reused", ["--accounted", accounted, "--audit-ref", ref])
        self.assertEqual(code, 0, reused)
        self.assertEqual(reused["runner_dispatch_count"], 0)
        self.assertEqual(list(self.root.rglob("*.pyc")), [])
        self.assertEqual(list(self.root.rglob("__pycache__")), [])

    def test_unprojected_handoff_multifile_and_conflict_are_blocking(self):
        self.put("docs/second.md", b"Return to map after the reward handoff.\n")
        self.registration(["docs/source.md", "docs/second.md"])
        account, _ = self.accounted(disposition="context")
        for index, mode in enumerate(("omission", "conflict")):
            self.mode(mode)
            code, report = self.audit(account, "blocking-" + str(index))
            self.assertEqual(code, 1, report)
            self.assertTrue(report["execution_complete"])
            self.assertFalse(report["planning_eligible"])
            finding = report["semantic_blockers"][0]
            self.assertEqual(finding["affected_proposal_ids"], [])
            self.assertTrue(finding["unprojected"])
            if mode == "conflict":
                self.assertEqual(len({r["path"] for r in finding["citations"]}), 2)
            code, verified = self.verify(report, "verify-" + str(index))
            self.assertEqual(code, 1, verified)
            self.assertTrue(verified["execution_complete"])

    def test_original_unresolved_survives_synthetic_acceptance(self):
        account, _ = self.accounted(disposition="unresolved")
        code, report = self.audit(account)
        self.assertEqual(code, 1, report)
        self.assertTrue(report["execution_complete"])
        self.assertEqual(report["semantic_blockers"][:len(account["unresolved"])], account["unresolved"])

    def test_full_files_and_empty_file_denominators(self):
        self.put("docs/empty.md", b"")
        self.registration(["docs/source.md", "docs/empty.md"])
        prepared = self.prepare()
        candidate = self.candidate(prepared)
        raw = (self.root / "docs/source.md").read_bytes()
        candidate["file_results"][0].update(disposition="context", reason="Empty file independently reviewed.",
            evidence={"path": "docs/source.md", "raw_digest": codec.raw_digest(raw), "byte_start": 0, "byte_end": 6})
        self.put("candidate.json", candidate)
        code, account = self.account(prepared)
        self.assertEqual(code, 0, account)
        code, report = self.audit(account)
        self.assertEqual(code, 0, report)
        self.assertEqual(report["source_count"], 2)
        self.assertEqual(report["runner_dispatch_count"], 3)
        self.assertEqual(self.verify(report)[0], 0)

    def test_invalid_output_receipt_and_dispositions_fail_closed(self):
        account, _ = self.accounted()
        for mode in ("bad-quote", "missing-block", "duplicate-block", "reordered-blocks", "fake-pass", "bad-proposal",
                     "missing-file", "tools", "extra-dispatch", "unknown", "deferred"):
            with self.subTest(mode=mode):
                self.mode(mode)
                code, report = self.audit(account, mode, run=mode)
                self.assertEqual(code, 1, report)
                self.assertFalse(report["execution_complete"])
                self.assertFalse(report["planning_eligible"])
                self.assertEqual(report["termination_reason"], "execution_blocked")
                self.assertTrue((self.root / report["output_ref"] / "event.json").is_file())

    def test_capacity_zero_dispatch_and_persistent_budget_cannot_increase(self):
        account, _ = self.accounted()
        code, report = self.audit(account, extras=["--transport-max-bytes", "100"])
        self.assertEqual(code, 1, report)
        self.assertEqual(report["termination_reason"], "capacity_blocked")
        self.assertEqual(report["runner_dispatch_count"], 0)
        code, report = self.audit(account, "raised", ["--request-budget", "100"])
        self.assertEqual(code, 1, report)
        self.assertEqual(report["runner_dispatch_count"], 0)

    def test_budget_across_attempt_and_date_failure_not_refunded(self):
        account, _ = self.accounted()
        self.mode("crash")
        code, first = self.audit(account, extras=["--request-budget", "1", "--active-budget-seconds", "330"])
        self.assertEqual(code, 1, first)
        self.assertEqual(first["runner_dispatch_count"], 1)
        self.assertEqual(first["model_dispatch_count"], "unknown")
        home = (self.root / first["output_ref"]).parent
        date_path = home.parents[1]
        destination = self.root / "logs/ci/2001-01-01/b-route-source-audit/run"
        destination.parent.mkdir(parents=True)
        home.rename(destination)
        code, second = self.audit(account, "second", ["--request-budget", "1", "--active-budget-seconds", "330"])
        self.assertEqual(code, 1, second)
        self.assertEqual(second["termination_reason"], "budget_blocked")
        self.assertEqual(second["runner_dispatch_count"], 0)
        self.assertEqual(len(list((destination / "reservations").iterdir())), 1)

    def test_pending_metadata_lock_does_not_dispatch(self):
        account, _ = self.accounted()
        code, first = self.audit(account)
        self.assertEqual(code, 0, first)
        home = (self.root / first["output_ref"]).parent
        (home / "budget.lock").write_bytes(b"Interrupted metadata reservation.")
        code, report = self.audit(account, "busy")
        self.assertEqual(code, 1, report)
        self.assertEqual(report["termination_reason"], "budget_blocked")
        self.assertEqual(report["runner_dispatch_count"], 0)

    def test_budget_deletion_and_corruption_fail_closed_without_rewriting_history(self):
        account, _ = self.accounted()
        for mutation in ("budget", "tail", "tail-and-step-copy", "all-permits", "permit-duration",
                         "permit-scope", "step-copy", "binding", "terminal-count", "invalid-json"):
            with self.subTest(mutation=mutation):
                run = "integrity-" + mutation
                code, first = self.audit(account, run=run)
                self.assertEqual(code, 0, first)
                home = (self.root / first["output_ref"]).parent
                permit = sorted((home / "reservations").glob("*.json"))[-1]
                value = self.json(permit.relative_to(self.root).as_posix())
                step_copy = home / first["attempt_id"] / "steps" / value["step"] / "reservation.json"
                missing = []
                if mutation == "budget":
                    missing = [home / "budget.json"]
                elif mutation in {"tail", "tail-and-step-copy"}:
                    missing = [permit] + ([step_copy] if mutation == "tail-and-step-copy" else [])
                elif mutation == "all-permits":
                    missing = list((home / "reservations").iterdir())
                elif mutation in {"permit-duration", "permit-scope", "step-copy"}:
                    target = step_copy if mutation == "step-copy" else permit
                    value["reserved_seconds"] = 1
                    if mutation == "permit-scope":
                        value["scope_id"] = "wrong-scope"
                    self.put(target.relative_to(self.root).as_posix(), value)
                elif mutation == "binding":
                    target = home / first["attempt_id"] / "budget-binding.json"
                    value = self.json(target.relative_to(self.root).as_posix())
                    value["request_budget"] += 1
                    self.put(target.relative_to(self.root).as_posix(), value)
                elif mutation == "terminal-count":
                    target = home / first["attempt_id"] / "report.json"
                    value = self.json(target.relative_to(self.root).as_posix())
                    value["runner_dispatch_count"] += 1
                    self.put(target.relative_to(self.root).as_posix(), value)
                else:
                    (home / "budget.json").write_bytes(b'{"broken":')
                for path in missing:
                    path.unlink()
                before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
                with patch.object(audit, "run_isolated_model") as model:
                    code, blocked = self.audit(account, "after-corruption", run=run)
                self.assertEqual(code, 1, blocked)
                self.assertEqual(blocked["runner_dispatch_count"], 0)
                self.assertFalse(blocked["execution_complete"])
                model.assert_not_called()
                for path, raw in before.items():
                    self.assertEqual((home / path).read_bytes(), raw)
                self.assertTrue(all(not p.exists() for p in missing))

    def test_missing_fixed_budget_after_zero_dispatch_cannot_raise_limits(self):
        account, _ = self.accounted()
        code, first = self.audit(account, extras=["--transport-max-bytes", "100"])
        self.assertEqual(code, 1, first)
        self.assertEqual(first["runner_dispatch_count"], 0)
        home = (self.root / first["output_ref"]).parent
        (home / "budget.json").unlink()
        shutil.rmtree(home / "reservations")
        with patch.object(audit, "run_isolated_model") as model:
            code, blocked = self.audit(account, "raised-after-deletion", ["--request-budget", "100"])
        self.assertEqual(code, 1, blocked)
        self.assertEqual(blocked["runner_dispatch_count"], 0)
        self.assertFalse((home / "budget.json").exists())
        model.assert_not_called()

    def test_orphan_reservation_witness_prevents_refund_before_step_copy(self):
        account, _ = self.accounted()
        parser = sources.Parser()
        sources.register_arguments(parser)
        args = parser.parse_args(["--stage", "audit", "--root", str(self.root), "--run-id", "orphan",
            "--scope-id", "scope", "--attempt-id", "lost-process", "--accounted", "account.json",
            "--runner", self.runner, "--expected-model", "synthetic/source-audit-v1",
            "--request-budget", "1", "--timeout-seconds", "1", "--active-budget-seconds", "31"])
        root, home, _, _ = audit.enter(args)
        audit.reserve(root, home, args, None)
        audit.reserve(root, home, args, "extract-000001")
        witness = home / "lost-process/budget-permits/000001.json"
        raw = witness.read_bytes()
        (home / "reservations/000001.json").unlink()
        code, blocked = self.audit(account, "after-loss", ["--request-budget", "1", "--timeout-seconds", "1",
            "--active-budget-seconds", "31"], run="orphan")
        self.assertEqual(code, 1, blocked)
        self.assertEqual(blocked["runner_dispatch_count"], 0)
        self.assertEqual(witness.read_bytes(), raw)
        self.assertFalse((home / "reservations/000001.json").exists())

    def test_legacy_partial_dispatch_with_deleted_permits_remains_blocked(self):
        account, _ = self.accounted()
        self.mode("crash")
        code, first = self.audit(account)
        self.assertEqual(code, 1, first)
        self.assertEqual(first["runner_dispatch_count"], 1)
        home = (self.root / first["output_ref"]).parent
        attempt = home / first["attempt_id"]
        # Remove only the new witness entries from this controlled fixture to
        # reproduce the pre-patch evidence layout; retain actual OS failure proof.
        (attempt / "budget-binding.json").unlink()
        shutil.rmtree(attempt / "budget-permits")
        event = self.json(first["output_ref"] + "/event.json")
        event["artifacts"] = {p: digest for p, digest in event["artifacts"].items()
                              if p != "budget-binding.json" and not p.startswith("budget-permits/")}
        self.put(first["output_ref"] + "/event.json", event)
        (home / "reservations/000001.json").unlink()
        (attempt / "steps/extract-000001/reservation.json").unlink()
        code, blocked = self.audit(account, "after-partial-loss")
        self.assertEqual(code, 1, blocked)
        self.assertEqual(blocked["runner_dispatch_count"], 0)
        self.assertTrue((attempt / "steps/extract-000001/execution.json").is_file())

    def test_legacy_valid_budget_continues_without_rewriting_old_evidence(self):
        account, _ = self.accounted()
        code, first = self.audit(account)
        self.assertEqual(code, 0, first)
        home = (self.root / first["output_ref"]).parent
        attempt = home / first["attempt_id"]
        (attempt / "budget-binding.json").unlink()
        shutil.rmtree(attempt / "budget-permits")
        event = self.json(first["output_ref"] + "/event.json")
        event["artifacts"] = {p: digest for p, digest in event["artifacts"].items()
                              if p != "budget-binding.json" and not p.startswith("budget-permits/")}
        self.put(first["output_ref"] + "/event.json", event)
        before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
        code, second = self.audit(account, "legacy-next")
        self.assertEqual(code, 0, second)
        self.assertEqual(len(list((home / "reservations").iterdir())), 4)
        for path, raw in before.items():
            self.assertEqual((home / path).read_bytes(), raw)

    def test_first_initialization_survives_unfunded_concurrent_lock_failure(self):
        account, _ = self.accounted()
        parser = sources.Parser()
        sources.register_arguments(parser)
        args = parser.parse_args(["--stage", "audit", "--root", str(self.root), "--run-id", "first-concurrent",
            "--scope-id", "scope", "--attempt-id", "waiting", "--accounted", account["output_ref"] + "/report.json",
            "--runner", self.runner, "--expected-model", "synthetic/source-audit-v1", "--request-budget", "32",
            "--timeout-seconds", "300", "--active-budget-seconds", "3600"])
        root, home, waiting, _ = audit.enter(args)
        sources.write(waiting / "request.json", {**vars(args), "root": str(root)})
        (home / "budget.lock").write_bytes(b"Synthetic concurrent first initializer.")
        code, loser = self.audit(account, "lock-loser", run="first-concurrent")
        self.assertEqual(code, 1, loser)
        self.assertEqual(loser["termination_reason"], "budget_blocked")
        self.assertEqual(loser["runner_dispatch_count"], 0)
        (home / "budget.lock").unlink()
        before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
        code, winner = self.audit(account, "initializer", run="first-concurrent")
        self.assertEqual(code, 0, winner)
        self.assertEqual(len(list((home / "reservations").iterdir())), 2)
        for path, raw in before.items():
            self.assertEqual((home / path).read_bytes(), raw)

    def test_damaged_proof_rejected_without_rerun(self):
        account, _ = self.accounted()
        code, report = self.audit(account)
        self.assertEqual(code, 0, report)
        path = self.root / report["output_ref"] / "steps/extract-000001/workspace/output.json"
        path.write_bytes(b"{}\n")
        code, failed = self.audit(account, "reuse-broken", ["--audit-ref", report["output_ref"] + "/report.json"])
        self.assertEqual(code, 1, failed)
        self.assertEqual(failed["runner_dispatch_count"], 0)
        self.assertEqual(self.verify(report)[0], 1)

    def test_source_changes_reuse_only_unchanged_extraction_and_global_reruns(self):
        self.put("docs/second.md", b"A second complete file.\n")
        self.registration(["docs/source.md", "docs/second.md"])
        account, prepared = self.accounted()
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        self.put("docs/second.md", b"A changed complete second file.\n")
        next_prepared = self.prepare("changed", ["--previous", prepared["prepared_ref"]["path"]])
        self.candidate(next_prepared)
        code, next_account = self.account(next_prepared, "changed")
        self.assertEqual(code, 0, next_account)
        code, changed = self.audit(next_account, "changed-audit", ["--audit-ref", original["output_ref"] + "/report.json"])
        self.assertEqual(code, 0, changed)
        self.assertEqual(changed["runner_dispatch_count"], 2)
        self.assertEqual([r["path"] for r in changed["reused_extractions"]], ["docs/source.md"])
        self.assertEqual(self.verify(changed)[0], 0)
        self.assertEqual(self.verify(original, "stale-original")[0], 1)

    def test_projection_only_change_reuses_all_extractions(self):
        account, prepared = self.accounted()
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        candidate = self.json("candidate.json")
        for row in candidate["block_results"]:
            for atom in row["atoms"]:
                atom["acceptance_intent"] = "Reviewed changed acceptance intent."
        self.put("candidate.json", candidate)
        code, next_account = self.account(prepared, "changed-proposal")
        self.assertEqual(code, 0, next_account)
        code, changed = self.audit(next_account, "changed-audit", ["--audit-ref", original["output_ref"] + "/report.json"])
        self.assertEqual(code, 0, changed)
        self.assertEqual(changed["runner_dispatch_count"], 1)
        self.assertEqual(len(changed["reused_extractions"]), 1)

    def test_runner_and_expected_model_changes_reject_reuse(self):
        account, _ = self.accounted()
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        self.put(self.runner, (self.fixture + "\n# Relevant runner byte change.\n").encode())
        code, report = self.audit(account, "changed-tool", ["--audit-ref", original["output_ref"] + "/report.json"])
        self.assertEqual(code, 1, report)
        self.assertEqual(report["runner_dispatch_count"], 0)
        self.assertEqual(self.verify(original)[0], 1)
        self.assertEqual(self.audit(account, "wrong-model", ["--expected-model", "wrong-model"])[0], 1)

    def test_terminal_event_conflict_partial_and_argument_rejection(self):
        account, _ = self.accounted()
        self.assertEqual(self.audit(account, "reservations", run="reserved-first")[0], 2)
        self.assertEqual(list((self.root / "logs/ci").glob("*/b-route-source-audit/reserved-first")), [])
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        event = self.root / original["output_ref"] / "event.json"
        before = event.read_bytes()
        self.assertEqual(self.audit(account, extras=["--request-budget", "99"])[0], 2)
        self.assertEqual(event.read_bytes(), before)
        event.unlink()
        self.assertEqual(self.audit(account)[0], 2)
        for extras in (["--runner", "../escape.py"], ["--expected-model", "environment-default"], ["--prepared", "unwanted.json"]):
            self.assertEqual(self.audit(account, "bad-args", extras)[0], 2)

    def test_old_prepare_account_request_identity_and_audit_options_rejected(self):
        account, prepared = self.accounted()
        for report in (account, prepared):
            request = self.json(report["output_ref"] + "/request.json")
            self.assertEqual(len(request), 14)
            self.assertTrue(set(request).isdisjoint(sources.AUDIT_ARGUMENTS))
        self.assertEqual(self.prepare("base"), prepared)
        self.assertEqual(self.account(prepared, "base")[1], account)
        for option, value in (("--runner", "runner.py"), ("--accounted", "a.json"),
                              ("--request-budget", "32"), ("--timeout-seconds", "300")):
            code, _ = self.invoke("prepare", "invalid-old", ["--source-set", "docs/source-set.json", option, value])
            self.assertEqual(code, 2)

    def test_actual_timeout_kills_runner_and_retains_unknown_reservation(self):
        account, _ = self.accounted()
        self.mode("timeout")
        code, report = self.audit(account, extras=["--timeout-seconds", "1", "--active-budget-seconds", "31", "--request-budget", "1"])
        self.assertEqual(code, 1, report)
        self.assertEqual(report["termination_reason"], "time_blocked")
        self.assertEqual(report["diagnostics"][0]["reason_code"], "budget_exhausted")
        self.assertEqual(report["runner_dispatch_count"], 1)
        self.assertEqual(report["model_dispatch_count"], "unknown")
        execution = self.json(report["output_ref"] + "/steps/extract-000001/execution.json")
        self.assertEqual(execution["status"], "timeout")
        self.assertNotEqual(execution["returncode"], 0)
        self.assertLess(report["active_elapsed_seconds"], 30)

    def test_transitive_runner_dependency_and_sc_backend_are_bound(self):
        account, _ = self.accounted()
        self.put("runner_dependency.py", b"MARKER = 'original'\n")
        self.put(self.runner, ("from runner_dependency import MARKER\n" + self.fixture).encode())
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        identity = self.json(original["output_ref"] + "/identity.json")
        self.assertIn("runner_dependency.py", identity["tools"])
        backend = (Path(audit.__file__).resolve().parents[1] / "sc" / "_llm_backend.py").resolve(strict=True)
        self.assertEqual(codec.raw_digest(backend.read_bytes()), identity["tools"][str(backend)])
        self.put("runner_dependency.py", b"MARKER = 'changed'\n")
        code, report = self.audit(account, "changed-dependency", ["--audit-ref", original["output_ref"] + "/report.json"])
        self.assertEqual(code, 1, report)
        self.assertEqual(report["runner_dispatch_count"], 0)

    def test_same_sources_and_proposals_new_preparation_time_reuses_global(self):
        account, _ = self.accounted()
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        next_account, _ = self.accounted("new-prepare")
        code, report = self.audit(next_account, "same-content", ["--audit-ref", original["output_ref"] + "/report.json"])
        self.assertEqual(code, 0, report)
        self.assertEqual(report["runner_dispatch_count"], 0)

    def test_concurrent_budget_permits_cannot_overspend(self):
        parser = sources.Parser()
        sources.register_arguments(parser)
        args = parser.parse_args(["--stage", "audit", "--root", str(self.root), "--run-id", "parallel", "--scope-id", "scope",
            "--attempt-id", "one", "--accounted", "account.json", "--runner", self.runner, "--expected-model", "synthetic/source-audit-v1",
            "--request-budget", "1", "--timeout-seconds", "1", "--active-budget-seconds", "31"])
        root, home, _, _ = audit.enter(args)
        audit.reserve(root, home, args, None)
        def reserve_one(index):
            try:
                return audit.reserve(root, home, args, "step-" + str(index))
            except (audit.AuditStop, codec.CodecError):
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(reserve_one, range(4)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(len(list((home / "reservations").iterdir())), 1)

    def test_actual_cli_audit_verify_both_entries_and_negative_without_bytecode(self):
        account, _ = self.accounted()
        script_root = Path(__file__).resolve().parents[1]
        for name in ("account_b_route_sources.py", "dev_cli.py"):
            entry = script_root / name
            code, report = self.audit(account, "cli-" + name.replace(".", "-"), entry=entry)
            self.assertEqual(code, 0, report)
            code, verified = self.verify(report, "verify-" + name.replace(".", "-"), entry=entry)
            self.assertEqual(code, 0, verified)
            self.assertEqual(self.verify(report, "bad-" + name.replace(".", "-"), ["--expected-model", "default"], entry=entry)[0], 2)
        self.assertEqual(list(self.root.rglob("*.pyc")), [])

    def test_rehashed_proof_with_bad_quote_is_still_rejected(self):
        account, _ = self.accounted()
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        prefix = original["output_ref"]
        step = prefix + "/steps/extract-000001"
        value = self.json(step + "/workspace/output.json")
        value["obligations"][0]["citations"][0]["quote"] = "Invented original quotation."
        self.put(step + "/workspace/output.json", value)
        receipt = self.json(step + "/receipt.json")
        receipt["output_chars"] = len((self.root / step / "workspace/output.json").read_text(encoding="utf-8"))
        self.put(step + "/receipt.json", receipt)
        execution = self.json(step + "/execution.json")
        execution["stdout"] = json.dumps(receipt) + "\n"
        execution["stdout_base64"] = base64.b64encode(execution["stdout"].encode()).decode()
        self.put(step + "/execution.json", execution)
        event = self.json(prefix + "/event.json")
        for name in event["artifacts"]:
            event["artifacts"][name] = codec.raw_digest((self.root / prefix / name).read_bytes())
        self.put(prefix + "/event.json", event)
        code, report = self.audit(account, "rehashed", ["--audit-ref", prefix + "/report.json"])
        self.assertEqual(code, 1, report)
        self.assertEqual(report["runner_dispatch_count"], 0)
        self.assertIn("citation.quote", json.dumps(report["diagnostics"]))

    def test_source_and_glob_drift_fail_before_dispatch(self):
        self.registration(["docs/*.md"], active=["docs/source.md"])
        account, _ = self.accounted()
        raw = (self.root / "docs/source.md").read_bytes()
        self.put("docs/source.md", raw + b"Drift.\n")
        code, changed = self.audit(account)
        self.assertEqual(code, 1, changed)
        self.assertEqual(changed["runner_dispatch_count"], 0)
        self.put("docs/source.md", raw)
        self.put("docs/added.md", b"A new glob member.\n")
        code, added = self.audit(account, "new-member")
        self.assertEqual(code, 1, added)
        self.assertEqual(added["runner_dispatch_count"], 0)

    def test_supported_deferred_obligation_keeps_explicit_review(self):
        account, _ = self.accounted()
        self.mode("supported-deferred")
        code, report = self.audit(account)
        self.assertEqual(code, 0, report)
        self.assertTrue(report["execution_complete"])
        self.assertEqual(self.verify(report)[0], 0)

    def test_local_package_relative_dependency_changes_invalidate_runner_identity(self):
        self.put('runner.py',b'import helper_package\n')
        self.put('helper_package/__init__.py',b'from . import nested\n')
        dependency=self.put('helper_package/nested.py',b'VALUE = 1\n')
        first=audit.tool_identity(self.root,self.root/'runner.py','fixture-model')
        self.assertIn('helper_package/__init__.py',first['tools'])
        self.assertIn('helper_package/nested.py',first['tools'])
        dependency.write_bytes(b'VALUE = 2\n')
        self.assertNotEqual(first,audit.tool_identity(self.root,self.root/'runner.py','fixture-model'))
        runner=self.put('runners/runner.py',b'import helper_namespace.nested\n')
        dependency=self.put('helper_namespace/nested.py',b'VALUE = 1\n')
        first=audit.tool_identity(self.root,runner,'fixture-model')
        self.assertIn('helper_namespace/nested.py',first['tools'])
        dependency.write_bytes(b'VALUE = 2\n')
        self.assertNotEqual(first,audit.tool_identity(self.root,runner,'fixture-model'))

    def test_invalid_runner_syntax_persists_terminal_failure_and_replays_without_dispatch(self):
        account,_=self.accounted()
        self.put(self.runner,b'def invalid(\n')
        code,report=self.audit(account)
        self.assertEqual(1,code)
        self.assertFalse(report['execution_complete'])
        self.assertEqual(0,report['runner_dispatch_count'])
        self.assertEqual('input_blocked',report['termination_reason'])
        self.assertTrue((self.root/report['output_ref']/'event.json').is_file())
        self.assertEqual((code,report),self.audit(account))

    def test_rule_schema_and_parser_change_do_not_reuse_old_conclusions(self):
        account, _ = self.accounted()
        code, original = self.audit(account)
        self.assertEqual(code, 0, original)
        ref = original["output_ref"] + "/report.json"
        with patch.object(audit, "RULES", "changed-rule"):
            code, changed = self.audit(account, "rule-change", ["--audit-ref", ref])
            self.assertEqual(code, 1, changed)
            self.assertEqual(changed["runner_dispatch_count"], 0)
        with patch.dict(audit.PROMPTS, {"extract": audit.PROMPTS["extract"] + "Changed prompt rule."}):
            code, changed = self.audit(account, "prompt-change", ["--audit-ref", ref])
            self.assertEqual(code, 1, changed)
            self.assertEqual(changed["runner_dispatch_count"], 0)
        schema = audit.output_schema
        def changed_schema(phase):
            result = schema(phase)
            result["properties"]["new_field"] = {"type": "string"}
            result["required"].append("new_field")
            return result
        with patch.object(audit, "output_schema", changed_schema):
            code, changed = self.audit(account, "schema-change", ["--audit-ref", ref])
            self.assertEqual(code, 1, changed)
            self.assertEqual(changed["runner_dispatch_count"], 0)
        build = sources.native.build_ledger
        def changed_parser(*args, **kwargs):
            manifest, ledger = build(*args, **kwargs)
            ledger["blocks"][0]["raw_text"] = "A changed native parser result."
            return manifest, ledger
        with patch.object(sources.native, "build_ledger", changed_parser):
            code, changed = self.audit(account, "parser-change", ["--audit-ref", ref])
            self.assertEqual(code, 1, changed)
            self.assertEqual(changed["runner_dispatch_count"], 0)

    def test_disk_failure_and_end_read_drift_never_claim_completion(self):
        account, _ = self.accounted()
        write = sources.write
        def disk_failure(path, value):
            if path.name == "event.json" and "b-route-source-audit" in str(path):
                raise OSError("Synthetic final event persistence failure.")
            return write(path, value)
        with patch.object(sources, "write", disk_failure):
            code, failed = self.audit(account, "partial")
        self.assertEqual(code, 1, failed)
        self.assertEqual(failed["termination_reason"], "partial_write")
        self.assertFalse(failed["execution_complete"])
        self.assertEqual(self.audit(account, "partial")[0], 2)
        verify = sources.Observations.verify
        changed = False
        def drift(obs):
            nonlocal changed
            if not changed:
                self.put("docs/source.md", b"Synthetic concurrent source edit.\n")
                changed = True
            return verify(obs)
        with patch.object(sources.Observations, "verify", drift):
            code, failed = self.audit(account, "drift")
        self.assertEqual(code, 1, failed)
        self.assertFalse(failed["execution_complete"])
        self.assertFalse(failed["planning_eligible"])

    @unittest.skipUnless(os.name == "nt", "Requires actual Windows junction and short-path rejection")
    def test_windows_audit_real_junction_and_short_path_rejected(self):
        account, _ = self.accounted()
        outside = self.root / "outside-long-audit-directory"
        outside.mkdir()
        (outside / "runner.py").write_bytes(self.fixture.encode("utf-8"))
        link = self.root / "junction"
        proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        try:
            self.assertEqual(self.audit(account, extras=["--runner", "junction/runner.py"])[0], 2)
            self.assertEqual([p.name for p in outside.iterdir()], ["runner.py"])
        finally:
            os.rmdir(link)
        directory = self.root / "long-runner-directory-for-source-audit"
        directory.mkdir()
        (directory / "runner.py").write_bytes(self.fixture.encode("utf-8"))
        buffer = ctypes.create_unicode_buffer(32768)
        self.assertGreater(ctypes.windll.kernel32.GetShortPathNameW(str(directory), buffer, len(buffer)), 0)
        if "~" not in buffer.value:
            proc = subprocess.run(["fsutil", "file", "setshortname", str(directory), "AUDIT2~2"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertGreater(ctypes.windll.kernel32.GetShortPathNameW(str(directory), buffer, len(buffer)), 0)
        self.assertIn("~", buffer.value)
        relative_alias = Path(buffer.value).name + "/runner.py"
        self.assertTrue((self.root / relative_alias).is_file(), "The alias must address the actual existing runner")
        self.assertEqual(self.audit(account, "alias", ["--runner", relative_alias])[0], 2)
        self.assertEqual(list(directory.iterdir()), [directory / "runner.py"])


# Prevent duplicated inherited Story 2.1 test execution in this targeted suite.
for _name in list(vars(SourceAccountingTests)):
    if _name.startswith("test_") and _name not in vars(SourceAuditTests):
        setattr(SourceAuditTests, _name, None)
del SourceAccountingTests

if __name__ == "__main__":
    unittest.main()
