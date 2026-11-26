"""Deterministic tests for Story 4.9 consumer alignment & pre-switch audit."""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPTS_PY = Path(__file__).resolve().parents[1]
SCRIPTS_SC = SCRIPTS_PY.parent / "sc"
REPO_ROOT = SCRIPTS_PY.parents[1]
for p in (str(SCRIPTS_PY), str(SCRIPTS_SC)):
    if p not in sys.path:
        sys.path.insert(0, p)

import _b_route_codec as codec
import _b_route_consumer_alignment as alignment
import _b_route_inventory as inventory
import audit_b_route_consumer_alignment as alignment_cli
import build_taskmaster_tasks
import compile_task_triplet
import create_chapter7_tasks_from_ui_candidates as ch7_create
import dev_cli
import dev_cli_builders
import llm_generate_overlays_batch


DIAG_KEYS = {"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}


def _create_dir_reparse(link_path: Path, target_path: Path, *, create_target: bool = True) -> None:
    """Create a real directory junction on Windows or symlink on POSIX without skipping."""
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if create_target:
        target_path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link_path), str(target_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise AssertionError(f"mklink /J failed: {proc.stdout} {proc.stderr}")
    else:
        os.symlink(target_path, link_path, target_is_directory=True)


def _remove_dir_reparse(link_path: Path) -> None:
    if not os.path.lexists(link_path):
        return
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "rmdir", str(link_path)], capture_output=True, check=False)
    else:
        link_path.unlink(missing_ok=True)


class ConsumerAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.live_report = alignment.audit_b_route_consumer_alignment(
            REPO_ROOT, probe_temp_contracts=True,
        )

    def _assert_six_field_diag(self, diag: dict) -> None:
        self.assertEqual(set(diag.keys()), DIAG_KEYS)
        self.assertIn(diag["reason_code"], {c.value for c in codec.ReasonCode})
        if diag["stage"] is not None:
            self.assertIn(diag["stage"], {s.value for s in codec.Stage})

    def test_ac1_live_consumer_matrix_all_ten_groups_and_mutation_blocking(self) -> None:
        report = self.live_report
        self.assertEqual(report["schema_version"], alignment.SCHEMA_VERSION)
        self.assertTrue(report["ok"], report["diagnostics"])
        matrix = report["consumer_matrix"]
        self.assertTrue(matrix["ok"], matrix["diagnostics"])
        self.assertTrue(matrix["summary_only_claim_rejected"])
        self.assertEqual(matrix["groups_expected"], len(inventory.GROUPS))
        self.assertEqual(matrix["groups_covered"], len(inventory.GROUPS))
        self.assertEqual(matrix["inventory_entries_covered"], matrix["inventory_entries_expected"])
        self.assertGreaterEqual(matrix["total_consumers"], 60)
        self.assertEqual(matrix["blocked_count"], 0)
        self.assertGreaterEqual(matrix["not_applicable_count"], 1)
        self.assertGreaterEqual(matrix["direct_underlying_scripts_verified"], 15)
        self.assertGreaterEqual(matrix["shared_task_multi_scope_consumers_verified"], 15)

        module_paths = {row["module_path"] for row in matrix["consumers"]}
        for required_direct in (
            "scripts/python/compile_task_triplet.py",
            "scripts/python/build_taskmaster_tasks.py",
            "scripts/python/create_chapter7_tasks_from_ui_candidates.py",
            "scripts/python/apply_chapter7_status_patch.py",
            "scripts/sc/llm_generate_overlays_batch.py",
            "scripts/python/run_single_task_chapter6_lane.py",
            "scripts/python/resume_task.py",
            "scripts/python/chapter6_route.py",
            "scripts/python/inspect_run.py",
            "scripts/python/_mvg_obligations.py",
            "scripts/python/run_chapter7_ui_wiring.py",
            "scripts/python/run_chapter7_backlog_gap.py",
            "scripts/python/run_mvg_acceptance.py",
            "scripts/python/milestone_incremental_handoff.py",
            "scripts/python/query_b_route_knowledge_projection.py",
            "scripts/python/query_b_route_planning_page.py",
            "scripts/python/query_b_route_observability.py",
            "workflow.md",
        ):
            self.assertIn(required_direct, module_paths)

        wf_row = next(r for r in matrix["consumers"] if r["module_path"] == "workflow.md")
        self.assertEqual(wf_row["status"], "not_applicable")

        # Generic test_ prefix is rejected by _verify_test_evidence_ref.
        ok_gen, msg_gen = alignment._verify_test_evidence_ref(
            REPO_ROOT, "scripts/python/tests/test_b_route_consumer_alignment.py", "test_",
        )
        self.assertFalse(ok_gen)
        self.assertIn("exact test method name required", msg_gen)

        # Summary-only / workflow.md-only / dispatcher-only claims must be explicitly rejected.
        for bad_basis in ("summary_only", "workflow_md_only", "dispatcher_only"):
            ok_claim, diags = alignment.validate_consumer_claim({"claim_basis": bad_basis})
            self.assertFalse(ok_claim)
            self.assertTrue(diags)
            self._assert_six_field_diag(diags[0])

        ok_real, real_diags = alignment.validate_consumer_claim({"consumers": matrix["consumers"]})
        self.assertTrue(ok_real, real_diags)

        # Mutation negative control: stripping the B-route gate call from _mvg_obligations.py
        # must flip that consumer to blocked with a six-field Diagnostic.
        with tempfile.TemporaryDirectory(prefix="nr-align-ac1-mut-") as tmpdir:
            mut_root = Path(tmpdir)
            for row in matrix["consumers"]:
                src = REPO_ROOT / row["module_path"]
                dst = mut_root / row["module_path"]
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                for ref_str in (*row["pass_evidence_refs"], *row["fail_evidence_refs"]):
                    tf = ref_str.split("::", 1)[0]
                    t_src = REPO_ROOT / tf
                    t_dst = mut_root / tf
                    if not t_dst.exists():
                        t_dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(t_src, t_dst)
            (mut_root / "scripts/python/_mvg_obligations.py").write_text(
                '"""Summary-only stub."""\ndef check_task_obligations():\n    return True\n',
                encoding="utf-8",
            )
            mut_matrix = alignment._audit_consumer_matrix(mut_root)
            self.assertFalse(mut_matrix["ok"])
            self.assertGreaterEqual(mut_matrix["blocked_count"], 1)
            ob_row = next(r for r in mut_matrix["consumers"] if r["consumer_id"] == "ch6_mvg_obligations_gate")
            self.assertEqual(ob_row["status"], "blocked")
            self.assertTrue(ob_row["diagnostics"])
            self._assert_six_field_diag(ob_row["diagnostics"][0])

    def test_p02_direct_writers_block_under_active_b_route_and_allow_pure_legacy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nr-align-p02-writers-") as tmpdir:
            base = Path(tmpdir)
            legacy_root = base / "legacy"
            legacy_root.mkdir()
            active_b_root = base / "active_b"
            active_b_root.mkdir()
            (active_b_root / "docs/planning/b-route").mkdir(parents=True, exist_ok=True)
            (active_b_root / "docs/planning/b-route/policy.v1.json").write_text('{"schema_version":"newrouge.b-route-policy.v1"}\n', encoding="utf-8")

            # Pure legacy repo (no B-route governance files) must be allowed by all 4 guards.
            compile_task_triplet._guard_active_b_route_direct_write(legacy_root)
            build_taskmaster_tasks._guard_active_b_route_direct_write(legacy_root)
            ch7_create._guard_active_b_route_direct_write(legacy_root)
            llm_generate_overlays_batch._guard_active_b_route_direct_write(legacy_root)

            # Active B-route repo must fail closed on all 4 direct writers.
            with self.assertRaises(SystemExit) as ctx_compile:
                compile_task_triplet._guard_active_b_route_direct_write(active_b_root)
            self.assertIn("b-route-task-compile", str(ctx_compile.exception))

            with self.assertRaises(SystemExit) as ctx_build:
                build_taskmaster_tasks._guard_active_b_route_direct_write(active_b_root)
            self.assertIn("b-route-task-compile", str(ctx_build.exception))

            with self.assertRaises(ValueError) as ctx_ch7:
                ch7_create._guard_active_b_route_direct_write(active_b_root)
            self.assertIn("b-route-chapter7-slice", str(ctx_ch7.exception))

            with self.assertRaises(SystemExit) as ctx_ov:
                llm_generate_overlays_batch._guard_active_b_route_direct_write(active_b_root)
            self.assertIn("b-route-chapter4-binding", str(ctx_ov.exception))

            # End-to-end compile_task_triplet.py --write CLI blocks when B-route presence is active.
            (active_b_root / ".taskmaster/tasks").mkdir(parents=True, exist_ok=True)
            (active_b_root / ".taskmaster/tasks/tasks_back.json").write_text("[]\n", encoding="utf-8")
            (active_b_root / ".taskmaster/tasks/tasks_gameplay.json").write_text("[]\n", encoding="utf-8")
            (active_b_root / "logs/ci/task-generation").mkdir(parents=True, exist_ok=True)
            (active_b_root / "logs/ci/task-generation/task-candidates.enriched.json").write_text('{"candidates":[]}\n', encoding="utf-8")
            (active_b_root / "logs/ci/task-generation/coverage-report.json").write_text('{"status":"ok"}\n', encoding="utf-8")
            # First run preview (read-only allowed), then --write must block.
            proc_prev = subprocess.run(
                [sys.executable, "-B", str(REPO_ROOT / "scripts/python/compile_task_triplet.py"), "--repo-root", str(active_b_root)],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
            self.assertEqual(proc_prev.returncode, 0, proc_prev.stdout + proc_prev.stderr)
            proc_write = subprocess.run(
                [sys.executable, "-B", str(REPO_ROOT / "scripts/python/compile_task_triplet.py"), "--repo-root", str(active_b_root), "--write"],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
            self.assertNotEqual(proc_write.returncode, 0)
            self.assertIn("b-route-task-compile", proc_write.stderr + proc_write.stdout)

    def test_ac2_five_state_version_contract_and_anti_downgrade(self) -> None:
        ac2 = self.live_report["five_state_version_contract"]
        self.assertTrue(ac2["ok"], ac2["diagnostics"])
        self.assertTrue(ac2["live_probes_executed"])
        self.assertTrue(ac2["legacy_a_bounded_to_frozen_scope"])
        self.assertTrue(ac2["anti_downgrade_verified"])
        self.assertTrue(ac2["migration_doc"]["ok"])

        states = ac2["states"]
        self.assertEqual(states["new_b_format"]["route"], "B")
        self.assertEqual(states["new_b_format"]["shared_task_applicable_plan_count"], 2)
        self.assertFalse(states["new_b_format"]["runtime_verified"])
        self.assertFalse(states["new_b_format"]["default_b_enabled"])

        self.assertEqual(states["legacy_a_format"]["explicit_not_enabled_route"], "explicit_not_enabled_a")
        self.assertEqual(states["legacy_a_format"]["outside_frozen_a_refs_route"], "blocked")
        self.assertEqual(states["legacy_a_format"]["unbounded_non_frozen_route"], "blocked")
        self.assertEqual(states["legacy_a_format"]["forbidden_a_op_route"], "blocked")

        self.assertTrue(states["legal_absence"]["pre_3c_projection_ok"])
        self.assertTrue(states["legal_absence"]["pre_3c_marker_present"])
        self.assertTrue(states["legal_absence"]["pre_3c_ch6_blocked"])
        self.assertTrue(states["legal_absence"]["non_flow_missing_rationale_rejected"])
        self.assertTrue(states["legal_absence"]["non_flow_missing_refs_rejected"])

        self.assertEqual(states["corrupted_input"]["json_error_codes"]["truncated"], "invalid_json")
        self.assertEqual(states["corrupted_input"]["json_error_codes"]["nan"], "non_finite_number")
        self.assertEqual(states["corrupted_input"]["json_error_codes"]["duplicate_key"], "duplicate_key")
        self.assertEqual(states["corrupted_input"]["tampered_route"], "blocked")
        self.assertIn("digest_mismatch", states["corrupted_input"]["tampered_reason_codes"])

        self.assertTrue(states["unknown_schema_version"]["plan_v999_rejected"])
        self.assertTrue(states["unknown_schema_version"]["catalog_v999_rejected"])
        self.assertTrue(states["unknown_schema_version"]["scope_v999_rejected"])
        self.assertIn("unknown_schema", states["unknown_schema_version"]["scope_v999_reason_codes"])

        self.assertEqual(states["anti_downgrade"]["stripped_origins_route"], "blocked")
        self.assertFalse(states["anti_downgrade"]["stripped_origins_gate_ok"])
        self.assertEqual(states["anti_downgrade"]["stripped_manifest_route"], "blocked")
        self.assertFalse(states["anti_downgrade"]["stripped_manifest_gate_ok"])
        self.assertEqual(states["anti_downgrade"]["stripped_trace_route"], "blocked")
        self.assertFalse(states["anti_downgrade"]["stripped_trace_gate_ok"])
        self.assertEqual(states["anti_downgrade"]["residual_trace_without_governance_route"], "blocked")

        # Negative control: missing required migration doc section blocks AC-2.
        with tempfile.TemporaryDirectory(prefix="nr-align-ac2-mig-") as tmpdir:
            mig_root = Path(tmpdir)
            dst = mig_root / alignment.MIGRATION_DOC_PATH
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text("# Incomplete Migration Doc\ninput_contract output_contract\n", encoding="utf-8")
            bad_ac2 = alignment._audit_five_state_and_migration(mig_root, probe_temp_contracts=False)
            self.assertFalse(bad_ac2["ok"])
            self.assertFalse(bad_ac2["legacy_a_bounded_to_frozen_scope"])
            self.assertIn("recovery_procedure", bad_ac2["migration_doc"]["missing_sections"])
            self._assert_six_field_diag(bad_ac2["diagnostics"][0])

    def _copy_ac3_surface(self, dst_root: Path) -> None:
        for rel in (
            "AGENTS.md",
            "workflow.md",
            "docs/workflows/stable-public-entrypoints.md",
            "docs/workflows/script-entrypoints-index.md",
            "docs/architecture/ADR_INDEX_GODOT.md",
            "docs/planning/semantic-topology/README.md",
            "docs/workflows/knowledge-context-shadow.md",
            "docs/workflows/chapter3-closeout.md",
            "docs/workflows/mvg-integration-acceptance.md",
            "docs/workflows/acceptance-check-and-llm-review.md",
            "docs/workflows/project-health-knowledge.md",
            "docs/workflows/prototype-lane.md",
            "docs/workflows/run-protocol.md",
            "docs/workflows/local-hard-checks.md",
            "docs/testing-framework.md",
            "docs/PROJECT_DOCUMENTATION_INDEX.md",
            "docs/agents/13-rag-sources-and-session-ssot.md",
            "geminiuse.md",
            *alignment.GOVERNED_SKILLS,
            *alignment.REQUIRED_WORKFLOW_PROTECTIONS,
        ):
            src = REPO_ROOT / rel
            if src.is_file():
                target = dst_root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
        for wf_doc in (REPO_ROOT / "docs/workflows").glob("b-route-*.md"):
            target = dst_root / "docs/workflows" / wf_doc.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(wf_doc, target)
        for adr_doc in (REPO_ROOT / "docs/adr").glob("ADR-*.md"):
            target = dst_root / "docs/adr" / adr_doc.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(adr_doc, target)
        for sub_dir in ("docs/workflows/templates",):
            src_d = REPO_ROOT / sub_dir
            if src_d.is_dir():
                shutil.copytree(src_d, dst_root / sub_dir, dirs_exist_ok=True)

    def test_ac3_docs_skills_adr_alignment_and_negative_controls(self) -> None:
        ac3 = self.live_report["docs_skills_adr_alignment"]
        self.assertTrue(ac3["ok"], ac3["diagnostics"])
        self.assertEqual(ac3["broken_links"], [])
        self.assertEqual(ac3["invalid_cli_flags"], [])
        self.assertEqual(ac3["bare_adr_0038_hits"], [])
        self.assertEqual(ac3["fence_errors"], [])
        self.assertEqual(ac3["per_skill_failures"], [])
        self.assertEqual(ac3["adr_anomalies"], [])
        self.assertTrue(ac3["dual_adr_0038_present"])
        self.assertEqual(ac3["adr_0040_status"], "accepted")
        self.assertEqual(ac3["proposed_adrs_misclassified_as_accepted"], [])
        self.assertTrue(all(ac3["boundaries"].values()), ac3["boundaries"])
        self.assertTrue(ac3["workflow_protections_present"])
        self.assertFalse(ac3["workflow_md_mutated"])
        self.assertGreaterEqual(ac3["adr_index_sections_parsed"], 6)

        with tempfile.TemporaryDirectory(prefix="nr-align-ac3-neg-") as tmpdir:
            base = Path(tmpdir)
            self._copy_ac3_surface(base)

            # 1. Inject CJK-adjacent bare ADR-0038 into Chapter 3 SKILL.md -> must fail with invalid_reference.
            ch3_skill = base / ".agents/skills/workflow-chapter3-task-triplet-baseline/SKILL.md"
            orig_ch3 = ch3_skill.read_text(encoding="utf-8")
            ch3_skill.write_text(orig_ch3 + "\n参考ADR-0038规范。\n", encoding="utf-8")
            res_bare = alignment._audit_docs_skills_and_adrs(base)
            self.assertFalse(res_bare["ok"])
            self.assertTrue(res_bare["bare_adr_0038_hits"])
            self._assert_six_field_diag(res_bare["diagnostics"][0])
            ch3_skill.write_text(orig_ch3, encoding="utf-8")

            # 2. Emptying a single SKILL.md -> must fail per-Skill coverage check.
            ch4_skill = base / ".agents/skills/workflow-chapter4-overlays-contracts-baseline/SKILL.md"
            orig_ch4 = ch4_skill.read_text(encoding="utf-8")
            ch4_skill.write_text("# Empty Skill\n", encoding="utf-8")
            res_empty_skill = alignment._audit_docs_skills_and_adrs(base)
            self.assertFalse(res_empty_skill["ok"])
            self.assertTrue(res_empty_skill["per_skill_failures"])
            ch4_skill.write_text(orig_ch4, encoding="utf-8")

            # 3. Injecting literal ```\n or unclosed code fence -> must fail AC-3.
            ch4_skill.write_text(orig_ch4 + "\n```powershell\necho hi\n```\\n\n", encoding="utf-8")
            res_fence = alignment._audit_docs_skills_and_adrs(base)
            self.assertFalse(res_fence["ok"])
            self.assertTrue(res_fence["fence_errors"])
            ch4_skill.write_text(orig_ch4, encoding="utf-8")

            # 4. Promote Proposed ADR (ADR-0053) into tail Accepted section -> must fail with conflict.
            adr_idx = base / "docs/architecture/ADR_INDEX_GODOT.md"
            orig_idx = adr_idx.read_text(encoding="utf-8")
            adr_idx.write_text(
                orig_idx + "\n- ADR-0053: Illegally promoted into tail Accepted section\n",
                encoding="utf-8",
            )
            res_prop = alignment._audit_docs_skills_and_adrs(base)
            self.assertFalse(res_prop["ok"])
            self.assertTrue(any(p["adr"] == "ADR-0053" for p in res_prop["proposed_adrs_misclassified_as_accepted"]))
            adr_idx.write_text(orig_idx, encoding="utf-8")

            # 5. Conflicting Accepted + Draft ADR status -> classified as conflict, never accepted.
            conflict_adr = base / "docs/adr/ADR-0099-conflict-probe.md"
            conflict_adr.write_text("# ADR-0099\n- Status: Accepted\n- Status: Draft\n", encoding="utf-8")
            res_conf = alignment._audit_docs_skills_and_adrs(base)
            self.assertFalse(res_conf["ok"])
            self.assertTrue(any(a["status"] == "conflict" for a in res_conf["adr_anomalies"]))
            conflict_adr.unlink()

            # 6. Unknown dev_cli.py subcommand, unknown flag, and broken link -> all fail AC-3.
            mig_doc = base / alignment.MIGRATION_DOC_PATH
            orig_mig = mig_doc.read_text(encoding="utf-8")
            mig_doc.write_text(
                orig_mig
                + "\n`py -3 -B scripts/python/dev_cli.py nonexistent-subcmd`\n"
                + "`py -3 -B scripts/python/dev_cli.py b-route-consumer-alignment --fake-flag`\n"
                + "[broken](nonexistent-file-409.md)\n",
                encoding="utf-8",
            )
            res_cli = alignment._audit_docs_skills_and_adrs(base)
            self.assertFalse(res_cli["ok"])
            self.assertTrue(any(f.get("subcommand") == "nonexistent-subcmd" for f in res_cli["invalid_cli_flags"]))
            self.assertTrue(any(f.get("flag") == "--fake-flag" for f in res_cli["invalid_cli_flags"]))
            self.assertTrue(res_cli["broken_links"])
            mig_doc.write_text(orig_mig, encoding="utf-8")

            # 7. Mutating workflow.md in temp copy sets workflow_md_mutated=True & ok=False.
            wf_copy = base / "workflow.md"
            orig_wf = wf_copy.read_bytes()
            wf_copy.write_bytes(orig_wf + b"\npy -3 -B scripts/python/dev_cli.py b-route-consumer-alignment\n")
            res_wf = alignment._audit_docs_skills_and_adrs(base)
            self.assertFalse(res_wf["ok"])
            self.assertTrue(res_wf["workflow_md_mutated"])
            self.assertTrue(any(d["entity_id"] == "workflow.md" and d["reason_code"] == "conflict" for d in res_wf["diagnostics"]))

    def test_ac4_clean_clone_exclusions_duplicate_codec_and_reparse_guard(self) -> None:
        ac4 = self.live_report["git_layout_and_codec_audit"]
        self.assertTrue(ac4["ok"], ac4["diagnostics"])
        self.assertTrue(ac4["formal_schemas_present"])
        self.assertTrue(ac4["minimal_governance_files_present"])
        self.assertTrue(ac4["logs_excluded_from_knowledge_search"])
        self.assertEqual(ac4["excluded_prefixes_checked"], ["backup", "docs/migration", "logs"])
        self.assertEqual(
            ac4["knowledge_builder_excluded_probe"],
            {"logs/ci/x.json": True, "backup/x.md": True, "docs/migration/x.md": True},
        )
        self.assertTrue(ac4["clean_clone_verified"])
        self.assertEqual(ac4["clean_clone"]["empty_logs_file_count"], 0)
        self.assertTrue(ac4["clean_clone"]["clone_schemas_valid"])
        self.assertTrue(ac4["clean_clone"]["bundle_valid"])
        self.assertTrue(ac4["clean_clone"]["projection_valid"])
        self.assertFalse(ac4["clean_clone"]["requires_logs_committed_in_git"])
        self.assertTrue(ac4["zero_duplicate_codec_verified"])
        self.assertTrue(ac4["generic_b_route_ready_without_reward_hacks"])

        # Negative controls: functional Enum, AnnAssign CODEC_VERSION, unapproved json.loads, Reward hack.
        with tempfile.TemporaryDirectory(prefix="nr-align-ac4-neg-") as tmpdir:
            tmp_root = Path(tmpdir)
            for rel in (
                "docs/workflows/chapter3-source-set.json",
                "knowledge/policies/source-exclusions.v1.json",
                "knowledge/policies/consumer-policies.v1.json",
            ):
                dst = tmp_root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO_ROOT / rel, dst)
            shutil.copytree(REPO_ROOT / "docs/planning/b-route/schemas", tmp_root / "docs/planning/b-route/schemas")
            (tmp_root / "scripts/python").mkdir(parents=True, exist_ok=True)
            (tmp_root / "scripts/python/_b_route_fake_dup.py").write_text(
                "import json\nfrom enum import Enum\nReasonCode = Enum('ReasonCode', ['OK'])\n"
                "CODEC_VERSION: str = 'dup'\ndef parse(s):\n    return json.loads(s)\n",
                encoding="utf-8",
            )
            (tmp_root / "scripts/python/_b_route_fake_hack.py").write_text(
                "def bypass_reward_gate():\n    return True\n",
                encoding="utf-8",
            )
            bad_ac4 = alignment._audit_git_layout_clean_clone_and_codec(tmp_root, probe_temp_contracts=False)
            self.assertFalse(bad_ac4["ok"])
            self.assertFalse(bad_ac4["clean_clone_verified"])
            self.assertFalse(bad_ac4["zero_duplicate_codec_verified"])
            self.assertFalse(bad_ac4["generic_b_route_ready_without_reward_hacks"])
            kinds = {v["kind"] for v in bad_ac4["duplicate_codec_violations"]}
            self.assertIn("duplicate_functional_enum", kinds)
            self.assertIn("duplicate_codec_constant", kinds)
            self.assertIn("unapproved_private_json_loads", kinds)

        # Reparse/junction guard on --report, broken junction on --root, reserved dirs, and no-overwrite.
        with tempfile.TemporaryDirectory(prefix="nr-align-reparse-") as tmpdir:
            tmp_root = Path(tmpdir)
            outside = tmp_root / "outside_target"
            junction = tmp_root / "logs/ci/2026-11-26/reparse_dir"
            _create_dir_reparse(junction, outside)
            try:
                with self.assertRaises(codec.CodecError) as ctx:
                    alignment.write_alignment_report(
                        tmp_root, "logs/ci/2026-11-26/reparse_dir/report.json", {"ok": True},
                    )
                self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.UNSAFE_PATH)
            finally:
                _remove_dir_reparse(junction)

            # Broken junction on --root must emit UNSAFE_PATH (not FILE_NOT_FOUND).
            missing_target = tmp_root / "never_created_target"
            broken_root_junc = tmp_root / "broken_root_junction"
            _create_dir_reparse(broken_root_junc, missing_target, create_target=False)
            try:
                with self.assertRaises(codec.CodecError) as ctx_broken:
                    alignment.audit_b_route_consumer_alignment(broken_root_junc, probe_temp_contracts=False)
                self.assertEqual(ctx_broken.exception.diagnostic.reason_code, codec.ReasonCode.UNSAFE_PATH)
            finally:
                _remove_dir_reparse(broken_root_junc)

            # Reserved producer directories (including newly guarded logs/ci/chapter5) must be rejected.
            for reserved_rel in ("logs/ci/b-route-operations/report.json", "logs/ci/chapter5/report.json"):
                with self.assertRaises(codec.CodecError) as ctx2:
                    alignment.write_alignment_report(tmp_root, reserved_rel, {"ok": True})
                self.assertEqual(ctx2.exception.diagnostic.reason_code, codec.ReasonCode.UNSAFE_PATH)

            # Valid --report writes matching report_path; second write to same path fails with CONFLICT.
            report_rel = "logs/ci/2026-11-26/alignment-probe-out.json"
            payload_obj = {"schema_version": alignment.SCHEMA_VERSION, "ok": True}
            written = alignment.write_alignment_report(tmp_root, report_rel, payload_obj)
            self.assertEqual(payload_obj["report_path"], report_rel)
            on_disk = json.loads(written.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["report_path"], report_rel)
            self.assertEqual(on_disk, payload_obj)
            with self.assertRaises(codec.CodecError) as ctx_dup:
                alignment.write_alignment_report(tmp_root, report_rel, {"ok": True})
            self.assertEqual(ctx_dup.exception.diagnostic.reason_code, codec.ReasonCode.CONFLICT)

    def test_ac5_pre_switch_report_invariants_and_cli_forbids_switch_flags(self) -> None:
        report = self.live_report
        pre = report["pre_switch_coverage_report"]
        self.assertTrue(pre["epic4_alignment_ready"])
        self.assertTrue(pre["generic_b_route_ready_without_reward_hacks"])
        self.assertTrue(pre["switch_blocked"])
        self.assertFalse(pre["default_b_enabled"])
        self.assertFalse(pre["a_write_compatibility_retired"])
        self.assertFalse(pre["second_state_machine_created"])
        self.assertFalse(report["runtime_verified"])
        self.assertFalse(report["implicit_global_refresh_performed"])
        self.assertEqual(pre["epic5_remaining_gates"], list(alignment.EPIC5_REMAINING_GATES))

        sample = pre["evidence_locators"][0]
        actual_sha = "sha256:" + hashlib.sha256((REPO_ROOT / sample["module_path"]).read_bytes()).hexdigest()
        self.assertEqual(sample["sha256"], actual_sha)

        # CLI & dev_cli_builders forbid all switch/write/publish/refresh flags.
        for bad_flag in ("--apply", "--switch-default-b", "--retire-a", "--write-tasks", "--publish", "--refresh-knowledge"):
            with self.subTest(flag=bad_flag):
                proc = subprocess.run(
                    [sys.executable, "-B", str(REPO_ROOT / "scripts/python/dev_cli.py"), "b-route-consumer-alignment", bad_flag],
                    capture_output=True, text=True, encoding="utf-8", cwd=str(REPO_ROOT), check=False,
                )
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                payload = json.loads(proc.stdout)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["reason_code"], "conflict")
                self._assert_six_field_diag(payload["diagnostics"][0])

        with self.assertRaises(ValueError):
            dev_cli_builders.build_b_route_consumer_alignment_cmd(SimpleNamespace(root=".", switch_default_b=True))

        # --skip-live-probes MUST fail closed (ok=False, epic4_alignment_ready=False, CLI exit 2).
        cmd = dev_cli_builders.build_b_route_consumer_alignment_cmd(
            SimpleNamespace(root=str(REPO_ROOT), skip_live_probes=True, report=None),
        )
        self.assertIn("--skip-live-probes", cmd)
        proc_skip = subprocess.run(
            [sys.executable, "-B", str(REPO_ROOT / "scripts/python/dev_cli.py"), "b-route-consumer-alignment", "--skip-live-probes"],
            capture_output=True, text=True, encoding="utf-8", cwd=str(REPO_ROOT), check=False,
        )
        self.assertEqual(proc_skip.returncode, 2, proc_skip.stdout + proc_skip.stderr)
        cli_payload = json.loads(proc_skip.stdout)
        self.assertFalse(cli_payload["ok"])
        self.assertFalse(cli_payload["five_state_version_contract"]["ok"])
        self.assertFalse(cli_payload["five_state_version_contract"]["legacy_a_bounded_to_frozen_scope"])
        self.assertFalse(cli_payload["git_layout_and_codec_audit"]["clean_clone_verified"])
        self.assertFalse(cli_payload["pre_switch_coverage_report"]["epic4_alignment_ready"])
        self.assertTrue(cli_payload["diagnostics"])
        self._assert_six_field_diag(cli_payload["diagnostics"][0])

        parser = dev_cli.build_parser()
        parsed = parser.parse_args(["b-route-consumer-alignment", "--skip-live-probes"])
        self.assertEqual(parsed.cmd, "b-route-consumer-alignment")
        self.assertTrue(parsed.skip_live_probes)


if __name__ == "__main__":
    unittest.main()
