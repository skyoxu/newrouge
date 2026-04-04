using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task55CoverageScriptEntrypointBindingTests
{
    // ACC:T55.1
    [Fact]
    public void ShouldUseDefaultThresholds_WhenNoCoverageOverrideEnvironmentVariablesProvided()
    {
        var payload = RunPythonJson(
            """
            import importlib.util, json, pathlib
            root = pathlib.Path.cwd()
            spec = importlib.util.spec_from_file_location("run_dotnet", root / "scripts/python/run_dotnet.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            lines, lines_src = mod._resolve_threshold_value(preferred_key="COVERAGE_LINES_THRESHOLD", legacy_key="COVERAGE_LINES_MIN", default_value=mod.DEFAULT_LINES_THRESHOLD)
            branches, branches_src = mod._resolve_threshold_value(preferred_key="COVERAGE_BRANCHES_THRESHOLD", legacy_key="COVERAGE_BRANCHES_MIN", default_value=mod.DEFAULT_BRANCHES_THRESHOLD)
            print(json.dumps({"lines": lines, "branches": branches, "lines_src": lines_src, "branches_src": branches_src}))
            """,
            new Dictionary<string, string?>
            {
                ["COVERAGE_LINES_THRESHOLD"] = null,
                ["COVERAGE_LINES_MIN"] = null,
                ["COVERAGE_BRANCHES_THRESHOLD"] = null,
                ["COVERAGE_BRANCHES_MIN"] = null,
            });

        payload.GetProperty("lines").GetDouble().Should().Be(90.0);
        payload.GetProperty("branches").GetDouble().Should().Be(85.0);
        payload.GetProperty("lines_src").GetString().Should().Be("default");
        payload.GetProperty("branches_src").GetString().Should().Be("default");
    }

    // ACC:T55.2
    [Fact]
    public void ShouldHonorCoverageOverrideEnvironmentVariables_WhenThresholdsAreProvided()
    {
        var payload = RunPythonJson(
            """
            import importlib.util, json, pathlib
            root = pathlib.Path.cwd()
            spec = importlib.util.spec_from_file_location("run_dotnet", root / "scripts/python/run_dotnet.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            lines, lines_src = mod._resolve_threshold_value(preferred_key="COVERAGE_LINES_THRESHOLD", legacy_key="COVERAGE_LINES_MIN", default_value=mod.DEFAULT_LINES_THRESHOLD)
            branches, branches_src = mod._resolve_threshold_value(preferred_key="COVERAGE_BRANCHES_THRESHOLD", legacy_key="COVERAGE_BRANCHES_MIN", default_value=mod.DEFAULT_BRANCHES_THRESHOLD)
            print(json.dumps({"lines": lines, "branches": branches, "lines_src": lines_src, "branches_src": branches_src}))
            """,
            new Dictionary<string, string?>
            {
                ["COVERAGE_LINES_THRESHOLD"] = "93",
                ["COVERAGE_LINES_MIN"] = "95",
                ["COVERAGE_BRANCHES_MIN"] = "88",
                ["COVERAGE_BRANCHES_THRESHOLD"] = null,
            });

        payload.GetProperty("lines").GetDouble().Should().Be(93.0);
        payload.GetProperty("branches").GetDouble().Should().Be(88.0);
        payload.GetProperty("lines_src").GetString().Should().Be("COVERAGE_LINES_THRESHOLD");
        payload.GetProperty("branches_src").GetString().Should().Be("COVERAGE_BRANCHES_MIN");
    }

    // ACC:T55.3
    [Fact]
    public void ShouldDifferentiateSoftAndHardGate_WhenMeasuredCoverageIsBelowEffectiveThresholds()
    {
        var payload = RunPythonJson(
            """
            import datetime as dt
            import importlib.util, json, pathlib, tempfile, os
            root = pathlib.Path.cwd()
            rd_spec = importlib.util.spec_from_file_location("run_dotnet", root / "scripts/python/run_dotnet.py")
            run_dotnet = importlib.util.module_from_spec(rd_spec)
            rd_spec.loader.exec_module(run_dotnet)
            qg_spec = importlib.util.spec_from_file_location("quality_gates", root / "scripts/python/quality_gates.py")
            quality_gates = importlib.util.module_from_spec(qg_spec)
            qg_spec.loader.exec_module(quality_gates)
            with tempfile.TemporaryDirectory() as tmp:
                tmp_root = pathlib.Path(tmp)
                date = dt.date.today().strftime("%Y-%m-%d")
                cov_path = tmp_root / "coverage.cobertura.xml"
                cov_path.write_text('<coverage lines-covered="80" lines-valid="100" branches-covered="70" branches-valid="100"></coverage>', encoding="utf-8")
                trx_path = tmp_root / "tests.trx"
                trx_path.write_text("trx", encoding="utf-8")

                def fake_run_cmd(args, cwd=None, timeout=0):
                    return 0, "ok"

                run_dotnet.run_cmd = fake_run_cmd
                run_dotnet.parse_paths_from_test_output = lambda out: {"trx_paths": [str(trx_path)], "coverage_paths": [str(cov_path)]}
                run_dotnet.pick_latest_existing = lambda paths: paths[0] if paths else None

                original_cwd = os.getcwd()
                os.chdir(tmp_root)
                try:
                    os.environ["COVERAGE_LINES_THRESHOLD"] = "90"
                    os.environ["COVERAGE_BRANCHES_THRESHOLD"] = "85"
                    os.environ["COVERAGE_GATE_MODE"] = "soft"
                    soft_rc = run_dotnet.main(["--solution", "NewRouge.sln", "--out-dir", str(tmp_root / "run_soft")])
                    soft_summary = json.loads((tmp_root / "run_soft" / "summary.json").read_text(encoding="utf-8"))

                    os.environ["COVERAGE_GATE_MODE"] = "hard"
                    hard_rc = run_dotnet.main(["--solution", "NewRouge.sln", "--out-dir", str(tmp_root / "run_hard")])
                    hard_summary = json.loads((tmp_root / "run_hard" / "summary.json").read_text(encoding="utf-8"))
                finally:
                    os.chdir(original_cwd)

                quality_gates._repo_root = lambda: tmp_root
                unit_summary = tmp_root / "logs" / "unit" / date / "summary.json"
                unit_summary.parent.mkdir(parents=True, exist_ok=True)
                base_payload = {
                    "measured_line_coverage": 80.0,
                    "measured_branch_coverage": 70.0,
                    "effective_thresholds": {"lines_min": 90, "branches_min": 85},
                    "pass": False,
                }
                unit_summary.write_text(json.dumps({**base_payload, "gate_mode": "soft"}), encoding="utf-8")
                qg_soft = quality_gates._resolve_coverage_gate_summary(date)
                unit_summary.write_text(json.dumps({**base_payload, "gate_mode": "hard"}), encoding="utf-8")
                qg_hard = quality_gates._resolve_coverage_gate_summary(date)
                print(json.dumps({
                    "run_dotnet_soft_rc": soft_rc,
                    "run_dotnet_hard_rc": hard_rc,
                    "run_dotnet_soft_pass": bool(soft_summary.get("pass")),
                    "run_dotnet_hard_pass": bool(hard_summary.get("pass")),
                    "run_dotnet_soft_warning_count": len(soft_summary.get("warnings", [])),
                    "run_dotnet_hard_warning_count": len(hard_summary.get("warnings", [])),
                    "quality_gates_soft_pass": bool(qg_soft.get("pass")),
                    "quality_gates_soft_suite_status": qg_soft.get("suite_status"),
                    "quality_gates_hard_pass": bool(qg_hard.get("pass")),
                    "quality_gates_hard_suite_status": qg_hard.get("suite_status")
                }))
            """);

        payload.GetProperty("run_dotnet_soft_rc").GetInt32().Should().Be(0);
        payload.GetProperty("run_dotnet_hard_rc").GetInt32().Should().NotBe(0);
        payload.GetProperty("run_dotnet_soft_pass").GetBoolean().Should().BeTrue();
        payload.GetProperty("run_dotnet_hard_pass").GetBoolean().Should().BeFalse();
        payload.GetProperty("run_dotnet_soft_warning_count").GetInt32().Should().BeGreaterThan(0);
        payload.GetProperty("run_dotnet_hard_warning_count").GetInt32().Should().Be(0);
        payload.GetProperty("quality_gates_soft_pass").GetBoolean().Should().BeTrue();
        payload.GetProperty("quality_gates_soft_suite_status").GetString().Should().Be("warn");
        payload.GetProperty("quality_gates_hard_pass").GetBoolean().Should().BeFalse();
        payload.GetProperty("quality_gates_hard_suite_status").GetString().Should().Be("failed");
    }

    // ACC:T55.4
    [Fact]
    public void ShouldEmitMachineReadableCoverageSummaryContract_WhenCoverageGateSummaryIsResolved()
    {
        var payload = RunPythonJson(
            """
            import importlib.util, json, pathlib, tempfile
            root = pathlib.Path.cwd()
            spec = importlib.util.spec_from_file_location("quality_gates", root / "scripts/python/quality_gates.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            with tempfile.TemporaryDirectory() as tmp:
                tmp_root = pathlib.Path(tmp)
                mod._repo_root = lambda: tmp_root
                date = "2026-04-04"
                summary_path = tmp_root / "logs/unit" / date / "summary.json"
                summary_path.parent.mkdir(parents=True, exist_ok=True)
                summary_path.write_text(json.dumps({
                    "measured_line_coverage": 91.2,
                    "measured_branch_coverage": 88.4,
                    "effective_thresholds": {"lines_min": 90, "branches_min": 85},
                    "gate_mode": "hard",
                    "pass": True
                }), encoding="utf-8")
                resolved = mod._resolve_coverage_gate_summary(date)
                suite_runs = {
                    "adapters": mod._suite_record(gate_level="hard", selected=False, executed=False, status="skipped", rc=None),
                    "security": mod._suite_record(gate_level="hard", selected=False, executed=False, status="skipped", rc=None),
                    "integration": mod._suite_record(gate_level="soft", selected=False, executed=False, status="skipped", rc=None),
                    "ui": mod._suite_record(gate_level="soft", selected=False, executed=False, status="skipped", rc=None),
                }
                ci_payload = mod._write_quality_summary(
                    date=date,
                    security_profile="host-safe",
                    suite_runs=suite_runs,
                    ci_rc=0,
                    smoke_rc=None,
                    smoke_enabled=False,
                    invalid_suites=[],
                    junit_artifact={"status": "skipped"},
                    coverage_gate=resolved,
                )
                ci_summary_path = tmp_root / "logs" / "ci" / date / "quality-gates" / "summary.json"
                ci_summary = json.loads(ci_summary_path.read_text(encoding="utf-8"))
                print(json.dumps({
                    "unit_summary_exists": summary_path.exists(),
                    "ci_summary_exists": ci_summary_path.exists(),
                    "unit_has_measured_line_coverage": "measured_line_coverage" in resolved,
                    "unit_has_measured_branch_coverage": "measured_branch_coverage" in resolved,
                    "unit_has_effective_thresholds": isinstance(resolved.get("effective_thresholds"), dict),
                    "ci_has_gate_mode": bool(ci_summary.get("gate_mode")),
                    "ci_has_pass": "pass" in ci_summary,
                    "ci_line": ci_summary.get("measured_line_coverage"),
                    "ci_branch": ci_summary.get("measured_branch_coverage"),
                    "ci_threshold_lines": ci_summary.get("effective_thresholds", {}).get("lines_min"),
                    "ci_threshold_branches": ci_summary.get("effective_thresholds", {}).get("branches_min"),
                    "ci_payload_gate_mode": ci_payload.get("gate_mode")
                }))
            """);

        payload.GetProperty("unit_summary_exists").GetBoolean().Should().BeTrue();
        payload.GetProperty("ci_summary_exists").GetBoolean().Should().BeTrue();
        payload.GetProperty("unit_has_measured_line_coverage").GetBoolean().Should().BeTrue();
        payload.GetProperty("unit_has_measured_branch_coverage").GetBoolean().Should().BeTrue();
        payload.GetProperty("unit_has_effective_thresholds").GetBoolean().Should().BeTrue();
        payload.GetProperty("ci_has_gate_mode").GetBoolean().Should().BeTrue();
        payload.GetProperty("ci_has_pass").GetBoolean().Should().BeTrue();
        payload.GetProperty("ci_line").GetDouble().Should().Be(91.2);
        payload.GetProperty("ci_branch").GetDouble().Should().Be(88.4);
        payload.GetProperty("ci_threshold_lines").GetDouble().Should().Be(90.0);
        payload.GetProperty("ci_threshold_branches").GetDouble().Should().Be(85.0);
        payload.GetProperty("ci_payload_gate_mode").GetString().Should().Be("hard");
    }

    // ACC:T55.5
    [Fact]
    public void ShouldResolveEquivalentEffectiveThresholdsAcrossScripts_WhenSameEnvironmentOverridesAreProvided()
    {
        var payload = RunPythonJson(
            """
            import importlib.util, json, pathlib, tempfile
            root = pathlib.Path.cwd()
            rd_spec = importlib.util.spec_from_file_location("run_dotnet", root / "scripts/python/run_dotnet.py")
            run_dotnet = importlib.util.module_from_spec(rd_spec)
            rd_spec.loader.exec_module(run_dotnet)
            qg_spec = importlib.util.spec_from_file_location("quality_gates", root / "scripts/python/quality_gates.py")
            quality_gates = importlib.util.module_from_spec(qg_spec)
            qg_spec.loader.exec_module(quality_gates)
            with tempfile.TemporaryDirectory() as tmp:
                tmp_root = pathlib.Path(tmp)
                quality_gates._repo_root = lambda: tmp_root
                lines, _ = run_dotnet._resolve_threshold_value(preferred_key="COVERAGE_LINES_THRESHOLD", legacy_key="COVERAGE_LINES_MIN", default_value=run_dotnet.DEFAULT_LINES_THRESHOLD)
                branches, _ = run_dotnet._resolve_threshold_value(preferred_key="COVERAGE_BRANCHES_THRESHOLD", legacy_key="COVERAGE_BRANCHES_MIN", default_value=run_dotnet.DEFAULT_BRANCHES_THRESHOLD)
                coverage = quality_gates._resolve_coverage_gate_summary("2026-04-04")
                eff = coverage.get("effective_thresholds", {})
                print(json.dumps({
                    "run_dotnet_lines": lines,
                    "run_dotnet_branches": branches,
                    "quality_gates_lines": eff.get("lines_min"),
                    "quality_gates_branches": eff.get("branches_min")
                }))
            """,
            new Dictionary<string, string?>
            {
                ["COVERAGE_LINES_THRESHOLD"] = "94",
                ["COVERAGE_BRANCHES_THRESHOLD"] = "89",
            });

        payload.GetProperty("run_dotnet_lines").GetDouble().Should().Be(94.0);
        payload.GetProperty("run_dotnet_branches").GetDouble().Should().Be(89.0);
        payload.GetProperty("quality_gates_lines").GetDouble().Should().Be(94.0);
        payload.GetProperty("quality_gates_branches").GetDouble().Should().Be(89.0);
    }

    // ACC:T55.6
    [Fact]
    public void ShouldReturnSuccessInBothScriptsAcrossBothModes_WhenMeasuredCoverageMeetsThresholds()
    {
        var payload = RunPythonJson(
            """
            import datetime as dt
            import importlib.util, json, pathlib, tempfile, os
            root = pathlib.Path.cwd()
            rd_spec = importlib.util.spec_from_file_location("run_dotnet", root / "scripts/python/run_dotnet.py")
            run_dotnet = importlib.util.module_from_spec(rd_spec)
            rd_spec.loader.exec_module(run_dotnet)
            qg_spec = importlib.util.spec_from_file_location("quality_gates", root / "scripts/python/quality_gates.py")
            quality_gates = importlib.util.module_from_spec(qg_spec)
            qg_spec.loader.exec_module(quality_gates)
            with tempfile.TemporaryDirectory() as tmp:
                tmp_root = pathlib.Path(tmp)
                date = dt.date.today().strftime("%Y-%m-%d")
                cov_path = tmp_root / "coverage.cobertura.xml"
                cov_path.write_text('<coverage lines-covered="95" lines-valid="100" branches-covered="90" branches-valid="100"></coverage>', encoding="utf-8")
                trx_path = tmp_root / "tests.trx"
                trx_path.write_text("trx", encoding="utf-8")
                def fake_run_cmd(args, cwd=None, timeout=0):
                    return 0, "ok"
                run_dotnet.run_cmd = fake_run_cmd
                run_dotnet.parse_paths_from_test_output = lambda out: {"trx_paths": [str(trx_path)], "coverage_paths": [str(cov_path)]}
                run_dotnet.pick_latest_existing = lambda paths: paths[0] if paths else None
                original_cwd = os.getcwd()
                os.chdir(tmp_root)
                try:
                    os.environ["COVERAGE_LINES_THRESHOLD"] = "90"
                    os.environ["COVERAGE_BRANCHES_THRESHOLD"] = "85"
                    os.environ["COVERAGE_GATE_MODE"] = "soft"
                    rc_soft = run_dotnet.main(["--solution", "NewRouge.sln", "--out-dir", str(tmp_root / "pass_soft")])
                    soft_summary = json.loads((tmp_root / "pass_soft" / "summary.json").read_text(encoding="utf-8"))
                    os.environ["COVERAGE_GATE_MODE"] = "hard"
                    rc_hard = run_dotnet.main(["--solution", "NewRouge.sln", "--out-dir", str(tmp_root / "pass_hard")])
                    hard_summary = json.loads((tmp_root / "pass_hard" / "summary.json").read_text(encoding="utf-8"))
                finally:
                    os.chdir(original_cwd)
                quality_gates._repo_root = lambda: tmp_root
                unit_summary = tmp_root / "logs" / "unit" / date / "summary.json"
                unit_summary.parent.mkdir(parents=True, exist_ok=True)
                base_payload = {
                    "measured_line_coverage": 95.0,
                    "measured_branch_coverage": 90.0,
                    "effective_thresholds": {"lines_min": 90, "branches_min": 85},
                    "pass": True,
                }
                unit_summary.write_text(json.dumps({**base_payload, "gate_mode": "soft"}), encoding="utf-8")
                qg_soft = quality_gates._resolve_coverage_gate_summary(date)
                unit_summary.write_text(json.dumps({**base_payload, "gate_mode": "hard"}), encoding="utf-8")
                qg_hard = quality_gates._resolve_coverage_gate_summary(date)
                print(json.dumps({
                    "run_dotnet_soft_rc": rc_soft,
                    "run_dotnet_hard_rc": rc_hard,
                    "run_dotnet_soft_pass": bool(soft_summary.get("pass")),
                    "run_dotnet_hard_pass": bool(hard_summary.get("pass")),
                    "quality_gates_soft_pass": bool(qg_soft.get("pass")),
                    "quality_gates_hard_pass": bool(qg_hard.get("pass")),
                    "quality_gates_soft_suite_status": qg_soft.get("suite_status"),
                    "quality_gates_hard_suite_status": qg_hard.get("suite_status")
                }))
            """);

        payload.GetProperty("run_dotnet_soft_rc").GetInt32().Should().Be(0);
        payload.GetProperty("run_dotnet_hard_rc").GetInt32().Should().Be(0);
        payload.GetProperty("run_dotnet_soft_pass").GetBoolean().Should().BeTrue();
        payload.GetProperty("run_dotnet_hard_pass").GetBoolean().Should().BeTrue();
        payload.GetProperty("quality_gates_soft_pass").GetBoolean().Should().BeTrue();
        payload.GetProperty("quality_gates_hard_pass").GetBoolean().Should().BeTrue();
        payload.GetProperty("quality_gates_soft_suite_status").GetString().Should().Be("passed");
        payload.GetProperty("quality_gates_hard_suite_status").GetString().Should().Be("passed");
    }

    private static JsonElement RunPythonJson(string scriptBody, IReadOnlyDictionary<string, string?>? envOverrides = null)
    {
        var repoRoot = ResolveRepoRoot();
        var scriptPath = Path.Combine(Path.GetTempPath(), $"task55-binding-{Guid.NewGuid():N}.py");
        File.WriteAllText(scriptPath, scriptBody, new UTF8Encoding(false));

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "py",
                Arguments = $"-3 \"{scriptPath}\"",
                WorkingDirectory = repoRoot,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            psi.Environment["PYTHONUTF8"] = "1";
            var scriptsPython = Path.Combine(repoRoot, "scripts", "python");
            var currentPythonPath = psi.Environment.TryGetValue("PYTHONPATH", out var existingPythonPath)
                ? existingPythonPath
                : null;
            psi.Environment["PYTHONPATH"] = string.IsNullOrWhiteSpace(currentPythonPath)
                ? scriptsPython
                : $"{scriptsPython};{currentPythonPath}";
            if (envOverrides is not null)
            {
                foreach (var pair in envOverrides)
                {
                    if (pair.Value is null)
                    {
                        psi.Environment.Remove(pair.Key);
                    }
                    else
                    {
                        psi.Environment[pair.Key] = pair.Value;
                    }
                }
            }

            using var process = Process.Start(psi);
            process.Should().NotBeNull();
            var stdout = process!.StandardOutput.ReadToEnd();
            var stderr = process.StandardError.ReadToEnd();
            process.WaitForExit();

            process.ExitCode.Should().Be(0, $"python script failed: {stderr}");

            var jsonText = stdout;
            if (!string.IsNullOrWhiteSpace(stdout))
            {
                var lines = stdout.Split(new[] { "\r\n", "\n" }, StringSplitOptions.RemoveEmptyEntries);
                for (var i = lines.Length - 1; i >= 0; i--)
                {
                    var candidate = lines[i].Trim();
                    if (candidate.StartsWith("{", StringComparison.Ordinal) || candidate.StartsWith("[", StringComparison.Ordinal))
                    {
                        jsonText = candidate;
                        break;
                    }
                }
            }

            using var document = JsonDocument.Parse(jsonText);
            return document.RootElement.Clone();
        }
        finally
        {
            try
            {
                if (File.Exists(scriptPath))
                {
                    File.Delete(scriptPath);
                }
            }
            catch
            {
                // Best effort cleanup only.
            }
        }
    }

    private static string ResolveRepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var marker = Path.Combine(dir.FullName, "scripts", "python", "run_dotnet.py");
            if (File.Exists(marker))
            {
                return dir.FullName;
            }

            dir = dir.Parent;
        }

        throw new InvalidOperationException("Failed to resolve repository root from test base directory.");
    }
}
