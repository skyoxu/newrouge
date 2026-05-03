using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0031AcceptanceTests
{
    private const int TaskmasterId = 31;
    private const string ThisTestFilePath = "Game.Core.Tests/Tasks/Task0031AcceptanceTests.cs";
    private const string OverlayChecklistPath = "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md";

    private static readonly string[] ExpectedAdrRefs = { "ADR-0010", "ADR-0021" };
    private static readonly string[] ExpectedChapterRefs = { "CH01", "CH06", "CH10", "CH07", "CH05" };
    private static readonly string[] ExpectedRelicIds =
    {
        "relic.ashen_hourglass",
        "relic.obsidian_mirror",
        "relic.blood_oath",
        "relic.rusted_compass",
        "relic.twilight_coin",
        "relic.embershard",
        "relic.frostbite_ring",
        "relic.gale_charm",
        "relic.iron_vow",
        "relic.moonlit_compass",
        "relic.nightwatch_lantern",
        "relic.oaken_talisman",
        "relic.phantom_quill",
        "relic.quicksilver_seal",
        "relic.raven_feather",
        "relic.sunken_idol",
        "relic.thorn_crown",
        "relic.umbral_shard",
        "relic.vigilant_emblem",
        "relic.warden_mark",
    };

    // ACC:T31.1
    [Fact]
    public void ShouldExposeExactlyTwentyRelicDefinitions_WhenEnumeratingStartingRelicCatalog()
    {
        var definitions = StartingRelicService.Definitions;

        definitions.Should().HaveCount(20);
        definitions.Select(item => item.RelicId)
            .Should()
            .BeEquivalentTo(ExpectedRelicIds, options => options.WithoutStrictOrdering());
    }

    // ACC:T31.2
    [Fact]
    public void ShouldEnforceUniqueRelicIdsAndTranslationKeys_WhenValidatingStartingRelicCatalog()
    {
        var definitions = StartingRelicService.Definitions;

        var validation = StartingRelicService.ValidateUniqueRelicIds(definitions);
        validation.IsValid.Should().BeTrue();

        definitions.Should().OnlyContain(item => !string.IsNullOrWhiteSpace(item.TranslationKey));

        var duplicateDefinitions = definitions.Concat(new[]
        {
            new StartingRelicDefinition(
                definitions[0].RelicId,
                "relic.name.duplicate",
                "effect.duplicate",
                new[] { "m1", "duplicate" }),
        }).ToArray();
        var duplicateValidation = StartingRelicService.ValidateUniqueRelicIds(duplicateDefinitions);

        duplicateValidation.IsValid.Should().BeFalse();
        duplicateValidation.DuplicateRelicIds.Should().Contain(definitions[0].RelicId);
    }

    // ACC:T31.3
    [Fact]
    public void ShouldRestrictOverlayTestRefsToTask0031Files_WhenTask31ChecklistExists()
    {
        var taskNode = ReadTaskNodeByTaskmasterId(
            Path.Combine(FindRepositoryRoot(), ".taskmaster", "tasks", "tasks_gameplay.json"),
            TaskmasterId);

        var taskTestRefs = ReadStringArray(taskNode, "test_refs");
        taskTestRefs.Should().Contain(ThisTestFilePath);
        taskTestRefs.Should().OnlyContain(path => path.StartsWith("Game.Core.Tests/", StringComparison.Ordinal));
        var repositoryRoot = FindRepositoryRoot();
        taskTestRefs.Select(path => Path.Combine(repositoryRoot, path.Replace('/', Path.DirectorySeparatorChar)))
            .Should()
            .OnlyContain(path => File.Exists(path));

        var checklistFullPath = Path.Combine(FindRepositoryRoot(), OverlayChecklistPath.Replace('/', Path.DirectorySeparatorChar));
        if (!File.Exists(checklistFullPath))
        {
            return;
        }

        var checklist = File.ReadAllText(checklistFullPath);
        var taskSection = ExtractTask31Section(checklist);
        if (string.IsNullOrWhiteSpace(taskSection))
        {
            return;
        }

        var checklistRefs = ExtractTestRefs(taskSection).ToArray();
        if (checklistRefs.Length == 0)
        {
            return;
        }

        checklistRefs.Should().Contain(ThisTestFilePath);
        checklistRefs.Should().OnlyContain(path =>
            path.StartsWith("Game.Core.Tests/", StringComparison.Ordinal) &&
            File.Exists(Path.Combine(FindRepositoryRoot(), path.Replace('/', Path.DirectorySeparatorChar))));
    }

    // ACC:T31.4
    [Fact]
    public void ShouldRequireEffectDescriptorFieldAndValues_WhenValidatingStartingRelicCatalog()
    {
        var definitions = StartingRelicService.Definitions;

        definitions.Should().HaveCount(20);
        definitions.Should().OnlyContain(item => !string.IsNullOrWhiteSpace(item.EffectDescriptor));
    }

    // ACC:T31.5
    [Fact]
    public void ShouldAllowOnlyM1Relics_WhenValidatingStartingRelicCatalog()
    {
        var definitions = StartingRelicService.Definitions;

        definitions.Should().HaveCount(20);
        definitions.Should().OnlyContain(item =>
            item.Tags.Any(tag => string.Equals(tag, "m1", StringComparison.OrdinalIgnoreCase)));
    }

    // ACC:T31.6
    [Fact]
    public void ShouldContainAdr0010AndAdr0021Backlinks_WhenTask31MetadataIsValidated()
    {
        var taskNode = ReadTaskNodeByTaskmasterId(
            Path.Combine(FindRepositoryRoot(), ".taskmaster", "tasks", "tasks_gameplay.json"),
            TaskmasterId);
        var adrRefs = ReadStringArray(taskNode, "adr_refs");

        adrRefs.Should().Equal(ExpectedAdrRefs);
    }

    // ACC:T31.7
    [Fact]
    public void ShouldMatchAdrRefsExactly_WhenBuildingGateSummaryFromTaskMetadata()
    {
        using var gateSummary = CreateGateSummaryArtifact();

        GateSummaryValidator.HasExactStringArray(gateSummary.RootElement, "adr_refs", ExpectedAdrRefs).Should().BeTrue();
    }

    // ACC:T31.8
    [Fact]
    public void ShouldMatchChapterRefsExactly_WhenBuildingGateSummaryFromTaskMetadata()
    {
        using var gateSummary = CreateGateSummaryArtifact();

        GateSummaryValidator.HasExactStringArray(gateSummary.RootElement, "chapter_refs", ExpectedChapterRefs).Should().BeTrue();
    }

    // ACC:T31.9
    [Fact]
    public void ShouldRequireExecutedPassingEvidence_WhenEvaluatingGateSummary()
    {
        var metadata = ReadTask31Metadata();
        using var passSummary = CreateGateSummaryArtifact();

        GateSummaryValidator.HasExecutedPassingEvidence(passSummary.RootElement, metadata.TestRefs).Should().BeTrue();

        var failedEvidence = metadata.TestRefs.ToDictionary(
            key => key,
            _ => new EvidenceStatus(true, "pass"),
            StringComparer.Ordinal);
        failedEvidence[metadata.TestRefs[0]] = new EvidenceStatus(false, "fail");

        using var failedSummary = CreateGateSummaryArtifact(evidenceOverrides: failedEvidence);
        GateSummaryValidator.HasExecutedPassingEvidence(failedSummary.RootElement, metadata.TestRefs).Should().BeFalse();
    }

    // ACC:T31.10
    [Fact]
    public void ShouldRejectPassStatus_WhenOptionalSwitchIsDisabled()
    {
        var optionalSwitches = new Dictionary<string, OptionalSwitchStatus>(StringComparer.Ordinal)
        {
            ["experimentalStartingRelicSwitch"] = new OptionalSwitchStatus(false, false, "pass"),
        };
        using var gateSummary = CreateGateSummaryArtifact(optionalSwitchOverrides: optionalSwitches);

        GateSummaryValidator.HasValidDisabledOptionalSwitchStates(gateSummary.RootElement).Should().BeFalse();
    }

    // ACC:T31.11
    [Fact]
    public void ShouldReturnNonZeroExitCode_WhenRequiredBacklinksAreMissing()
    {
        var metadata = ReadTask31Metadata();
        var backlinks = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["adr_refs"] = string.Join(",", metadata.AdrRefs),
            ["chapter_refs"] = string.Join(",", metadata.ChapterRefs),
        };
        using var gateSummary = CreateGateSummaryArtifact(backlinksOverrides: backlinks);

        var exitCode = GateSummaryValidator.ComputeFailClosedExitCode(
            gateSummary.RootElement,
            new[] { "adr_refs", "chapter_refs", "test_refs" });

        exitCode.Should().NotBe(0);
    }

    private static Task31Metadata ReadTask31Metadata()
    {
        var taskNode = ReadTaskNodeByTaskmasterId(
            Path.Combine(FindRepositoryRoot(), ".taskmaster", "tasks", "tasks_gameplay.json"),
            TaskmasterId);

        return new Task31Metadata(
            ReadStringArray(taskNode, "adr_refs"),
            ReadStringArray(taskNode, "chapter_refs"),
            ReadStringArray(taskNode, "test_refs"));
    }

    private static JsonDocument CreateGateSummaryArtifact(
        IReadOnlyDictionary<string, EvidenceStatus>? evidenceOverrides = null,
        IReadOnlyDictionary<string, OptionalSwitchStatus>? optionalSwitchOverrides = null,
        IReadOnlyDictionary<string, string>? backlinksOverrides = null)
    {
        var metadata = ReadTask31Metadata();

        var evidence = evidenceOverrides ?? metadata.TestRefs.ToDictionary(
            path => path,
            _ => new EvidenceStatus(true, "pass"),
            StringComparer.Ordinal);
        var optionalSwitches = optionalSwitchOverrides ??
            new Dictionary<string, OptionalSwitchStatus>(StringComparer.Ordinal)
            {
                ["experimentalStartingRelicSwitch"] = new OptionalSwitchStatus(false, false, "skipped"),
            };
        var backlinks = backlinksOverrides ??
            new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["adr_refs"] = string.Join(",", metadata.AdrRefs),
                ["chapter_refs"] = string.Join(",", metadata.ChapterRefs),
                ["test_refs"] = string.Join(",", metadata.TestRefs),
            };

        var payload = new GateSummaryPayload(
            metadata.AdrRefs,
            metadata.ChapterRefs,
            metadata.TestRefs,
            evidence,
            optionalSwitches,
            backlinks);

        return JsonDocument.Parse(JsonSerializer.Serialize(payload));
    }

    private static JsonElement ReadTaskNodeByTaskmasterId(string taskFilePath, int taskmasterId)
    {
        File.Exists(taskFilePath).Should().BeTrue("task metadata file must exist: {0}", taskFilePath);

        using var document = JsonDocument.Parse(File.ReadAllText(taskFilePath));
        var matched = document.RootElement
            .EnumerateArray()
            .FirstOrDefault(node =>
                node.TryGetProperty("taskmaster_id", out var value) &&
                value.ValueKind == JsonValueKind.Number &&
                value.GetInt32() == taskmasterId);

        matched.ValueKind.Should().NotBe(JsonValueKind.Undefined, "taskmaster_id={0} must exist in {1}", taskmasterId, taskFilePath);
        return matched.Clone();
    }

    private static string[] ReadStringArray(JsonElement node, string propertyName)
    {
        node.TryGetProperty(propertyName, out var property).Should().BeTrue("property {0} must exist in task metadata", propertyName);
        property.ValueKind.Should().Be(JsonValueKind.Array, "property {0} must be an array", propertyName);

        return property
            .EnumerateArray()
            .Select(item => item.GetString())
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .Select(item => item!)
            .ToArray();
    }

    private static string ExtractTask31Section(string checklistContent)
    {
        var normalized = checklistContent.Replace("\r", string.Empty);
        var lines = normalized.Split('\n');
        var start = -1;

        for (var index = 0; index < lines.Length; index++)
        {
            if (lines[index].Contains("Task 31", StringComparison.OrdinalIgnoreCase) ||
                lines[index].Contains("Task31", StringComparison.OrdinalIgnoreCase) ||
                lines[index].Contains("T31", StringComparison.OrdinalIgnoreCase))
            {
                start = index;
                break;
            }
        }

        if (start < 0)
        {
            return string.Empty;
        }

        var end = lines.Length;
        for (var index = start + 1; index < lines.Length; index++)
        {
            var trimmed = lines[index].TrimStart();
            if ((trimmed.StartsWith("## ", StringComparison.Ordinal) || trimmed.StartsWith("# ", StringComparison.Ordinal)) &&
                !trimmed.Contains("31", StringComparison.OrdinalIgnoreCase))
            {
                end = index;
                break;
            }
        }

        return string.Join(Environment.NewLine, lines.Skip(start).Take(end - start));
    }

    private static IEnumerable<string> ExtractTestRefs(string section)
    {
        var refs = new HashSet<string>(StringComparer.Ordinal);
        var lines = section.Replace("\r", string.Empty).Split('\n');
        var separators = new[] { ' ', ',', ';', '|', '\t' };

        foreach (var line in lines)
        {
            var tokens = line.Split(separators, StringSplitOptions.RemoveEmptyEntries);
            foreach (var token in tokens)
            {
                var normalized = token.Trim().Trim('"', '\'', '(', ')', '[', ']', '{', '}', ',', ';', '.');
                if (normalized.StartsWith("Game.Core.Tests/", StringComparison.Ordinal) &&
                    normalized.EndsWith(".cs", StringComparison.OrdinalIgnoreCase))
                {
                    refs.Add(normalized);
                }
            }
        }

        return refs;
    }

    private static string FindRepositoryRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);

        while (current is not null)
        {
            if (Directory.Exists(Path.Combine(current.FullName, ".taskmaster")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate repository root.");
    }

    private sealed record Task31Metadata(
        string[] AdrRefs,
        string[] ChapterRefs,
        string[] TestRefs);

    private sealed record GateSummaryPayload(
        [property: JsonPropertyName("adr_refs")] string[] AdrRefs,
        [property: JsonPropertyName("chapter_refs")] string[] ChapterRefs,
        [property: JsonPropertyName("test_refs")] string[] TestRefs,
        [property: JsonPropertyName("evidence")] IReadOnlyDictionary<string, EvidenceStatus> Evidence,
        [property: JsonPropertyName("optional_switches")] IReadOnlyDictionary<string, OptionalSwitchStatus> OptionalSwitches,
        [property: JsonPropertyName("backlinks")] IReadOnlyDictionary<string, string> Backlinks);

    private sealed record EvidenceStatus(
        [property: JsonPropertyName("executed")] bool Executed,
        [property: JsonPropertyName("pass_fail")] string PassFail);

    private sealed record OptionalSwitchStatus(
        [property: JsonPropertyName("enabled")] bool Enabled,
        [property: JsonPropertyName("executed")] bool Executed,
        [property: JsonPropertyName("pass_fail")] string PassFail);

    private static class GateSummaryValidator
    {
        public static bool HasExactStringArray(JsonElement gateSummary, string propertyName, IReadOnlyList<string> expectedValues)
        {
            if (!gateSummary.TryGetProperty(propertyName, out var property) || property.ValueKind != JsonValueKind.Array)
            {
                return false;
            }

            var actualValues = property
                .EnumerateArray()
                .Select(item => item.GetString())
                .Where(item => !string.IsNullOrWhiteSpace(item))
                .Select(item => item!)
                .ToArray();

            return actualValues.SequenceEqual(expectedValues, StringComparer.Ordinal);
        }

        public static bool HasExecutedPassingEvidence(JsonElement gateSummary, IEnumerable<string> requiredEvidence)
        {
            if (!gateSummary.TryGetProperty("evidence", out var evidence) || evidence.ValueKind != JsonValueKind.Object)
            {
                return false;
            }

            foreach (var evidenceRef in requiredEvidence)
            {
                if (!evidence.TryGetProperty(evidenceRef, out var status) || status.ValueKind != JsonValueKind.Object)
                {
                    return false;
                }

                if (!status.TryGetProperty("executed", out var executed) || executed.ValueKind != JsonValueKind.True)
                {
                    return false;
                }

                if (!status.TryGetProperty("pass_fail", out var passFail) ||
                    !string.Equals(passFail.GetString(), "pass", StringComparison.Ordinal))
                {
                    return false;
                }
            }

            return true;
        }

        public static bool HasValidDisabledOptionalSwitchStates(JsonElement gateSummary)
        {
            if (!gateSummary.TryGetProperty("optional_switches", out var optionalSwitches) || optionalSwitches.ValueKind != JsonValueKind.Object)
            {
                return false;
            }

            foreach (var entry in optionalSwitches.EnumerateObject())
            {
                var switchStatus = entry.Value;
                if (!switchStatus.TryGetProperty("enabled", out var enabled) || enabled.ValueKind == JsonValueKind.Undefined)
                {
                    return false;
                }

                if (enabled.GetBoolean())
                {
                    continue;
                }

                if (!switchStatus.TryGetProperty("executed", out var executed) || executed.ValueKind != JsonValueKind.False)
                {
                    return false;
                }

                if (!switchStatus.TryGetProperty("pass_fail", out var passFail) ||
                    !string.Equals(passFail.GetString(), "skipped", StringComparison.Ordinal))
                {
                    return false;
                }
            }

            return true;
        }

        public static int ComputeFailClosedExitCode(JsonElement gateSummary, IEnumerable<string> requiredBacklinks)
        {
            var hasRequiredTopLevel =
                gateSummary.TryGetProperty("adr_refs", out var adrRefs) && adrRefs.ValueKind == JsonValueKind.Array &&
                gateSummary.TryGetProperty("chapter_refs", out var chapterRefs) && chapterRefs.ValueKind == JsonValueKind.Array &&
                gateSummary.TryGetProperty("test_refs", out var testRefs) && testRefs.ValueKind == JsonValueKind.Array &&
                gateSummary.TryGetProperty("evidence", out var evidence) && evidence.ValueKind == JsonValueKind.Object;
            if (!hasRequiredTopLevel)
            {
                return 1;
            }

            if (!gateSummary.TryGetProperty("backlinks", out var backlinks) || backlinks.ValueKind != JsonValueKind.Object)
            {
                return 1;
            }

            var missingBacklink = requiredBacklinks.Any(required => !backlinks.TryGetProperty(required, out _));
            if (missingBacklink)
            {
                return 1;
            }

            return 0;
        }
    }

}
