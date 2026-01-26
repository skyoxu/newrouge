# ADR-0024: 模板谱系与命名口径（Template Lineage & Naming）

- Status: Accepted
- Context:
  - 本仓库是 Windows-only 的 Godot 4.5 + C#/.NET 8 游戏模板，目标是“可复制、可审计、可在 CI 中开箱即用”。
  - 模板仓库经常被复制派生为多个“兄弟项目”。如果文档/脚本残留了旧仓库名、旧路径、旧工程名，就会在后续工作中持续误导人和自动化工具（尤其是 CI、任务回链校验、验收脚本）。
  - 需要一条 ADR 固化：模板与派生项目之间的谱系关系、命名口径、以及“哪些名字应该稳定、哪些名字必须在派生后立即替换”。
- Decision:
  1. 谱系定位
     - 本仓库：作为“上游模板（Upstream Template）”，沉淀与玩法无关的基础能力（架构口径、质量门禁、脚本工具、迁移文档、可观测性/安全基线等）。
     - 派生仓库：作为“下游项目（Downstream Project）”，在不改变模板口径的前提下实现具体玩法/产品；如确需改变口径，必须新增或 Supersede 相应 ADR。
  2. 命名分层（避免把不同层级的名字混在一起）
     - 仓库名（Repo Name）：对外唯一标识。所有外链（README、Actions badge、Issue/PR 模板、Release Notes）必须使用派生仓库自己的仓库名。
     - 工程名（Solution/Project Names）：模板允许保持稳定（例如 `NewRouge.sln`、`Game.Core` 等），以降低复制成本；派生仓库如选择重命名，必须同步修改脚本/CI 中的入口路径。
     - 项目路径（Local Paths）：文档中禁止把某台机器上的绝对路径当作“唯一真实路径”。
       - 推荐写法：使用相对路径（相对仓库根目录）或用占位符表示（如 `<RepoRoot>`、`%REPO_ROOT%`）。
       - 若必须示例绝对路径，必须明确标注为“示例”，不得把具体项目名写死在路径中。
  3. 派生仓库的必做替换清单（止损）
     - 所有文档中出现的“本仓库/本项目/本模板”必须能在派生语境下自洽：
       - “本仓库”指当前仓库，而不是上游模板仓库。
       - 如需引用上游模板，必须显式写“上游模板仓库”，避免使用模糊称呼。
     - 对外标识必须替换：README、PULL_REQUEST_TEMPLATE、workflow 名称/说明中的仓库名、Release 说明等。
     - 对内入口如保持模板默认名（例如 `NewRouge.sln`），允许不替换，但文档必须解释“工程名与仓库名不同层级”。
- Consequences:
  - 模板仓库与派生仓库的文档/脚本需要定期扫描“旧仓库名/旧路径/旧项目名”残留；发现后应以本 ADR 的分层口径进行修正。
  - 该 ADR 不规定任何具体派生项目名称；派生项目可以另立 ADR 描述自身谱系与命名，但不得反向污染上游模板口径。
- Supersedes: None
- References:
  - ADR-0018-godot-csharp-tech-stack
  - ADR-0011-windows-only-platform-and-ci
  - ADR-0005-quality-gates

