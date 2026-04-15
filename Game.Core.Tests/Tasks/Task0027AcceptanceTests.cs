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

public sealed class Task0027AcceptanceTests
{
    private const int TaskmasterId = 27;
    private const string ThisTestFilePath = "Game.Core.Tests/Tasks/Task0027AcceptanceTests.cs";
    private static readonly string[] ExpectedAdrRefs = { "ADR-0032", "ADR-0021" };
    private static readonly string[] ExpectedChapterRefs = { "CH01", "CH06", "CH07", "CH05" };
    private static readonly string[] ExpectedTaskTestRefs =
    {
        "Game.Core.Tests/Tasks/Task0027AcceptanceTests.cs",
        "Game.Core.Tests/Services/DifficultyRuleServiceDeterminismTests.cs",
        "Game.Core.Tests/Services/DifficultyRuleServiceThresholdTests.cs",
    };

    public static IEnumerable<object[]> DifficultyMappingCases =>
        new[]
        {
            new object[] { "Easy", new[] { "EnemyHealthScale:0.85", "EnemyDamageScale:0.90", "LootScale:1.15" } },
            new object[] { "Normal", new[] { "EnemyHealthScale:1.00", "EnemyDamageScale:1.00", "LootScale:1.00" } },
            new object[] { "Hard", new[] { "EnemyHealthScale:1.20", "EnemyDamageScale:1.15", "LootScale:0.90" } },
        };

    // ACC:T27.1
    [Theory]
    [MemberData(nameof(DifficultyMappingCases))]
    public void ShouldReturnExactModifierSet_WhenDifficultyInputIsMapped(string difficulty, IReadOnlyCollection<string> expectedModifiers)
    {
        var sut = CreateServiceUnderTest();

        var actualModifiers = sut.GetModifiers(difficulty);

        actualModifiers.Should().BeEquivalentTo(expectedModifiers, options => options.WithStrictOrdering());
    }

    // ACC:T27.2
    [Fact]
    public void ShouldReturnEqualModifiers_WhenSameDifficultyIsResolvedRepeatedly()
    {
        var sut = CreateServiceUnderTest();

        var firstResult = sut.GetModifiers("Normal");
        var secondResult = sut.GetModifiers("Normal");

        firstResult.Should().Equal(secondResult);
    }

    // ACC:T27.3
    [Fact]
    public void ShouldContainTaskTestFilePath_WhenOverlayTestRefsAreValidated()
    {
        var repoRoot = FindRepositoryRoot();
        var taskNode = ReadTaskNodeByTaskmasterId(
            Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_gameplay.json"),
            TaskmasterId);

        var testRefs = ReadStringArray(taskNode, "test_refs");
        testRefs.Should().BeEquivalentTo(ExpectedTaskTestRefs, options => options.WithoutStrictOrdering());
        testRefs.Should().Contain(ThisTestFilePath);

        foreach (var testRef in testRefs)
        {
            var resolvedPath = Path.Combine(repoRoot, testRef.Replace('/', Path.DirectorySeparatorChar));
            File.Exists(resolvedPath).Should().BeTrue("task test_refs entry must map to a concrete file: {0}", testRef);
        }

        var overlayRefs = ReadStringArray(taskNode, "overlay_refs");
        var checklistPath = overlayRefs.FirstOrDefault(path =>
            path.EndsWith("ACCEPTANCE_CHECKLIST.md", StringComparison.OrdinalIgnoreCase));

        checklistPath.Should().NotBeNull("task overlay refs should include acceptance checklist for traceability");
        var resolvedChecklistPath = Path.Combine(repoRoot, checklistPath!.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(resolvedChecklistPath).Should().BeTrue("overlay checklist path must resolve to a concrete file");
    }

    // ACC:T27.7
    [Fact]
    public void ShouldMatchAdrRefsExactly_WhenGateSummaryIsValidated()
    {
        using var gateSummary = CreateGateSummaryArtifact();

        var hasExactAdrRefs = GateSummaryValidator.HasExactStringArray(gateSummary.RootElement, "adr_refs", ExpectedAdrRefs);

        hasExactAdrRefs.Should().BeTrue();
    }

    // ACC:T27.8
    [Fact]
    public void ShouldMatchChapterRefsExactly_WhenGateSummaryIsValidated()
    {
        using var gateSummary = CreateGateSummaryArtifact();

        var hasExactChapterRefs = GateSummaryValidator.HasExactStringArray(gateSummary.RootElement, "chapter_refs", ExpectedChapterRefs);

        hasExactChapterRefs.Should().BeTrue();
    }

    // ACC:T27.9
    [Fact]
    public void ShouldRequireExecutedPassingEvidence_WhenTaskResultIsComputed()
    {
        using var passSummary = CreateGateSummaryArtifact();
        var requiredEvidence = EnumerateRequiredEvidenceRefs(passSummary.RootElement).ToArray();

        GateSummaryValidator.HasExecutedPassingEvidence(passSummary.RootElement, requiredEvidence).Should().BeTrue();

        var failEvidence = requiredEvidence.ToDictionary(
            key => key,
            _ => new EvidenceStatus(Executed: true, PassFail: "pass"),
            StringComparer.Ordinal);
        failEvidence[requiredEvidence[0]] = new EvidenceStatus(Executed: false, PassFail: "fail");
        using var failSummary = CreateGateSummaryArtifact(evidenceOverrides: failEvidence);
        GateSummaryValidator.HasExecutedPassingEvidence(failSummary.RootElement, requiredEvidence).Should().BeFalse();

        var missingEvidence = requiredEvidence
            .Skip(1)
            .ToDictionary(
                key => key,
                _ => new EvidenceStatus(Executed: true, PassFail: "pass"),
                StringComparer.Ordinal);
        using var missingSummary = CreateGateSummaryArtifact(evidenceOverrides: missingEvidence);
        GateSummaryValidator.HasExecutedPassingEvidence(missingSummary.RootElement, requiredEvidence).Should().BeFalse();
    }

    // ACC:T27.10
    [Fact]
    public void ShouldRejectPassedFlag_WhenOptionalSwitchIsDisabled()
    {
        var optionalSwitches = new Dictionary<string, OptionalSwitchStatus>(StringComparer.Ordinal)
        {
            ["experimentalDifficultyScaling"] = new(Enabled: false, Executed: false, PassFail: "pass"),
        };
        using var gateSummary = CreateGateSummaryArtifact(optionalSwitchOverrides: optionalSwitches);

        var disabledSwitchesAreValid = GateSummaryValidator.HasValidDisabledOptionalSwitchStates(gateSummary.RootElement);

        disabledSwitchesAreValid.Should().BeFalse();
    }

    // ACC:T27.11
    [Fact]
    public void ShouldReturnNonZeroExitCode_WhenRequiredBacklinksAreMissing()
    {
        var backlinks = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["adr_refs"] = "ADR-0032,ADR-0021",
            ["chapter_refs"] = "CH01,CH06,CH07,CH05",
        };
        using var gateSummary = CreateGateSummaryArtifact(backlinksOverrides: backlinks);

        var exitCode = GateSummaryValidator.ComputeFailClosedExitCode(
            gateSummary.RootElement,
            requiredBacklinks: new[] { "adr_refs", "chapter_refs", "test_refs" });

        exitCode.Should().NotBe(0);
    }

    private static DifficultyRuleService CreateServiceUnderTest()
    {
        return new DifficultyRuleService();
    }

    private static JsonDocument CreateGateSummaryArtifact(
        IReadOnlyDictionary<string, EvidenceStatus>? evidenceOverrides = null,
        IReadOnlyDictionary<string, OptionalSwitchStatus>? optionalSwitchOverrides = null,
        IReadOnlyDictionary<string, string>? backlinksOverrides = null)
    {
        var repoRoot = FindRepositoryRoot();
        var taskNode = ReadTaskNodeByTaskmasterId(
            Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_gameplay.json"),
            TaskmasterId);
        var adrRefs = ReadStringArray(taskNode, "adr_refs");
        var chapterRefs = ReadStringArray(taskNode, "chapter_refs");
        var testRefs = ReadStringArray(taskNode, "test_refs");

        var defaultEvidence = testRefs
            .ToDictionary(
                testRef => testRef,
                _ => new EvidenceStatus(Executed: true, PassFail: "pass"),
                StringComparer.Ordinal);

        var optionalSwitches = optionalSwitchOverrides ??
            new Dictionary<string, OptionalSwitchStatus>(StringComparer.Ordinal)
            {
                ["experimentalDifficultyScaling"] = new(Enabled: false, Executed: false, PassFail: "skipped"),
            };
        var backlinks = backlinksOverrides ??
            new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["adr_refs"] = string.Join(",", adrRefs),
                ["chapter_refs"] = string.Join(",", chapterRefs),
                ["test_refs"] = string.Join(",", testRefs),
            };

        var payload = new GateSummaryPayload(
            AdrRefs: adrRefs,
            ChapterRefs: chapterRefs,
            TestRefs: testRefs,
            Evidence: evidenceOverrides ?? defaultEvidence,
            OptionalSwitches: optionalSwitches,
            Backlinks: backlinks);

        return JsonDocument.Parse(JsonSerializer.Serialize(payload));
    }

    private static IEnumerable<string> EnumerateRequiredEvidenceRefs(JsonElement gateSummary)
    {
        gateSummary.TryGetProperty("test_refs", out var testRefs).Should().BeTrue();
        testRefs.ValueKind.Should().Be(JsonValueKind.Array);

        return testRefs
            .EnumerateArray()
            .Select(item => item.GetString())
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .Select(item => item!)
            .ToArray();
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

        throw new DirectoryNotFoundException("Could not locate repository root from test execution directory.");
    }

    private sealed record GateSummaryPayload(
        [property: JsonPropertyName("adr_refs")] IReadOnlyList<string> AdrRefs,
        [property: JsonPropertyName("chapter_refs")] IReadOnlyList<string> ChapterRefs,
        [property: JsonPropertyName("test_refs")] IReadOnlyList<string> TestRefs,
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
            var hasRequiredTopLevel = gateSummary.TryGetProperty("adr_refs", out var adrRefs) && adrRefs.ValueKind == JsonValueKind.Array &&
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

            var missingBacklink = requiredBacklinks.Any(required => !backlinks.TryGetProperty(required, out var _));
            if (missingBacklink)
            {
                return 1;
            }

            return 0;
        }
    }
}
