using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using System.Xml.Linq;
using FluentAssertions;
using Xunit;

namespace NewRouge.Core.Tests.Tasks;

public sealed class Task2RootBuildGateTests
{
    // ACC:T2.1
    [Fact]
    public void ShouldFindRequiredRootDirectories_WhenRepositoryRootIsResolved()
    {
        var root = FindRepoRoot();

        Directory.Exists(Path.Combine(root, "Game.Core")).Should().BeTrue();
        Directory.Exists(Path.Combine(root, "Game.Godot")).Should().BeTrue();
        Directory.Exists(Path.Combine(root, "Game.Core.Tests")).Should().BeTrue();
        Directory.Exists(Path.Combine(root, "Tests.Godot")).Should().BeTrue();
    }

    // ACC:T2.3
    [Fact]
    public void ShouldKeepGameCoreProjectIsolatedAndTaskOwnedNamespacesUnderNewRouge_WhenScanningRepositoryFiles()
    {
        var root = FindRepoRoot();
        var csprojPath = Path.Combine(root, "Game.Core", "Game.Core.csproj");

        File.Exists(csprojPath).Should().BeTrue();
        var csproj = File.ReadAllText(csprojPath);
        csproj.Contains("Godot", StringComparison.OrdinalIgnoreCase).Should().BeFalse();

        var taskOwnedFiles = EnumerateTaskOwnedSourceFiles(root).ToArray();
        taskOwnedFiles.Should().NotBeEmpty("Task 2 namespace policy must be bound to real repository files.");
        taskOwnedFiles.Should().Contain(
            static path => path.Replace('\\', '/').Contains("/Game.Core/Conventions/", StringComparison.Ordinal),
            "Task 2 owned file set must include Game.Core conventions code.");

        foreach (var taskOwnedFile in taskOwnedFiles)
        {
            var fileNamespaces = ReadNamespaceDeclarationsFromSourceFile(taskOwnedFile).ToArray();
            fileNamespaces.Should().NotBeEmpty($"{taskOwnedFile} must declare at least one namespace.");
            fileNamespaces.Should().OnlyContain(
                static ns => ns.StartsWith("NewRouge.", StringComparison.Ordinal),
                $"{taskOwnedFile} must use NewRouge.* namespaces.");
        }
    }

    // ACC:T2.3
    [Fact]
    public void ShouldRequireTask2ChangeSetManifestToCoverTaskScopedCSharpFiles_WhenEvaluatingAuthoritativeScope()
    {
        var root = FindRepoRoot();
        var manifestPaths = ReadTaskOwnedRelativePathsFromManifest(root)
            .ToHashSet(StringComparer.Ordinal);

        manifestPaths.Should().Contain("Game.Core/Conventions/NamespaceConventions.cs");
        manifestPaths.Should().Contain("Game.Core.Tests/Tasks/Task2NamespaceCoexistenceTests.cs");
        manifestPaths.Should().Contain("Game.Core.Tests/Tasks/Task2RootBuildGateTests.cs");

        var expectedPaths = EnumerateExpectedTask2ScopeRelativePaths(root);
        foreach (var expectedPath in expectedPaths)
        {
            manifestPaths.Should().Contain(expectedPath, $"manifest must include task-scoped file '{expectedPath}'.");
        }
    }

    // ACC:T2.2
    [Fact]
    public void ShouldValidateProjectFilesTargetNet8AndNullableEnable_WhenReadingProjectConfigurations()
    {
        var root = FindRepoRoot();

        AssertProjectTargetsNet8WithNullableEnable(Path.Combine(root, "Game.Core", "Game.Core.csproj"));
        AssertProjectTargetsNet8WithNullableEnable(Path.Combine(root, "Game.Core.Tests", "Game.Core.Tests.csproj"));
        AssertProjectTargetsNet8WithNullableEnable(Path.Combine(root, "Tests.Godot", "Tests.Godot.csproj"));

        var godotCsprojs = Directory.EnumerateFiles(
            Path.Combine(root, "Game.Godot"),
            "*.csproj",
            SearchOption.AllDirectories);
        godotCsprojs.Should().BeEmpty("Game.Godot is a script/resource directory and does not require standalone csproj.");
    }

    // ACC:T2.2
    [Fact]
    public void ShouldRejectProjectSettings_WhenTargetFrameworkOrNullableIsInvalid()
    {
        HasExpectedProjectSettings("<Project><PropertyGroup><TargetFramework>net7.0</TargetFramework><Nullable>enable</Nullable></PropertyGroup></Project>")
            .Should()
            .BeFalse();
        HasExpectedProjectSettings("<Project><PropertyGroup><TargetFramework>net8.0</TargetFramework><Nullable>disable</Nullable></PropertyGroup></Project>")
            .Should()
            .BeFalse();
    }

    // ACC:T2.2
    [Fact]
    public void ShouldDetectStandaloneCsproj_WhenGameGodotDirectoryContainsProjectFile()
    {
        var tempRoot = Path.Combine(Path.GetTempPath(), $"task2-godot-{Guid.NewGuid():N}");
        var gameGodotDir = Path.Combine(tempRoot, "Game.Godot");
        Directory.CreateDirectory(gameGodotDir);

        try
        {
            File.WriteAllText(Path.Combine(gameGodotDir, "Game.Godot.csproj"), "<Project Sdk=\"Microsoft.NET.Sdk\" />");
            HasStandaloneCsproj(gameGodotDir).Should().BeTrue();
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    // ACC:T2.4
    [Fact]
    public void ShouldAllowGameAndNewRougeNamespacesToCoexist_WhenRepositoryNamespacesAreScanned()
    {
        var root = FindRepoRoot();
        var namespaceDeclarations = ReadNamespaceDeclarationsFromDirectory(root).ToArray();

        namespaceDeclarations.Should().Contain(static ns => ns.StartsWith("Game.", StringComparison.Ordinal));
        namespaceDeclarations.Should().Contain(static ns => ns.StartsWith("NewRouge.", StringComparison.Ordinal));
        var policy = EvaluateNamespaceCoexistencePolicy(namespaceDeclarations);
        policy.IsAccepted.Should().BeTrue();
        policy.RequiresFullRename.Should().BeFalse();
    }

    // evidence: build-output-classification
    [Fact]
    public void ShouldClassifyBuildFailures_WhenExitCodeOrCompilerErrorsExist()
    {
        var root = FindRepoRoot();
        File.Exists(Path.Combine(root, "NewRouge.sln")).Should().BeTrue();

        var failedByExitCode = ClassifyBuildOutput(1, "Build FAILED.", string.Empty);
        failedByExitCode.IsSuccess.Should().BeFalse();
        failedByExitCode.Reason.Should().Contain("exit-code");

        var failedByCompilerError = ClassifyBuildOutput(0, "Build started.", "error CS1002: ; expected");
        failedByCompilerError.IsSuccess.Should().BeFalse();
        failedByCompilerError.Reason.Should().Contain("compiler-error-marker");

        var failedByBuildMarker = ClassifyBuildOutput(0, "Build FAILED.", string.Empty);
        failedByBuildMarker.IsSuccess.Should().BeFalse();
        failedByBuildMarker.Reason.Should().Contain("build-failed-marker");
    }

    // evidence: build-output-classification
    [Fact]
    public void ShouldClassifyBuildSuccess_WhenExitCodeIsZeroAndFailureMarkersAreMissing()
    {
        var root = FindRepoRoot();
        File.Exists(Path.Combine(root, "NewRouge.sln")).Should().BeTrue();

        var success = ClassifyBuildOutput(0, "Build succeeded.", string.Empty);
        success.IsSuccess.Should().BeTrue();
        success.Reason.Should().Be("success");
    }

    // evidence: root-build-proof
    [Fact]
    public void ShouldPassRootDotnetBuild_WhenExecutingRepositoryBuild()
    {
        var root = FindRepoRoot();
        File.Exists(Path.Combine(root, "NewRouge.sln")).Should().BeTrue();

        var result = RunDotnetBuild(root);
        result.TimedOut.Should().BeFalse("dotnet build should complete within timeout.");
        result.ExitCode.Should().Be(0);

        var classification = ClassifyBuildOutput(result.ExitCode, result.Stdout, result.Stderr);
        classification.IsSuccess.Should().BeTrue();
        classification.Reason.Should().Be("success");
    }

    private static void AssertProjectTargetsNet8WithNullableEnable(string csprojPath)
    {
        File.Exists(csprojPath).Should().BeTrue();
        HasExpectedProjectSettings(File.ReadAllText(csprojPath)).Should().BeTrue();
    }

    private static IEnumerable<string> EnumerateTaskOwnedSourceFiles(string root)
    {
        var relativePaths = ReadTaskOwnedRelativePathsFromManifest(root);
        var resolved = new List<string>();

        foreach (var relativePath in relativePaths)
        {
            var absolutePath = Path.Combine(root, relativePath.Replace('/', Path.DirectorySeparatorChar));
            if (File.Exists(absolutePath) && !IsBuildArtifactPath(absolutePath))
            {
                resolved.Add(absolutePath);
            }
        }

        if (resolved.Count == 0)
        {
            throw new InvalidOperationException("Task 2 change-set manifest contains no existing C# files.");
        }

        return resolved.Distinct(StringComparer.Ordinal);
    }

    private static IReadOnlyCollection<string> ReadTaskOwnedRelativePathsFromManifest(string root)
    {
        var manifestPath = Path.Combine(root, "taskdoc", "task-0002-change-set.json");
        if (!File.Exists(manifestPath))
        {
            throw new InvalidOperationException($"Missing Task 2 change-set manifest: {manifestPath}");
        }

        using var document = JsonDocument.Parse(File.ReadAllText(manifestPath));
        if (!document.RootElement.TryGetProperty("csharp_files", out var csharpFiles) || csharpFiles.ValueKind != JsonValueKind.Array)
        {
            throw new InvalidOperationException("Task 2 change-set manifest must contain csharp_files array.");
        }

        var relativePaths = new List<string>();
        foreach (var element in csharpFiles.EnumerateArray())
        {
            if (element.ValueKind != JsonValueKind.String)
            {
                continue;
            }

            var relativePath = element.GetString();
            if (string.IsNullOrWhiteSpace(relativePath))
            {
                continue;
            }

            var normalized = relativePath.Replace('\\', '/').Trim();
            if (normalized.EndsWith(".cs", StringComparison.OrdinalIgnoreCase))
            {
                relativePaths.Add(normalized);
            }
        }

        if (relativePaths.Count == 0)
        {
            throw new InvalidOperationException("Task 2 change-set manifest contains no C# relative paths.");
        }

        return relativePaths.Distinct(StringComparer.Ordinal).ToArray();
    }

    private static IReadOnlyCollection<string> EnumerateExpectedTask2ScopeRelativePaths(string root)
    {
        static IEnumerable<string> RelativePaths(string rootPath, string directoryPath, string pattern, SearchOption searchOption)
        {
            if (!Directory.Exists(directoryPath))
            {
                return Array.Empty<string>();
            }

            return Directory.EnumerateFiles(directoryPath, pattern, searchOption)
                .Where(static path => !IsBuildArtifactPath(path))
                .Select(path => Path.GetRelativePath(rootPath, path).Replace('\\', '/'));
        }

        var expected = new List<string>();
        expected.AddRange(RelativePaths(root, Path.Combine(root, "Game.Core", "Conventions"), "*.cs", SearchOption.AllDirectories));
        expected.AddRange(RelativePaths(root, Path.Combine(root, "Game.Core.Tests", "Tasks"), "Task2*.cs", SearchOption.TopDirectoryOnly));
        expected.AddRange(RelativePaths(root, Path.Combine(root, "Tests.Godot", "tests", "Tasks"), "task0002*.cs", SearchOption.AllDirectories));
        return expected.Distinct(StringComparer.Ordinal).ToArray();
    }

    private static IEnumerable<string> ReadNamespaceDeclarationsFromSourceFile(string sourceFile)
    {
        foreach (var rawLine in File.ReadAllLines(sourceFile))
        {
            var line = rawLine.Trim();
            if (!line.StartsWith("namespace ", StringComparison.Ordinal))
            {
                continue;
            }

            var namespaceValue = line["namespace ".Length..].Trim().TrimEnd('{').Trim().TrimEnd(';').Trim();
            if (!string.IsNullOrWhiteSpace(namespaceValue))
            {
                yield return namespaceValue;
            }
        }
    }

    private static IEnumerable<string> ReadNamespaceDeclarationsFromDirectory(string root)
    {
        foreach (var sourceFile in Directory.EnumerateFiles(root, "*.cs", SearchOption.AllDirectories))
        {
            if (IsBuildArtifactPath(sourceFile))
            {
                continue;
            }

            foreach (var namespaceValue in ReadNamespaceDeclarationsFromSourceFile(sourceFile))
            {
                yield return namespaceValue;
            }
        }
    }

    private static bool HasExpectedProjectSettings(string csprojContent)
    {
        var document = XDocument.Parse(csprojContent);
        var targetFramework = document.Descendants().FirstOrDefault(static node => node.Name.LocalName == "TargetFramework")?.Value?.Trim();
        var nullable = document.Descendants().FirstOrDefault(static node => node.Name.LocalName == "Nullable")?.Value?.Trim();
        return string.Equals(targetFramework, "net8.0", StringComparison.Ordinal)
            && string.Equals(nullable, "enable", StringComparison.OrdinalIgnoreCase);
    }

    private static (int ExitCode, string Stdout, string Stderr, bool TimedOut) RunDotnetBuild(string root)
    {
        using var process = new Process();
        process.StartInfo = new ProcessStartInfo
        {
            FileName = "dotnet",
            Arguments = "build NewRouge.sln -nologo -v minimal",
            WorkingDirectory = root,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };

        process.Start();
        Task<string> stdoutTask = process.StandardOutput.ReadToEndAsync();
        Task<string> stderrTask = process.StandardError.ReadToEndAsync();

        var completed = process.WaitForExit(300_000);
        if (!completed)
        {
            try
            {
                process.Kill(true);
            }
            catch
            {
                // Ignore cleanup failures on timeout; caller asserts timeout semantics.
            }

            return (ExitCode: -1, Stdout: string.Empty, Stderr: "dotnet build timeout", TimedOut: true);
        }

        Task.WaitAll(stdoutTask, stderrTask);
        return (ExitCode: process.ExitCode, Stdout: stdoutTask.Result, Stderr: stderrTask.Result, TimedOut: false);
    }

    private static NamespacePolicyResult EvaluateNamespaceCoexistencePolicy(IEnumerable<string> namespaceDeclarations)
    {
        var hasLegacyPrefix = namespaceDeclarations.Any(static ns => ns.StartsWith("Game.", StringComparison.Ordinal));
        var hasNewPrefix = namespaceDeclarations.Any(static ns => ns.StartsWith("NewRouge.", StringComparison.Ordinal));
        if (!hasNewPrefix)
        {
            return new NamespacePolicyResult(
                IsAccepted: false,
                RequiresFullRename: false,
                Reason: "Missing NewRouge.* namespace declarations.");
        }

        if (hasLegacyPrefix)
        {
            return new NamespacePolicyResult(
                IsAccepted: true,
                RequiresFullRename: false,
                Reason: "Legacy Game.* and NewRouge.* coexistence is allowed.");
        }

        return new NamespacePolicyResult(
            IsAccepted: true,
            RequiresFullRename: false,
            Reason: "Legacy Game.* namespaces are not required.");
    }

    private static BuildClassification ClassifyBuildOutput(int exitCode, string stdout, string stderr)
    {
        if (exitCode != 0)
        {
            return new BuildClassification(false, $"exit-code:{exitCode}");
        }

        var combined = stdout + Environment.NewLine + stderr;
        if (combined.Contains("error CS", StringComparison.OrdinalIgnoreCase))
        {
            return new BuildClassification(false, "compiler-error-marker");
        }

        if (combined.Contains("Build FAILED", StringComparison.OrdinalIgnoreCase))
        {
            return new BuildClassification(false, "build-failed-marker");
        }

        return new BuildClassification(true, "success");
    }

    private static string FindRepoRoot()
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

        throw new InvalidOperationException("Unable to locate repository root containing NewRouge.sln.");
    }

    private static bool IsBuildArtifactPath(string path)
    {
        var normalized = path.Replace('\\', '/');
        return normalized.Contains("/bin/", StringComparison.OrdinalIgnoreCase)
            || normalized.Contains("/obj/", StringComparison.OrdinalIgnoreCase)
            || normalized.Contains("/.godot/", StringComparison.OrdinalIgnoreCase)
            || normalized.Contains("/TestResults/", StringComparison.OrdinalIgnoreCase);
    }

    private static bool HasStandaloneCsproj(string gameGodotDirectory)
    {
        return Directory.Exists(gameGodotDirectory)
            && Directory.EnumerateFiles(gameGodotDirectory, "*.csproj", SearchOption.AllDirectories).Any();
    }

    private sealed record NamespacePolicyResult(bool IsAccepted, bool RequiresFullRename, string Reason);
    private sealed record BuildClassification(bool IsSuccess, string Reason);
}
