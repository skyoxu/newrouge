"""Offline deterministic unit and E2E tests for <=70,000-byte 3B segmentation.

Covers:
1. Story 25 AST and 52-symbol semantic lock verification against staged track_b.
2. Real sc25 (440,014-byte inputs.json) prepare -> generate (Stages 1/2/3/4/5/6a)
   -> review -> verify-selection -> handoff.json, asserting every single
   workspace_payload is <= 70,000 UTF-8 bytes and all paths fit Windows 259-char
   budget.
3. Run 2 0-call mvg-recovery reuse hit, constraint drift rejection, clear epoch
   increment, and reopen revocation.
4. Stage 6b initial adoption-request.v1 full lifecycle (review-prepare ->
   review-complete -> prepare -> reserve -> apply -> verify -> publish ->
   read --context) for BOTH non-mechanical (> 70,000-byte segmented review with
   machine_mode is None + blocked fail-closed rejection) AND mechanical
   (machine_mode == "new_plan_exact_native_projection", 0 model calls).
"""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

NEWROUGE_ROOT = Path(__file__).resolve().parents[3]
NEWROUGE_PYTHON = (NEWROUGE_ROOT / "scripts/python").resolve()
NEWROUGE_TESTS = (NEWROUGE_PYTHON / "tests").resolve()

for entry in (str(NEWROUGE_PYTHON), str(NEWROUGE_TESTS)):
    if entry in sys.path:
        sys.path.remove(entry)
sys.path[:0] = [str(NEWROUGE_PYTHON), str(NEWROUGE_TESTS)]

import _b_route_3b_segmented_input as seg_input
import _b_route_3b_segmented_runtime as seg_runtime
import _b_route_adoption as adoption
import _b_route_adoption_review as adoption_review
import _b_route_candidate as candidate
import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_completed_reuse as reuse
import _b_route_planning_input as planning
import _b_route_planning_runtime as runtime
import _b_route_protection as protection
import _b_route_records as records
import _b_route_source_audit as audit
import b_route_adoption as adoption_cli
import plan_capabilities
import plan_mvg
from test_b_route_records import ORIGINS, POLICY, MatrixFixture, encoded

SC25_REL = "logs/ci/2026-11-12/b-route-planning-input/sc25/347a984ba1e3e23266004e095be33f47a148bb7ce40d7fe132bd7bf700876dce"
SC25_EXPECTED_IDENTITY = "sha256:347a984ba1e3e23266004e095be33f47a148bb7ce40d7fe132bd7bf700876dce"
HANDOFF_BASELINE_COMMIT = "50e7e58ffdccca2d755c34563a9816708e4769e5"


def _temp_dir_base() -> str | None:
    base = os.environ.get("BR_TEST_TEMP") or os.environ.get("ADOPTION_TEST_TEMP")
    if base:
        Path(base).mkdir(parents=True, exist_ok=True)
        return base
    return None


FAKE_CODEX_SCRIPT = r'''#!/usr/bin/env python3
"""Deterministic offline Codex/Gemini CLI responder enforcing <= 70,000 UTF-8 bytes."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re
import sys
import uuid

sys.dont_write_bytecode = True

MAX_BYTES = int(os.environ.get("FAKE_PROVIDER_MAX_BYTES", "70000"))


def _const_val(node: dict | None, default=None):
    if not isinstance(node, dict):
        return default
    if "const" in node:
        return node["const"]
    if "enum" in node and isinstance(node["enum"], list) and len(node["enum"]) == 1:
        return node["enum"][0]
    return default


def _extract_embedded_json(prompt_text: str) -> dict | None:
    lines = prompt_text.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("{") and ("wire_delivery" in stripped or "schema_version" in stripped or "segmented_" in stripped):
            try:
                return json.loads("\n".join(lines[idx:]))
            except Exception:
                pass
    for idx in range(len(lines) - 1, -1, -1):
        if lines[idx].lstrip().startswith("{"):
            chunk = "\n".join(lines[idx:])
            try:
                val = json.loads(chunk)
                if isinstance(val, dict):
                    return val
            except Exception:
                continue
    return None


def _build_turn_response(
    prompt_text: str, output_schema: dict, state_dir: Path, cwd_val: str
) -> tuple[str, dict]:
    utf8_bytes = len(prompt_text.encode("utf-8"))
    if utf8_bytes > MAX_BYTES:
        raise RuntimeError(f"FAKE_PROVIDER_PAYLOAD_EXCEEDED_70K:{utf8_bytes}")

    props = output_schema.get("properties", {})
    stage_label = "unknown"

    def _load_wire():
        repo_py = os.environ.get("FAKE_NEWROUGE_PYTHON")
        if repo_py and repo_py not in sys.path:
            sys.path.insert(0, repo_py)
        import _b_route_planning_wire as _w

        return _w

    snap_marker = "\n\nThe following is the complete model-visible workspace snapshot."

    # Case 1: 3B Generation / Rolling Compaction / Tree-Reduce / Synthesis / Repair
    if "producer_schema_version" in props and "content_json" in props:
        raw_prompt = prompt_text.split(snap_marker, 1)[0]
        input_id = _const_val(props["input_identity"])
        stage_const = _const_val(props["stage"])
        ordinal = _const_val(props["ordinal"])

        pdi_schema = props["parent_draft_identities"]
        expected_pdi_len = pdi_schema.get("maxItems")
        parent_ids = None
        if expected_pdi_len == 0:
            parent_ids = []
        elif "const" in pdi_schema:
            parent_ids = list(pdi_schema["const"])
        elif expected_pdi_len == 1 and "enum" in pdi_schema.get("items", {}):
            parent_ids = list(pdi_schema["items"]["enum"])
        elif isinstance(expected_pdi_len, int):
            pdi_m = re.search(r"'parent_draft_identities':\[([^\]]*)\]", raw_prompt)
            if pdi_m:
                found_ids = re.findall(r"sha256:[0-9a-f]{64}", pdi_m.group(1))
                if len(found_ids) == expected_pdi_len:
                    parent_ids = found_ids

        slot_name = (
            "candidate-1"
            if "'candidate-1'" in raw_prompt
            else ("candidate-2" if "'candidate-2'" in raw_prompt else "candidate-3")
        )

        if stage_const == "batch":
            if parent_ids is None:
                wire = _load_wire()
                wd_match = re.search(r"newrouge\.b-route-planning-wire\.v\d+", raw_prompt)
                wd = wd_match.group(0) if wd_match else wire.CURRENT_SCHEMA
                parent_ids = list(
                    wire.read_prompt(raw_prompt, wd).get("root_request", {}).get("parent_draft_identities", [])
                )
            stage_label = "stage1_2_batch"
            # On candidate-1 ordinals 1, 2 during sc25 r1, emit ~30 KB distinct notes to force window rollover + tree_reduce!
            if (
                slot_name == "candidate-1"
                and ordinal in (1, 2)
                and (state_dir / "enable_stage4_repair.flag").exists()
            ):
                pad = "".join(
                    f"item-{ordinal}-{i:04d}-{(i * 104729 + ordinal * 7919) & 0xffffff:06x}-"
                    for i in range(1350)
                )
            else:
                pad = f"batch-{ordinal}-notes"
            content_obj = {
                "batch_ordinal": ordinal,
                "slot": slot_name,
                "accumulated_notes": pad,
            }
        elif parent_ids is not None and "'bounded_repair'" not in raw_prompt and "'repair_scope':" not in raw_prompt:
            if "'rolling_compaction'" in raw_prompt or "'tree_reduce'" in raw_prompt:
                stage_label = "stage1_2_rolling_or_tree_reduce"
                content_obj = {
                    "compacted_at_ordinal": ordinal,
                    "slot": slot_name,
                    "summary": "compact-rolling-state",
                }
            else:
                stage_label = "stage3_synthesis"
                template_map = json.loads((state_dir / "candidate_templates.json").read_text(encoding="utf-8"))
                base_content = template_map["default"]
                content_obj = json.loads(json.dumps(template_map.get(slot_name, base_content)))
        else:
            wire = _load_wire()
            wd_match = re.search(r"newrouge\.b-route-planning-wire\.v\d+", raw_prompt)
            wd = wd_match.group(0) if wd_match else wire.CURRENT_SCHEMA
            materials = wire.read_prompt(raw_prompt, wd)
            root_req = materials.get("root_request", {})
            parent_ids = list(root_req.get("parent_draft_identities", []))
            synthesis_role = root_req.get("synthesis_role") or root_req.get("substage", stage_const)
            template_map = json.loads((state_dir / "candidate_templates.json").read_text(encoding="utf-8"))
            base_content = template_map["default"]
            slot_name = materials.get("slot") or "candidate-1"
            has_repair = materials.get("repair_issue") is not None or synthesis_role == "bounded_repair"

            # Distinguish rolling_compaction / tree_reduce vs final_synthesis vs repair
            if has_repair:
                stage_label = "stage4_repair"
                content_obj = json.loads(json.dumps(template_map.get(slot_name, base_content)))
                allowed_paths = materials.get("repair_scope", {}).get("allowed_content_paths", [])
                updated_any = False
                for p in allowed_paths:
                    if (
                        isinstance(p, list)
                        and len(p) == 2
                        and p[0] in ("requirement_verification", "coverage_table", "applicability")
                        and isinstance(p[1], int)
                    ):
                        content_obj[p[0]][p[1]]["rationale"] = (
                            "Repaired flow rationale explicitly aligned with durable journal J."
                        )
                        updated_any = True
                if not updated_any:
                    for sec in ("requirement_verification", "coverage_table", "applicability"):
                        for row in content_obj.get(sec, [])[:1]:
                            row["rationale"] = "Repaired flow rationale explicitly aligned with durable journal J."
            elif synthesis_role in ("rolling_compaction", "tree_reduce"):
                stage_label = "stage1_2_rolling_or_tree_reduce"
                content_obj = {
                    "compacted_at_ordinal": ordinal,
                    "slot": slot_name,
                    "summary": "compact-rolling-state",
                }
            else:
                stage_label = "stage3_synthesis"
                content_obj = json.loads(json.dumps(template_map.get(slot_name, base_content)))

        response_obj = {
            "schema_version": _const_val(props["schema_version"]),
            "producer_schema_version": _const_val(props["producer_schema_version"]),
            "input_identity": input_id,
            "stage": stage_const,
            "ordinal": ordinal,
            "parent_draft_identities": parent_ids,
            "content_json": json.dumps(content_obj, ensure_ascii=False, separators=(",", ":")),
        }
        return stage_label, response_obj

    # Case 2: Stage 5 Segmented Indexed Independent Admission Review
    if str(_const_val(props.get("schema_version"), "")).startswith(
        "newrouge.b-route-indexed-independent-review."
    ):
        wire = _load_wire()
        stage_label = "stage5_review"
        raw_prompt = prompt_text.split(snap_marker, 1)[0]
        wd_match = re.search(r"newrouge\.b-route-planning-wire\.v\d+", raw_prompt)
        wd = wd_match.group(0) if wd_match else wire.CURRENT_SCHEMA
        materials = wire.read_prompt(raw_prompt, wd)
        seg_obs = materials["obligations"]
        ob_count = props["checks"].get("minItems", len(seg_obs))
        seg_srcs = materials["qualified_sources"]
        src_idx_map = {row["id"]: idx for idx, row in enumerate(seg_srcs)}
        slot_name = materials.get("slot", "")
        repair_issue = materials.get("repair_issue")
        seg_index = materials["root_request"]["segment_index"]

        block_marker = state_dir / "triggered_stage4_repair.flag"
        inject_block = (
            slot_name == "candidate-1"
            and repair_issue is None
            and seg_index == 1
            and not block_marker.exists()
            and (state_dir / "enable_stage4_repair.flag").exists()
        )
        block_idx = -1
        if inject_block:
            block_marker.write_text("1", encoding="utf-8")
            block_idx = next(
                (
                    i
                    for i, ob in enumerate(seg_obs)
                    if isinstance(ob.get("target"), list) and ob["target"] and ob["target"][0] == "requirement"
                ),
                0,
            )

        checks = []
        findings = []
        for idx, ob in enumerate(seg_obs):
            cited = [src_idx_map[sid] for sid in ob["source_block_ids"] if sid in src_idx_map]
            if not cited:
                cited = [0]
            if inject_block and idx == block_idx:
                rationale = f"Requirement obligation {ob['id']} requires explicit journal J rationale."
                checks.append(
                    {
                        "id": idx,
                        "verdict": "blocked",
                        "rationale": rationale,
                        "source_block_ids": cited[:1],
                    }
                )
                findings.append(rationale)
            else:
                checks.append(
                    {
                        "id": idx,
                        "verdict": "approved",
                        "rationale": f"Verified {ob['id']} against governed source blocks.",
                        "source_block_ids": cited[:1],
                    }
                )
        assert len(checks) == ob_count
        response_obj = {
            "schema_version": _const_val(props["schema_version"]),
            "input_identity": _const_val(props["input_identity"]),
            "runtime_identity": _const_val(props["runtime_identity"]),
            "proposal_sha256": _const_val(props["proposal_sha256"]),
            "verdict": "blocked" if findings else "approved",
            "findings": findings,
            "checks": checks,
        }
        if "reopen_reviews" in props:
            variants = props["reopen_reviews"].get("items", {}).get("anyOf", [])
            response_obj["reopen_reviews"] = [
                {
                    "conflict_id": _const_val(v["properties"]["conflict_id"]),
                    "plan_sha256": _const_val(v["properties"]["plan_sha256"]),
                    "verdict": "resolved",
                    "rationale": "Conflict resolved cleanly.",
                }
                for v in variants
            ]
        return stage_label, response_obj

    # Case 3: Stage 6a Anonymous Selection (single-turn, pairwise tournament, and Turn-3 synthesis)
    if "candidate_reviews" in props and _const_val(props.get("status")) == "selected":
        stage_label = "stage6a_selection"
        aliases = list(props["selected"]["enum"])
        raw_prompt = prompt_text.split(snap_marker, 1)[0]
        chosen = aliases[0]
        if "tournament_synthesis" in raw_prompt or "selection_pair" in raw_prompt:
            wire = _load_wire()
            wd_match = re.search(r"newrouge\.b-route-planning-wire\.v\d+", raw_prompt)
            wd = wd_match.group(0) if wd_match else wire.CURRENT_SCHEMA
            materials = wire.read_prompt(raw_prompt, wd)
            if materials.get("tournament_synthesis") and isinstance(materials.get("pairwise_verdicts"), dict):
                chosen = materials["pairwise_verdicts"]["bracket_winner"]
                if (state_dir / "force_tournament_bracket_mismatch.flag").exists():
                    chosen = next((a for a in aliases if a != chosen), chosen)
            elif materials.get("phase") == "selection_pair" and (state_dir / "tournament_pick_second.flag").exists():
                chosen = aliases[-1]
        ordered = [chosen, *[a for a in aliases if a != chosen]]
        response_obj = {
            "status": "selected",
            "selected": chosen,
            "candidate_reviews": [
                {
                    "candidate": alias,
                    "rank": idx + 1,
                    "verdict": "viable",
                    "rationale": f"Candidate {alias} satisfies all governed obligations cleanly.",
                }
                for idx, alias in enumerate(ordered)
            ],
        }
        return stage_label, response_obj

    # Case 4: Stage 6b Adoption Review (single or segmented)
    schema_const = str(_const_val(props.get("schema_version"), ""))
    if schema_const in (
        "newrouge.b-route-adoption-review-verdict.v1",
        "newrouge.b-route-segmented-adoption-review-verdict.v1",
    ):
        stage_label = "stage6b_adoption_review"
        req_checks = list(props["checks"]["items"]["properties"]["id"]["enum"])
        force_block = (state_dir / "force_stage6b_block.flag").exists()
        checks = []
        findings = []
        for idx, cid in enumerate(req_checks):
            if force_block and idx == 0:
                rat = f"Injected Stage 6b semantic block on {cid} for fail-closed verification."
                checks.append({"id": cid, "verdict": "blocked", "rationale": rat})
                findings.append(rat)
            else:
                checks.append(
                    {
                        "id": cid,
                        "verdict": "approved",
                        "rationale": f"Independently verified {cid} against governed adoption subject.",
                    }
                )
        response_obj = {
            "schema_version": schema_const,
            "subject_digest": _const_val(props["subject_digest"]),
            "verdict": "blocked" if findings else "approved",
            "findings": findings,
            "checks": checks,
        }
        if "plan_digest" in props:
            response_obj["plan_digest"] = _const_val(props["plan_digest"])
        if "segment_id" in props:
            response_obj["segment_id"] = _const_val(props["segment_id"])
        return stage_label, response_obj

    raise RuntimeError(f"Unsupported schema in fake codex: {list(props)}")


def _run_gemini_stream_mode(state_dir: Path, log_path: Path, uid: str) -> int:
    model = "gemini-4-carbon-high"
    if "-m" in sys.argv:
        idx = sys.argv.index("-m")
        if idx + 1 < len(sys.argv):
            model = sys.argv[idx + 1]
    if os.environ.get("FAKE_GEMINI_MODEL_OVERRIDE"):
        model = os.environ["FAKE_GEMINI_MODEL_OVERRIDE"]
    sys_md_path = os.environ.get("GEMINI_SYSTEM_MD") or ""
    if not sys_md_path or not Path(sys_md_path).is_file():
        sys.stderr.write("Missing GEMINI_SYSTEM_MD\n")
        return 2
    sys_md = Path(sys_md_path).read_text(encoding="utf-8")
    marker = "Requested JSON Schema:\n"
    if marker not in sys_md:
        sys.stderr.write("Missing Requested JSON Schema in GEMINI_SYSTEM_MD\n")
        return 2
    output_schema = json.loads(sys_md.split(marker, 1)[1].strip())
    prompt_text = sys.stdin.read()
    utf8_bytes = len(prompt_text.encode("utf-8"))
    cwd_val = os.getcwd()
    stage_label, output_obj = _build_turn_response(prompt_text, output_schema, state_dir, cwd_val)
    output_text = json.dumps(output_obj, ensure_ascii=False, separators=(",", ":"))
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "provider": "google",
                    "stage": stage_label,
                    "utf8_bytes": utf8_bytes,
                    "cwd": cwd_val,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    session_id = f"gem-sess-70k-{uid}"
    events = (
        {"type": "init", "timestamp": "2026-11-14T00:00:00Z", "session_id": session_id, "model": model},
        {"type": "message", "timestamp": "2026-11-14T00:00:01Z", "role": "user", "content": prompt_text},
        {"type": "message", "timestamp": "2026-11-14T00:00:02Z", "role": "assistant", "content": output_text, "delta": True},
        {"type": "result", "timestamp": "2026-11-14T00:00:03Z", "status": "success", "stats": {"tool_calls": 0, "total_tokens": 42}},
    )
    for ev in events:
        sys.stdout.write(json.dumps(ev, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


def main() -> int:
    if "--version" in sys.argv:
        print("codex-cli 0.1.0-offline-test")
        return 0
    state_dir = Path(os.environ["FAKE_CODEX_STATE_DIR"])
    log_path = state_dir / "turns.jsonl"
    uid = uuid.uuid4().hex[:12]
    if "stream-json" in sys.argv:
        return _run_gemini_stream_mode(state_dir, log_path, uid)
    if "app-server" not in sys.argv:
        sys.stderr.write("Expected app-server or stream-json mode\n")
        return 2

    thread_id = f"thr-offline-70k-{uid}"
    cwd_val = os.getcwd()
    reasoning_val = "high"

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        msg = json.loads(line)
        req_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}

        if method == "initialize":
            resp = {"id": req_id, "result": {"serverInfo": {"name": "fake-codex", "version": "1.0"}}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        elif method == "initialized":
            continue
        elif method == "mcpServerStatus/list":
            resp = {"id": req_id, "result": {"data": [], "nextCursor": None}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        elif method == "thread/start":
            cwd_val = params.get("cwd", cwd_val)
            cfg = params.get("config") or {}
            if "model_reasoning_effort" in cfg:
                reasoning_val = cfg["model_reasoning_effort"]
            resp = {
                "id": req_id,
                "result": {
                    "model": "gpt-5.4",
                    "modelProvider": "openai",
                    "cwd": cwd_val,
                    "reasoningEffort": reasoning_val,
                    "sandbox": {"type": "readOnly"},
                    "thread": {
                        "id": thread_id,
                        "ephemeral": True,
                        "cwd": cwd_val,
                        "model": "gpt-5.4",
                        "modelProvider": "openai",
                        "turns": [],
                    },
                },
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        elif method == "turn/start":
            turn_id = f"turn-offline-70k-{uid}"
            prompt_text = params["input"][0]["text"]
            output_schema = params["outputSchema"]
            utf8_bytes = len(prompt_text.encode("utf-8"))
            stage_label, output_obj = _build_turn_response(prompt_text, output_schema, state_dir, cwd_val)
            output_text = json.dumps(output_obj, ensure_ascii=False, separators=(",", ":"))

            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "provider": "openai",
                            "stage": stage_label,
                            "utf8_bytes": utf8_bytes,
                            "cwd": cwd_val,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            sys.stdout.write(
                json.dumps({"id": req_id, "result": {"turn": {"id": turn_id, "status": "inProgress", "items": []}}})
                + "\n"
            )
            msg_item = {"id": "msg-001", "type": "agentMessage", "text": output_text}
            for notif in (
                {"method": "turn/started", "params": {"threadId": thread_id, "turn": {"id": turn_id}}},
                {"method": "item/started", "params": {"threadId": thread_id, "turnId": turn_id, "item": {"id": "msg-001", "type": "agentMessage", "text": ""}}},
                {"method": "item/completed", "params": {"threadId": thread_id, "turnId": turn_id, "item": msg_item}},
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": thread_id,
                        "turn": {"id": turn_id, "status": "completed", "error": None, "items": [msg_item]},
                    },
                },
            ):
                sys.stdout.write(json.dumps(notif, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _build_sc25_candidate_content(frozen: dict, *, variant: str = "A") -> dict:
    gp = frozen["inputs"]["global_proof"]
    deps = frozen["inputs"]["dependencies"]["files"]
    manifest_path = next(k for k in deps if k.endswith("source-manifest.json"))
    ledger_path = next(k for k in deps if k.endswith("source-blocks.json"))
    proposals = gp["proposals"]["proposals"]
    all_block_ids = [b["block_id"] for b in gp["ledger"]["blocks"]]

    def owned(owner: str, path: str) -> dict:
        return {"owner": owner, "ref": path, "files": [{"path": path, "raw_digest": deps[path]}]}

    fid = f"FLOW-EXCL-RES-{variant}"
    owner = {"kind": "flow", "definition_id": fid, "proposed_owner_key": f"reward-controller-{variant.lower()}"}

    def point(node: str) -> dict:
        return {"flow_id": fid, "node_id": node}

    nodes = [
        {
            "id": n,
            "responsibility": f"Handle {n} state in exclusive reward resolution ({variant}).",
            "owner": deepcopy(owner),
            "command_uses": [],
            "state_uses": [],
        }
        for n in ("entry", "act", "success")
    ]
    edges = [
        {
            "id": f"edge-{i}",
            "from": point(a),
            "to": point(b),
            "condition": f"{a}->{b}",
            "responsibility": "Atomic journal transition",
            "owner": deepcopy(owner),
        }
        for i, (a, b) in enumerate((("entry", "act"), ("act", "success")))
    ]
    boundaries = [
        {
            "id": n,
            "kind": n,
            "node": point(n),
            "condition": f"{n} boundary",
            "required": True,
            "rationale": "Governed source boundary",
        }
        for n in ("entry", "success")
    ]
    ob_na = {
        "applicability": "not_applicable",
        "rationale": "Pure deterministic controller and journal verification.",
        "responsibilities": [],
        "owner": deepcopy(owner),
    }
    flow_obj = {
        "id": fid,
        "proposed_owner_key": f"reward-controller-{variant.lower()}",
        "requirement_ids": [p["proposal_id"] for p in proposals],
        "capability_ids": ["controlled-exclusive-resolution-v15"],
        "source_block_ids": all_block_ids,
        "entry_condition": "Scenario provisioned with empty durable journal J and fixed reward R.",
        "branches": [
            {
                "kind": k,
                "applicability": "not_applicable",
                "rationale": "Handled via immutable single-append journal semantics.",
                "boundary_ids": [],
            }
            for k in ("failure", "cancel", "return")
        ],
        "handoffs": [],
        "state_owners": [],
        "parts": [
            {
                "kind": k,
                "applicability": "applicable" if k == "domain_rules" else "not_applicable",
                "rationale": "Source-backed exclusive resolution rules.",
                "responsibilities": ["Enforce atomic Commit(R) or Cancel(R)"] if k == "domain_rules" else [],
            }
            for k in sorted(candidate.PARTS)
        ],
        "observable_result": f"Exclusive Commit(R) or Cancel(R) recorded once ({variant}).",
        "verification_targets": ["Verify exclusive journal state and idempotent UI restore"],
        "ui": {**deepcopy(ob_na), "inputs": [], "feedback": [], "scene_entry": [], "scene_return": []},
        "human_verification": deepcopy(ob_na),
        "graph": {"nodes": nodes, "edges": edges, "boundaries": boundaries, "loops": []},
    }
    reqs, verifs, covs, routes, appls = [], [], [], [], []
    for p in proposals:
        rid = p["proposal_id"]
        reqs.append(
            {
                "requirement_id": rid,
                "source_block_ids": deepcopy(p["source_block_ids"]),
                "acceptance_intent": p["acceptance_intent"],
                "prior_requirement_ids": deepcopy(p["prior_requirement_ids"]),
                "non_task_sinks": deepcopy(p["non_task_sinks"]),
            }
        )
        v = {
            "requirement_id": rid,
            "disposition": "flow",
            "flow_id": fid,
            "rationale": f"Verified through exclusive resolution flow {fid}.",
            "sink_id": None,
            "verification_ref": None,
            "authority_ref": None,
            "evidence_ids": [],
        }
        verifs.append(v)
        covs.append({k: val for k, val in v.items() if k != "evidence_ids"})
        routes.append({"requirement_id": rid, "flow_id": fid, "observable_role": "Exclusive reward resolution"})
        appls.append(
            {
                "requirement_id": rid,
                "disposition": "flow",
                "rationale": v["rationale"],
                "other_verification_refs": [],
            }
        )
    return {
        "source_identity": {
            "manifest_ref": owned("source_manifest", manifest_path),
            "ledger_ref": owned("source_ledger", ledger_path),
            "source_revision": gp["manifest"]["source_revision"],
            "source_manifest_digest": gp["manifest"]["manifest_sha256"],
        },
        "requirements": reqs,
        "out_of_scope_requirement_ids": [],
        "selected_dependencies": [],
        "definitions": {"flows": [flow_obj], "commands": [], "states": []},
        "logical_references": [],
        "requirement_verification": verifs,
        "coverage_table": covs,
        "requirement_route_memberships": routes,
        "requirement_evidence": [],
        "evidence_source_refs": [],
        "applicability": appls,
        "unresolved": [],
        "implementation_objects": [
            {
                "id": f"planned-scene-{variant.lower()}",
                "kind": "scene",
                "availability": "planned",
                "owner": deepcopy(owner),
                "expected_type": f"ExclusiveRewardScene{variant}",
                "lifecycle": "Scenario-scoped scene",
                "target_ref": None,
                "later_checks": ["type", "compile", "binding", "engine"],
            }
        ],
    }


_INV_FIXTURE_CACHE: dict | None = None


def _init_unmocked_protection(root: Path, run_id: str = "prot-01") -> dict:
    """Create a real git-backed protection archive verified by protection.verify_protection."""
    global _INV_FIXTURE_CACHE
    if _INV_FIXTURE_CACHE is None:
        import test_b_route_inventory as inv_test

        fx = inv_test.InventoryTests("runTest")
        fx.setUp()
        try:
            files_map: dict[str, bytes] = {}
            for src in fx.root.rglob("*"):
                if not src.is_file():
                    continue
                rel = src.relative_to(fx.root)
                if ".git" in rel.parts or rel.as_posix() == fx.epics:
                    continue
                files_map[rel.as_posix()] = src.read_bytes()
            _INV_FIXTURE_CACHE = {
                "files": files_map,
                "sources": list(fx.sources),
                "epics": fx.epics,
            }
        finally:
            fx.tearDown()

    for rel_str, raw_bytes in _INV_FIXTURE_CACHE["files"].items():
        dst = root / rel_str
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(raw_bytes)
    sources = list(_INV_FIXTURE_CACHE["sources"])
    epics_rel = _INV_FIXTURE_CACHE["epics"]

    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    }
    subprocess.run(["git", "init", "-q"], cwd=root, env=git_env, check=True)
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=root, env=git_env, check=True)
    subprocess.run(["git", "add", "."], cwd=root, env=git_env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "Fixture baseline"], cwd=root, env=git_env, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, env=git_env, check=True, capture_output=True, text=True
    ).stdout.strip()
    epics_path = root / epics_rel
    epics_path.parent.mkdir(parents=True, exist_ok=True)
    epics_path.write_text(
        "---\nstatus: final\ncodeBaselineCommit: "
        + head
        + "\ninputSnapshotCommit: "
        + head
        + "\ninputDocuments:\n"
        + "".join("  - " + json.dumps(x) + "\n" for x in sources)
        + "---\n# Epics\n",
        encoding="utf-8",
        newline="\n",
    )
    subprocess.run(["git", "add", "."], cwd=root, env=git_env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "Epic inputs"], cwd=root, env=git_env, check=True)

    captured = protection.collect_protection(root, epics_rel)
    out_dir = protection.create_run_directory(root, run_id)
    protection.write_capture(out_dir, captured)
    snap_path = out_dir / "snapshot.json"
    snap_rel = snap_path.relative_to(root).as_posix()
    verified = protection.verify_protection(root, snap_rel)
    if not (verified.get("ok") and verified.get("capture_complete")):
        raise AssertionError(f"Protection archive verification failed: {verified}")
    snap_raw = snap_path.read_bytes()
    snap_doc = codec.strict_json_loads(snap_raw)
    return {
        "path": snap_rel,
        "schema_version": snap_doc["schema_version"],
        "raw_digest": codec.raw_digest(snap_raw),
    }


def _build_adoption_request_from_handoff(
    root: Path,
    *,
    operation_id: str,
    run_id: str,
    handoff_rel: str,
    admission_rel: str,
    protection_ref: dict,
    include_policy_and_origins: bool,
) -> dict:
    from _b_route_adoption_projection import project_content

    handoff_raw = (root / handoff_rel).read_bytes()
    handoff_doc = codec.strict_json_loads(handoff_raw)
    admission_raw = (root / admission_rel).read_bytes()
    admission_doc = codec.strict_json_loads(admission_raw)
    content = deepcopy(handoff_doc["proposal"]["content"])

    req_ids = [r["requirement_id"] for r in content["requirements"]]
    flow_ids = [f["id"] for f in content["definitions"]["flows"]]
    placeholder = {
        "plan_id": "PLAN-TEMPLATE",
        "plan_revision": 123,
        "requirements": {rid: f"RQ-TPL-{i}" for i, rid in enumerate(req_ids, 1)},
        "flows": {fid: f"FLOW-TPL-{i}" for i, fid in enumerate(flow_ids, 1)},
    }
    projected = project_content(content, placeholder)

    fx = MatrixFixture()
    sample_plan_path = fx.add_plan("tpl", 1)
    fx.add_flow(sample_plan_path)
    base_plan = deepcopy(fx.models[sample_plan_path])

    target_plan = {
        **base_plan,
        **projected,
        "plan_id": "PLAN-TEMPLATE",
        "revision": 123,
        "adoption_proof_refs": [
            {
                "owner": "planning_proof",
                "ref": admission_rel,
                "files": [{"path": admission_rel, "raw_digest": codec.raw_digest(admission_raw)}],
            }
        ],
        "native_candidate_ref": {
            "owner": "planning_proof",
            "ref": handoff_rel + "#/proposal/content",
            "files": [{"path": handoff_rel, "raw_digest": codec.raw_digest(handoff_raw)}],
        },
    }

    inv_req = {v: k for k, v in placeholder["requirements"].items()}
    inv_flow = {v: k for k, v in placeholder["flows"].items()}

    def templatize(val, key=None):
        if isinstance(val, dict):
            return {k: templatize(v, k) for k, v in val.items()}
        if isinstance(val, list):
            return [templatize(item, key) for item in val]
        if val == "PLAN-TEMPLATE":
            return {"$allocation": "plan_id"}
        if key in ("revision", "owner_revision") and val == 123:
            return {"$allocation": "plan_revision"}
        if isinstance(val, str) and val in inv_req:
            return {"$allocation": "requirement:" + inv_req[val]}
        if isinstance(val, str) and val in inv_flow:
            return {"$allocation": "flow:" + inv_flow[val]}
        return val

    templates = [
        {
            "path_template": "docs/planning/b-route/plans/{plan_id}/{plan_revision}.json",
            "schema_version": adoption.PLAN,
            "before_raw_digest": None,
            "after_payload": templatize(target_plan),
            "verification_mode": "immutable_bytes",
        }
    ]
    if include_policy_and_origins:
        policy_doc = deepcopy(fx.policy)
        origins_doc = {
            "schema_version": "newrouge.b-route-origins.v1",
            "origins_id": "task-origins",
            "revision": 1,
            "tasks": [],
            "frozen_legacy_refs": [],
        }
        for path, payload in ((POLICY, policy_doc), (ORIGINS, origins_doc)):
            templates.append(
                {
                    "path_template": path,
                    "schema_version": payload["schema_version"],
                    "before_raw_digest": None,
                    "after_payload": payload,
                    "verification_mode": "immutable_bytes",
                }
            )

    return {
        "schema_version": "newrouge.b-route-adoption-request.v1",
        "operation_id": operation_id,
        "material": {
            "planner": "mvg",
            "run_id": run_id,
            "handoff_ref": {
                "path": handoff_rel,
                "schema_version": handoff_doc["schema_version"],
                "raw_digest": codec.raw_digest(handoff_raw),
            },
            "protection_ref": protection_ref,
            "authority_refs": [],
            "lineage_refs": [],
            "identity_alignment": {
                "plan": {"mode": "new"},
                "binding": {"mode": "none"},
                "requirements": [
                    {
                        "candidate_id": rid,
                        "mode": "allocate",
                        "rationale": f"Initial governed allocation for {rid}",
                    }
                    for rid in req_ids
                ],
                "flows": [
                    {
                        "candidate_id": fid,
                        "mode": "allocate",
                        "rationale": f"Initial governed allocation for {fid}",
                    }
                    for fid in flow_ids
                ],
                "tasks": [],
            },
            "target_templates": templates,
        },
        "review_ref": {
            "path": admission_rel,
            "schema_version": admission_doc["schema_version"],
            "raw_digest": codec.raw_digest(admission_raw),
        },
    }


class TrackBSegmented70kTests(unittest.TestCase):
    """Comprehensive verification for Track B 3B <= 70,000-byte segmentation."""

    @classmethod
    def setUpClass(cls):
        cls.env_temp = tempfile.TemporaryDirectory(prefix="tbenv", dir=_temp_dir_base())
        env_root = Path(cls.env_temp.name)
        cls.bin_dir = env_root / "bin"
        cls.bin_dir.mkdir()
        cls.codex_home = env_root / "codex_home"
        cls.codex_home.mkdir()
        cls.boot_dir = env_root / "boot"
        cls.boot_dir.mkdir()
        cls.state_dir = env_root / "codex_state"
        cls.state_dir.mkdir()

        cls.fake_provider_py = cls.bin_dir / "fake_provider_cli.py"
        cls.fake_provider_py.write_text(FAKE_CODEX_SCRIPT, encoding="utf-8")

        # Write sitecustomize.py so child Python subprocesses work identically on Windows & Linux
        # while keeping launch[0]['command'] in _codex_app_server journal unpatched.
        (cls.boot_dir / "sitecustomize.py").write_text(
            "import base64, copy, json, os, subprocess, sys\n"
            "from pathlib import Path\n"
            "sys.dont_write_bytecode = True\n"
            f"_FAKE_PROVIDER = {str(cls.fake_provider_py)!r}\n"
            "_ORIG_POPEN = subprocess.Popen\n"
            "class _CodexRedirectPopen(_ORIG_POPEN):\n"
            "    def __init__(self, args, *a, **kw):\n"
            "        if isinstance(args, (list, tuple)) and args and Path(str(args[0])).stem.lower() == 'codex':\n"
            "            args = [sys.executable, '-B', _FAKE_PROVIDER, *list(args[1:])]\n"
            "        super().__init__(args, *a, **kw)\n"
            "subprocess.Popen = _CodexRedirectPopen\n"
            "seam_path = os.environ.get('FAKE_CODEX_SC25_SEAM_INPUTS')\n"
            "if seam_path and '_mvg_capability_worker' in Path(sys.argv[0]).name:\n"
            "    import _b_route_source_audit as _a, _b_route_planning_input as _pi\n"
            "    _cache = {}\n"
            "    def _get_orig():\n"
            "        if 'v' not in _cache:\n"
            "            _cache['v'] = json.loads(Path(seam_path).read_text(encoding='utf-8'))\n"
            "        return _cache['v']\n"
            "    def _seam(obs, ref, *, scope_id):\n"
            "        _orig = _get_orig()\n"
            "        for _r in _orig['raw_proof_inventory']:\n"
            "            obs.read(_r['path'], optional=_r['raw_digest'] is None)\n"
            "        for _g in _orig['dependencies']['globs']:\n"
            "            obs.watch(_g['patterns'])\n"
            "        _gp = _orig['global_proof']\n"
            "        _sf = [{'path': s['path'], 'raw_digest': s['raw_digest'], 'raw_base64': base64.b64encode(obs.read(s['path'])).decode('ascii'), 'text': obs.read(s['path']).decode('utf-8')} for s in _orig['source_inventory']]\n"
            "        return {'report': _gp['report'], 'bundle': {'files': _sf, 'ledger': _gp['ledger'], 'manifest': _gp['manifest'], 'accounting': _gp['accounting'], 'proposals': _gp['proposals'], 'candidate': _gp['candidate'], 'unresolved': _gp['unresolved']}, 'identity': _gp['identity'], 'comparison': _gp['comparison'], 'extractions': _gp['extractions'], 'steps': _gp['steps']}\n"
            "    _a.verify_current_proof = _seam\n"
            "    _pi.rules_identity = lambda _root: _get_orig()['dependencies']['rules']\n",
            encoding="utf-8",
        )
        (cls.codex_home / "models_cache.json").write_text(
            json.dumps({"models": [{"slug": "gpt-5.4"}]}),
            encoding="utf-8",
        )
        if os.name == "nt":
            codex_bin = cls.bin_dir / "codex.cmd"
            codex_bin.write_text("@echo off\r\n", encoding="utf-8")
        else:
            codex_bin = cls.bin_dir / "codex"
            codex_bin.write_text(f"#!{sys.executable} -B\n" + FAKE_CODEX_SCRIPT, encoding="utf-8")
            codex_bin.chmod(codex_bin.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        cls.orig_env = {
            k: os.environ.get(k)
            for k in (
                "PATH",
                "PYTHONPATH",
                "PYTHONDONTWRITEBYTECODE",
                "CODEX_HOME",
                "NEWROGUE_CODEX_REASONING_EFFORT",
                "NEWROGUE_GEMINI_BIN",
                "FAKE_CODEX_STATE_DIR",
                "FAKE_NEWROUGE_PYTHON",
            )
        }
        os.environ["PATH"] = os.pathsep.join([str(cls.bin_dir), os.environ.get("PATH", "")])
        os.environ["PYTHONPATH"] = os.pathsep.join(
            [str(cls.boot_dir), str(NEWROUGE_PYTHON), str(NEWROUGE_TESTS), str(NEWROUGE_ROOT)]
        )
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        os.environ["CODEX_HOME"] = str(cls.codex_home)
        os.environ["NEWROGUE_CODEX_REASONING_EFFORT"] = "high"
        os.environ["NEWROGUE_GEMINI_BIN"] = str(cls.fake_provider_py)
        os.environ["FAKE_CODEX_STATE_DIR"] = str(cls.state_dir)
        os.environ["FAKE_NEWROUGE_PYTHON"] = str(NEWROUGE_PYTHON)
        cls.sc25_temp = None
        cls.sc25_ctx = None
        cls.compact_temp = None
        cls.compact_ctx = None

    @classmethod
    def tearDownClass(cls):
        if cls.compact_temp is not None:
            cls.compact_temp.cleanup()
            cls.compact_temp = None
            cls.compact_ctx = None
        if cls.sc25_temp is not None:
            cls.sc25_temp.cleanup()
            cls.sc25_temp = None
            cls.sc25_ctx = None
        for k, v in cls.orig_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        cls.env_temp.cleanup()

    def tearDown(self):
        import gc

        gc.collect()

    def _read_logged_turns(self) -> list[dict]:
        log_path = self.state_dir / "turns.jsonl"
        if not log_path.is_file():
            return []
        return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _run_adoption_cli(self, root: Path, argv: list[str]) -> tuple[int, dict]:
        buf = io.StringIO()
        from contextlib import redirect_stdout

        with redirect_stdout(buf):
            code = adoption_cli.main(["--root", str(root), *argv])
        return code, json.loads(buf.getvalue())

    def _dispatch_adoption_review(
        self, root: Path, prep_resp: dict, *, unflag_after_first: Path | None = None
    ) -> None:
        if prep_resp.get("segmented_review"):
            for idx, seg_row in enumerate(prep_resp["segments"]):
                self.assertLessEqual(seg_row["request_bytes"], 70_000)
                cmd = list(seg_row["runner_command"])
                proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=120)
                self.assertEqual(proc.returncode, 0, f"Segment {seg_row['segment_id']} failed: {proc.stderr}\n{proc.stdout}")
                execution = {
                    "command": cmd,
                    "status": "completed",
                    "returncode": proc.returncode,
                    "runner_dispatch_count": 1,
                    "active_elapsed_seconds": 0.5,
                    "stdout": proc.stdout,
                    "stdout_base64": base64.b64encode(proc.stdout.encode("utf-8")).decode("ascii"),
                }
                (root / seg_row["execution_capture_ref"]).write_bytes(encoded(execution))
                if idx == 0 and unflag_after_first is not None and unflag_after_first.exists():
                    unflag_after_first.unlink()
        else:
            req_txt = (root / prep_resp["workspace"]).parent / "request.txt"
            self.assertLessEqual(len(req_txt.read_bytes()), 70_000)
            cmd = list(prep_resp["runner_command"])
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=120)
            self.assertEqual(proc.returncode, 0, f"Adoption runner failed: {proc.stderr}\n{proc.stdout}")
            execution = {
                "command": cmd,
                "status": "completed",
                "returncode": proc.returncode,
                "runner_dispatch_count": 1,
                "active_elapsed_seconds": 0.5,
                "stdout": proc.stdout,
                "stdout_base64": base64.b64encode(proc.stdout.encode("utf-8")).decode("ascii"),
            }
            (root / prep_resp["execution_capture_ref"]).write_bytes(encoded(execution))

    def test_01_story25_ast_and_semantic_lock_guard(self):
        """Verify zero-touch AST lock on _b_route_planning_input.py and 52-symbol closure on _b_route_planning_runtime.py."""
        self.assertEqual(
            Path(runtime.__file__).resolve(),
            (NEWROUGE_PYTHON / "_b_route_planning_runtime.py").resolve(),
        )
        import test_b_route_story25_host_fault_guard as s25

        lock_test_names = (
            "test_loop3_input_resource_delta_pins_all_six_owners_and_immutable_remainder",
            "test_loop3_input_resource_imports_do_not_create_free_module_slots",
            "test_host_projection_is_not_reused_for_semantic_import_closure",
            "test_early_source_delta_is_finite_and_never_waives_removal",
            "test_historical_r25_minimal_runner_exception_remains_exactly_local",
            "test_loop3_issue_account_adapter_addition_is_bound_to_exact_reviewed_bytes",
            "test_loop3_lifetime_exact_fault_owners_and_other_job_behavior_remain_bound",
            "test_loop3_worker_cleanup_helper_and_finally_are_exactly_pinned",
            "test_reviewed_common_bodies_and_new_helper_cannot_be_modified",
            "test_unknown_duplicate_and_missing_host_definitions_are_rejected",
        )
        suite = unittest.TestSuite(s25.HostFaultSourceGuardTests(name) for name in lock_test_names)
        stream = io.StringIO()
        res = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        self.assertTrue(res.wasSuccessful(), f"Story 25 guard suite failed: {res.failures} {res.errors}\n{stream.getvalue()}")

        with tempfile.TemporaryDirectory(prefix="tbbase", dir=_temp_dir_base()) as base_tmp:
            base_root = Path(base_tmp)
            guard = s25.guard_namespace()

            def overlay_path(which: str, rel_name: str) -> Path:
                rel_posix = Path(rel_name).as_posix()
                if which == "baseline":
                    cached = base_root / rel_posix
                    if not cached.is_file():
                        proc = subprocess.run(
                            ["git", "show", f"{HANDOFF_BASELINE_COMMIT}:{rel_posix}"],
                            cwd=NEWROUGE_ROOT,
                            capture_output=True,
                            check=True,
                        )
                        cached.parent.mkdir(parents=True, exist_ok=True)
                        cached.write_bytes(proc.stdout)
                    return cached
                return NEWROUGE_ROOT / rel_posix

            guard["_path"] = overlay_path
            guard["_same"] = lambda left, right: json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)
            guard["codec"] = codec
            digests = guard["_semantic_unchanged"]("baseline", "current")
            self.assertEqual(len(digests), 52)
            # Also verify _b_route_planning_input.py is byte-identical (normalized LF) to baseline
            base_pi = overlay_path("baseline", "scripts/python/_b_route_planning_input.py").read_bytes().replace(b"\r\n", b"\n")
            curr_pi = (NEWROUGE_PYTHON / "_b_route_planning_input.py").read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(base_pi, curr_pi)

    def _ensure_sc25_r1_and_r2(self) -> dict:
        if self.__class__.sc25_ctx is not None:
            return self.__class__.sc25_ctx
        if self.__class__.sc25_temp is not None:
            self.__class__.sc25_temp.cleanup()
            self.__class__.sc25_temp = None
        sc25_dir = NEWROUGE_ROOT / SC25_REL
        raw_index = json.loads((sc25_dir / "raw-index.json").read_text(encoding="utf-8"))
        sc25_report = json.loads((sc25_dir / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(sc25_report["status"], "blocked")
        self.assertIn("complete_request_bytes=278315", json.dumps(sc25_report))
        orig_inputs_bytes = (sc25_dir / "inputs.json").read_bytes()
        self.assertEqual(len(orig_inputs_bytes), 498_886)
        orig_inputs = json.loads(orig_inputs_bytes.decode("utf-8"))
        self.assertEqual(
            len(json.dumps(orig_inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")),
            440_014,
        )

        def sc25_proof_seam(obs, ref, *, scope_id):
            for row in orig_inputs["raw_proof_inventory"]:
                obs.read(row["path"], optional=row["raw_digest"] is None)
            for glob_row in orig_inputs["dependencies"]["globs"]:
                obs.watch(glob_row["patterns"])
            gp = orig_inputs["global_proof"]
            src_files = []
            for s in orig_inputs["source_inventory"]:
                raw = obs.read(s["path"])
                src_files.append(
                    {
                        "path": s["path"],
                        "raw_digest": s["raw_digest"],
                        "raw_base64": base64.b64encode(raw).decode("ascii"),
                        "text": raw.decode("utf-8"),
                    }
                )
            return {
                "report": gp["report"],
                "bundle": {
                    "files": src_files,
                    "ledger": gp["ledger"],
                    "manifest": gp["manifest"],
                    "accounting": gp["accounting"],
                    "proposals": gp["proposals"],
                    "candidate": gp["candidate"],
                    "unresolved": gp["unresolved"],
                },
                "identity": gp["identity"],
                "comparison": gp["comparison"],
                "extractions": gp["extractions"],
                "steps": gp["steps"],
            }

        self.__class__.sc25_temp = tempfile.TemporaryDirectory(prefix="tb", dir=_temp_dir_base())
        root = Path(self.__class__.sc25_temp.name)
        for row in raw_index:
            src = NEWROUGE_ROOT / row["path"]
            if src.is_file():
                dst = root / row["path"]
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        prot_ref = _init_unmocked_protection(root, run_id="p1")
        routing_dst = root / "docs/workflows/llm-routing.json"
        routing_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(NEWROUGE_ROOT / "docs/workflows/llm-routing.json", routing_dst)

        with patch.object(audit, "verify_current_proof", new=sc25_proof_seam), patch.object(
            planning, "rules_identity", new=lambda _r: orig_inputs["dependencies"]["rules"]
        ), patch.dict(os.environ, {"FAKE_CODEX_SC25_SEAM_INPUTS": str(sc25_dir / "inputs.json")}):
            # Part A: Real sc25 (440,014 B) prepare via CLI wrapper
            cli_args = type(
                "Args",
                (),
                {
                    "repo_root": str(root),
                    "command": "prepare",
                    "input_stage": "3b",
                    "run_id": "sc25",
                    "planning_contract": orig_inputs["contract_ref"],
                    "task_id": None,
                    "allow_unready_draft": False,
                    "capabilities": None,
                    "manifest": None,
                    "evidence_ref": None,
                    "run_invocation_limit": None,
                },
            )()
            prep = seg_input.prepare_from_cli(root, cli_args, planner="mvg")
            self.assertEqual(prep["status"], "prepared", prep)
            self.assertEqual(prep["exit_code"], 0)
            self.assertEqual(prep["input_identity"], SC25_EXPECTED_IDENTITY)
            self.assertGreaterEqual(prep["batch_count"], 2)

            frozen = seg_input.load_prepared(root, prep["resume_ref"])
            self.assertEqual(frozen["inputs"], orig_inputs)
            tp = frozen["transport"]
            self.assertEqual(
                seg_input.reconstruct_inputs(tp["common_header"], tp["batches"], tp["host_frames"]),
                orig_inputs,
            )
            for batch in frozen["transport"]["batches"]:
                rep = batch["input_report"]
                self.assertLessEqual(rep["workspace_payload_utf8_bytes"], 70_000)
                self.assertLessEqual(rep["token_plus_reserved_upper_bound"], 96_000)

            templates = {
                "default": _build_sc25_candidate_content(frozen, variant="A"),
                "candidate-1": _build_sc25_candidate_content(frozen, variant="A"),
                "candidate-2": _build_sc25_candidate_content(frozen, variant="B"),
                "candidate-3": _build_sc25_candidate_content(frozen, variant="C"),
            }
            (self.state_dir / "candidate_templates.json").write_text(
                json.dumps(templates, ensure_ascii=False), encoding="utf-8"
            )
            repair_flag = self.state_dir / "enable_stage4_repair.flag"
            repair_flag.write_text("1", encoding="utf-8")

            # Part B: Stages 1/2, 3, 4, 5, 6a E2E on real sc25
            runner_script = NEWROUGE_PYTHON / "codex_isolated_model_runner.py"
            try:
                gen_res = runtime.operate(
                    root,
                    planner="mvg",
                    command="generate",
                    run_id="r1",
                    prepared_ref=prep["resume_ref"],
                    profile="3b-mvg-v1",
                    runner=runner_script,
                    timeout_sec=120,
                )
            except Exception as exc:
                r1_json = runtime.run_location(root, "mvg", "r1") / "run.json"
                diag = ""
                if r1_json.is_file():
                    st_tmp = json.loads(r1_json.read_text(encoding="utf-8"))
                    diag = json.dumps(st_tmp.get("candidate_admissions"), indent=2)
                raise AssertionError(f"operate(generate) failed: {exc}\n{diag}") from exc
            finally:
                if repair_flag.exists():
                    repair_flag.unlink()
            self.assertEqual(gen_res["selected"], "winner-chain", gen_res)
            self.assertEqual(gen_res["candidate_count"], 3, gen_res)
            rev_res = runtime.operate(
                root,
                planner="mvg",
                command="review",
                run_id="r1",
                prepared_ref=prep["resume_ref"],
                profile="3b-mvg-v1",
                runner=runner_script,
                timeout_sec=120,
            )
            self.assertEqual(rev_res["status"], "passed", rev_res)
            ver_res = runtime.operate(
                root,
                planner="mvg",
                command="verify-selection",
                run_id="r1",
                prepared_ref=prep["resume_ref"],
                profile="3b-mvg-v1",
                runner=runner_script,
                timeout_sec=120,
            )
            self.assertEqual(ver_res["status"], "passed", ver_res)

            run_dir = runtime.run_location(root, "mvg", "r1")
            run_state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run_state["selection_status"], "selected")
            handoff_path = run_dir / "handoff.json"
            self.assertTrue(handoff_path.is_file())
            handoff_doc = json.loads(handoff_path.read_text(encoding="utf-8"))
            self.assertEqual(handoff_doc["schema_version"], "newrouge.b-route-planning-handoff.v1")
            runtime.validate_input(root, run_dir, run_state)
            self.assertEqual(runtime.handoff(root, run_dir, run_state), handoff_doc)

            turns_r1 = self._read_logged_turns()
            self.assertGreater(len(turns_r1), 0)
            stages_seen = {t["stage"] for t in turns_r1}
            for expected_stage in (
                "stage1_2_batch",
                "stage1_2_rolling_or_tree_reduce",
                "stage3_synthesis",
                "stage4_repair",
                "stage5_review",
                "stage6a_selection",
            ):
                self.assertIn(expected_stage, stages_seen, f"Missing stage {expected_stage} in {stages_seen}")

            for call_row in run_state["capability_selection"]["calls"]:
                meas = call_row["request_identity"]["measurement"]
                self.assertLessEqual(meas["request_bytes"], 70_000)
                self.assertLessEqual(
                    meas["request_bytes"] + frozen["inputs"]["contract"]["limits"]["reserved_tokens"],
                    96_000,
                )
            for t in turns_r1:
                self.assertLessEqual(t["utf8_bytes"], 70_000)

            many_cand = deepcopy(handoff_doc["proposal"])
            extra_flows = []
            for idx in range(8):
                fl = deepcopy(many_cand["content"]["definitions"]["flows"][0])
                fl["id"] = f"FLOW-MULTI-{idx:02d}"
                fl["proposed_owner_key"] = f"owner-multi-{idx:02d}"
                fl["observable_result"] = f"Observable result {idx:02d} " + ("detail-" * 480)
                for edge in fl["graph"]["edges"]:
                    edge["from"]["flow_id"] = fl["id"]
                    edge["to"]["flow_id"] = fl["id"]
                    edge["owner"]["definition_id"] = fl["id"]
                    edge["owner"]["proposed_owner_key"] = fl["proposed_owner_key"]
                for node in fl["graph"]["nodes"]:
                    node["owner"]["definition_id"] = fl["id"]
                    node["owner"]["proposed_owner_key"] = fl["proposed_owner_key"]
                for bnd in fl["graph"]["boundaries"]:
                    bnd["node"]["flow_id"] = fl["id"]
                fl["ui"]["owner"]["definition_id"] = fl["id"]
                fl["ui"]["owner"]["proposed_owner_key"] = fl["proposed_owner_key"]
                fl["human_verification"]["owner"]["definition_id"] = fl["id"]
                fl["human_verification"]["owner"]["proposed_owner_key"] = fl["proposed_owner_key"]
                extra_flows.append(fl)
            many_cand["content"]["definitions"]["flows"].extend(extra_flows)
            base_seed = runtime.seed(run_state, run_dir / "analysis-input")
            multi_slices = seg_runtime._plan_review_segments(
                run_state,
                frozen,
                base_seed=base_seed,
                proposal=many_cand,
                slot="candidate-1",
                generation_no=1,
                execution_no=1,
                lineage_id="0" * 64,
                context=1,
                prior_projection=None,
                issue=None,
            )
            self.assertGreaterEqual(len(multi_slices), 2)
            for _, sl_sch, sl_prm, _, _ in multi_slices:
                sl_ws = seg_input._runner_wrapper_text(sl_prm, sl_sch, compact_schema_file=True)
                self.assertLessEqual(len(sl_ws.encode("utf-8")), 70_000)

            max_rel_path = max(len(p.relative_to(root).as_posix()) for p in run_dir.rglob("*"))
            self.assertLessEqual(12 + max_rel_path, 259, f"Path budget exceeded: 12 + {max_rel_path}")

            # Part C: Run 2 0-call mvg-recovery reuse
            turns_before_r2 = len(self._read_logged_turns())
            r2_gen = runtime.operate(
                root,
                planner="mvg",
                command="generate",
                run_id="r2",
                prepared_ref=prep["resume_ref"],
                profile="3b-mvg-v1",
                runner=runner_script,
                timeout_sec=120,
            )
            self.assertEqual(r2_gen["selected"], "winner-chain", r2_gen)
            r2_rev = runtime.operate(
                root,
                planner="mvg",
                command="review",
                run_id="r2",
                prepared_ref=prep["resume_ref"],
                profile="3b-mvg-v1",
                runner=runner_script,
                timeout_sec=120,
            )
            self.assertEqual(r2_rev["status"], "passed", r2_rev)
            r2_ver = runtime.operate(
                root,
                planner="mvg",
                command="verify-selection",
                run_id="r2",
                prepared_ref=prep["resume_ref"],
                profile="3b-mvg-v1",
                runner=runner_script,
                timeout_sec=120,
            )
            self.assertEqual(r2_ver["status"], "passed", r2_ver)
            turns_after_r2 = len(self._read_logged_turns())
            self.assertEqual(turns_before_r2, turns_after_r2, "Run 2 reuse must dispatch 0 model calls!")

            r2_dir = runtime.run_location(root, "mvg", "r2")
            r2_state = json.loads((r2_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(r2_state["capability_selection"]["total_invocations"], 0)
            self.assertEqual(
                r2_state["capability_selection"]["selected"][0]["record"]["kind"],
                "adoption",
            )

        import gc

        self.__class__.sc25_ctx = {
            "root": root,
            "sc25_dir": sc25_dir,
            "orig_inputs": orig_inputs,
            "sc25_proof_seam": sc25_proof_seam,
            "prot_ref": prot_ref,
            "prep": prep,
            "run_dir": run_dir,
            "r1_selection_status": run_state["selection_status"],
            "r2_dir": r2_dir,
            "r2_total_invocations": r2_state["capability_selection"]["total_invocations"],
            "max_rel_path": max_rel_path,
        }
        del run_state, r2_state, handoff_doc, many_cand
        gc.collect()
        return self.__class__.sc25_ctx

    def test_02a_real_sc25_stages_1_to_6a_and_run2_reuse(self):
        """Run full E2E pipeline on real 440,014-byte sc25 + Run 2 0-call reuse."""
        ctx = self._ensure_sc25_r1_and_r2()
        self.assertEqual(ctx["r1_selection_status"], "selected")
        self.assertEqual(ctx["r2_total_invocations"], 0)

    def test_02b_real_sc25_stage6b_adoption_and_recovery_invalidation(self):
        """Run Stage 6b non-mechanical adoption on real sc25 + mvg-recovery drift/revoke/clear."""
        ctx = self._ensure_sc25_r1_and_r2()
        root = ctx["root"]
        sc25_dir = ctx["sc25_dir"]
        orig_inputs = ctx["orig_inputs"]
        sc25_proof_seam = ctx["sc25_proof_seam"]
        prot_ref = ctx["prot_ref"]
        prep = ctx["prep"]
        run_dir = ctx["run_dir"]
        run_state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        r2_dir = ctx["r2_dir"]
        r2_state = json.loads((r2_dir / "run.json").read_text(encoding="utf-8"))

        with patch.object(audit, "verify_current_proof", new=sc25_proof_seam), patch.object(
            planning, "rules_identity", new=lambda _r: orig_inputs["dependencies"]["rules"]
        ), patch.dict(os.environ, {"FAKE_CODEX_SC25_SEAM_INPUTS": str(sc25_dir / "inputs.json")}):
            # Part D1: Stage 6b Real Unmocked Adoption on sc25 (3 targets -> non-mechanical)
            handoff_rel = (run_dir / "handoff.json").relative_to(root).as_posix()
            admission_rel = run_state["selected_admission_review"]["path"]
            op_sc25 = "OP-sc25-init"
            req_sc25 = _build_adoption_request_from_handoff(
                root,
                operation_id=op_sc25,
                run_id="r1",
                handoff_rel=handoff_rel,
                admission_rel=admission_rel,
                protection_ref=prot_ref,
                include_policy_and_origins=True,
            )
            req_sc25_rel = "logs/ci/adoption-req-sc25.json"
            (root / req_sc25_rel).write_bytes(encoded(req_sc25))

            code, rev_prep = self._run_adoption_cli(
                root, ["--stage", "review-prepare", "--operation-id", op_sc25, "--request", req_sc25_rel]
            )
            self.assertEqual(code, 0, rev_prep)
            self.assertIsNone(rev_prep.get("machine_preservation"))
            self.assertTrue(rev_prep["semantic_execution_required"])
            self._dispatch_adoption_review(root, rev_prep)

            code, rev_done = self._run_adoption_cli(
                root, ["--stage", "review-complete", "--operation-id", op_sc25]
            )
            self.assertEqual(code, 0, rev_done)
            req_sc25["host_review_ref"] = rev_done["host_review_ref"]
            (root / req_sc25_rel).write_bytes(encoded(req_sc25))

            for stg, extra in (
                ("prepare", ["--request", req_sc25_rel]),
                ("reserve", []),
                ("apply", []),
                ("verify", []),
                ("publish", []),
                ("read", ["--context"]),
            ):
                code, out = self._run_adoption_cli(root, ["--stage", stg, "--operation-id", op_sc25, *extra])
                self.assertEqual(code, 0, (stg, out))
                if stg == "read":
                    self.assertEqual(out["context"]["kind"], "published_operation")
                    self.assertEqual(out["context"]["operation_id"], op_sc25)
                    self.assertEqual(len(out["context"]["plan_refs"]), 1)
                    self.assertTrue(out["scope_ids"])
            rev_dir = root / adoption_review.location(op_sc25)
            max_rev_rel = max(len(p.relative_to(root).as_posix()) for p in rev_dir.rglob("*"))
            self.assertLessEqual(12 + max_rev_rel, 259, f"Stage 6b path budget exceeded: 12 + {max_rev_rel}")

            # Verify logless clean-clone read --context works from committed docs/ without logs/
            with tempfile.TemporaryDirectory(prefix="tbcln", dir=_temp_dir_base()) as cln_tmp:
                clone_root = Path(cln_tmp)
                for sub in ("docs", ".taskmaster"):
                    if (root / sub).exists():
                        shutil.copytree(root / sub, clone_root / sub)
                self.assertFalse((clone_root / "logs").exists())
                cln_code, cln_out = self._run_adoption_cli(
                    clone_root, ["--stage", "read", "--operation-id", op_sc25, "--context"]
                )
                self.assertEqual(cln_code, 0, cln_out)
                self.assertEqual(cln_out["context"]["kind"], "published_operation")
                self.assertEqual(cln_out["context"]["operation_id"], op_sc25)
                self.assertEqual(len(cln_out["context"]["plan_refs"]), 1)

            # Part C2: Verify mvg-recovery constraint drift rejection, reopen revocation, and clear epoch
            import _mvg_capability_recovery as mvg_recovery

            extra_constraint_rel = "docs/testing/story-2-5-controlled-acceptance/extra-constraint.md"
            extra_constraint_path = root / extra_constraint_rel
            extra_constraint_path.parent.mkdir(parents=True, exist_ok=True)
            extra_constraint_path.write_text("# Extra governed constraint\n", encoding="utf-8")
            drift_contract = deepcopy(orig_inputs["contract"])
            drift_contract["constraints"] = [
                *drift_contract["constraints"],
                {"path": extra_constraint_rel, "format": "text"},
            ]
            drift_contract_rel = "logs/ci/planning-contract-drift.json"
            (root / drift_contract_rel).write_bytes(encoded(drift_contract))
            try:
                cli_args_drift = type(
                    "Args",
                    (),
                    {
                        "repo_root": str(root),
                        "command": "prepare",
                        "input_stage": "3b",
                        "run_id": "sc25-drift",
                        "planning_contract": drift_contract_rel,
                        "task_id": None,
                        "allow_unready_draft": False,
                        "capabilities": None,
                        "manifest": None,
                        "evidence_ref": None,
                        "run_invocation_limit": None,
                    },
                )()
                prep_drift = seg_input.prepare_from_cli(root, cli_args_drift, planner="mvg")
                self.assertEqual(prep_drift["status"], "prepared", prep_drift)
                r3_dir = runtime.run_location(root, "mvg", "r3")
                runtime.create_run(root, r3_dir, "r3", prep_drift["resume_ref"], "3b-mvg-v1")
                r3_state = json.loads((r3_dir / "run.json").read_text(encoding="utf-8"))
                mvg_recovery.bind_epoch(root, r3_state)
                drift_adopt = mvg_recovery.try_adopt(
                    root,
                    r3_dir,
                    r3_state,
                    runtime.scopes(r3_state, r3_dir / "analysis-input")[0],
                    0,
                    runtime.seed(r3_state, r3_dir / "analysis-input"),
                )
                self.assertIsNone(drift_adopt, "Constraint drift must reject completed reuse!")
                drift_lookup = json.loads(
                    (r3_dir / "recovery-lookups/scope-1.json").read_text(encoding="utf-8")
                )
                self.assertEqual(drift_lookup["status"], "generate_fresh")
                self.assertIn(
                    "recovery_current_dependencies_incompatible",
                    json.dumps(drift_lookup),
                )
            finally:
                extra_constraint_path.unlink(missing_ok=True)
                (root / drift_contract_rel).unlink(missing_ok=True)

            r1_tx_id = run_state["capability_selection"]["selected"][0]["checkpoint"]["transaction_id"]
            mvg_recovery.revoke(root, run_state, [r1_tx_id])
            with self.assertRaisesRegex(ValueError, "recovery_source_revoked"):
                mvg_recovery.assert_active_chain(root, r2_state, r2_dir)
            r4_dir = runtime.run_location(root, "mvg", "r4")
            runtime.create_run(root, r4_dir, "r4", prep["resume_ref"], "3b-mvg-v1")
            r4_state = json.loads((r4_dir / "run.json").read_text(encoding="utf-8"))
            mvg_recovery.bind_epoch(root, r4_state)
            revoked_adopt = mvg_recovery.try_adopt(
                root,
                r4_dir,
                r4_state,
                runtime.scopes(r4_state, r4_dir / "analysis-input")[0],
                0,
                runtime.seed(r4_state, r4_dir / "analysis-input"),
            )
            self.assertIsNone(revoked_adopt, "Revoked source must reject completed reuse!")
            revoked_lookup = json.loads(
                (r4_dir / "recovery-lookups/scope-1.json").read_text(encoding="utf-8")
            )
            self.assertIn("recovery_source_revoked", json.dumps(revoked_lookup["failures"]))

            cleared_info = mvg_recovery.clear(root)
            self.assertEqual(cleared_info["epoch"], 1)
            self.assertEqual(cleared_info["completed"], 0)
            with self.assertRaisesRegex(ValueError, "mvg_recovery_epoch_invalidated"):
                mvg_recovery.assert_epoch(root, r2_state)

        turns_t02 = self._read_logged_turns()
        by_stage_t02: dict[str, int] = {}
        for row in turns_t02:
            st = row["stage"]
            by_stage_t02[st] = max(by_stage_t02.get(st, 0), row["utf8_bytes"])
            self.assertLessEqual(row["utf8_bytes"], 70_000)
        print(
            "\nSC25_E2E_SUMMARY="
            + json.dumps(
                {
                    "max_workspace_payload_bytes": by_stage_t02,
                    "max_run_rel_path": ctx["max_rel_path"],
                    "max_rev_rel_path": max_rev_rel,
                    "op_sc25_segments": len(rev_prep.get("segments", [])),
                },
                sort_keys=True,
            )
        )

    def test_03_stage6b_forced_oversized_and_mechanical_adoption(self):
        """Verify forced > 120,000-byte non-mechanical segmented Stage 6b + mechanical 0-call adoption."""
        fx_comp = __import__("test_b_route_adoption").AdoptionCompositionTests(
            "test_prepare_replay_reserve_freezes_allocations_and_writes_no_formal_target"
        )
        fx_comp.setUp()
        try:
            comp_root = fx_comp.root
            for rel, val in (
                (".taskmaster/tasks/tasks.json", {"master": {"tasks": []}}),
                (".taskmaster/tasks/tasks_back.json", []),
                (".taskmaster/tasks/tasks_gameplay.json", []),
            ):
                p = comp_root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(encoded(val))

            # Relocate proofs under logs/proof/ and configure local recovery dir
            commit_helper = __import__("test_b_route_commit").CommitFixture()
            commit_helper.fx = fx_comp
            commit_helper.root = comp_root
            big_req = commit_helper.relocate_proofs(deepcopy(fx_comp.request))
            big_req["operation_id"] = "OP-big70k"

            # Expand candidate & target plan with 9 verbose flows (> 130 KB subject, >= 3 segments!)
            fixture_one, cand_content = fx_comp.cases["one"]
            handoff_rel = big_req["material"]["handoff_ref"]["path"]
            req_id = cand_content["requirements"][0]["requirement_id"]
            base_flow = deepcopy(cand_content["definitions"]["flows"][0])
            for idx in range(2, 10):
                nf = deepcopy(base_flow)
                fid = f"FLOW-LARGE-{idx:02d}"
                nf["id"] = fid
                nf["proposed_owner_key"] = f"owner-{idx:02d}"
                nf["entry_condition"] = " ".join(
                    f"Flow-{idx:02d}-entry-clause-{k:03d}-invariant-{idx * 1000 + k}" for k in range(165)
                )
                nf["observable_result"] = " ".join(
                    f"Flow-{idx:02d}-outcome-clause-{k:03d}-assertion-{idx * 2000 + k}" for k in range(165)
                )
                for node in nf["graph"]["nodes"]:
                    node["owner"]["definition_id"] = fid
                    node["owner"]["proposed_owner_key"] = nf["proposed_owner_key"]
                for edge in nf["graph"]["edges"]:
                    edge["from"]["flow_id"] = fid
                    edge["to"]["flow_id"] = fid
                    edge["owner"]["definition_id"] = fid
                    edge["owner"]["proposed_owner_key"] = nf["proposed_owner_key"]
                for bnd in nf["graph"]["boundaries"]:
                    bnd["node"]["flow_id"] = fid
                for lp in nf["graph"]["loops"]:
                    for anc in lp["anchors"]:
                        anc["flow_id"] = fid
                nf["ui"]["owner"]["definition_id"] = fid
                nf["ui"]["owner"]["proposed_owner_key"] = nf["proposed_owner_key"]
                nf["human_verification"]["owner"]["definition_id"] = fid
                nf["human_verification"]["owner"]["proposed_owner_key"] = nf["proposed_owner_key"]
                cand_content["definitions"]["flows"].append(nf)
                cand_content["requirement_route_memberships"].append(
                    {
                        "requirement_id": req_id,
                        "flow_id": fid,
                        "observable_role": f"Observe governed outcome {idx:02d}",
                    }
                )
                big_req["material"]["identity_alignment"]["flows"].append(
                    {
                        "candidate_id": fid,
                        "mode": "allocate",
                        "rationale": f"Allocate governed flow {fid}",
                    }
                )

            # Rebuild projected target plan + add POLICY & ORIGINS so machine_mode is None (3 targets)
            from _b_route_adoption_projection import project_content
            flow_map = {
                f["id"]: f"FLOW-TPL-{i}" for i, f in enumerate(cand_content["definitions"]["flows"], 1)
            }
            placeholder = {
                "plan_id": "PLAN-TEMPLATE",
                "plan_revision": 123,
                "requirements": {req_id: "RQ-TEMPLATE"},
                "flows": flow_map,
            }
            new_handoff_bytes = encoded({"schema_version": "synthetic.handoff.v1", "proposal": {"content": cand_content}})
            fixture_one.artifacts[handoff_rel] = new_handoff_bytes
            (comp_root / handoff_rel).write_bytes(new_handoff_bytes)
            big_req["material"]["handoff_ref"]["raw_digest"] = codec.raw_digest(new_handoff_bytes)

            projected_big = project_content(cand_content, placeholder)
            inv_flow_map = {v: k for k, v in flow_map.items()}

            def tpl_big(val, key=None):
                if isinstance(val, dict):
                    return {k: tpl_big(v, k) for k, v in val.items()}
                if isinstance(val, list):
                    return [tpl_big(v, key) for v in val]
                if val == "PLAN-TEMPLATE":
                    return {"$allocation": "plan_id"}
                if key in ("revision", "owner_revision") and val == 123:
                    return {"$allocation": "plan_revision"}
                if val == "RQ-TEMPLATE":
                    return {"$allocation": "requirement:" + req_id}
                if isinstance(val, str) and val in inv_flow_map:
                    return {"$allocation": "flow:" + inv_flow_map[val]}
                return val

            raw_plan_base = deepcopy(fixture_one.models[next(iter(fixture_one.models))])
            adm_rel = big_req["review_ref"]["path"]
            target_big_plan = {
                **raw_plan_base,
                **projected_big,
                "plan_id": "PLAN-TEMPLATE",
                "revision": 123,
                "adoption_proof_refs": [
                    {
                        "owner": "planning_proof",
                        "ref": adm_rel,
                        "files": [{"path": adm_rel, "raw_digest": big_req["review_ref"]["raw_digest"]}],
                    }
                ],
                "native_candidate_ref": {
                    "owner": "planning_proof",
                    "ref": handoff_rel + "#/proposal/content",
                    "files": [{"path": handoff_rel, "raw_digest": codec.raw_digest(new_handoff_bytes)}],
                },
            }
            big_req["material"]["target_templates"] = [
                {
                    "path_template": "docs/planning/b-route/plans/{plan_id}/{plan_revision}.json",
                    "schema_version": adoption.PLAN,
                    "before_raw_digest": None,
                    "after_payload": tpl_big(target_big_plan),
                    "verification_mode": "immutable_bytes",
                },
                {
                    "path_template": POLICY,
                    "schema_version": fixture_one.policy["schema_version"],
                    "before_raw_digest": None,
                    "after_payload": deepcopy(fixture_one.policy),
                    "verification_mode": "immutable_bytes",
                },
                {
                    "path_template": ORIGINS,
                    "schema_version": "newrouge.b-route-origins.v1",
                    "before_raw_digest": None,
                    "after_payload": {
                        "schema_version": "newrouge.b-route-origins.v1",
                        "origins_id": "task-origins",
                        "revision": 1,
                        "tasks": [],
                        "frozen_legacy_refs": [],
                    },
                    "verification_mode": "immutable_bytes",
                },
            ]
            big_req_rel = fx_comp.request_ref(big_req)

            with patch.object(adoption, "capture_completed", fx_comp.synthetic_capture):
                # 1. Verify fail-closed rejection when one segment returns blocked
                op_blocked = "OP-big-blocked"
                blocked_req = deepcopy(big_req)
                blocked_req["operation_id"] = op_blocked
                blocked_req_rel = fx_comp.request_ref(blocked_req)
                prep_blk = adoption.prepare_review(
                    comp_root, operation_id=op_blocked, request_ref=blocked_req_rel
                )
                self.assertTrue(prep_blk.get("segmented_review"), prep_blk)
                self.assertGreaterEqual(len(prep_blk["segment_runner_commands"]), 3)

                flag_blk = self.state_dir / "force_stage6b_block.flag"
                flag_blk.write_text("1", encoding="utf-8")
                try:
                    self._dispatch_adoption_review(comp_root, prep_blk, unflag_after_first=flag_blk)
                finally:
                    if flag_blk.exists():
                        flag_blk.unlink()

                with self.assertRaises(codec.CodecError):
                    adoption.complete_review(comp_root, operation_id=op_blocked)

                # 2. Positive > 120 KB segmented Stage 6b review-prepare -> runner -> review-complete -> publish -> read --context
                prep_big = adoption.prepare_review(
                    comp_root, operation_id="OP-big70k", request_ref=big_req_rel
                )
                self.assertIsNone(prep_big.get("machine_preservation"))
                self.assertTrue(prep_big.get("segmented_review"), prep_big)
                self.assertGreaterEqual(len(prep_big["segment_runner_commands"]), 3)
                seg0 = prep_big["segments"][0]
                self.assertTrue(seg0["workspace"].endswith("/s/001/w"), seg0)
                self.assertTrue(seg0["request_ref"].endswith("/s/001/req.txt"), seg0)
                self.assertTrue(seg0["execution_capture_ref"].endswith("/s/001/exec.json"), seg0)
                self.assertTrue(
                    any(str(arg).replace("\\", "/").endswith("/s/001/w/o.json") for arg in seg0["runner_command"]),
                    seg0["runner_command"],
                )
                self._dispatch_adoption_review(comp_root, prep_big)

                sealed_big = adoption.complete_review(comp_root, operation_id="OP-big70k")
                proof_doc = codec.strict_json_loads(
                    (comp_root / sealed_big["host_review_ref"]["path"]).read_bytes()
                )
                self.assertEqual(proof_doc["schema_version"], "newrouge.b-route-adoption-review-proof.v1")
                big_req["host_review_ref"] = sealed_big["host_review_ref"]
                big_req_rel = fx_comp.request_ref(big_req)

                adoption.prepare(comp_root, operation_id="OP-big70k", request_ref=big_req_rel)
                adoption.reserve(comp_root, operation_id="OP-big70k")
                commit.execute(comp_root, operation_id="OP-big70k", stage="apply")
                commit.execute(comp_root, operation_id="OP-big70k", stage="verify")
                pub_big = commit.execute(comp_root, operation_id="OP-big70k", stage="publish")
                self.assertTrue(pub_big["published"])

                code, read_big = self._run_adoption_cli(
                    comp_root, ["--stage", "read", "--operation-id", "OP-big70k", "--context"]
                )
                self.assertEqual(code, 0, read_big)
                self.assertEqual(read_big["context"]["kind"], "published_operation")

                # 2b. Historical single-turn > 70k v1 proof replay compatibility (without segmented-plan.json)
                #     while blocking new unsegmented review-complete on > 70k subjects!
                from fixtures.adoption_review_protocol import completed as synth_completed

                op_hist = "OP-hist-single70k"
                hist_req = deepcopy(big_req)
                hist_req.pop("host_review_ref", None)
                hist_req["operation_id"] = op_hist
                # Adjust POLICY & ORIGINS before_raw_digest now that OP-big70k published them
                for tpl in hist_req["material"]["target_templates"]:
                    if tpl["path_template"] in (POLICY, ORIGINS):
                        cur_bytes = (comp_root / tpl["path_template"]).read_bytes()
                        tpl["before_raw_digest"] = codec.raw_digest(cur_bytes)
                        tpl["after_payload"] = codec.strict_json_loads(cur_bytes)
                hist_req_rel = fx_comp.request_ref(hist_req)
                prep_hist = adoption.prepare_review(comp_root, operation_id=op_hist, request_ref=hist_req_rel)
                hist_subj = codec.strict_json_loads((comp_root / prep_hist["subject_ref"]).read_bytes())
                self.assertTrue(adoption_review.segmented_adoption_required(hist_subj))

                # Convert layout to historical single-turn layout (NO segmented-plan.json!)
                hist_home = comp_root / adoption_review.location(op_hist)
                (hist_home / "segmented-plan.json").unlink(missing_ok=True)
                shutil.rmtree(hist_home / "s", ignore_errors=True)
                (hist_home / "w").mkdir(parents=True, exist_ok=True)
                (hist_home / "subject.json").write_bytes(adoption_review.raw(hist_subj))
                (hist_home / "w/prompt.txt").write_bytes(adoption_review._legacy_prompt(hist_subj).encode("utf-8"))
                (hist_home / "w/schema.json").write_bytes(
                    adoption_review.raw(adoption_review._legacy_verdict_schema(hist_subj))
                )
                (hist_home / "request.txt").write_bytes(
                    adoption_review._legacy_request_payload(hist_subj).encode("utf-8")
                )
                synth_completed(comp_root, op_hist, legacy=True, thread_id="hist-single-turn-thr-01")
                self.assertFalse(adoption_review._is_saved_segmented_adoption(comp_root, hist_subj))

                # New review-complete (produce_proof) MUST fail closed without segmented-plan.json on > 70k!
                with self.assertRaises(codec.CodecError):
                    adoption_review.produce_proof(comp_root, op_hist)

                # A previously saved historical single-turn review.json proof MUST replay 100% cleanly!
                hist_ev = adoption_review._legacy_verify_semantic(comp_root, hist_subj)
                hist_support = adoption_review.support_names("semantic", subject=hist_subj, segmented=False)
                hist_files = [
                    {
                        "path": adoption_review.location(op_hist) + "/" + name,
                        "schema_version": "raw.bytes.v1",
                        "raw_digest": codec.raw_digest((hist_home / name).read_bytes()),
                    }
                    for name in hist_support
                ]
                hist_proof = {
                    "schema_version": adoption_review.PROOF,
                    "operation_id": op_hist,
                    "subject_digest": codec.canonical_digest(hist_subj),
                    "policy_identity": hist_subj["policy_identity"],
                    "mode": "semantic",
                    "evidence": hist_ev,
                    "files": hist_files,
                }
                hist_proof_bytes = adoption_review.raw(hist_proof)
                hist_proof_rel = adoption_review.location(op_hist) + "/review.json"
                (comp_root / hist_proof_rel).write_bytes(hist_proof_bytes)
                hist_req["host_review_ref"] = {
                    "path": hist_proof_rel,
                    "schema_version": adoption_review.PROOF,
                    "raw_digest": codec.raw_digest(hist_proof_bytes),
                }
                self.assertEqual(
                    adoption_review.support_names(
                        "semantic",
                        subject=hist_subj,
                        segmented=adoption_review._is_saved_segmented_adoption(comp_root, hist_subj),
                    ),
                    ["subject.json", "w/prompt.txt", "w/schema.json", "request.txt", "execution.json", "w/output.json"],
                )
                replayed_hist, _ = adoption_review._verify_saved(comp_root, hist_req)
                self.assertEqual(replayed_hist["operation_id"], op_hist)

                # 3. Mechanical (machine_mode == "new_plan_exact_native_projection", 0 model calls)
                #    Now that POLICY & ORIGINS are published on comp_root, adopt a 2nd disjoint scope ("two")
                #    with ONLY [PLAN] in target_templates!
                turns_before_mech = len(self._read_logged_turns())
                mech_req = commit_helper.relocate_proofs(fx_comp.case("two", "OP-mech"))
                mech_req_rel = fx_comp.request_ref(mech_req)
                prep_mech = adoption.prepare_review(
                    comp_root, operation_id="OP-mech", request_ref=mech_req_rel
                )
                self.assertEqual(prep_mech["machine_preservation"], "new_plan_exact_native_projection")
                self.assertFalse(prep_mech["semantic_execution_required"])
                sealed_mech = adoption.complete_review(comp_root, operation_id="OP-mech")
                mech_req["host_review_ref"] = sealed_mech["host_review_ref"]
                mech_req_rel = fx_comp.request_ref(mech_req)

                adoption.prepare(comp_root, operation_id="OP-mech", request_ref=mech_req_rel)
                adoption.reserve(comp_root, operation_id="OP-mech")
                commit.execute(comp_root, operation_id="OP-mech", stage="apply")
                commit.execute(comp_root, operation_id="OP-mech", stage="verify")
                pub_mech = commit.execute(comp_root, operation_id="OP-mech", stage="publish")
                self.assertTrue(pub_mech["published"])
                self.assertEqual(turns_before_mech, len(self._read_logged_turns()), "Mechanical mode must use 0 model calls!")

                code, read_mech = self._run_adoption_cli(
                    comp_root, ["--stage", "read", "--operation-id", "OP-mech", "--context"]
                )
                self.assertEqual(code, 0, read_mech)
                self.assertEqual(read_mech["context"]["kind"], "published_operation")

            # Print summary of max observed workspace_payload UTF-8 bytes per stage for verification log
            all_turns = self._read_logged_turns()
            by_stage: dict[str, int] = {}
            for row in all_turns:
                st = row["stage"]
                by_stage[st] = max(by_stage.get(st, 0), row["utf8_bytes"])
                self.assertLessEqual(row["utf8_bytes"], 70_000)
            self.assertIn("stage6b_adoption_review", by_stage)
            print("\nMAX_WORKSPACE_PAYLOAD_BYTES_BY_STAGE=" + json.dumps(by_stage, sort_keys=True))
        finally:
            shutil.rmtree(fx_comp.root, ignore_errors=True)

    def _ensure_compact_70k_fixture(self) -> dict:
        """Prepare a fast 2-batch (~95 KB, > 70,000-byte) segmented 3B fixture shared across targeted E2E tests."""
        if self.__class__.compact_ctx is not None:
            return self.__class__.compact_ctx

        sc25_dir = NEWROUGE_ROOT / SC25_REL
        raw_index = json.loads((sc25_dir / "raw-index.json").read_text(encoding="utf-8"))
        orig_inputs = json.loads((sc25_dir / "inputs.json").read_text(encoding="utf-8"))

        slim_inputs = deepcopy(orig_inputs)
        slim_inputs["global_proof"]["comparison"] = {"findings": []}
        slim_inputs["global_proof"]["extractions"] = []
        slim_inputs["global_proof"]["candidate"] = {"proposals": []}
        keep_raw_paths = {
            r["path"]
            for r in orig_inputs["raw_proof_inventory"]
            if r["path"].endswith(("source-manifest.json", "source-blocks.json", "audit-report.json"))
        }
        slim_inputs["raw_proof_inventory"] = [
            r for r in orig_inputs["raw_proof_inventory"] if r["path"] in keep_raw_paths
        ]

        if self.__class__.compact_temp is not None:
            self.__class__.compact_temp.cleanup()
            self.__class__.compact_temp = None
        self.__class__.compact_temp = tempfile.TemporaryDirectory(prefix="tbcmp", dir=_temp_dir_base())
        root = Path(self.__class__.compact_temp.name)
        needed_files = (
            keep_raw_paths
            | {s["path"] for s in orig_inputs["source_inventory"]}
            | {orig_inputs["contract_ref"]}
            | {c["path"] for c in orig_inputs["contract"].get("constraints", [])}
            | {c["path"] for c in orig_inputs["contract"].get("contexts", [])}
        )
        for row in raw_index:
            if row["path"] in needed_files:
                src = NEWROUGE_ROOT / row["path"]
                if src.is_file():
                    dst = root / row["path"]
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)

        # Keep single-turn request > 70,000 bytes with minimal extra clauses for fast E2E execution
        constraint_rel = orig_inputs["contract"]["constraints"][0]["path"]
        constraint_path = root / constraint_rel
        orig_md = constraint_path.read_text(encoding="utf-8")
        extra_md = "\n\n## Extended Governed Invariants\n" + "\n".join(
            f"- Governed invariant clause {i:04d} [{(i * 104729 + 17) & 0xffffffff:08x}]: exclusive atomic journal commitment rule {i * 7919}."
            for i in range(220)
        )
        constraint_path.write_text(orig_md + extra_md + "\n", encoding="utf-8", newline="\n")

        prot_ref = _init_unmocked_protection(root, run_id="pc1")
        routing_dst = root / "docs/workflows/llm-routing.json"
        routing_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(NEWROUGE_ROOT / "docs/workflows/llm-routing.json", routing_dst)

        seam_file = root / "logs/ci/compact-seam-inputs.json"
        seam_file.parent.mkdir(parents=True, exist_ok=True)
        seam_file.write_text(json.dumps(slim_inputs, ensure_ascii=False), encoding="utf-8")

        def compact_proof_seam(obs, ref, *, scope_id):
            for row in slim_inputs["raw_proof_inventory"]:
                obs.read(row["path"], optional=row["raw_digest"] is None)
            for glob_row in slim_inputs["dependencies"]["globs"]:
                obs.watch(glob_row["patterns"])
            gp = slim_inputs["global_proof"]
            src_files = []
            for s in slim_inputs["source_inventory"]:
                raw = obs.read(s["path"])
                src_files.append(
                    {
                        "path": s["path"],
                        "raw_digest": s["raw_digest"],
                        "raw_base64": base64.b64encode(raw).decode("ascii"),
                        "text": raw.decode("utf-8"),
                    }
                )
            return {
                "report": gp["report"],
                "bundle": {
                    "files": src_files,
                    "ledger": gp["ledger"],
                    "manifest": gp["manifest"],
                    "accounting": gp["accounting"],
                    "proposals": gp["proposals"],
                    "candidate": gp["candidate"],
                    "unresolved": gp["unresolved"],
                },
                "identity": gp["identity"],
                "comparison": gp["comparison"],
                "extractions": gp["extractions"],
                "steps": gp["steps"],
            }

        with patch.object(audit, "verify_current_proof", new=compact_proof_seam), patch.object(
            planning, "rules_identity", new=lambda _r: slim_inputs["dependencies"]["rules"]
        ), patch.dict(os.environ, {"FAKE_CODEX_SC25_SEAM_INPUTS": str(seam_file)}):
            cli_args = type(
                "Args",
                (),
                {
                    "repo_root": str(root),
                    "command": "prepare",
                    "input_stage": "3b",
                    "run_id": "cmp2",
                    "planning_contract": slim_inputs["contract_ref"],
                    "task_id": None,
                    "allow_unready_draft": False,
                    "capabilities": None,
                    "manifest": None,
                    "evidence_ref": None,
                    "run_invocation_limit": None,
                },
            )()
            prep = seg_input.prepare_from_cli(root, cli_args, planner="mvg")
            self.assertEqual(prep["status"], "prepared", prep)
            self.assertTrue(prep["reconstruction"]["lossless"], prep)
            self.assertGreaterEqual(prep["batch_count"], 2)
            self.assertLessEqual(prep["batch_count"], 5)
            frozen = seg_input.load_prepared(root, prep["resume_ref"])

        self.__class__.compact_ctx = {
            "root": root,
            "slim_inputs": slim_inputs,
            "seam_file": seam_file,
            "proof_seam": compact_proof_seam,
            "prot_ref": prot_ref,
            "prep": prep,
            "frozen": frozen,
        }
        return self.__class__.compact_ctx

    def test_04_gemini_runner_sc25_and_stage6b(self):
        """Verify Gemini isolated runner E2E, Stage 6b native_threads/native_turns disjointness, and governed model enforcement."""
        import _b_route_compensation_segmented_execution as comp_seg

        cctx = self._ensure_compact_70k_fixture()
        root = cctx["root"]
        slim_inputs = cctx["slim_inputs"]
        seam_file = cctx["seam_file"]
        proof_seam = cctx["proof_seam"]
        prot_ref = cctx["prot_ref"]
        prep = cctx["prep"]
        frozen = cctx["frozen"]

        import _mvg_capability_recovery as mvg_recovery

        mvg_recovery.clear(root)
        gemini_runner = NEWROUGE_PYTHON / "gemini_isolated_model_runner.py"

        # Prepare a rogue routing file claiming gemini-2.5-flash to verify it is IGNORED without test override
        rogue_routing = root / "logs/ci/rogue-llm-routing.json"
        rogue_doc = json.loads((NEWROUGE_ROOT / "docs/workflows/llm-routing.json").read_text(encoding="utf-8"))
        rogue_doc["plane_b"]["runners"]["gemini"]["model"] = "gemini-2.5-flash"
        rogue_routing.write_text(json.dumps(rogue_doc), encoding="utf-8")

        with patch.object(audit, "verify_current_proof", new=proof_seam), patch.object(
            planning, "rules_identity", new=lambda _r: slim_inputs["dependencies"]["rules"]
        ), patch.dict(
            os.environ,
            {
                "FAKE_CODEX_SC25_SEAM_INPUTS": str(seam_file),
                "NEWROGUE_PLANE_B_RUNNER": "gemini",
                "NEWROGUE_GEMINI_REASONING_EFFORT": "high",
            },
        ):
            # Compensation segmented execution must also resolve gemini runner via resolve_plane_b_runner(root)
            self.assertEqual(comp_seg._official_runner(root=root).name, "gemini_isolated_model_runner.py")
            with patch.dict(os.environ, {"NEWROGUE_LLM_ROUTING_PATH": str(rogue_routing)}):
                self.assertEqual(adoption_review._governed_gemini_model(root), "gemini-4-carbon-high")

            templates = {
                "default": _build_sc25_candidate_content(frozen, variant="A"),
                "candidate-1": _build_sc25_candidate_content(frozen, variant="A"),
                "candidate-2": _build_sc25_candidate_content(frozen, variant="B"),
                "candidate-3": _build_sc25_candidate_content(frozen, variant="C"),
            }
            (self.state_dir / "candidate_templates.json").write_text(
                json.dumps(templates, ensure_ascii=False), encoding="utf-8"
            )
            (self.state_dir / "enable_stage4_repair.flag").unlink(missing_ok=True)

            turns_before = len(self._read_logged_turns())
            gen_res = runtime.operate(
                root,
                planner="mvg",
                command="generate",
                run_id="rg1",
                prepared_ref=prep["resume_ref"],
                profile="3b-mvg-v1",
                runner=gemini_runner,
                timeout_sec=120,
            )
            self.assertEqual(gen_res["selected"], "winner-chain", gen_res)
            rev_res = runtime.operate(
                root,
                planner="mvg",
                command="review",
                run_id="rg1",
                prepared_ref=prep["resume_ref"],
                profile="3b-mvg-v1",
                runner=gemini_runner,
                timeout_sec=120,
            )
            self.assertEqual(rev_res["status"], "passed", rev_res)
            ver_res = runtime.operate(
                root,
                planner="mvg",
                command="verify-selection",
                run_id="rg1",
                prepared_ref=prep["resume_ref"],
                profile="3b-mvg-v1",
                runner=gemini_runner,
                timeout_sec=120,
            )
            self.assertEqual(ver_res["status"], "passed", ver_res)

            run_dir = runtime.run_location(root, "mvg", "rg1")
            stream_journals = list(run_dir.rglob("*.gemini-stream.jsonl"))
            self.assertGreater(len(stream_journals), 0)

            run_state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            handoff_rel = (run_dir / "handoff.json").relative_to(root).as_posix()
            admission_rel = run_state["selected_admission_review"]["path"]
            op_gem = "OP-cmp-gem"
            req_gem = _build_adoption_request_from_handoff(
                root,
                operation_id=op_gem,
                run_id="rg1",
                handoff_rel=handoff_rel,
                admission_rel=admission_rel,
                protection_ref=prot_ref,
                include_policy_and_origins=True,
            )
            req_gem_rel = "logs/ci/adoption-req-cmp-gem.json"
            (root / req_gem_rel).write_bytes(encoded(req_gem))

            code, rev_prep = self._run_adoption_cli(
                root, ["--stage", "review-prepare", "--operation-id", op_gem, "--request", req_gem_rel]
            )
            self.assertEqual(code, 0, rev_prep)
            # Verify make_subject unwraps .gemini-stream.jsonl stdout lines into native_threads AND native_turns!
            gem_subj = codec.strict_json_loads((root / rev_prep["subject_ref"]).read_bytes())
            self.assertGreater(len(gem_subj["native_threads"]), 0)
            self.assertGreater(len(gem_subj["native_turns"]), 0)
            first_cmd = (
                rev_prep["segments"][0]["runner_command"]
                if rev_prep.get("segmented_review")
                else rev_prep["runner_command"]
            )
            self.assertTrue(any("gemini_isolated_model_runner.py" in str(x) for x in first_cmd))

            # Negative check 1: Ungoverned model ("gemini-2.5-flash") MUST be rejected at runner protocol gate AND Stage 6b review-complete
            op_bad_mod = "OP-gem-badmod"
            req_bad_mod = deepcopy(req_gem)
            req_bad_mod["operation_id"] = op_bad_mod
            req_bad_mod_rel = "logs/ci/adoption-req-gem-badmod.json"
            (root / req_bad_mod_rel).write_bytes(encoded(req_bad_mod))
            code_bm, prep_bm = self._run_adoption_cli(
                root, ["--stage", "review-prepare", "--operation-id", op_bad_mod, "--request", req_bad_mod_rel]
            )
            self.assertEqual(code_bm, 0, prep_bm)
            bad_cmd = list(
                prep_bm["segments"][0]["runner_command"]
                if prep_bm.get("segmented_review")
                else prep_bm["runner_command"]
            )
            with patch.dict(os.environ, {"FAKE_GEMINI_MODEL_OVERRIDE": "gemini-2.5-flash"}):
                proc_bm = subprocess.run(bad_cmd, capture_output=True, text=True, encoding="utf-8", timeout=120)
            self.assertEqual(proc_bm.returncode, 2, proc_bm.stdout)
            self.assertIn("gemini_cli_protocol_init_model_mismatch", proc_bm.stdout)
            with self.assertRaises(codec.CodecError):
                adoption.complete_review(root, operation_id=op_bad_mod)

            # Positive Stage 6b Gemini dispatch -> review-complete -> publish -> read --context
            self._dispatch_adoption_review(root, rev_prep)

            # Negative check 2: Reusing a native Gemini session_id in Stage 6b execution capture MUST fail closed!
            exec_ref = (
                rev_prep["segments"][0]["execution_capture_ref"]
                if rev_prep.get("segmented_review")
                else rev_prep["execution_capture_ref"]
            )
            orig_exec_bytes = (root / exec_ref).read_bytes()
            try:
                exec_doc = json.loads(orig_exec_bytes.decode("utf-8"))
                stdout_lines = exec_doc["stdout"].splitlines()
                rec = json.loads(stdout_lines[-1])
                ev0 = rec["model_identity_evidence"][0]
                old_sid = ev0["thread_id"]
                reused_sid = sorted(gem_subj["native_threads"])[0]
                raw_proto = base64.b64decode(ev0["protocol_jsonl_base64"]).decode("utf-8").replace(old_sid, reused_sid)
                import _gemini_cli_protocol as gem_proto

                req_text_path = (
                    root / rev_prep["segments"][0]["request_ref"]
                    if rev_prep.get("segmented_review")
                    else (root / rev_prep["workspace"]).parent / "request.txt"
                )
                sch_path = (
                    (root / rev_prep["segments"][0]["workspace"]) / "s.json"
                    if rev_prep.get("segmented_review")
                    else root / rev_prep["workspace"] / "schema.json"
                )
                _, rebuilt_ev = gem_proto.replay(
                    raw_proto.encode("utf-8"),
                    prompt=req_text_path.read_text(encoding="utf-8"),
                    schema=json.loads(sch_path.read_text(encoding="utf-8")),
                )
                rec["model_identity_evidence"] = [rebuilt_ev]
                stdout_lines[-1] = json.dumps(rec, ensure_ascii=False)
                new_stdout = "\n".join(stdout_lines) + "\n"
                exec_doc["stdout"] = new_stdout
                exec_doc["stdout_base64"] = base64.b64encode(new_stdout.encode("utf-8")).decode("ascii")
                (root / exec_ref).write_bytes(encoded(exec_doc))
                with self.assertRaises(codec.CodecError):
                    adoption.complete_review(root, operation_id=op_gem)
            finally:
                (root / exec_ref).write_bytes(orig_exec_bytes)

            code, rev_done = self._run_adoption_cli(
                root, ["--stage", "review-complete", "--operation-id", op_gem]
            )
            self.assertEqual(code, 0, rev_done)

            req_gem["host_review_ref"] = rev_done["host_review_ref"]
            (root / req_gem_rel).write_bytes(encoded(req_gem))

            for stg, extra in (
                ("prepare", ["--request", req_gem_rel]),
                ("reserve", []),
                ("apply", []),
                ("verify", []),
                ("publish", []),
                ("read", ["--context"]),
            ):
                code, out = self._run_adoption_cli(root, ["--stage", stg, "--operation-id", op_gem, *extra])
                self.assertEqual(code, 0, (stg, out))
                if stg == "read":
                    self.assertEqual(out["context"]["operation_id"], op_gem)

            # Also verify _b_route_qualified_compensation_review_v2.original_review extracts Gemini thread/turn IDs
            import _planning_apply_journal as adoption_journal
            import _b_route_qualified_compensation_review_v2 as qcomp_v2

            published_op = next(
                row for row in adoption_journal.operation_inventory(root) if row["operation_id"] == op_gem
            )
            snap_gem = adoption.Snapshot(root)
            with qcomp_v2.action():
                rev_threads, rev_turns = qcomp_v2.original_review(snap_gem, published_op)
            self.assertGreater(len(rev_threads), 0)
            self.assertGreater(len(rev_turns), 0)

            gem_turns = self._read_logged_turns()[turns_before:]
            self.assertGreater(len(gem_turns), 0)
            for row in gem_turns:
                self.assertEqual(row["provider"], "google")
                self.assertLessEqual(row["utf8_bytes"], 70_000)

    def test_05_stage6a_pairwise_tournament_and_capabilities_3b_profile(self):
        """Verify > 70,000-byte 3-candidate Stage 6a Pairwise + Turn-3 Synthesis Tournament AND 3b-capabilities-v1 E2E."""
        cctx = self._ensure_compact_70k_fixture()
        root = cctx["root"]
        slim_inputs = cctx["slim_inputs"]
        seam_file = cctx["seam_file"]
        proof_seam = cctx["proof_seam"]
        prep = cctx["prep"]
        frozen = cctx["frozen"]

        import _mvg_capability_recovery as mvg_recovery

        mvg_recovery.clear(root)
        codex_runner = NEWROUGE_PYTHON / "codex_isolated_model_runner.py"

        # Inflate each candidate content to ~28 KB distinct text so 3 candidates = ~86 KB (> 70,000 bytes!)
        big_templates = {}
        for slot_key, var in (
            ("default", "A"),
            ("candidate-1", "A"),
            ("candidate-2", "B"),
            ("candidate-3", "C"),
        ):
            cand_obj = _build_sc25_candidate_content(frozen, variant=var)
            cand_obj["definitions"]["flows"][0]["entry_condition"] = " ".join(
                f"Cand-{var}-entry-invariant-{i:04d}-clause-{i * 31}" for i in range(420)
            )
            cand_obj["definitions"]["flows"][0]["observable_result"] = " ".join(
                f"Cand-{var}-outcome-assertion-{i:04d}-state-{i * 47}" for i in range(420)
            )
            big_templates[slot_key] = cand_obj

        (self.state_dir / "candidate_templates.json").write_text(
            json.dumps(big_templates, ensure_ascii=False), encoding="utf-8"
        )
        pick_second_flag = self.state_dir / "tournament_pick_second.flag"
        pick_second_flag.write_text("1", encoding="utf-8")
        try:
            with patch.object(audit, "verify_current_proof", new=proof_seam), patch.object(
                planning, "rules_identity", new=lambda _r: slim_inputs["dependencies"]["rules"]
            ), patch.dict(os.environ, {"FAKE_CODEX_SC25_SEAM_INPUTS": str(seam_file)}):
                # 1. Stage 6a > 70k Pairwise + Turn-3 Synthesis Tournament
                turns_before = len(self._read_logged_turns())
                gen_res = runtime.operate(
                    root,
                    planner="mvg",
                    command="generate",
                    run_id="rtourn",
                    prepared_ref=prep["resume_ref"],
                    profile="3b-mvg-v1",
                    runner=codex_runner,
                    timeout_sec=120,
                )
                self.assertEqual(gen_res["selected"], "winner-chain", gen_res)
                rev_res = runtime.operate(
                    root,
                    planner="mvg",
                    command="review",
                    run_id="rtourn",
                    prepared_ref=prep["resume_ref"],
                    profile="3b-mvg-v1",
                    runner=codex_runner,
                    timeout_sec=120,
                )
                self.assertEqual(rev_res["status"], "passed", rev_res)
                ver_res = runtime.operate(
                    root,
                    planner="mvg",
                    command="verify-selection",
                    run_id="rtourn",
                    prepared_ref=prep["resume_ref"],
                    profile="3b-mvg-v1",
                    runner=codex_runner,
                    timeout_sec=120,
                )
                self.assertEqual(ver_res["status"], "passed", ver_res)

                tourn_dir = runtime.run_location(root, "mvg", "rtourn")
                tourn_state = json.loads((tourn_dir / "run.json").read_text(encoding="utf-8"))
                self.assertIsNone(tourn_state["capability_selection"]["current"])
                self.assertEqual(len(tourn_state["capability_selection"]["selected"]), 1)
                self.assertEqual(tourn_state["capability_selection"]["selected"][0]["attempt"], 1)

                manifests = list(tourn_dir.rglob("pairwise-tournament-manifest.json"))
                sidecars = list(tourn_dir.rglob("segmented-selector-materials.json"))
                self.assertEqual(len(manifests), 1)
                self.assertEqual(len(sidecars), 1)
                manifest_doc = json.loads(manifests[0].read_text(encoding="utf-8"))
                self.assertEqual(len(manifest_doc["bindings"]), 3)
                self.assertEqual(len(manifest_doc["reservation_ids"]), 3)
                self.assertEqual(manifest_doc["bracket_winner"], manifest_doc["final_selected"])

                # Bracket propagation with tournament_pick_second.flag: Pair 1 picks aliases[1] over aliases[0], Pair 2 picks aliases[2] over aliases[1]
                selected_step = tourn_state["capability_selection"]["selected"][0]
                alias_order = list(selected_step["aliases"].keys())
                self.assertEqual(manifest_doc["bracket_winner"], alias_order[-1])
                winner_slot = selected_step["aliases"][alias_order[-1]]
                expected_flow_id = {
                    "candidate-1": "FLOW-EXCL-RES-A",
                    "candidate-2": "FLOW-EXCL-RES-B",
                    "candidate-3": "FLOW-EXCL-RES-C",
                }[winner_slot]
                tourn_handoff = json.loads((tourn_dir / "handoff.json").read_text(encoding="utf-8"))
                self.assertEqual(
                    tourn_handoff["proposal"]["content"]["definitions"]["flows"][0]["id"],
                    expected_flow_id,
                )

                # Negative check: Tampering bracket_winner in manifest MUST fail verify-selection!
                orig_manifest_bytes = manifests[0].read_bytes()
                try:
                    bad_manifest = deepcopy(manifest_doc)
                    bad_manifest["bracket_winner"] = "tampered-alias"
                    manifests[0].write_text(json.dumps(bad_manifest), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        runtime.operate(
                            root,
                            planner="mvg",
                            command="verify-selection",
                            run_id="rtourn",
                            prepared_ref=prep["resume_ref"],
                            profile="3b-mvg-v1",
                            runner=codex_runner,
                            timeout_sec=120,
                        )
                finally:
                    manifests[0].write_bytes(orig_manifest_bytes)

                # 2. plan-capabilities --input-stage 3b (planner="capabilities", profile="3b-capabilities-v1") E2E
                compact_templates = {
                    "default": _build_sc25_candidate_content(frozen, variant="A"),
                    "candidate-1": _build_sc25_candidate_content(frozen, variant="A"),
                    "candidate-2": _build_sc25_candidate_content(frozen, variant="B"),
                    "candidate-3": _build_sc25_candidate_content(frozen, variant="C"),
                }
                (self.state_dir / "candidate_templates.json").write_text(
                    json.dumps(compact_templates, ensure_ascii=False), encoding="utf-8"
                )
                cap_args = type(
                    "Args",
                    (),
                    {
                        "repo_root": str(root),
                        "command": "prepare",
                        "input_stage": "3b",
                        "run_id": "cap3b",
                        "planning_contract": slim_inputs["contract_ref"],
                        "task_id": None,
                        "allow_unready_draft": False,
                        "source_manifest": "logs/ci/task-generation/source-manifest.v1.json",
                        "ledger": "logs/ci/task-generation/source-blocks.v1.json",
                        "semantics": "logs/ci/task-generation/semantic-requirements.v1.json",
                    },
                )()
                cap_prep = seg_input.prepare_from_cli(root, cap_args, planner="capabilities")
                self.assertEqual(cap_prep["status"], "prepared", cap_prep)
                cap_gen = runtime.operate(
                    root,
                    planner="capabilities",
                    command="generate",
                    run_id="rcap1",
                    prepared_ref=cap_prep["resume_ref"],
                    profile="3b-capabilities-v1",
                    runner=codex_runner,
                    timeout_sec=120,
                )
                self.assertEqual(cap_gen["selected"], "winner-chain", cap_gen)
                cap_rev = runtime.operate(
                    root,
                    planner="capabilities",
                    command="review",
                    run_id="rcap1",
                    prepared_ref=cap_prep["resume_ref"],
                    profile="3b-capabilities-v1",
                    runner=codex_runner,
                    timeout_sec=120,
                )
                self.assertEqual(cap_rev["status"], "passed", cap_rev)
                cap_ver = runtime.operate(
                    root,
                    planner="capabilities",
                    command="verify-selection",
                    run_id="rcap1",
                    prepared_ref=cap_prep["resume_ref"],
                    profile="3b-capabilities-v1",
                    runner=codex_runner,
                    timeout_sec=120,
                )
                self.assertEqual(cap_ver["status"], "passed", cap_ver)
                cap_handoff = runtime.run_location(root, "capabilities", "rcap1") / "handoff.json"
                self.assertTrue(cap_handoff.is_file())

                for row in self._read_logged_turns()[turns_before:]:
                    self.assertLessEqual(row["utf8_bytes"], 70_000)
        finally:
            pick_second_flag.unlink(missing_ok=True)

    def test_06_stage4_repair_replay_and_segmented_input_edge_cases(self):
        """Verify Stage 4 repair scope replay rejection and JSON-escaped / oversized-unit / >20KB dep_files edge cases."""
        # 1. Stage 4 repair replay rejection when an out-of-scope field is modified on repaired candidate-1 in r1
        ctx = self._ensure_sc25_r1_and_r2()
        root = ctx["root"]
        orig_inputs = ctx["orig_inputs"]
        sc25_proof_seam = ctx["sc25_proof_seam"]
        run_dir = ctx["run_dir"]
        run_state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

        with patch.object(audit, "verify_current_proof", new=sc25_proof_seam), patch.object(
            planning, "rules_identity", new=lambda _r: orig_inputs["dependencies"]["rules"]
        ):
            adm_c1 = run_state["candidate_admissions"]["candidate-1"]
            c1_prop = json.loads((run_dir / adm_c1["proposal_path"]).read_text(encoding="utf-8"))
            c1_proof = json.loads((run_dir / adm_c1["proof_path"]).read_text(encoding="utf-8"))
            self.assertEqual(
                seg_runtime.segmented_proof_errors(root, run_state, c1_prop, c1_proof),
                [],
            )

            # Tamper an out-of-scope field in the repaired proposal & delta & carrier check
            bad_prop = deepcopy(c1_prop)
            bad_prop["content"]["implementation_objects"][0]["lifecycle"] = "Tampered-out-of-scope-lifecycle"
            bad_prop["provenance"]["draft_chain"][-1]["content"] = deepcopy(bad_prop["content"])
            bad_prop["provenance"]["final_draft_identity"] = codec.canonical_digest(
                bad_prop["provenance"]["draft_chain"][-1]
            )
            bad_rec = deepcopy(c1_proof["records"][0])
            bad_rec["delta"]["candidate"] = deepcopy(bad_prop)
            bad_rec["proposal_sha256"] = seg_runtime.canonical_sha(bad_prop)
            bad_rec["record_sha256"] = seg_runtime.canonical_sha(
                {k: v for k, v in bad_rec.items() if k != "record_sha256"}
            )
            bad_proof = runtime.admission_proof(
                run_state, c1_proof["seed"], c1_proof["scopes"], [bad_rec], bad_prop
            )
            # Patch _cached_decode_generation_carrier for the last call so replay reaches repair_scope_errors!
            last_binding_sha = bad_rec["delta"]["generation_calls"][-1]["binding_sha256"]
            orig_decode = seg_runtime._cached_decode_generation_carrier

            def patched_decode(raw_val):
                dec = deepcopy(orig_decode(raw_val))
                if dec.get("stage") == "synthesis" and dec.get("ordinal") == len(bad_prop["provenance"]["draft_chain"]):
                    dec["content"] = deepcopy(bad_prop["content"])
                return dec

            seg_runtime._PROOF_ERRORS_CACHE.clear()
            with patch.object(seg_runtime, "_cached_decode_generation_carrier", new=patched_decode):
                errs = seg_runtime.segmented_proof_errors(root, run_state, bad_prop, bad_proof)
            self.assertTrue(
                any("b_route_repair_outside_domain" in e or "b_route_repair_replay_rejected" in e for e in errs),
                f"Expected out-of-scope repair rejection for {last_binding_sha}, got: {errs}",
            )

        # 2. JSON-escaped string splitting (quotes & newlines expansion stays bounded)
        quote_heavy = ('line-"escaped-quote"-\\slash\\\n') * 1200
        parts = seg_input._split_utf8_text(quote_heavy, 4096)
        self.assertGreater(len(parts), 5)
        self.assertEqual("".join(parts), quote_heavy)
        for p in parts:
            self.assertLessEqual(len(json.dumps(p, ensure_ascii=False).encode("utf-8")) - 2, 4096)

        # Stage 6b _split_oversized_unit with quote-heavy string payload
        big_unit = {
            "unit_id": "u-quote",
            "section": "target_templates",
            "key": "k0",
            "payload": {"big_str": ('"quoted"\n') * 5000},
        }
        split_u = adoption_review._split_oversized_unit(big_unit, max_raw_bytes=8000)
        self.assertGreater(len(split_u), 3)
        for su in split_u:
            self.assertLessEqual(len(adoption_review.text(su).encode("utf-8")), 8000)

        # 3. Oversized structured unit (> 18 KB gp_proposal_item) + > 20 KB priority dependencies.files spillover
        edge_inputs = deepcopy(orig_inputs)
        edge_inputs["global_proof"]["comparison"] = {"findings": []}
        edge_inputs["global_proof"]["extractions"] = []
        edge_inputs["global_proof"]["candidate"] = {"proposals": []}
        # Make proposal[0] acceptance_intent ~42 KB (> MAX_UNIT_TEXT_CHUNK_BYTES = 18,000!)
        edge_inputs["global_proof"]["proposals"]["proposals"][0]["acceptance_intent"] = " ".join(
            f'Intent-"clause"-{i:04d}' for i in range(2200)
        )
        # Add 260 priority-matching source-manifest.json dependency keys (> 28 KB total > 20 KB cap!)
        extra_deps = {
            f"logs/ci/extra-{i:04d}/source-manifest.json": f"sha256:{i:064x}" for i in range(260)
        }
        edge_inputs["dependencies"]["files"] = {
            **edge_inputs["dependencies"]["files"],
            **extra_deps,
        }

        hdr, units, hf = seg_input.decompose_inputs(edge_inputs)
        self.assertLessEqual(
            seg_input._compact_json_bytes(hdr["dependencies_files"]),
            seg_input.MAX_INLINE_DEPENDENCY_FILES_BYTES,
        )
        unit_kinds = {u["unit_kind"] for u in units}
        self.assertIn("structured_unit_chunk", unit_kinds)
        self.assertIn("dependency_files_slice", unit_kinds)
        fake_batches = [{"ordinal": 1, "unit_count": len(units), "parts": units}]
        self.assertEqual(seg_input.reconstruct_inputs(hdr, fake_batches, hf), edge_inputs)

    def test_07_stage3_single_window_compaction_sharding_and_fail_closed(self):
        """Verify Stage 3 single-window compaction, deterministic lossless sharding, non-shrink retry, and fail-closed >70k rejection."""
        cctx = self._ensure_compact_70k_fixture()
        root = cctx["root"]
        slim_inputs = cctx["slim_inputs"]
        proof_seam = cctx["proof_seam"]
        prep = cctx["prep"]
        frozen = cctx["frozen"]
        import _b_route_planning_wire as wire

        def _const(node: dict | None, default=None):
            if not isinstance(node, dict):
                return default
            if "const" in node:
                return node["const"]
            if "enum" in node and isinstance(node["enum"], list) and len(node["enum"]) == 1:
                return node["enum"][0]
            return default

        def _run_direct_stage3(run_id: str, handler):
            run_dir = runtime.run_location(root, "mvg", run_id)
            state = runtime.create_run(root, run_dir, run_id, prep["resume_ref"], "3b-mvg-v1")
            state["runtime_slot"] = "candidate-1"
            state["runtime_execution"] = 1
            ws = run_dir / "candidates/candidate-1/scope-1"
            (ws / "analysis-input").mkdir(parents=True, exist_ok=True)
            shutil.copy2(run_dir / "analysis-input/b-route-prepared.json", ws / "analysis-input/b-route-prepared.json")
            observed: list[dict] = []

            def invoke_factory(call_dir: Path):
                call_dir.mkdir(parents=True, exist_ok=True)

                def invoke(
                    prompt_text: str,
                    call_no: int,
                    *,
                    output_name: str,
                    output_schema_path: Path,
                    output_schema: dict,
                    before_dispatch,
                ):
                    before_dispatch(
                        {
                            "runtime_identity": state["runtime_identity"],
                            "planning_profile": "3b-mvg-v1",
                        }
                    )
                    ws_text = seg_input._runner_wrapper_text(
                        prompt_text, output_schema, compact_schema_file=(call_no > 0 and "checks" in output_schema.get("properties", {}))
                    )
                    # Generation uses compact_schema_file=False, semantic uses True; re-measure via runtime phase below
                    materials = wire.read_prompt(prompt_text, wire.CURRENT_SCHEMA)
                    compact_flag = materials["phase"] != "generation"
                    ws_text = seg_input._runner_wrapper_text(
                        prompt_text, output_schema, compact_schema_file=compact_flag
                    )
                    ws_bytes = len(ws_text.encode("utf-8"))
                    self.assertLessEqual(ws_bytes, seg_runtime.MAX_WORKSPACE_PAYLOAD_BYTES)
                    props = output_schema["properties"]
                    if materials["phase"] == "generation":
                        content_obj = handler(materials, observed)
                        out_obj = {
                            "schema_version": _const(props["schema_version"]),
                            "producer_schema_version": _const(props["producer_schema_version"]),
                            "input_identity": _const(props["input_identity"]),
                            "stage": _const(props["stage"]),
                            "ordinal": _const(props["ordinal"]),
                            "parent_draft_identities": list(materials["root_request"]["parent_draft_identities"]),
                            "content_json": json.dumps(content_obj, ensure_ascii=False, separators=(",", ":")),
                        }
                    else:
                        seg_obs = materials["obligations"]
                        src_idx = {row["id"]: i for i, row in enumerate(materials["qualified_sources"])}
                        checks = [
                            {
                                "id": i,
                                "verdict": "approved",
                                "rationale": f"Verified {ob['id']}.",
                                "source_block_ids": [
                                    next((src_idx[sid] for sid in ob["source_block_ids"] if sid in src_idx), 0)
                                ],
                            }
                            for i, ob in enumerate(seg_obs)
                        ]
                        out_obj = {
                            "schema_version": _const(props["schema_version"]),
                            "input_identity": _const(props["input_identity"]),
                            "runtime_identity": _const(props["runtime_identity"]),
                            "proposal_sha256": _const(props["proposal_sha256"]),
                            "verdict": "approved",
                            "findings": [],
                            "checks": checks,
                        }
                    out_path = call_dir / output_name
                    out_path.write_bytes(encoded(out_obj))
                    output_schema_path.write_bytes(encoded(output_schema))
                    return out_path, {
                        "execution_binding": {
                            "workspace": str(call_dir),
                            "output_path": str(out_path),
                            "request_payload": ws_text,
                        }
                    }

                return invoke

            res = seg_runtime.generate_segmented_append(
                root,
                state,
                ws,
                invoke_factory=invoke_factory,
                before_call=lambda phase, request_identity=None: None,
                checkpoint=lambda _ledger: None,
            )
            return res, observed

        valid_candidate = _build_sc25_candidate_content(frozen, variant="A")

        with patch.object(audit, "verify_current_proof", new=proof_seam), patch.object(
            planning, "rules_identity", new=lambda _r: slim_inputs["dependencies"]["rules"]
        ), patch.object(
            runtime,
            "verify_call",
            side_effect=lambda b: codec.strict_json_loads(Path(b["output_path"]).read_bytes()),
        ):
            # Case A: Reproduces r1c exact failure shape (batch -> tree_reduce emits 48KB -> single-window tree_reduce compacts -> final_synthesis fits <= 70KB)
            def handler_case_a(materials: dict, observed: list[dict]):
                req = materials["root_request"]
                role = req.get("synthesis_role") or req["stage"]
                observed.append({"stage": req["stage"], "role": role, "req": deepcopy(req)})
                if req["stage"] == "batch":
                    if req["ordinal"] == 1:
                        return {"batch_1": "x" * 52_000}
                    return {"batch_rest": req["ordinal"], "notes": "small"}
                if role == "tree_reduce":
                    if len(req["window_drafts"]) > 1:
                        return {"merged_uncompacted": "y" * 48_000}
                    return {"compacted": "ok", "from_len": len(req["window_drafts"])}
                return deepcopy(valid_candidate)

            res_a, obs_a = _run_direct_stage3("rst3-case-a", handler_case_a)
            self.assertEqual(res_a["status"], "admitted", res_a)
            batch_reqs_a = [r["req"] for r in obs_a if r["role"] == "batch"]
            self.assertTrue(
                all(
                    r.get("intermediate_draft_budget", {}).get("target_compact_bytes")
                    == seg_runtime.MAX_INTERMEDIATE_DRAFT_BYTES
                    for r in batch_reqs_a
                )
            )
            reduce_reqs_a = [r["req"] for r in obs_a if r["role"] == "tree_reduce"]
            self.assertTrue(
                any(len(r["window_drafts"]) == 1 and "compaction_target" in r for r in reduce_reqs_a),
                reduce_reqs_a,
            )

            # Case B: Extreme >70KB single window (nested list + single-key dict + large str) -> deterministic lossless sharding -> convergence
            extreme_payload = {
                "items_list": [{"idx": i, "payload": f"row-{i:04d}-{'Z' * 72}"} for i in range(300)],
                "single_key_nested": {"deep_str": "".join(f"[{i:04d}:nested]" for i in range(2100))},
                "plain_blob": "".join(f"<blob-{i:04d}>" for i in range(2400)),
                "source_tag": "sc25-lossless",
            }
            self.assertGreater(seg_runtime._compact_bytes_len(extreme_payload), 80_000)

            def handler_case_b(materials: dict, observed: list[dict]):
                req = materials["root_request"]
                role = req.get("synthesis_role") or req["stage"]
                observed.append({"stage": req["stage"], "role": role, "req": deepcopy(req)})
                if req["stage"] == "batch":
                    if req["ordinal"] == 1:
                        return deepcopy(extreme_payload)
                    return {"batch_rest": req["ordinal"]}
                if role == "tree_reduce":
                    return {
                        "compacted_shards": [w.get("shard", w["ordinal"]) for w in req["window_drafts"]],
                        "keys": sorted(k for w in req["window_drafts"] for k in w["content"].keys()),
                    }
                return deepcopy(valid_candidate)

            res_b, obs_b = _run_direct_stage3("rst3-case-b", handler_case_b)
            self.assertEqual(res_b["status"], "admitted", res_b)
            # Reconstruct batch-1 shards from observed Stage 3 calls (tree_reduce + final_synthesis) and assert 100% lossless recovery
            shard_windows_b: dict[str, dict] = {}
            for rec in obs_b:
                if rec["role"] in ("tree_reduce", "final_synthesis"):
                    for w in rec["req"]["window_drafts"]:
                        if w.get("ordinal") == 1 and "shard" in w:
                            shard_windows_b[w["shard"]] = w["content"]
            self.assertGreaterEqual(len(shard_windows_b), 4, shard_windows_b.keys())
            total_shard_count = int(next(iter(shard_windows_b)).split("/", 1)[1])
            self.assertEqual(
                set(shard_windows_b),
                {f"{idx}/{total_shard_count}" for idx in range(1, total_shard_count + 1)},
            )
            rec_items: list = []
            rec_nested = ""
            rec_blob = ""
            rec_tag = None
            for shard_key in sorted(shard_windows_b, key=lambda s: int(s.split("/", 1)[0])):
                chunk = shard_windows_b[shard_key]
                sk = chunk.get("_sharded_key")
                if sk == "items_list":
                    rec_items.extend(chunk["items_list"])
                elif sk == "single_key_nested":
                    rec_nested += chunk["single_key_nested"]["inner" if "inner" in chunk["single_key_nested"] else "deep_str"]
                elif sk == "plain_blob":
                    rec_blob += chunk["plain_blob"]
                else:
                    if "source_tag" in chunk:
                        rec_tag = chunk["source_tag"]
                    if "items_list" in chunk:
                        rec_items.extend(chunk["items_list"])
                    if "plain_blob" in chunk:
                        rec_blob += chunk["plain_blob"]
                    if "single_key_nested" in chunk:
                        rec_nested += chunk["single_key_nested"]["deep_str"]
            self.assertEqual(rec_items, extreme_payload["items_list"])
            self.assertEqual(rec_nested, extreme_payload["single_key_nested"]["deep_str"])
            self.assertEqual(rec_blob, extreme_payload["plain_blob"])
            self.assertEqual(rec_tag, extreme_payload["source_tag"])

            # Case C: Non-shrinking stubborn model on first two single-window compactions -> shards on single_compact_attempts == 2 -> recovers cleanly
            nonshrink_payload = {
                f"k_{i}": "".join(f"v{i}-{j:03d}-" for j in range(300)) for i in range(24)
            }
            self.assertGreater(seg_runtime._compact_bytes_len(nonshrink_payload), 44_000)
            reduce_single_calls = [0]

            def handler_case_c(materials: dict, observed: list[dict]):
                req = materials["root_request"]
                role = req.get("synthesis_role") or req["stage"]
                observed.append({"stage": req["stage"], "role": role, "req": deepcopy(req)})
                if req["stage"] == "batch":
                    if req["ordinal"] == 1:
                        return deepcopy(nonshrink_payload)
                    return {"ok": req["ordinal"]}
                if role == "tree_reduce":
                    has_shards = any("shard" in w for w in req["window_drafts"])
                    if not has_shards and len(req["window_drafts"]) == 1:
                        reduce_single_calls[0] += 1
                        if reduce_single_calls[0] <= 2:
                            return deepcopy(nonshrink_payload)
                    if not has_shards and len(req["window_drafts"]) > 1:
                        return deepcopy(nonshrink_payload)
                    return {"shrunk": True}
                return deepcopy(valid_candidate)

            res_c, obs_c = _run_direct_stage3("rst3-case-c", handler_case_c)
            self.assertEqual(res_c["status"], "admitted", res_c)
            self.assertEqual(reduce_single_calls[0], 2)
            self.assertTrue(
                any("shard" in w for r in obs_c if r["role"] == "tree_reduce" for w in r["req"]["window_drafts"])
            )

            # Case D: Fail-closed bounded stop when model refuses compaction forever (hits MAX_STAGE3_REDUCE_ROUNDS and rejects >70k final_synthesis)
            monolithic = {"unshrinkable": "M" * 48_000}

            def handler_case_d(materials: dict, observed: list[dict]):
                req = materials["root_request"]
                role = req.get("synthesis_role") or req["stage"]
                observed.append({"stage": req["stage"], "role": role, "req": deepcopy(req)})
                if req["stage"] == "batch":
                    if req["ordinal"] == 1:
                        return deepcopy(monolithic)
                    return {"tiny": req["ordinal"]}
                if role == "tree_reduce":
                    return deepcopy(monolithic)
                return deepcopy(valid_candidate)

            res_d, obs_d = _run_direct_stage3("rst3-case-d", handler_case_d)
            self.assertEqual(res_d["status"], "blocked", res_d)
            self.assertEqual(res_d["errors"][0]["code"], "append_execution_failure", res_d)
            self.assertIn(
                "b_route_segmented_payload_exceeds_70k:final-synthesis-",
                res_d["errors"][0]["detail"],
                res_d,
            )
            reduce_d = [r for r in obs_d if r["role"] == "tree_reduce"]
            self.assertEqual(len(reduce_d), 16, f"Expected MAX_STAGE3_REDUCE_ROUNDS=16, got {len(reduce_d)}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
