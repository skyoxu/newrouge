"""Offline current-repository Capability input preflight; never invokes a model."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _planning_skill_common import atomic_json, build_blinded_analysis_bundle
from plan_capabilities import CANDIDATE_PROMPT
import codex_isolated_model_runner as codex


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    workspace = root / 'logs/ci/capability-input-integrity/current-offline'
    index = build_blinded_analysis_bundle(root, workspace / 'analysis-input',
        source_manifest_path=root / 'logs/ci/task-generation/source-manifest.v1.json',
        ledger_path=root / 'docs/planning/semantic-topology/source-blocks.v1.json',
        semantics_path=root / 'docs/planning/semantic-topology/semantic-requirements.v1.json',
        task_view_paths=[root / '.taskmaster/tasks/tasks_back.json', root / '.taskmaster/tasks/tasks_gameplay.json'],
        readiness_summary={'formal_ready': False, 'purpose': 'offline transport measurement only'})
    prompt = workspace / 'prompt.txt'
    prompt.write_text(CANDIDATE_PROMPT, encoding='utf-8')
    args = argparse.Namespace(workspace=str(workspace), prompt_file=str(prompt), output=str(workspace / 'candidate.json'),
        max_bytes=8 * 1024 * 1024, timeout_sec=1, output_schema='', preflight=True)
    try:
        codex.run(args)
        result = {'status': 'ready', 'model_invoked': False}
    except ValueError as exc:
        result = {'status': 'blocked', 'reason': str(exc), 'model_invoked': False}
    result.update(source_blocks=index['model_batch_index']['block_count'],
                  requirements=index['model_batch_index']['requirement_count'])
    atomic_json(workspace.parent / 'current-preflight.json', result)
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
