---
title: "Audit Artifact Pipeline"
project: "newrouge"
date: "2026-01-23"
author: "skyo"
ssot:
  - project-context.md
  - docs/adr/ADR-0032-save-resume-determinism.md
---

# 审计与取证工件归档链路（user:// → logs/**）

目标：解决“运行时审计在 user://，但 CI/排障需要仓库内 logs/** 证据”的断层，避免出现“本地有日志、CI 没证据、无法复现”的扯皮。

---

## 1) 运行时写入（事实来源）

- 运行时审计写入：`user://logs/security/security-audit.jsonl`
- 字段口径（SSoT）：`{ts, area, action, reason, target, caller}`（见 `project-context.md` 与 ADR-0032）

---

## 2) 归档目标（仓库内证据）

所有自动化测试/门禁/冒烟的最终证据必须落到仓库目录 `logs/**`，并按日期归档：

- CI 工件：`logs/ci/<YYYY-MM-DD>/**`
- 引擎冒烟：`logs/e2e/<YYYY-MM-DD>/**`

---

## 3) 归档责任与触发时机（硬口径）

无论使用哪种 Runner（GdUnit4、自建 Runner、Python 驱动 headless），都必须满足：

1) **在测试运行结束时**（无论成功/失败），把 `user://logs/security/security-audit.jsonl` 复制/汇总到仓库：
   - 目标路径（推荐）：`logs/ci/<YYYY-MM-DD>/security/security-audit.jsonl`
2) 如果发生存档迁移（成功或失败），必须同时归档迁移摘要：
   - `logs/ci/<YYYY-MM-DD>/save-migrations/<timestamp>/summary.json`
3) 归档失败必须视为门禁失败（因为“无证据 = 不可复现”）。

---

## 4) Windows 上的 user:// 位置（提示）

Godot 在 Windows 的 user:// 通常落在 AppData 下的项目专属目录（路径由 Godot 决定）。

门禁脚本/Runner 必须显式解析并取证该目录，而不是假设固定路径。

