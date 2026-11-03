# B 路线记录只读校验（Story 1.4）

公共字段和 owner 边界由 [记录格式合同](b-route-record-contract.md) 定义；可执行定义仅位于 `docs/planning/b-route/schemas/` 的六份记录 schema 与 common。身份适配与诊断继续由 `_b_route_codec.py` 拥有，校验服务为 `_b_route_records.py`。本入口不启用 B 路线、不写正式规划记录或 Taskmaster 三联。

## Windows 准备

在仓库根目录使用已有 Python 3.12 环境，安装本 Story 锁定依赖；不需要 Godot、模型、数据库或 Chapter 6。

```powershell
py -3.12 -m pip install -r scripts/python/requirements-b-route.txt
```

缺少校验库返回 `dependency_unavailable`，不会退化为只检查 required 字段。schema 只使用本地显式注册的资源；未知 `$ref` 返回 `schema_resource_error`，不会联网下载。

## 单记录 CLI

`--input` 是仓库内原 bytes 来源，`--record-path` 可选，用于校验该记录的精确受管逻辑地址。候选可以存放在 `logs/**`，无需在正式路径创建文件。

```powershell
py -3.12 scripts/python/validate_b_route_records.py record --repo-root . --input logs/ci/story-1-4/candidate-plan.json --record-path docs/planning/b-route/plans/PLAN-EXAMPLE/2.json
```

结果 `claim` 为 `record_structure_only`。成功仅说明该记录的严格 JSON、schema、身份及已给逻辑路径有效；`references_validated` 和 `monotonicity_checked` 始终为 false。API 接受 dict 时不制造原始文件身份，`raw_identity` 为 null。

## 候选 bundle CLI

候选载体只允许以下结构；所有字段必需，不接受额外字段或重复逻辑目标。`path` 是正式逻辑路径，`source_path` 是同一 `--repo-root` 内的候选源路径。载体不带正式 schema、实体或发布身份，不是第七类治理记录。

```json
{
  "records": [
    {
      "path": "docs/planning/b-route/plans/PLAN-EXAMPLE/2.json",
      "source_path": "logs/ci/story-1-4/candidate-plan.json"
    }
  ]
}
```

上例只演示载体形状。bundle 必须从 catalog 解析到完整必需闭包，所需 policy、origins、plan、binding、receipt 和外部原 bytes 应在载体内或可由安全 reader 从 root 定位。零 Task 3B 允许没有 binding、空 origins 和空冻结 A 集合，无需虚构 Task 或 readiness。

```powershell
py -3.12 scripts/python/validate_b_route_records.py bundle --repo-root . --input logs/ci/story-1-4/candidates.json
py -3.12 scripts/python/validate_b_route_records.py bundle --repo-root . --input logs/ci/story-1-4/candidates.json --catalog-path docs/planning/b-route/catalog.v1.json --baseline logs/ci/story-1-4/baseline.json --task-master .taskmaster/tasks/tasks.json --task-back .taskmaster/tasks/tasks_back.json --task-gameplay .taskmaster/tasks/tasks_gameplay.json
```

`--baseline` 使用同一载体格式。三联参数须全部提供或全部省略；当前 binding 有 Task 映射时必须提供完整三联上下文，严格核对 master 整数 ID 与业务视图原字符串 ID。没有 Task 映射时不要求三联。

候选按逻辑路径优先于磁盘文件。候选摘要错误直接失败，不回退到磁盘取得成功。bundle 只收原 bytes，API 传入 dict 不能证明 raw 引用。所有源文件经公共安全 reader 读取，拒绝根外链接与不安全路径；同次读取缓存发现漂移会失败。此机制是只读观察，不提供隔离、锁或正式 snapshot。

成功结果 `claim` 为 `candidate_structure_only`，分别报告 `schema_validated`、`references_validated`、`monotonicity_checked`。只有提供且核对给定 baseline 才报告单调性已查；这不证明未提供的全部历史。Task 定义投影 codec 仅核字段，`target_projection_verified` 为 false，不声称已计算投影。

历史 receipt 使用自身冻结 owner 映射核对结构；当前 scope 只比较实际相关的 owner 闭包。已由另一当前 head 的 receipt 绑定新后像的历史 policy／origins 目标，会在 `historical_targets_not_revalidated` 中逐项列出 operation 和路径；当前 TypedReference 仍精确核验。这些旧后像不被声明为仍匹配当前文件。

两个命令均向 stdout 输出一份公共 JSON 结果，成功退出 0，校验／输入／参数失败退出 1；诊断的六字段空项显式为 null。命令内部禁写 pycache，无输出或修复参数。需要保留证据时，将 stdout 重定向到 `logs/**`。

## API 与证明边界

```python
from pathlib import Path
from _b_route_records import TaskJoinContext, validate_bundle, validate_record

single = validate_record(raw_bytes, path="docs/planning/b-route/plans/PLAN-EXAMPLE/2.json")
candidate = validate_bundle(
    records, root=Path(repo_root),
    catalog_path="docs/planning/b-route/catalog.v1.json",
    baseline=baseline_bytes_or_none,
    task_join=TaskJoinContext(master, back, gameplay),
)
```

调用方应把 `scripts/python` 加入 Python import 路径。`records`／`baseline` 为逻辑路径到原 bytes 的映射；`TaskJoinContext` 接原三联对象。`validate_record(data, *, path=None)` 接受 bytes、UTF-8 str 或 dict，`validate_bundle(records, *, root=None, catalog_path=..., baseline=None, task_join=None)` 返回同一结构化结果接口。

OwnedRef 校验原 locator、实际文件集合和各文件 raw digest；source manifest／ledger 的 native 字符串 revision 与 manifest digest 独立核对。contract 复用既有符号／DTO resolver 的安全预读 seam，保留原 text digest 语义。文件／JSON Pointer／行范围按合同分派，verification record 使用原 evidence fragment；Markdown heading 返回 `unsupported_locator`。

允许合法 Flow 循环与跨 plan 共享，catalog owner 和 receipt 递归解析闭包须精确一致。这里只证明声明、定位和给定引用关系；不证明循环终止、实现类型、编译、引擎、规划准入、正式发布、Task readiness 或 runtime 通过。原 identity-only API 的 `schema_validated:false` 不被升级，Taskmaster 仍是唯一 Task 状态权威。

## 验证与真实 Windows 证据

```powershell
py -3.12 -B -m unittest discover -s scripts/python/tests -p test_b_route_records.py -v
py -3.12 -B -m unittest discover -s scripts/python/tests -p test_b_route_codec.py -v
```

每套预算 180 秒。独立工作流 `.github/workflows/story-1-4-windows.yml` 仅响应 `test/b-route-story-1-4-windows-2026-11-03` 的 push，检出事件 SHA；job 预算 10 分钟，仅具 `contents: read`。它保留依赖安装和两套单测实际耗时、原始 stdout／stderr、源码 raw／Git blob 身份，以及独立 CLI 正负、raw 身份、candidate 遮蔽和输入树不变证据。

真实 Windows reader 的 Unicode／大小写、根内及根外 junction、独占占用测试必须实际 `ok`；skip 不算通过。每轮 artifact 仅上传 `logs/ci/story-1-4-windows/<run_id>-<attempt>/`，原始失败也保留。Linux 结果与未执行／skip 均不能替代真实 Windows 证据。
