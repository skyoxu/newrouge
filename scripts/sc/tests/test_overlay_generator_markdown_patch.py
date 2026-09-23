import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SC_DIR = REPO_ROOT / "scripts" / "sc"
if str(SC_DIR) not in sys.path:
    sys.path.insert(0, str(SC_DIR))

import _overlay_generator_markdown_patch as patchmod
import _overlay_generator_scaffold_prompting as prompting


class OverlayGeneratorMarkdownPatchTests(unittest.TestCase):
    def test_sparse_section_addition_keeps_unstructured_old_constraint(self) -> None:
        old = "# Page\n\n## Rules\n\nOld invariant prose must survive.\n\n- Old bullet\n"
        result = patchmod.apply_scaffold_update_to_existing_markdown(
            current_markdown=old,
            scaffold_update={"strict_incremental_patch": True, "sections": [{"heading": "Rules", "bullets": ["New bullet"]}]},
        )
        self.assertIn("Old invariant prose must survive.", result)
        self.assertIn("- Old bullet", result)
        self.assertIn("- New bullet", result)
        with self.assertRaisesRegex(ValueError, "manual review"):
            patchmod.apply_scaffold_update_to_existing_markdown(
                current_markdown=old,
                scaffold_update={"strict_incremental_patch": True, "sections": [{"heading": "Rules", "operation": "replace", "bullets": ["New bullet"]}]},
            )
        with self.assertRaisesRegex(ValueError, "Unsupported scaffold section operation"):
            prompting.parse_and_validate_scaffold_update(
                raw_output='{"filename":"page.md","update":{"sections":[{"heading":"Rules","remove_bullets":["Old bullet"]}]}}',
                expected_filename="page.md",
            )

    def test_apply_scaffold_update_to_existing_markdown_should_preserve_rich_intro_and_nested_sections(self) -> None:
        current_markdown = """---

PRD-ID: PRD-TEMPLATE-V1

Title: 08 Feature Slice Index (V3 Campaign Mode)

Status: Accepted

ADR-Refs:

  - ADR-0003

---

# PRD-TEMPLATE-V1 Feature Slice Index

This directory is the V3 campaign overlay root. It is driven by:

- `prd_template.md`

Compatibility note:

Some filenames intentionally keep old T2-oriented names.

## Directory Role

- Provide stable overlay targets for `T66~T175`.

## Document Groups

### Rules Freeze and Assertion Routing

- `08-rules-freeze-and-assertion-routing.md`

### Governance Owner Pages

- `08-governance-freeze-change-control.md`
"""
        scaffold_update = {
            "purpose": "Rewritten purpose that should not replace rich intro.",
            "task_ids": ["66", "67"],
            "sections": [
                {"heading": "Directory Role", "bullets": ["Updated role bullet"]},
                {"heading": "Document Groups", "bullets": ["This should not flatten nested headings"]},
            ],
        }

        patched = patchmod.apply_scaffold_update_to_existing_markdown(
            current_markdown=current_markdown,
            scaffold_update=scaffold_update,
        )

        self.assertIn("Some filenames intentionally keep old T2-oriented names.", patched)
        self.assertIn("### Rules Freeze and Assertion Routing", patched)
        self.assertIn("- Updated role bullet", patched)
        self.assertNotIn("This should not flatten nested headings", patched)
        self.assertNotIn("Rewritten purpose that should not replace rich intro.", patched)

    def test_apply_scaffold_update_to_existing_markdown_should_replace_simple_task_coverage_block(self) -> None:
        current_markdown = """---
PRD-ID: PRD-TEMPLATE-V1
Title: Checklist
Status: Draft
---

# V3 Campaign Acceptance Checklist

Simple intro.

Task coverage:

- 66, 67

## One

- Keep me
"""
        scaffold_update = {
            "task_ids": ["66", "67", "68"],
            "sections": [],
        }

        patched = patchmod.apply_scaffold_update_to_existing_markdown(
            current_markdown=current_markdown,
            scaffold_update=scaffold_update,
        )

        self.assertIn("Task coverage:", patched)
        self.assertIn("- 66, 67, 68", patched)
        self.assertNotIn("- 66, 67\n", patched)

    def test_sparse_update_should_merge_existing_coverage_and_bullets(self) -> None:
        current = """# Overlay

Task coverage:

- 10, 11

## Rules

- Keep old rule
"""
        patched = patchmod.apply_scaffold_update_to_existing_markdown(
            current_markdown=current,
            scaffold_update={
                "task_ids": ["12"],
                "sections": [{"heading": "Rules", "bullets": ["Add new rule"]}],
            },
        )
        self.assertIn("- 10, 11, 12", patched)
        self.assertIn("- Keep old rule", patched)
        self.assertIn("- Add new rule", patched)

    def test_explicit_remove_and_hash_drift_are_fail_closed(self) -> None:
        import hashlib
        current = """# Overlay

Task coverage:

- 10, 11

## Rules

- Keep
- Retire
"""
        expected = hashlib.sha256(current.encode("utf-8")).hexdigest()
        patched = patchmod.apply_scaffold_update_to_existing_markdown(
            current_markdown=current,
            scaffold_update={
                "expected_sha256": "sha256:" + expected,
                "remove_task_ids": ["10"],
                "sections": [{"heading": "Rules", "remove_bullets": ["Retire"]}],
            },
        )
        self.assertIn("- 11", patched)
        self.assertNotIn("- 10, 11", patched)
        self.assertIn("- Keep", patched)
        self.assertNotIn("- Retire", patched)
        with self.assertRaisesRegex(ValueError, "hash drifted"):
            patchmod.apply_scaffold_update_to_existing_markdown(
                current_markdown=current + "\nchanged",
                scaffold_update={"expected_sha256": expected, "task_ids": ["12"]},
            )

    def test_strict_existing_patch_should_block_complex_or_missing_targets(self) -> None:
        complex_page = """# Overlay

## Rules

### Nested

- Keep
"""
        with self.assertRaisesRegex(ValueError, "too complex"):
            patchmod.apply_scaffold_update_to_existing_markdown(
                current_markdown=complex_page,
                scaffold_update={
                    "strict_incremental_patch": True,
                    "sections": [{"heading": "Rules", "bullets": ["New"]}],
                },
            )
        with self.assertRaisesRegex(ValueError, "no matching target section"):
            patchmod.apply_scaffold_update_to_existing_markdown(
                current_markdown="# Overlay\n\n## Rules\n\n- Keep\n",
                scaffold_update={
                    "strict_incremental_patch": True,
                    "sections": [{"heading": "Missing", "bullets": ["New"]}],
                },
            )

    def test_apply_scaffold_update_to_existing_markdown_should_reject_foreign_section_headings(self) -> None:
        current_markdown = """---
PRD-ID: PRD-TEMPLATE-V1
Title: Index
Status: Accepted
---

# Index

## Directory Role

- Keep role

## Document Groups

- Keep groups
"""
        scaffold_update = {
            "sections": [
                {"heading": "一、文档完整性验收", "bullets": ["Wrong page content"]},
                {"heading": "二、架构设计验收", "bullets": ["Wrong page content"]},
            ]
        }

        patched = patchmod.apply_scaffold_update_to_existing_markdown(
            current_markdown=current_markdown,
            scaffold_update=scaffold_update,
        )

        self.assertEqual(current_markdown, patched)


if __name__ == "__main__":
    unittest.main()
