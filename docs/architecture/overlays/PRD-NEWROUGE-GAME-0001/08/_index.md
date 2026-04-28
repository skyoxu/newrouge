# 08 Overlay Index — PRD-NEWROUGE-GAME-0001

Status: active

Purpose:

- Organize Chapter 08 overlay artifacts for M1 playable gameplay, testing, and observability.
- Keep contract references and task mapping aligned with `.taskmaster/tasks/*` for gate checks.

Sections:

- [08-Feature-Slice-M1-Warrior.md](08-Feature-Slice-M1-Warrior.md)
- [08-Contracts-M1.md](08-Contracts-M1.md)
- [08-Testing-M1.md](08-Testing-M1.md)
- [08-Observability-M1.md](08-Observability-M1.md)
- [ACCEPTANCE_CHECKLIST.md](ACCEPTANCE_CHECKLIST.md)
- [overlay-manifest.json](overlay-manifest.json)

Contract-Refs:

- `Game.Core/Contracts/Services/ICombatService.cs`
- `Game.Core/Contracts/Services/IRunSummaryService.cs`
- `Game.Core/Contracts/Services/IRngService.cs`

Task-Refs:

- `.taskmaster/tasks/tasks.json`
- `.taskmaster/tasks/tasks_back.json`
- `.taskmaster/tasks/tasks_gameplay.json`

ADR-Refs:

- `docs/adr/ADR-0015-event-bus-publish-subscribe.md`
- `docs/adr/ADR-0016-acceptance-evidence-and-gates.md`
- `docs/adr/ADR-0032-task-refs-and-acceptance-contract.md`

Test-Refs:

- `Game.Core.Tests/`
- `Tests.Godot/tests/`

Notes:

- Do not duplicate base architecture content here.
- Keep this index updated when adding/removing 08 overlay files.

<!-- TASK_BASELINE_START -->
```json
{
  "generated_at": "2026-04-28T15:40:44.309928+00:00",
  "files": [
    {
      "path": ".taskmaster/tasks/tasks.json",
      "exists": true,
      "sha256": "437e1756c5d49372b2f5e8770d1089b0bde1fed8bd194050f281dcc1006526cf",
      "bytes": 177888
    },
    {
      "path": ".taskmaster/tasks/tasks_back.json",
      "exists": true,
      "sha256": "5fbbebd3cff9ebdbae38c3ac29104a05ed582f6de292191ba0da0d0ea0840e87",
      "bytes": 318865
    },
    {
      "path": ".taskmaster/tasks/tasks_gameplay.json",
      "exists": true,
      "sha256": "74eb614b361b10b715f463ad7204123e2d92d9ec273bce409c568f191012efe8",
      "bytes": 429307
    }
  ]
}
```
<!-- TASK_BASELINE_END -->
