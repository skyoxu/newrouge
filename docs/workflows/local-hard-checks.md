# 本地硬校验执行指南（newrouge 适配版）

本文档定义 `F:\newrouge` 当前可执行的本地硬校验入口。

## 结论先行

- 当前仓库 **未接入** `py -3 scripts/python/dev_cli.py run-local-hard-checks`。
- 当前仓库 `dev_cli.py` 可用子命令：
  - `run-ci-basic`
  - `run-quality-gates`
  - `run-gdunit-hard`
  - `run-gdunit-full`
  - `run-preflight`
  - `run-smoke-strict`
  - `detect-project-stage`
  - `doctor-project`
  - `check-directory-boundaries`
  - `project-health-scan`
  - `serve-project-health`
- 本仓本地硬门建议以 `run-ci-basic` 为主入口，必要时叠加 `run-quality-gates --gdunit-hard --smoke`。

## 推荐执行顺序（Windows）

1. 预检（快）

```powershell
py -3 scripts/python/dev_cli.py run-preflight --configuration Debug
```

2. Project-health 预热（建议）

```powershell
py -3 scripts/python/dev_cli.py project-health-scan
```

3. 核心硬门（必跑）

```powershell
py -3 scripts/python/dev_cli.py run-ci-basic --godot-bin C:\Godot\Godot_v4.5.1-stable_mono_win64_console.exe
```

4. 引擎侧补充硬门（按需）

```powershell
py -3 scripts/python/dev_cli.py run-quality-gates --godot-bin C:\Godot\Godot_v4.5.1-stable_mono_win64_console.exe --gdunit-hard --smoke
```

## 适用场景

- 提交前需要一次完整本地止损校验。
- CI 失败后需要在本地按同口径重放。
- 任务门禁跑完后，希望追加引擎安全集和严格冒烟验证。

## 与上游文档的差异（必须知道）

- 本仓已接入 `project-health` 脚本与 `dev_cli` 子命令。
- 本仓尚未接入上游 `run-local-hard-checks` 协议化 harness（sidecar 协议链）。
- 因此不要假设本仓存在 `local-hard-checks-<run-id>/summary.json` 这一整套上游产物。

## 止损规则

- 不要手工拼接大量命令替代主入口，优先走 `dev_cli.py` 子命令，避免执行顺序漂移。
- 若仅排查 GdUnit 问题，直接用：

```powershell
py -3 scripts/python/dev_cli.py run-gdunit-hard --godot-bin C:\Godot\Godot_v4.5.1-stable_mono_win64_console.exe
```

- 若仅看仓库健康，不要跑重流程，直接用：

```powershell
py -3 scripts/python/dev_cli.py project-health-scan
```

## 相关文档

- `docs/workflows/project-health-dashboard.md`
- `docs/workflows/gate-bundle.md`
- `docs/testing-framework.md`
