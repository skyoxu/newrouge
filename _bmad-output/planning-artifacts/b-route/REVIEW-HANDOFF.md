# newrouge B 路线独立审核交接

此分支只提供独立审核输入。尚未启动本次独立审核，也没有给出本次审核的通过或不通过结论。已有报告中的PASS、final及批准字段是原作者此前工作流记录，不能替代审核者的独立判断。

## 分支与快照

- 专用分支：`review/b-route-planning-2026-11-03`。
- 来源分支：`fix/capability-synthesis-input-integrity`；打包来源完整HEAD：`aa821824d1d2700e79cc615de34698dda12363d3`。
- 来源远端在打包前为：`cd925bdcae4b61992320773497f7edb729aac244`；main为：`8f93557d7f5f07b7931e3f4966a2dce04e458344`。
- 本分支继承该HEAD的两次本地文档提交，再添加最终Epic／Sprint及以下最小证据。主产物与来源工作区原始字节一致，不重新生成或改写批准正文。
- 原工作区的分支、HEAD、暂存区及全部未提交文件保持原样；本交接使用单独worktree。main和来源远端分支不作为推送目标。
- 本文件与review-manifest.json为此次打包新增说明。manifest枚举本次全部交付路径；除manifest自身外，每项保存SHA256和字节数。manifest自身不写入自引用哈希，完整提交身份由Git提供。

## 审核输入顺序

1. 原始需求；PRD及addendum／baseline-update，结合既有原始需求对账记录。
2. SPEC及全部七份companion；其中addendum／baseline-update和两份架构文档复用同一路径，不复制第二份。
3. Architecture主干及planning-records；原有reviews仅作历史资料。
4. 本范围的`epics.md`，再读取Sprint的`sprint-status.yaml`及`SPRINT-SCOPE.md`。
5. 对照本次明确选择的20份证据，核验来源哈希、Story批准范围、讨论修订与此前校验记录。

源文档中的历史“本轮不生成Story”、未推送、旧工作目录等语句是其对应阶段记录；后续用户另行授权Epic／Sprint，本分支不回写历史文档。部分讨论JSON保留终局确认之前的字段，请结合其中后续事件、最终epics frontmatter和校验报告的workflow_completion读取，不据旧字段推断当前授权。

## 已继承的明确依赖

- 当前仓库的AGENTS.md、workflow.md、DELIVERY_PROFILE.md、docs/agents、docs/workflows、docs/testing-framework.md、docs/adr和docs/architecture均从父提交继承，未另行修改。
- Taskmaster三联、Game.Core/Contracts、所引用的生产脚本／场景、Tests.Godot及docs/testing/mvg/m1-full.json均在同一Git树中，供按实际引用只读核对。Sprint文件不是第二套Task或MVG状态权威。
- 原始固定提交a8a363aa5f4ad09d5032731b0e7dfc5a17b8c89b和工作基线cd925bdcae4b61992320773497f7edb729aac244都在本分支祖先历史中；历史事实应按精确SHA读取，不能用当前文件替代旧版本。
- 两份ADR-0038须使用完整文件名；ADR状态以正文为准，ADR-0039及既有完成项恢复是继承能力，不是本次已完成B改造的证明。

## 被忽略证据的最小纳入范围

仅逐文件纳入下列20份已有文本／JSON证据，合计523636字节；保持logs原路径，不放宽.gitignore。它们是准备审核材料，不是新跑的审核、实施或运行验收。

- `logs/ci/2026-11-03/bmad-b-route-migration/new-baseline-evidence.md`
- `logs/ci/2026-11-03/b-route-epics/requirements-extraction.json`
- `logs/ci/2026-11-03/b-route-epics/existing-epics-hash.json`
- `logs/ci/2026-11-03/b-route-epics/final-validation.md`
- `logs/ci/2026-11-03/b-route-epics/final-validation.json`
- `logs/ci/2026-11-03/b-route-epics/epic-5-party-discussion.json`
- `logs/ci/2026-11-03/b-route-epics/epic-5-cutover-boundary-proposal.md`
- `logs/ci/2026-11-03/b-route-epics/epic-5-dual-path-input-evidence-proposal.md`
- `logs/ci/2026-11-03/b-route-epics/epic-1-approval.json`
- `logs/ci/2026-11-03/b-route-epics/epic-2-approval.json`
- `logs/ci/2026-11-03/b-route-epics/epic-3-approval.json`
- `logs/ci/2026-11-03/b-route-epics/epic-4-approval.json`
- `logs/ci/2026-11-03/b-route-epics/epic-5-approval.json`
- `logs/ci/2026-11-03/b-route-sprint-planning/readiness.md`
- `logs/ci/2026-11-03/b-route-sprint-planning/readiness.json`
- `logs/ci/2026-11-03/b-route-sprint-planning/preview.json`
- `logs/ci/2026-11-03/b-route-sprint-planning/generate.json`
- `logs/ci/2026-11-03/b-route-sprint-planning/refresh-preview.json`
- `logs/ci/2026-11-03/b-route-sprint-planning/validate.json`
- `logs/ci/2026-11-03/b-route-sprint-planning/taskmaster-snapshot.json`

## 未纳入资料与可能的审核影响

- 日志内历史草稿、修订前快照、每轮检查JSON、模型上下文、完整旧源码副本、pre-transfer-backup.tar.gz和安装／历史测试输出未上传。故本包不能重演每次编辑、安装或历史302项测试；相关源码本身可按祖先SHA读取。
- `_bmad-output/party-mode/memories/installed/.memlog.md`保留在原工作区，不纳入共享跨会话记忆。四项已采纳决定可从最终Story、epic-5-party-discussion.json及两份提案核对；若需逐轮原始对话或完整稿件演进，须另行明确申请对应最小资料。
- 本地忽略的`.agents/skills/bmad-*`与`_bmad/`安装、运行配置、设备路径和临时验证脚本未上传；不以本包声称精确重现原BMAD工具运行。版本与恢复命令见已有工作区说明，本文不授权运行安装或Build。
- 没有新增真实Task映射、Chapter5实施readiness、Windows／Godot／C#运行证据、真实切B／退A记录；这些尚未执行，不能将缺失材料解释成已完成或被省略的成功证据。
- Story5.10真实退出条件未成熟时保持blocked；标准Sprint状态backlog不授权执行。5.11不依赖实际退役，但不得代其完成或据此宣布Epic5全完。
- 未纳入凭据、设备私有配置或大量测试日志；未调用bmad-build，未修改程序、Taskmaster、main或来源分支，未合并或force push。

## 本次交付的准确文件清单

以下53项包含父提交已有的28份B路线文档、3份最终Epic／Sprint主文件、20份选择证据以及本次新增交接说明和manifest。权威依赖代码／文档由父提交提供，不属于此次改动清单。

- `_bmad-output/implementation-artifacts/b-route/SPRINT-SCOPE.md`
- `_bmad-output/implementation-artifacts/b-route/sprint-status.yaml`
- `_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/.memlog.md`
- `_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/ARCHITECTURE-SPINE.md`
- `_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/planning-records.md`
- `_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/result.json`
- `_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/reviews/lint-final.json`
- `_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/reviews/reconcile-baseline.md`
- `_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/reviews/reconcile-spec.md`
- `_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/reviews/review-adversarial.md`
- `_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/reviews/review-editorial.md`
- `_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/reviews/review-reality.md`
- `_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/reviews/review-rubric.md`
- `_bmad-output/planning-artifacts/b-route/REVIEW-HANDOFF.md`
- `_bmad-output/planning-artifacts/b-route/epics.md`
- `_bmad-output/planning-artifacts/b-route/review-manifest.json`
- `_bmad-output/planning-artifacts/newrouge-b-route-workspace.md`
- `_bmad-output/planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/.memlog.md`
- `_bmad-output/planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/addendum.md`
- `_bmad-output/planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/baseline-update.md`
- `_bmad-output/planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/prd.md`
- `_bmad-output/planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/reconcile-original-requirements.md`
- `_bmad-output/planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/result.json`
- `_bmad-output/planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/review-baseline-update.md`
- `_bmad-output/planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/review-editorial.md`
- `_bmad-output/planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/review-rubric.md`
- `_bmad-output/planning-artifacts/sources/newrouge-b-route-original-requirements.md`
- `_bmad-output/specs/spec-newrouge-b-route/.memlog.md`
- `_bmad-output/specs/spec-newrouge-b-route/SPEC.md`
- `_bmad-output/specs/spec-newrouge-b-route/migration-and-pilot.md`
- `_bmad-output/specs/spec-newrouge-b-route/result.json`
- `_bmad-output/specs/spec-newrouge-b-route/verification-contract.md`
- `_bmad-output/specs/spec-newrouge-b-route/workflow-contract.md`
- `logs/ci/2026-11-03/b-route-epics/epic-1-approval.json`
- `logs/ci/2026-11-03/b-route-epics/epic-2-approval.json`
- `logs/ci/2026-11-03/b-route-epics/epic-3-approval.json`
- `logs/ci/2026-11-03/b-route-epics/epic-4-approval.json`
- `logs/ci/2026-11-03/b-route-epics/epic-5-approval.json`
- `logs/ci/2026-11-03/b-route-epics/epic-5-cutover-boundary-proposal.md`
- `logs/ci/2026-11-03/b-route-epics/epic-5-dual-path-input-evidence-proposal.md`
- `logs/ci/2026-11-03/b-route-epics/epic-5-party-discussion.json`
- `logs/ci/2026-11-03/b-route-epics/existing-epics-hash.json`
- `logs/ci/2026-11-03/b-route-epics/final-validation.json`
- `logs/ci/2026-11-03/b-route-epics/final-validation.md`
- `logs/ci/2026-11-03/b-route-epics/requirements-extraction.json`
- `logs/ci/2026-11-03/b-route-sprint-planning/generate.json`
- `logs/ci/2026-11-03/b-route-sprint-planning/preview.json`
- `logs/ci/2026-11-03/b-route-sprint-planning/readiness.json`
- `logs/ci/2026-11-03/b-route-sprint-planning/readiness.md`
- `logs/ci/2026-11-03/b-route-sprint-planning/refresh-preview.json`
- `logs/ci/2026-11-03/b-route-sprint-planning/taskmaster-snapshot.json`
- `logs/ci/2026-11-03/b-route-sprint-planning/validate.json`
- `logs/ci/2026-11-03/bmad-b-route-migration/new-baseline-evidence.md`
