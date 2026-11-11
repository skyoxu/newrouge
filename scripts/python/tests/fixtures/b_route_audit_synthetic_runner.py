"""SYNTHETIC OS runner fixture. No model or semantic validation is performed."""
import argparse
import base64
import json
import time
import sys
from pathlib import Path

MODE = "clean"
MODEL = "synthetic/source-audit-v1"
CODE_ROOT = None


def decode_input(value):
    if value.get("schema_version") == "newrouge.b-route-source-producer-input.v5":
        sys.path.insert(0, CODE_ROOT or str(Path(__file__).resolve().parents[2]))
        from _b_route_source_audit import decode_producer_input
        return decode_producer_input(value, value["producer_schema_policy"])
    return value


def citation(file, block=None):
    raw = base64.b64decode(file["raw_base64"])
    if block is None:
        return {"path": file["path"], "raw_digest": file["raw_digest"], "block_id": None,
                "byte_start": 0, "byte_end": len(raw), "quote": raw.decode("utf-8")}
    # Fixture files use line spans, with raw CRLF retained.
    lines = raw.decode("utf-8").splitlines(keepends=True)
    start = len("".join(lines[:block["line_start"] - 1]).encode("utf-8"))
    quote = "".join(lines[block["line_start"] - 1:block["line_end"]])
    return {"path": file["path"], "raw_digest": file["raw_digest"], "block_id": block["block_id"],
            "byte_start": start, "byte_end": start + len(quote.encode("utf-8")), "quote": quote}


def execute(request):
    phase, data, ident = request["phase"], request["payload"], request["input_identity"]
    if phase == "extract":
        assert set(data) == {"file"}, "Extraction must not see the first proposal."
        file = data["file"]
        coverage = [{"block_id": b["block_id"], "disposition": "obligation", "reason": "Synthetic fixture coverage.", "basis": []}
                    for b in file["blocks"]]
        obligations = [{"local_id": f"local-{i}", "statement": b["raw_text"], "kind": "handoff" if MODE == "omission" else "obligation",
                        "citations": [citation(file, b)]} for i, b in enumerate(file["blocks"])]
        output = {"schema_version": "newrouge.b-route-source-audit.v1.extract", "input_identity": ident,
                  "file": {"path": file["path"], "raw_digest": file["raw_digest"]},
                  "file_review": "Synthetic full file review including empty bytes.", "coverage": coverage, "obligations": obligations}
        if MODE == "bad-quote" and obligations:
            obligations[0]["citations"][0]["quote"] = "Invented quotation."
        if MODE == "missing-block" and coverage:
            coverage.pop()
        if MODE == "duplicate-block" and coverage:
            coverage.append(coverage[0])
        if MODE == "reordered-blocks":
            coverage.reverse()
        if MODE == "unknown" and obligations:
            obligations[0]["kind"] = "unknown"
        if MODE in {"deferred", "supported-deferred"} and coverage:
            coverage[0]["disposition"] = "deferred"
            coverage[0]["basis"] = [citation(file, file["blocks"][0])]
        return output
    files, extractions = data["files"], data["extractions"]
    proposals = [p["proposal_id"] for p in data["proposals"]["proposals"]]
    reviews = [{"path": f["path"], "block_id": b["block_id"], "decision": "accepted",
                "reason": "Synthetic disposition review.", "basis": [], "finding_ids": []} for f in files for b in f["blocks"]]
    reviews += [{"path": f["path"], "block_id": None, "decision": "accepted",
                 "reason": "Synthetic empty file review.", "basis": [], "finding_ids": []} for f in files if not f["blocks"]]
    obligations = [{"path": e["file"]["path"], "local_id": r["local_id"], "decision": "represented",
                    "proposal_ids": proposals[:1], "reason": "Synthetic representation review.", "basis": [], "finding_ids": []}
                   for e in extractions for r in e["obligations"]]
    findings = []
    if MODE in {"omission", "conflict"}:
        cite = [citation(f, f["blocks"][-1]) for f in files if f["blocks"]]
        cite = cite[:2] if MODE == "conflict" else cite[:1]
        findings = [{"finding_id": "fixture-finding", "input_identity": ident,
            "classification": MODE, "severity": "blocking", "return_owner": "source-owner",
            "reason": "Synthetic omitted handoff." if MODE == "omission" else "Synthetic conflicting originals.",
            "citations": cite, "affected_proposal_ids": [], "unprojected": True}]
        obligations[0].update(decision="omitted" if MODE == "omission" else "conflicting", proposal_ids=[], finding_ids=["fixture-finding"])
    if obligations and not proposals:
        if not findings:
            file = next(f for f in files if f["blocks"])
            findings = [{"finding_id": "fixture-finding", "input_identity": ident,
                "classification": "omission", "severity": "blocking", "return_owner": "source-owner",
                "reason": "Synthetic absent projection.", "citations": [citation(file, file["blocks"][0])],
                "affected_proposal_ids": [], "unprojected": True}]
        for row in obligations:
            row.update(decision="omitted", proposal_ids=[], finding_ids=["fixture-finding"])
    output = {"schema_version": "newrouge.b-route-source-audit.v1.compare", "input_identity": ident,
        "file_reviews": [{"file": {"path": f["path"], "raw_digest": f["raw_digest"]}, "reason": "Synthetic complete file review."} for f in files],
        "disposition_reviews": reviews, "obligation_reviews": obligations, "findings": findings}
    if MODE == "fake-pass":
        output["approved"] = True
    if MODE == "bad-proposal" and obligations:
        obligations[0]["proposal_ids"] = ["FR-INVENTED"]
    if MODE == "missing-file":
        output["file_reviews"].pop()
    if MODE == "supported-deferred":
        for row in reviews:
            file = next(f for f in files if f["path"] == row["path"])
            block = next((b for b in file["blocks"] if b["block_id"] == row["block_id"]), None)
            row["basis"] = [citation(file, block)]
        for row in obligations:
            file = next(f for f in files if f["path"] == row["path"])
            row.update(decision="deferred", proposal_ids=[], basis=[citation(file, file["blocks"][0])])
    return output


def wire_output(request, output):
    transport = request.get("producer_transport", {})
    if transport.get("schema_version") not in ("input-identity-span-ref.v3", "input-identity-span-ref.v4", "input-identity-span-ref.v5") or MODE == "literal":
        return output
    files = [request["payload"]["file"]] if request["phase"] == "extract" else request["payload"]["files"]
    originals = {file["path"]: base64.b64decode(file["raw_base64"]) for file in files}
    keys = ("path", "raw_digest", "block_id", "byte_start", "byte_end")
    spans = {tuple(row[key] for key in keys): row["span_ref"] for row in transport["spans"]}
    slots = (("coverage", "basis"), ("obligations", "citations")) if request["phase"] == "extract" else (
        ("disposition_reviews", "basis"), ("obligation_reviews", "basis"), ("findings", "citations"))
    for group, field in slots:
        for row in output[group]:
            for index, cite in enumerate(row[field]):
                key = tuple(cite[name] for name in keys)
                raw = originals[cite["path"]][cite["byte_start"]:cite["byte_end"]]
                if key in spans and raw == cite["quote"].encode("utf-8"):
                    row[field][index] = {"span_ref": spans[key]}
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--describe", action="store_true")
    for name in ("workspace", "prompt-file", "output", "output-schema", "timeout-sec", "model-request-budget"):
        parser.add_argument("--" + name)
    args = parser.parse_args()
    if args.describe:
        print(json.dumps({"schema_version": "newrouge.isolated-model-runner.v1", "filesystem_scope": "prompt_only",
            "fresh_session_per_invocation": True, "can_read_outside_workspace": False, "model": MODEL,
            "model_tools": [], "supports_request_budget": True, "synthetic": True}))
        return
    if MODE == "timeout":
        time.sleep(int(args.timeout_sec) + 90)
    if MODE == "crash":
        raise RuntimeError("Synthetic runner crash after dispatch.")
    workspace = Path(args.workspace)
    assert set(p.name for p in workspace.iterdir()) == {"input.json", "schema.json", "prompt.txt"}
    request = json.loads((workspace / "input.json").read_bytes())
    request = decode_input(request)
    output = wire_output(request, execute(request))
    Path(args.output).write_bytes((json.dumps(output, ensure_ascii=False) + "\n").encode("utf-8"))
    print(json.dumps({"schema_version": "newrouge.isolated-model-runner-receipt.v1", "model": MODEL,
        "model_identity": MODEL, "model_identity_verified": True, "model_identity_source": "synthetic-fixture",
        "model_identity_evidence": [{"source": "synthetic-fixture", "model": MODEL}], "model_tools": ["shell"] if MODE == "tools" else [],
        "request_count_observable": True, "model_request_count": 2 if MODE == "extra-dispatch" else 1,
        "runner_invocations": 1, "workspace": workspace.as_posix(), "synthetic": True,
        "output_chars": len(Path(args.output).read_text(encoding="utf-8"))}))


if __name__ == "__main__":
    main()
