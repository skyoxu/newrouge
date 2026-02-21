using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Text.Json;
using System.Xml.Linq;
using FluentAssertions;
using Xunit;

namespace NewRouge.Core.Tests.Tasks;

public sealed class Task2NamespaceCoexistenceTests
{
    // ACC:T2.1
    [Fact]
    public void ShouldVerifyRequiredRootDirectories_WhenInspectingRepositoryRoot()
    {
        var repoRoot = FindRepoRoot();

        Directory.Exists(Path.Combine(repoRoot, "Game.Core")).Should().BeTrue();
        Directory.Exists(Path.Combine(repoRoot, "Game.Godot")).Should().BeTrue();
        Directory.Exists(Path.Combine(repoRoot, "Game.Core.Tests")).Should().BeTrue();
        Directory.Exists(Path.Combine(repoRoot, "Tests.Godot")).Should().BeTrue();
    }

    // ACC:T2.3
    [Fact]
    public void ShouldEnforceGameCoreIsolationAndNewRougeNamespacePrefix_WhenValidatingTaskAdditions()
    {
        var repoRoot = FindRepoRoot();
        var gameCoreProjectPath = Path.Combine(repoRoot, "Game.Core", "Game.Core.csproj");
        File.Exists(gameCoreProjectPath).Should().BeTrue("Task 2 requires a dedicated Game.Core project.");

        var projectReferences = ReadProjectReferenceIncludes(gameCoreProjectPath);
        projectReferences.Should().NotContain(
            static reference => reference.Contains("Godot", StringComparison.OrdinalIgnoreCase),
            "Game.Core must not declare Godot-related package/project references.");

        var gameCoreSourceFiles = Directory
            .EnumerateFiles(Path.Combine(repoRoot, "Game.Core"), "*.cs", SearchOption.AllDirectories)
            .Where(path => !IsBuildArtifactPath(path))
            .ToArray();

        gameCoreSourceFiles.Should().NotBeEmpty();

        foreach (var sourceFile in gameCoreSourceFiles)
        {
            var source = File.ReadAllText(sourceFile);
            var usingDirectives = ExtractUsingDirectives(source);
            usingDirectives.Should().NotContain(
                static directive => directive.Equals("Godot", StringComparison.Ordinal) || directive.StartsWith("Godot.", StringComparison.Ordinal),
                $"{sourceFile} must not import Godot APIs in Game.Core.");
            ContainsGodotAliasUsing(source).Should().BeFalse(
                $"{sourceFile} must not alias-import Godot APIs in Game.Core.");

            ContainsGodotQualifiedIdentifier(source).Should().BeFalse(
                $"{sourceFile} must not reference Godot API qualified identifiers in Game.Core.");
        }

        var namespacesByFile = ReadTaskScopedNamespaceDeclarationsByFile(repoRoot);
        namespacesByFile.Should().NotBeEmpty("Task 2 scoped files must provide namespace declarations.");
        var scopedRelativePaths = namespacesByFile.Keys
            .Select(path => Path.GetRelativePath(repoRoot, path).Replace('\\', '/'))
            .ToArray();
        scopedRelativePaths.Should().Contain("Game.Core/Conventions/NamespaceConventions.cs");
        scopedRelativePaths.Should().Contain("Game.Core.Tests/Tasks/Task2NamespaceCoexistenceTests.cs");
        scopedRelativePaths.Should().Contain("Game.Core.Tests/Tasks/Task2RootBuildGateTests.cs");

        foreach (var pair in namespacesByFile)
        {
            pair.Value.Should().NotBeEmpty($"{pair.Key} must declare at least one namespace.");
            pair.Value.Should().OnlyContain(
                static name => name.StartsWith("NewRouge.", StringComparison.Ordinal),
                $"{pair.Key} must use NewRouge.* namespaces.");
        }
    }

    // ACC:T2.4
    [Fact]
    public void ShouldNotRequireFullRename_WhenGameAndNewRougeNamespacesCoexist()
    {
        var repoRoot = FindRepoRoot();
        var declarations = ReadNamespaceDeclarations(repoRoot);
        declarations.Should().Contain(static value => value.StartsWith("Game.", StringComparison.Ordinal));
        declarations.Should().Contain(static value => value.StartsWith("NewRouge.", StringComparison.Ordinal));

        var result = EvaluateNamespaceCoexistencePolicy(declarations);

        result.IsAccepted.Should().BeTrue();
        result.RequiresFullRename.Should().BeFalse();
        result.Reason.Should().BeEmpty();
    }

    [Fact]
    public void ShouldRejectCoexistencePolicy_WhenNewRougeNamespaceDeclarationsAreMissing()
    {
        var result = EvaluateNamespaceCoexistencePolicy(new[]
        {
            "Game.Core.Domain",
            "Game.Godot.Scripts.UI",
        });

        result.IsAccepted.Should().BeFalse();
        result.RequiresFullRename.Should().BeFalse();
        result.Reason.Should().Contain("NewRouge");
    }

    [Fact]
    public void ShouldAllowCoexistencePolicy_WhenLegacyGameNamespaceDeclarationsAreMissing()
    {
        var result = EvaluateNamespaceCoexistencePolicy(new[]
        {
            "NewRouge.Core.Domain",
            "NewRouge.Gameplay.Runtime",
        });

        result.IsAccepted.Should().BeTrue();
        result.RequiresFullRename.Should().BeFalse();
        result.Reason.Should().Contain("not required");
    }

    [Fact]
    public void ShouldDetectGodotApiUsage_WhenSourceContainsForbiddenReferences()
    {
        const string source = """
            using Godot;
            namespace NewRouge.Core.Sample;
            public sealed class Sample { public Godot.Node Node { get; } = null!; }
            """;
        const string aliasSource = """
            using G = Godot;
            namespace NewRouge.Core.Sample;
            public sealed class AliasSample { public G.Node Node { get; } = null!; }
            """;
        const string globalUsingSource = """
            global using Godot;
            namespace NewRouge.Core.Sample;
            public sealed class GlobalSample { }
            """;
        const string globalAliasSource = """
            global using G = Godot;
            namespace NewRouge.Core.Sample;
            public sealed class GlobalAliasSample { public G.Node Node { get; } = null!; }
            """;

        var directives = ExtractUsingDirectives(source);
        directives.Should().Contain("Godot");
        ContainsGodotQualifiedIdentifier(source).Should().BeTrue();
        ContainsGodotAliasUsing(aliasSource).Should().BeTrue();
        ExtractUsingDirectives(globalUsingSource).Should().Contain("Godot");
        ContainsGodotAliasUsing(globalAliasSource).Should().BeTrue();
    }

    [Fact]
    public void ShouldDetectGodotReferences_WhenProjectXmlContainsForbiddenPackages()
    {
        const string csproj = """
            <Project Sdk="Microsoft.NET.Sdk">
              <ItemGroup>
                <PackageReference Include="Godot.NET.Sdk" Version="4.5.1" />
                <ProjectReference Include="..\Game.Godot\Game.Godot.csproj" />
              </ItemGroup>
            </Project>
            """;

        var includes = ExtractProjectReferenceIncludesFromXml(csproj);
        includes.Should().Contain(static value => value.Contains("Godot", StringComparison.OrdinalIgnoreCase));
    }

    private static NamespacePolicyResult EvaluateNamespaceCoexistencePolicy(IEnumerable<string> namespaceDeclarations)
    {
        var declarations = namespaceDeclarations
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .Select(static value => value.Trim())
            .Distinct(StringComparer.Ordinal)
            .ToArray();

        var hasLegacyGamePrefix = declarations.Any(static value => value.StartsWith("Game.", StringComparison.Ordinal));
        var hasNewRougePrefix = declarations.Any(static value => value.StartsWith("NewRouge.", StringComparison.Ordinal));

        if (!hasNewRougePrefix)
        {
            return new NamespacePolicyResult(
                IsAccepted: false,
                RequiresFullRename: false,
                Reason: "Missing NewRouge.* namespace declarations.");
        }

        if (hasLegacyGamePrefix)
        {
            return new NamespacePolicyResult(
                IsAccepted: true,
                RequiresFullRename: false,
                Reason: string.Empty);
        }

        return new NamespacePolicyResult(
            IsAccepted: true,
            RequiresFullRename: false,
            Reason: "Legacy Game.* namespace declarations are not required.");
    }

    private static IReadOnlyCollection<string> ReadNamespaceDeclarations(string repoRoot)
    {
        var namespaces = new HashSet<string>(StringComparer.Ordinal);

        foreach (var sourceFile in Directory.EnumerateFiles(repoRoot, "*.cs", SearchOption.AllDirectories))
        {
            if (IsBuildArtifactPath(sourceFile))
            {
                continue;
            }

            foreach (var namespaceValue in ExtractNamespaceDeclarations(File.ReadAllText(sourceFile)))
            {
                namespaces.Add(namespaceValue);
            }
        }

        return namespaces.ToArray();
    }

    private static IReadOnlyDictionary<string, IReadOnlyCollection<string>> ReadTaskScopedNamespaceDeclarationsByFile(string repoRoot)
    {
        var namespacesByFile = new Dictionary<string, IReadOnlyCollection<string>>(StringComparer.Ordinal);
        var taskScopedFiles = EnumerateTaskScopedFiles(repoRoot);

        foreach (var sourceFile in taskScopedFiles)
        {
            var namespaces = ExtractNamespaceDeclarations(File.ReadAllText(sourceFile)).ToArray();
            namespacesByFile[sourceFile] = namespaces;
        }

        return namespacesByFile;
    }

    private static IReadOnlyCollection<string> EnumerateTaskScopedFiles(string repoRoot)
    {
        var manifestPath = Path.Combine(repoRoot, "taskdoc", "task-0002-change-set.json");
        if (!File.Exists(manifestPath))
        {
            throw new InvalidOperationException($"Missing Task 2 change-set manifest: {manifestPath}");
        }

        using var document = JsonDocument.Parse(File.ReadAllText(manifestPath));
        if (!document.RootElement.TryGetProperty("csharp_files", out var csharpFiles) || csharpFiles.ValueKind != JsonValueKind.Array)
        {
            throw new InvalidOperationException("Task 2 change-set manifest must contain csharp_files array.");
        }

        var files = new List<string>();
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

            var absolutePath = Path.Combine(repoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar));
            if (File.Exists(absolutePath) && !IsBuildArtifactPath(absolutePath))
            {
                files.Add(absolutePath);
            }
        }

        if (files.Count == 0)
        {
            throw new InvalidOperationException("Task 2 change-set manifest contains no existing C# files.");
        }

        return files.Distinct(StringComparer.Ordinal).ToArray();
    }

    private static IEnumerable<string> ExtractNamespaceDeclarations(string sourceText)
    {
        var lines = sourceText.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);

        foreach (var rawLine in lines)
        {
            var line = rawLine.Trim();
            if (!line.StartsWith("namespace ", StringComparison.Ordinal))
            {
                continue;
            }

            var namespaceName = line["namespace ".Length..].Trim();
            namespaceName = namespaceName.TrimEnd('{').Trim();
            namespaceName = namespaceName.TrimEnd(';').Trim();

            if (!string.IsNullOrWhiteSpace(namespaceName))
            {
                yield return namespaceName;
            }
        }
    }

    private static IReadOnlyCollection<string> ExtractUsingDirectives(string sourceText)
    {
        var usings = new List<string>();
        var lines = sourceText.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);

        foreach (var rawLine in lines)
        {
            var line = rawLine.Trim();
            if (!line.EndsWith(";", StringComparison.Ordinal))
            {
                continue;
            }

            var usingPrefix = line.StartsWith("global using ", StringComparison.Ordinal)
                ? "global using "
                : (line.StartsWith("using ", StringComparison.Ordinal) ? "using " : string.Empty);
            if (usingPrefix.Length == 0)
            {
                continue;
            }

            var namespaceValue = line[usingPrefix.Length..].TrimEnd(';').Trim();
            if (namespaceValue.Length > 0 && !namespaceValue.StartsWith("static ", StringComparison.Ordinal))
            {
                usings.Add(namespaceValue);
            }
        }

        return usings;
    }

    private static bool ContainsGodotQualifiedIdentifier(string sourceText)
    {
        return Regex.IsMatch(sourceText, @"\bGodot\.", RegexOptions.CultureInvariant);
    }

    private static bool ContainsGodotAliasUsing(string sourceText)
    {
        return Regex.IsMatch(
            sourceText,
            @"^\s*(?:global\s+)?using\s+[A-Za-z_][A-Za-z0-9_]*\s*=\s*Godot(?:\.[A-Za-z_][A-Za-z0-9_.]*)?\s*;",
            RegexOptions.Multiline | RegexOptions.CultureInvariant);
    }

    private static IReadOnlyCollection<string> ReadProjectReferenceIncludes(string csprojPath)
    {
        var xml = File.ReadAllText(csprojPath);
        return ExtractProjectReferenceIncludesFromXml(xml);
    }

    private static IReadOnlyCollection<string> ExtractProjectReferenceIncludesFromXml(string projectXml)
    {
        var document = XDocument.Parse(projectXml);
        var includes = new List<string>();

        var referenceNodes = document
            .Descendants()
            .Where(static node => node.Name.LocalName is "PackageReference" or "ProjectReference");

        foreach (var node in referenceNodes)
        {
            var include = node.Attribute("Include")?.Value?.Trim();
            if (!string.IsNullOrWhiteSpace(include))
            {
                includes.Add(include);
            }
        }

        return includes;
    }

    private static bool IsBuildArtifactPath(string path)
    {
        var normalized = path.Replace('\\', '/');

        return normalized.Contains("/bin/", StringComparison.OrdinalIgnoreCase)
            || normalized.Contains("/obj/", StringComparison.OrdinalIgnoreCase)
            || normalized.Contains("/.godot/", StringComparison.OrdinalIgnoreCase)
            || normalized.Contains("/TestResults/", StringComparison.OrdinalIgnoreCase);
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

    private sealed record NamespacePolicyResult(bool IsAccepted, bool RequiresFullRename, string Reason);
}
