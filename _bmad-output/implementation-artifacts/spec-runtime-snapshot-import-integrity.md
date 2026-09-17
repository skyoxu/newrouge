---
title: '运行时快照的 GdUnit 导入缓存完整性'
type: 'bugfix'
created: '2026-09-17'
status: 'done'
baseline_commit: 'a6cff3ba9e3690e645dadb0e026f00799e8c3fb4'
review_loop_iteration: 0
context:
  - 'docs/workflows/project-health-knowledge.md'
  - '_bmad-output/implementation-artifacts/spec-project-health-local-scan.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Knowledge 页面在 main 模式执行运行时验证时，Godot/GdUnit 会改写隔离副本中已跟踪的 GdUnit 插件 `.import` 元数据。完整性校验将这些运行时派生改动误判为输入漂移，使通过的任务全部降级为 `runtime_unverified`。

**Approach:** 将例外严格限定为 `Tests.Godot/addons/gdUnit4/` 下的 `.import` 文件：它们既不复制到运行快照，也不进入输入清单哈希。项目自身及任何其他位置的 `.import` 文件仍必须复制并校验。

## Boundaries & Constraints

**Always:** main 与 workspace 快照必须使用同一条路径规则；快照仍从固定 local main 或 workspace 来源生成；其余受跟踪文件继续由 SHA-256 清单保护；运行证据、任务结果和测试报告仍只写入 `logs/**`；代码、测试及日志文本保持英文。

**Ask First:** 若需要排除 GdUnit 插件范围外的文件、放宽任意其他 `.import` 文件校验、改变 `runtime_verified` 的 revision/断言/证据要求，必须暂停并请求确认。

**Never:** 不排除所有 `.import` 文件；不跳过输入完整性校验；不修改任务三联、游戏源、Godot/GdUnit 插件内容或现有用户未提交的配置与知识目录改动；不以重新运行全量审计掩盖回归。

## I/O & Edge-Case Matrix

| 场景 | 输入 / 状态 | 预期输出 / 行为 | 错误处理 |
|---|---|---|---|
| 插件派生导入文件 | GdUnit 插件路径内存在 `.import` | main 与 workspace 快照不复制该文件，清单不含该路径 | Godot 可在隔离副本自行再生文件，不触发输入漂移 |
| 项目导入文件 | 任何非 GdUnit 插件 `.import` | 文件仍复制且记录 SHA-256 | 若运行中被改写，保持 fail-closed，结果不得标记 verified |
| 已通过任务 | 运行器只改写被排除的插件导入文件 | 完整证据、同 main revision、零失败的任务标记 `runtime_verified` | 其他清单文件漂移仍降级为 `runtime_unverified` |
| 非法或普通路径 | 不是精确插件范围内的 `.import` | 不适用例外 | 沿用现有安全相对路径和快照错误处理 |

</frozen-after-approval>

## Code Map

- `scripts/python/_project_health_runtime_snapshot.py` -- `prepare_snapshot` 在 main archive 与 workspace 文件遍历中复制文件并建立 `manifest['files']`；新增一个窄路径谓词，使两条分支一致排除 GdUnit 插件 `.import`。
- `scripts/python/project_health_runtime.py` -- `_verify` 使用 manifest 哈希判定 `inputs_unchanged`，不应放宽此处的总体完整性条件；修复后的清单自然避免派生文件污染。
- `scripts/sc/tests/test_project_health_runtime_snapshot.py` -- 现有真实 Git main/workspace 快照及证据边界测试的合适扩展点。
- `docs/workflows/project-health-knowledge.md` -- 已规定副本中的导入、编译与测试产物只能在副本中生成，且 main 验证要求输入未变化；本次实现必须保持这一承诺。
- `logs/ci/project-health-knowledge/runtime/batches/6341e2bf97344e01bbfa49fbb4d53ab0/input-manifest.json` -- 诊断证据：GdUnit 运行后仅该插件范围内八个 `.png.import` 文件产生哈希漂移。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/sc/tests/test_project_health_runtime_snapshot.py` -- 新增快照范围和运行结果回归测试：证明精确插件 `.import` 被排除、普通 `.import` 被保留，并证明仅改写被排除路径的 main 运行仍可 verified -- 锁定修复边界并满足 TDD 红灯要求。
- [x] `scripts/python/_project_health_runtime_snapshot.py` -- 以一个可审查的私有路径谓词在 main/workspace 两条快照路径中排除精确 GdUnit 插件 `.import` -- 避免派生缓存污染输入清单，同时不泛化例外。
- [x] `scripts/python/project_health_runtime.py` -- 不需调整；现有 manifest 使用继续保留 revision、报告计数和其余文件哈希检查 -- 防止借修复弱化可信运行证据。
- [x] `scripts/sc/tests/test_project_health_runtime_snapshot.py` -- 已运行该模块全量回归并确认原 main/workspace 隔离断言仍绿 -- 确认新规则未影响现有输入边界。

**Acceptance Criteria:**
- Given GdUnit 插件路径中的 `.import` 文件，when 构建 main 或 workspace 快照，then 副本和输入清单均不包含该文件。
- Given `Tests.Godot/addons/gdUnit4/` 外的 `.import` 文件，when 构建快照，then 该文件保留且清单记录其哈希。
- Given main 模式中通过的任务仅导致 GdUnit 插件导入文件再生，when 完整性和 revision 校验完成，then 任务保持 `passed` 且 `runtime_verified` 为 true。
- Given 任何保留在清单中的输入被改写，when 验证完成，then 任务仍降级为 `runtime_unverified`。

## Spec Change Log

## Design Notes

例外应在输入清单生成处实现，而不是在结束时按变更扩展忽略列表。前者使“允许 Godot 再生的派生缓存”不构成受声明输入；后者可能掩盖本应校验的项目文件。路径必须同时满足固定前缀 `Tests.Godot/addons/gdUnit4/` 与 `.import` 后缀，防止将普通资源或其它插件纳入例外。

## Verification

**Commands:**
- `py -3 -m unittest scripts.sc.tests.test_project_health_runtime_snapshot -v` -- 预期：新增测试先在旧实现失败，修复后该模块全绿。
- `py -3 -m unittest scripts.sc.tests.test_project_health_knowledge -v` -- 预期：运行时 revision 漂移和证据合并回归仍通过。
- `git diff --check` -- 预期：无空白错误。

## Suggested Review Order

**快照输入边界**

- 精确排除仅允许 Godot 再生的 GdUnit 导入缓存。
  [`_project_health_runtime_snapshot.py:15`](../../scripts/python/_project_health_runtime_snapshot.py#L15)

- main 与 workspace 共享同一窄化排除规则。
  [`_project_health_runtime_snapshot.py:43`](../../scripts/python/_project_health_runtime_snapshot.py#L43)

- workspace 路径仍哈希并保护所有未排除输入。
  [`_project_health_runtime_snapshot.py:57`](../../scripts/python/_project_health_runtime_snapshot.py#L57)

**回归保护**

- 同时锁定插件缓存排除与普通导入文件保留。
  [`test_project_health_runtime_snapshot.py:18`](../../scripts/sc/tests/test_project_health_runtime_snapshot.py#L18)

- 仅再生缓存时，完整主分支证据可保持 verified。
  [`test_project_health_runtime_snapshot.py:53`](../../scripts/sc/tests/test_project_health_runtime_snapshot.py#L53)

- 插件普通文件改动仍必须降级运行时结果。
  [`test_project_health_runtime_snapshot.py:89`](../../scripts/sc/tests/test_project_health_runtime_snapshot.py#L89)
