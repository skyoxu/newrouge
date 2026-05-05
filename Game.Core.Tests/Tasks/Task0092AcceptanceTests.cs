using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0092AcceptanceTests
{
    private const string CheckArchitectureBoundaryScript = "scripts/python/check_architecture_boundary.py";
    private const string CheckArchitectureBoundaryCommand = "py -3 scripts/python/check_architecture_boundary.py --out <json>";
    private const string Task0092AcceptanceRef = "Game.Core.Tests/Tasks/Task0092AcceptanceTests.cs";
    private const string Task0067AcceptanceRef = "Game.Core.Tests/Tasks/Task0067AcceptanceTests.cs";

    // ACC:T92.1
    [Fact]
    public void ShouldExposeRunnableGuardrail_WhenTaskIsPromotedToMainTaskLine()
    {
        var repoRoot = FindRepositoryRoot();
        var scriptPath = Path.Combine(repoRoot, CheckArchitectureBoundaryScript.Replace('/', Path.DirectorySeparatorChar));

        File.Exists(scriptPath).Should().BeTrue("the architecture boundary guardrail script must exist in the executable workflow path");

        var reportPath = RunArchitectureBoundaryCheck(repoRoot);
        using var report = JsonDocument.Parse(File.ReadAllText(reportPath));

        report.RootElement.TryGetProperty("ok", out var okNode).Should().BeTrue();
        okNode.ValueKind.Should().Be(JsonValueKind.True);
    }

    // ACC:T92.2
    [Fact]
    public void ShouldDetectViolation_WhenGameCoreDependsOnGodotAssembly()
    {
        var repoRoot = FindRepositoryRoot();
        var reportPath = RunArchitectureBoundaryCheck(repoRoot);
        using var report = JsonDocument.Parse(File.ReadAllText(reportPath));

        var csproj = report.RootElement.GetProperty("csproj");
        var forbiddenPackages = csproj.GetProperty("forbidden_package_refs").EnumerateArray().Select(item => item.GetString() ?? string.Empty).ToArray();
        var forbiddenProjects = csproj.GetProperty("forbidden_project_refs").EnumerateArray().Select(item => item.GetString() ?? string.Empty).ToArray();
        var sourceViolations = report.RootElement.GetProperty("source_violations").EnumerateArray().Select(item => item.GetString() ?? string.Empty).ToArray();

        var hasForbiddenCoreGodotDependency = forbiddenPackages.Any(ContainsGodotToken)
                                              || forbiddenProjects.Any(ContainsGodotToken)
                                              || sourceViolations.Any(ContainsGodotToken);

        hasForbiddenCoreGodotDependency.Should().BeFalse("real guardrail output must detect and reject any Game.Core -> Godot dependency");
    }

    // ACC:T92.3
    [Fact]
    public void ShouldAllowAdapterBoundaryOnly_WhenGodotReferenceStaysOutsideGameCore()
    {
        var repoRoot = FindRepositoryRoot();
        var reportPath = RunArchitectureBoundaryCheck(repoRoot);
        using var report = JsonDocument.Parse(File.ReadAllText(reportPath));

        report.RootElement.GetProperty("ok").GetBoolean().Should().BeTrue("adapter-side Godot usage should not violate the Core boundary guardrail");

        var gameGodotReferences = EnumerateRepoFiles(repoRoot, "Game.Godot", "*.cs")
            .Where(path => File.ReadAllText(path).Contains("Godot.", StringComparison.Ordinal))
            .ToArray();

        gameGodotReferences.Should().NotBeEmpty("adapter-side code should be the allowed place where Godot interaction exists");
    }

    // ACC:T92.4
    [Fact]
    public void ShouldRecordPassingEvidence_WhenBoundaryCheckAndCoverageRunInOnePass()
    {
        var repoRoot = FindRepositoryRoot();
        var latestSummaryPath = ResolveLatestTask92PipelineSummaryPath(repoRoot);
        using var pipelineSummary = JsonDocument.Parse(File.ReadAllText(latestSummaryPath));

        var steps = pipelineSummary.RootElement.GetProperty("steps").EnumerateArray().ToArray();
        var testStep = steps.First(step => step.GetProperty("name").GetString() == "sc-test");
        var acceptanceStep = steps.First(step => step.GetProperty("name").GetString() == "sc-acceptance-check");

        testStep.GetProperty("status").GetString().Should().Be("ok", "one-pass evidence requires deterministic test closure in the same run");
        acceptanceStep.GetProperty("status").GetString().Should().Be("ok", "one-pass evidence requires acceptance closure in the same run");
        pipelineSummary.RootElement.GetProperty("task_id").GetString().Should().Be("92");
    }

    // ACC:T92.5
    [Fact]
    public void ShouldFailDeterministically_WhenIntentionalGameCoreGodotDependencyIsInjected()
    {
        var repoRoot = FindRepositoryRoot();
        var csprojPath = Path.Combine(repoRoot, "Game.Core", "Game.Core.csproj");
        var originalContent = File.ReadAllText(csprojPath);
        var tempContent = originalContent.Replace(
            "</Project>",
            "  <ItemGroup>\n    <PackageReference Include=\"GodotSharp\" Version=\"4.5.1\" />\n  </ItemGroup>\n</Project>",
            StringComparison.Ordinal);

        try
        {
            File.WriteAllText(csprojPath, tempContent);
            var reportPath = RunArchitectureBoundaryCheck(repoRoot, expectSuccess: false);
            using var report = JsonDocument.Parse(File.ReadAllText(reportPath));

            report.RootElement.GetProperty("ok").GetBoolean().Should().BeFalse();
            report.RootElement.GetProperty("errors").EnumerateArray().Select(item => item.GetString() ?? string.Empty)
                .Should().Contain(error => error.Contains("forbidden PackageReference", StringComparison.OrdinalIgnoreCase));
            report.RootElement.GetProperty("csproj")
                .GetProperty("forbidden_package_refs")
                .EnumerateArray()
                .Select(item => item.GetString() ?? string.Empty)
                .Should().Contain("GodotSharp");
        }
        finally
        {
            File.WriteAllText(csprojPath, originalContent);
        }
    }

    private static string[] ReadTaskAcceptanceRef(string repoRoot, int taskmasterId, string field)
    {
        var path = Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_back.json");
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        var task = document.RootElement
            .EnumerateArray()
            .First(item => item.TryGetProperty("taskmaster_id", out var id) && id.ValueKind == JsonValueKind.Number && id.GetInt32() == taskmasterId);

        return task.GetProperty(field)
            .EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString() ?? string.Empty)
            .Where(text => !string.IsNullOrWhiteSpace(text))
            .ToArray();
    }

    private static string ResolveLatestTask92PipelineSummaryPath(string repoRoot)
    {
        var latestPath = Path.Combine(repoRoot, "logs", "ci", DateTime.UtcNow.ToString("yyyy-MM-dd"), "sc-review-pipeline-task-92", "latest.json");
        File.Exists(latestPath).Should().BeTrue("Task 92 one-pass verification requires latest pipeline index");

        using var latest = JsonDocument.Parse(File.ReadAllText(latestPath));
        var summaryPath = latest.RootElement.GetProperty("summary_path").GetString();
        summaryPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(summaryPath!).Should().BeTrue("latest pipeline index must point to a valid summary artifact");
        return summaryPath!;
    }

    private static string RunArchitectureBoundaryCheck(string repoRoot, bool expectSuccess = true)
    {
        var outDir = Path.Combine(repoRoot, "logs", "ci", DateTime.UtcNow.ToString("yyyy-MM-dd"), "task0092-architecture-boundary-test");
        Directory.CreateDirectory(outDir);
        var outputPath = Path.Combine(outDir, $"architecture-boundary-{Guid.NewGuid():N}.json");

        var processStartInfo = new ProcessStartInfo
        {
            FileName = "py",
            Arguments = $"-3 scripts/python/check_architecture_boundary.py --out \"{outputPath}\"",
            WorkingDirectory = repoRoot,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = System.Text.Encoding.UTF8,
            StandardErrorEncoding = System.Text.Encoding.UTF8,
        };

        using var process = Process.Start(processStartInfo);
        process.Should().NotBeNull($"must be able to launch: {CheckArchitectureBoundaryCommand}");
        var stdout = process!.StandardOutput.ReadToEnd();
        var stderr = process.StandardError.ReadToEnd();
        process.WaitForExit();

        if (expectSuccess)
        {
            process.ExitCode.Should().Be(0, $"architecture boundary command should pass on the current repository state.\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}");
        }
        else
        {
            process.ExitCode.Should().NotBe(0, $"architecture boundary command should fail for an intentional Core->Godot violation.\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}");
        }
        File.Exists(outputPath).Should().BeTrue("architecture boundary command must emit a JSON evidence report");
        return outputPath;
    }

    private static string[] EnumerateRepoFiles(string repoRoot, string relativeDir, string pattern)
    {
        var directory = Path.Combine(repoRoot, relativeDir.Replace('/', Path.DirectorySeparatorChar));
        if (!Directory.Exists(directory))
        {
            return Array.Empty<string>();
        }

        return Directory.EnumerateFiles(directory, pattern, SearchOption.AllDirectories).ToArray();
    }

    private static bool ContainsGodotToken(string input)
    {
        return input.Contains("godot", StringComparison.OrdinalIgnoreCase);
    }

    private static string FindRepositoryRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (File.Exists(Path.Combine(current.FullName, "NewRouge.sln")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Unable to locate repository root containing NewRouge.sln.");
    }
}
