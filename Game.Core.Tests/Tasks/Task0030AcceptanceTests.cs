using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.RegularExpressions;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

// ADR-REF: ADR-0020
public sealed class Task0030AcceptanceTests
{
    private static readonly string[] RequiredAdrRefs = { "ADR-0010", "ADR-0020", "ADR-0021" };
    private const string ThisTestPath = "Game.Core.Tests/Tasks/Task0030AcceptanceTests.cs";
    private const string Task30OverlayTestingPath = "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Testing-M1.md";

    // ACC:T30.1
    [Fact]
    public void ShouldExposeExpectedRelicContractShape_WhenTask0030AcceptanceRuns()
    {
        EnsureGameCoreAssemblyIsLoaded();

        var relicDefinition = FindTypeBySimpleName("RelicDefinition");
        var relicInstance = FindTypeBySimpleName("RelicInstance");

        relicDefinition.Should().NotBeNull("RelicDefinition contract type is required");
        relicInstance.Should().NotBeNull("RelicInstance contract type is required");

        var requiredDefinitionProps = new[] { "relic_id", "name_key", "description_key", "tags" };
        var requiredInstanceProps = new[] { "instance_id", "modifiers" };

        var definitionProps = GetPublicReadablePropertyNames(relicDefinition!);
        var instanceProps = GetPublicReadablePropertyNames(relicInstance!);

        definitionProps.Should().BeEquivalentTo(requiredDefinitionProps, "RelicDefinition contract shape must exactly match task details");
        instanceProps.Should().BeEquivalentTo(requiredInstanceProps, "RelicInstance contract shape must exactly match task details");

        var definitionCtor = FindRecordCtor(relicDefinition!, typeof(string), typeof(string), typeof(string), typeof(IReadOnlyList<string>));
        definitionCtor.Should().NotBeNull("RelicDefinition should expose the expected record constructor");

        var instanceCtor = FindRecordCtor(relicInstance!, typeof(string), typeof(IReadOnlyList<string>));
        instanceCtor.Should().NotBeNull("RelicInstance should expose the expected record constructor");

        var definitionValue = definitionCtor!.Invoke(new object[] { "relic.sword.001", "name.relic.sword.001", "desc.relic.sword.001", new[] { "starter", "attack" } });
        var instanceValue = instanceCtor!.Invoke(new object[] { "instance.001", new[] { "atk+5", "crit+1" } });

        var payload = new
        {
            relic_definition = definitionValue,
            relic_instance = instanceValue,
        };

        var serialized = JsonSerializer.Serialize(payload);
        serialized.Should().NotBeNullOrWhiteSpace();

        using var doc = JsonDocument.Parse(serialized);
        var root = doc.RootElement;
        root.TryGetProperty("relic_definition", out var relicDefinitionJson).Should().BeTrue();
        root.TryGetProperty("relic_instance", out var relicInstanceJson).Should().BeTrue();

        var definitionJsonKeys = relicDefinitionJson.EnumerateObject().Select(p => p.Name).ToArray();
        var instanceJsonKeys = relicInstanceJson.EnumerateObject().Select(p => p.Name).ToArray();

        definitionJsonKeys.Should().BeEquivalentTo(requiredDefinitionProps, "serialized RelicDefinition keys must exactly match required contract keys");
        instanceJsonKeys.Should().BeEquivalentTo(requiredInstanceProps, "serialized RelicInstance keys must exactly match required contract keys");
        ValidateSerializedContractKeysStrict(serialized, "relic_definition", requiredDefinitionProps).Should().BeTrue();
        ValidateSerializedContractKeysStrict(serialized, "relic_instance", requiredInstanceProps).Should().BeTrue();

        var tamperedPayload = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(serialized)!;
        var tamperedDefinition = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(tamperedPayload["relic_definition"].GetRawText())!;
        tamperedDefinition["legacy_key"] = JsonDocument.Parse("\"legacy\"").RootElement.Clone();
        var tamperedJson = JsonSerializer.Serialize(new
        {
            relic_definition = tamperedDefinition,
            relic_instance = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(tamperedPayload["relic_instance"].GetRawText()),
        });

        ValidateSerializedContractKeysStrict(tamperedJson, "relic_definition", requiredDefinitionProps)
            .Should()
            .BeFalse("serialized payload with undeclared extra keys must fail semantic validation");
    }

    // ACC:T30.2
    [Fact]
    public void ShouldDeclareRelicContractsOnlyUnderGameCoreContracts_WhenScanningRepositorySources()
    {
        RuntimeInformation.IsOSPlatform(OSPlatform.Windows).Should().BeTrue("Task 30 acceptance is defined for Windows environment");

        var root = FindRepositoryRoot();
        var sourceFiles = EnumerateRepositoryFiles(root, "*.cs");

        var declarationPattern = new Regex(
            @"\b(?:public|internal)?\s*(?:sealed\s+)?(?:partial\s+)?(?:record(?:\s+class)?|class)\s+(RelicDefinition|RelicInstance)\b",
            RegexOptions.Compiled);

        var declarations = sourceFiles
            .Select(path => new
            {
                Path = NormalizePath(path, root),
                Matches = declarationPattern.Matches(File.ReadAllText(path))
            })
            .Where(x => x.Matches.Count > 0)
            .SelectMany(x => x.Matches.Cast<Match>().Select(m => new { x.Path, TypeName = m.Groups[1].Value }))
            .ToList();

        declarations.Should().NotBeEmpty("relic contracts must be declared in source");

        declarations
            .Where(x => x.Path.StartsWith("Game.Core/Contracts/", StringComparison.OrdinalIgnoreCase))
            .Select(x => x.TypeName)
            .Distinct(StringComparer.Ordinal)
            .Should()
            .Contain(new[] { "RelicDefinition", "RelicInstance" });

        declarations
            .Where(x => !x.Path.StartsWith("Game.Core/Contracts/", StringComparison.OrdinalIgnoreCase))
            .Should()
            .BeEmpty("contract declarations must exist only under Game.Core/Contracts");
    }

    // ACC:T30.3
    [Fact]
    public void ShouldContainTask0030TestRefInOverlay_WhenValidatingDocumentationTraceability()
    {
        var root = FindRepositoryRoot();
        var overlayPath = Path.Combine(root, Task30OverlayTestingPath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(overlayPath).Should().BeTrue("Task 30 testing overlay file must exist");

        var content = File.ReadAllText(overlayPath);
        content.Contains("Test-Refs", StringComparison.OrdinalIgnoreCase).Should().BeTrue();
        content.Contains(ThisTestPath, StringComparison.Ordinal).Should().BeTrue("Task 30 testing overlay must include this acceptance test path");

        var thisTestContent = File.ReadAllText(GetCurrentSourceFilePath());
        thisTestContent.Contains("ACC:T30.1", StringComparison.Ordinal).Should().BeTrue("Task 30 acceptance anchor must be locatable from this test source");
    }

    // ACC:T30.7
    [Fact]
    public void ShouldIncludeRequiredAdrRefsInTask0030ResultJson_WhenValidatingTaskOutputs()
    {
        var root = FindRepositoryRoot();
        var adrSet = ReadTask30AdrRefsFromTaskViews(root);

        adrSet.Should().BeEquivalentTo(RequiredAdrRefs, "task-0030 JSON refs must include exactly ADR-0010, ADR-0020, ADR-0021");
    }

    // ACC:T30.8
    [Fact]
    public void ShouldMatchChecklistAdrRefsWithTask0030JsonRefs_WhenAuditingAcceptanceChecklist()
    {
        var root = FindRepositoryRoot();
        var checklistPath = FindSingleFile(root, "ACCEPTANCE_CHECKLIST.md");
        File.Exists(checklistPath).Should().BeTrue("ACCEPTANCE_CHECKLIST.md must exist");

        var checklistContent = File.ReadAllText(checklistPath);
        var checklistAdrSet = ParseChecklistTask30AdrRefs(checklistContent);

        checklistAdrSet.Should().BeEquivalentTo(RequiredAdrRefs, "checklist must explicitly list required ADR refs");

        var taskJsonAdrSet = ReadTask30AdrRefsFromTaskViews(root);

        taskJsonAdrSet.Should().BeEquivalentTo(RequiredAdrRefs);
        checklistAdrSet.Should().BeEquivalentTo(taskJsonAdrSet, "checklist ADR refs must exactly match task-0030 JSON refs");
    }

    // ACC:T30.9
    [Fact]
    public void ShouldExposeAuditableAdr0020Marker_WhenParsingThisAcceptanceFile()
    {
        var thisFile = GetCurrentSourceFilePath();
        File.Exists(thisFile).Should().BeTrue();

        var text = File.ReadAllText(thisFile);
        var markerRegex = new Regex(@"ADR-REF:\s*ADR-0020", RegexOptions.IgnoreCase | RegexOptions.Compiled);

        markerRegex.IsMatch(text).Should().BeTrue("this test file must contain a parseable ADR-0020 marker for gate scripts");
    }

    private static void EnsureGameCoreAssemblyIsLoaded()
    {
        var loaded = AppDomain.CurrentDomain
            .GetAssemblies()
            .Any(a => string.Equals(a.GetName().Name, "Game.Core", StringComparison.OrdinalIgnoreCase));

        if (!loaded)
        {
            try
            {
                _ = Assembly.Load("Game.Core");
            }
            catch
            {
                // Keep tests compile-safe even when assembly probing is controlled by runner.
            }
        }
    }

    private static Type? FindTypeBySimpleName(string typeName)
    {
        foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
        {
            try
            {
                var type = assembly.GetTypes().FirstOrDefault(t => string.Equals(t.Name, typeName, StringComparison.Ordinal));
                if (type is not null)
                {
                    return type;
                }
            }
            catch (ReflectionTypeLoadException)
            {
                // Ignore partial load failures and continue scan.
            }
        }

        return null;
    }

    private static HashSet<string> GetPublicReadablePropertyNames(Type type)
    {
        return type
            .GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .Where(p => p.CanRead)
            .Select(p => p.Name)
            .ToHashSet(StringComparer.Ordinal);
    }

    private static ConstructorInfo? FindRecordCtor(Type type, params Type[] parameterTypes)
    {
        return type.GetConstructor(parameterTypes);
    }

    private static bool ValidateSerializedContractKeysStrict(string json, string objectKey, IEnumerable<string> requiredKeys)
    {
        using var doc = JsonDocument.Parse(json);
        if (!doc.RootElement.TryGetProperty(objectKey, out var obj) || obj.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        var actualKeys = obj.EnumerateObject().Select(p => p.Name).ToHashSet(StringComparer.Ordinal);
        var requiredSet = requiredKeys.ToHashSet(StringComparer.Ordinal);
        return actualKeys.SetEquals(requiredSet);
    }

    private static string FindRepositoryRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var marker = Path.Combine(dir.FullName, "project.godot");
            if (File.Exists(marker))
            {
                return dir.FullName;
            }

            dir = dir.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate repository root from AppContext.BaseDirectory.");
    }

    private static IEnumerable<string> EnumerateRepositoryFiles(string root, string pattern)
    {
        return Directory
            .EnumerateFiles(root, pattern, SearchOption.AllDirectories)
            .Where(path => !path.Contains("\\bin\\", StringComparison.OrdinalIgnoreCase))
            .Where(path => !path.Contains("\\obj\\", StringComparison.OrdinalIgnoreCase))
            .Where(path => !path.Contains("\\.godot\\", StringComparison.OrdinalIgnoreCase));
    }

    private static string NormalizePath(string absolutePath, string root)
    {
        var relative = Path.GetRelativePath(root, absolutePath);
        return relative.Replace('\\', '/');
    }

    private static HashSet<string> ReadTask30AdrRefsFromTaskViews(string root)
    {
        var paths = new[]
        {
            Path.Combine(root, ".taskmaster", "tasks", "tasks_back.json"),
            Path.Combine(root, ".taskmaster", "tasks", "tasks_gameplay.json"),
        };

        var refs = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var path in paths)
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            var row = doc.RootElement
                .EnumerateArray()
                .First(x => x.TryGetProperty("taskmaster_id", out var id) && id.ToString() == "30");
            foreach (var adr in row.GetProperty("adr_refs").EnumerateArray())
            {
                var value = adr.GetString();
                if (!string.IsNullOrWhiteSpace(value))
                {
                    refs.Add(value.ToUpperInvariant());
                }
            }
        }

        return refs;
    }

    private static HashSet<string> ParseChecklistTask30AdrRefs(string checklist)
    {
        const string section = "## Task30 ADR Mapping";
        var index = checklist.IndexOf(section, StringComparison.Ordinal);
        index.Should().BeGreaterOrEqualTo(0, "checklist must include Task30 ADR Mapping section");

        var slice = checklist[index..];
        return slice
            .Split('\n')
            .Select(line => line.Trim())
            .Where(line => line.StartsWith("- ADR-", StringComparison.OrdinalIgnoreCase))
            .Select(line => line.TrimStart('-').Trim().ToUpperInvariant())
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
    }

    private static string FindSingleFile(string root, string fileName)
    {
        var matches = Directory
            .EnumerateFiles(root, fileName, SearchOption.AllDirectories)
            .Where(path => !path.Contains("\\bin\\", StringComparison.OrdinalIgnoreCase))
            .Where(path => !path.Contains("\\obj\\", StringComparison.OrdinalIgnoreCase))
            .ToArray();

        matches.Length.Should().BeGreaterThan(0, $"{fileName} must exist in repository");
        return matches[0];
    }

    private static string GetCurrentSourceFilePath([CallerFilePath] string path = "") => path;
}
