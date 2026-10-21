"""Reproduce the canonical link audit without preparing or invoking a model."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts/python"))

import _capability_task_evidence as codec
from _capability_input_integrity import _task_view_is_active, task_master_rows, task_master_status
from _planning_skill_common import atomic_json, load_json, scrub_capability_answers


def main():
    masters = task_master_rows(load_json(ROOT / ".taskmaster/tasks/tasks.json"))
    statuses = {codec.identity(row): task_master_status(row) for row in masters}
    views = {name: [row for row in scrub_capability_answers(load_json(ROOT / name))
                    if _task_view_is_active(row, statuses)]
             for name in (".taskmaster/tasks/tasks_back.json", ".taskmaster/tasks/tasks_gameplay.json")}
    requirements = scrub_capability_answers(load_json(
        ROOT / "docs/planning/semantic-topology/semantic-requirements.v1.json")["requirements"])
    blocks = scrub_capability_answers(load_json(
        ROOT / "docs/planning/semantic-topology/source-blocks.v1.json")["blocks"])
    payload = {"task_views": views, "related_evidence": {
        "master_tasks": scrub_capability_answers(masters), "requirements": requirements, "source_blocks": blocks}}
    catalog = codec.freeze_reference_catalog(ROOT, [row for rows in views.values() for row in rows] + requirements)
    links, pointers = codec.declared_relations(payload, catalog)
    packet = codec.compress(payload)
    packet["relation_index"]["declared_links"] = links
    packet["source_pointers"] = pointers
    proof = codec.validate_packet(payload, packet, catalog)
    report = {"scope": "canonical_authority_declared_links_only", "formal_ready": False, "model_invoked": False,
        "requirements": len(requirements), "source_blocks": len(blocks), "master_tasks": len(masters),
        "declared_link_count": len(links), "roundtrip_equal": proof["roundtrip_equal"],
        "input_sha256": proof["original_sha256"], "packet_sha256": proof["packet_sha256"],
        "all_external_refs_resolve": all(target["status"] == "valid"
                                        for entries in catalog.values() for target in entries.values()),
        "formal_gates_not_checked": ["local source manifest", "current Chapter 5 readiness",
                                    "runner isolation", "real model acceptance"]}
    atomic_json(Path(__file__).with_name("declared-link-audit.json"), report)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
