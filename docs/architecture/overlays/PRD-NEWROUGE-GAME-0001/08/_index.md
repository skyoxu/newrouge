---
PRD-ID: PRD-NEWROUGE-GAME-0001
Title: 08章功能纵切索引（M1: Warrior）
Status: Draft
ADR-Refs:
  - ADR-0005
  - ADR-0010
  - ADR-0011
  - ADR-0019
  - ADR-0020
  - ADR-0025
  - ADR-0032
  - ADR-0033
Arch-Refs:
  - CH01
  - CH02
  - CH03
  - CH05
  - CH06
  - CH07
  - CH09
  - CH10
Test-Refs:
  - logs/ci/2026-02-12/docs-utf8-gate/summary.json
  - logs/ci/2026-02-12/prd-gdd-consistency/summary.json
  - logs/ci/2026-02-12/sc-check-acceptance-garbled/summary.json
---

# 08章功能纵切索引（M1: Warrior）
本目录是 `PRD-NEWROUGE-GAME-0001` 的 Overlay 08，仅覆盖 M1 最小可玩纵切。

跨切面阈值、质量门禁、安全基线与可观测性口径统一引用 Base/ADR，不在本目录复制阈值。

## 使用边界
- 仅承载功能纵切：实体、事件、运行时路径、验收、测试回链。
- 不承载实现细节代码与排期说明；任务 SSoT 以 `.taskmaster/tasks/*.json` 为准。
- 任何改动必须同步 `ACCEPTANCE_CHECKLIST.md` 的 `Test-Refs` 与任务回链。

## 文档目录
- `08-Feature-Slice-M1-Warrior.md`：M1 玩法纵切与运行时骨干。
- `08-Contracts-M1.md`：M1 契约边界与命名约束。
- `08-Observability-M1.md`：M1 日志、审计、取证与发布健康对齐。
- `08-Testing-M1.md`：M1 测试策略与执行证据路径。
- `ACCEPTANCE_CHECKLIST.md`：M1 交付验收总清单。

## 任务基线快照（用于漂移提醒）
当 `tasks.json` 或视图任务文件变化时，运行
`py -3 scripts/python/remind_overlay_task_drift.py --write` 更新此快照。

<!-- TASK_BASELINE_START -->
```json
{
  "generated_at": "2026-02-14T08:36:30.290511+00:00",
  "files": [
    {
      "path": ".taskmaster/tasks/tasks.json",
      "exists": true,
      "sha256": "e2cc14ad2d320786f287e33f8c909f4f1a0261b29b68d7d08e3b0bfdabfb8876",
      "bytes": 83467
    },
    {
      "path": ".taskmaster/tasks/tasks_back.json",
      "exists": true,
      "sha256": "f8ddb38d82f92a62e2caf5a6d181d859d4a34b6988c64027f5af0a34c7b67f6d",
      "bytes": 131450
    },
    {
      "path": ".taskmaster/tasks/tasks_gameplay.json",
      "exists": true,
      "sha256": "624234fecb810930af4e99fc8822abb43131f19cdaefc5d1b1ec802bdee0e674",
      "bytes": 228262
    }
  ]
}
```
<!-- TASK_BASELINE_END -->

## 与任务回链（硬要求）
- Overlay 锚点必须覆盖任务 `T1-T57` 的 `overlay_refs`。
- `T56` 与 `T57` 必须可被搜索命中：
  - T56: `Audit JSONL validation + gate integration`
  - T57: `Traceability gate for ADR/Chapter/Overlay links`

## 变更纪律
- 新增、删除或重命名 08 下文档时，必须同步更新本索引和验收清单。
- 若口径变化影响 ADR（尤其 `ADR-0032`/`ADR-0033`），必须先补 ADR 再改 Overlay。
- `Test-Refs` 可先占位，但路径必须稳定且可被后续自动化替换为真实用例。
