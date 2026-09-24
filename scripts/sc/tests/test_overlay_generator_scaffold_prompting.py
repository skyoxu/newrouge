import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SC_DIR = REPO_ROOT / "scripts" / "sc"
if str(SC_DIR) not in sys.path:
    sys.path.insert(0, str(SC_DIR))

import _overlay_generator_scaffold_prompting as scaffold_prompting
import _overlay_generator_prompting as page_prompting


class OverlayGeneratorScaffoldPromptingTests(unittest.TestCase):
    def test_long_new_gdd_and_old_page_tail_are_visible_in_every_page_mode(self) -> None:
        source = "A" * 33_000 + "\nNew GDD requires shop save and resume."
        companion = [{"path": "docs/gdd/new.md", "excerpt": "B" * 14_500 + "\nRetain old reward regression."}]
        current = "C" * 5_500 + "\nOld contract invariant must remain."
        kwargs = dict(prd_path=Path("docs/gdd/new.md"), prd_text=source,
                      prd_id="PRD-SHOP", companion_docs=companion,
                      page={"filename": "08-shop.md", "page_kind": "feature"},
                      page_context={}, current_page_text=current)
        for builder in (scaffold_prompting.build_overlay_page_scaffold_prompt,
                        page_prompting.build_overlay_page_patch_prompt,
                        page_prompting.build_overlay_page_prompt):
            with self.subTest(builder=builder.__name__):
                prompt = builder(**kwargs, **({"base_page": {}} if builder is scaffold_prompting.build_overlay_page_scaffold_prompt else {}))
                self.assertIn("New GDD requires shop save and resume.", prompt)
                self.assertIn("Retain old reward regression.", prompt)
                self.assertIn("Old contract invariant must remain.", prompt)
        with self.assertRaisesRegex(ValueError, "source context exceeds"):
            scaffold_prompting.build_overlay_page_scaffold_prompt(**{**kwargs, "prd_text": "A" * 181_000}, base_page={})

    def test_build_overlay_page_scaffold_prompt_should_include_base_page(self) -> None:
        page = {
            "filename": "_index.md",
            "page_kind": "index",
            "current_title": "Current Index",
            "headings": ["Directory Role", "Document Groups"],
            "path": "docs/architecture/overlays/PRD-TEMPLATE-V1/08/_index.md",
        }
        base_page = {
            "filename": "_index.md",
            "page_kind": "index",
            "title": "Current Index",
            "purpose": "Current purpose",
            "adr_refs": ["ADR-0004"],
            "arch_refs": ["CH04"],
            "test_refs": ["scripts/python/validate_task_overlays.py"],
            "task_ids": ["66"],
            "sections": [{"heading": "Directory Role", "bullets": ["Old bullet"]}],
        }

        prompt = scaffold_prompting.build_overlay_page_scaffold_prompt(
            prd_path=Path("prd_template.md"),
            prd_text="Primary PRD body",
            prd_id="PRD-TEMPLATE-V1",
            companion_docs=[{"path": "PRD_RULES_FREEZE.md", "excerpt": "Freeze body"}],
            page=page,
            page_context={"master_task_ids": ["66"], "titles": ["Index routing"]},
            base_page=base_page,
            current_page_text="# Existing Index\n",
        )

        self.assertIn("Scaffold base page:", prompt)
        self.assertIn('"title": "Current Index"', prompt)
        self.assertIn("Return a scaffold update object", prompt)
        self.assertIn("omit that section from update", prompt)

    def test_parse_and_validate_scaffold_update_should_extract_update_payload(self) -> None:
        raw_output = """
        {
          "filename": "_index.md",
          "update": {
            "purpose": "Updated purpose",
            "adr_refs": ["ADR-0004", "ADR-0005"],
            "arch_refs": ["CH04"],
            "test_refs": ["scripts/python/validate_task_overlays.py"],
            "task_ids": ["66"],
            "sections": [
              {"heading": "Directory Role", "bullets": ["New bullet"]}
            ]
          }
        }
        """

        update = scaffold_prompting.parse_and_validate_scaffold_update(
            raw_output=raw_output,
            expected_filename="_index.md",
        )

        self.assertEqual("Updated purpose", update["purpose"])
        self.assertEqual(["ADR-0004", "ADR-0005"], update["adr_refs"])
        self.assertEqual(["66"], update["task_ids"])


if __name__ == "__main__":
    unittest.main()
