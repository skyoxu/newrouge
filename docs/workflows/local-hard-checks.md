# 本地硬校验执行指南（newrouge 对齐版）

本文档定义 `F:\newrouge` 当前可执行的 `run-local-hard-checks` 入口与行为。

## 主入口

```powershell
py -3 scripts/python/dev_cli.py run-local-hard-checks --godot-bin C:\Godot\Godot_v4.5.1-stable_mono_win64_console.exe
```

不带 `--godot-bin` 时，会跳过 GdUnit/Smoke，仅执行仓库级硬门与 dotnet。

## 默认执行顺序

`run-local-hard-checks` 按以下顺序执行，遇到首个失败即停止：

1. `project-health-scan`
2. `run_gate_bundle.py --mode hard`
3. `run_dotnet.py`
4. `run_gdunit.py`（仅当提供 `--godot-bin`）
5. `smoke_headless.py --strict`（仅当提供 `--godot-bin`）

## 关键参数

- `--solution`：默认 `Game.sln`
- `--configuration`：默认 `Debug`
- `--godot-bin`：启用 GdUnit + Strict Smoke
- `--delivery-profile`：传递交付档位（默认从配置解析）
- `--task-file`：可重复，覆盖 hard gate 读取的任务文件
- `--out-dir`：指定本次运行产物目录
- `--run-id`：指定稳定 run id
- `--timeout-sec`：strict smoke 超时，默认 5

## 产物

默认产物目录：

`logs/ci/<YYYY-MM-DD>/local-hard-checks-<run-id>/`

关键 sidecar：

- `summary.json`
- `execution-context.json`
- `repair-guide.json`
- `repair-guide.md`
- `run-events.jsonl`
- `harness-capabilities.json`
- `run_id.txt`
- `<step>.log`

latest 索引：

`logs/ci/<YYYY-MM-DD>/local-hard-checks-latest.json`

## 止损规则

- 日常全量本地硬门优先使用本入口，不再手工拼接三到五条命令。
- 若只排查仓库健康，直接跑 `project-health-scan`，不要拉长流程。
- 若只排查引擎测试，优先用 `run-gdunit-hard`。
