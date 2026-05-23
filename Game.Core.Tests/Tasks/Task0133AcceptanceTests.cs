using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0133AcceptanceTests
{
    private static readonly string RepoRoot = ResolveRepoRoot();
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string ThisTestRef = "Game.Core.Tests/Tasks/Task0133AcceptanceTests.cs";
    private const string VisibleTextFlowRef = "Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd";
    private const string RewardLockRef = "Tests.Godot/tests/Integration/test_reward_offer_lock_persist_reenter.gd";
    private const string PipelineLatestPath = "logs/ci/2026-05-23/sc-review-pipeline-task-133/latest.json";

    // acceptance anchor: ACC:T133.1
    [Fact]
    [Trait("acceptance", "ACC:T133.1")]
    public void ShouldAllowPreSnapshotModifierRegistrationWithinGovernedSchema()
    {
        AssertAcceptanceRefsContain(0, ThisTestRef);
        var pipeline = new RewardEntryModifierPipeline();

        pipeline.CanRegister(new RewardEntryModifier(
            Action: "mutate",
            TargetEntryId: "gold",
            RewardType: string.Empty,
            Config: Dict(("amount", 77)))).Should().BeTrue();
        pipeline.CanRegister(new RewardEntryModifier(
            Action: "add",
            TargetEntryId: string.Empty,
            RewardType: "relic",
            Config: Dict(("relic_id", "relic.twilight_coin")))).Should().BeTrue();
        pipeline.CanRegister(new RewardEntryModifier(
            Action: "remove",
            TargetEntryId: "consumable",
            RewardType: string.Empty,
            Config: Dict())).Should().BeTrue();
    }

    // acceptance anchor: ACC:T133.2
    [Fact]
    [Trait("acceptance", "ACC:T133.2")]
    public void ShouldApplyRegisteredModifiersToNextContextSnapshotBeforeLock()
    {
        AssertAcceptanceRefsContain(1, ThisTestRef, VisibleTextFlowRef);
        var result = new RewardEntryModifierPipeline().Apply(CreateBaselineEntries(), new[]
        {
            new RewardEntryModifier("mutate", "gold", string.Empty, Dict(("amount", 77))),
            new RewardEntryModifier("add", string.Empty, "relic", Dict(("relic_id", "relic.twilight_coin"))),
            new RewardEntryModifier("remove", "consumable", string.Empty, Dict()),
        });

        result.Rejected.Should().BeFalse();
        result.Entries.Should().Contain(entry => entry.RewardType == "gold" && ReadInt(entry.Config, "amount") == 77);
        result.Entries.Should().Contain(entry => entry.RewardType == "relic" && ReadString(entry.Config, "relic_id") == "relic.twilight_coin");
        result.Entries.Should().NotContain(entry => entry.EntryId == "consumable");
    }

    // acceptance anchor: ACC:T133.3
    [Fact]
    [Trait("acceptance", "ACC:T133.3")]
    public void ShouldKeepLockedSnapshotImmutableAndRequireLaterContextToStartFromFreshBaseline()
    {
        AssertAcceptanceRefsContain(2, ThisTestRef, RewardLockRef);
        var pipeline = new RewardEntryModifierPipeline();
        var baseline = CreateBaselineEntries();
        var first = pipeline.Apply(baseline, new[]
        {
            new RewardEntryModifier("mutate", "gold", string.Empty, Dict(("amount", 91))),
        });
        var lockedSnapshot = first.Entries.ToArray();
        var second = pipeline.Apply(lockedSnapshot, new[]
        {
            new RewardEntryModifier("mutate", "gold", string.Empty, Dict(("amount", -9))),
        });

        second.Rejected.Should().BeTrue();
        second.Entries.Should().BeEquivalentTo(lockedSnapshot, options => options.WithStrictOrdering());

        var laterContext = pipeline.Apply(baseline, new[]
        {
            new RewardEntryModifier("remove", "gold", string.Empty, Dict()),
        });
        laterContext.Entries.Should().NotContain(entry => entry.EntryId == "gold");
        laterContext.Entries.Should().NotContain(entry => entry.RewardType == "relic" && ReadString(entry.Config, "relic_id") == "relic.twilight_coin");
    }

    // acceptance anchor: ACC:T133.4
    [Fact]
    [Trait("acceptance", "ACC:T133.4")]
    public void ShouldReplayDeterministicallyForIdenticalInputs()
    {
        AssertAcceptanceRefsContain(3, ThisTestRef, RewardLockRef);
        var modifiers = new[]
        {
            new RewardEntryModifier("mutate", "gold", string.Empty, Dict(("amount", 91))),
            new RewardEntryModifier("add", string.Empty, "relic", Dict(("relic_id", "relic.obsidian_mirror"))),
        };

        var pipeline = new RewardEntryModifierPipeline();
        var first = pipeline.Apply(CreateBaselineEntries(), modifiers);
        var second = pipeline.Apply(CreateBaselineEntries(), modifiers);

        second.Should().BeEquivalentTo(first);
    }

    // acceptance anchor: ACC:T133.5
    [Fact]
    [Trait("acceptance", "ACC:T133.5")]
    public void ShouldConfineModifierEffectsToTheirTargetedNextContextOnly()
    {
        AssertAcceptanceRefsContain(4, ThisTestRef);
        var baseline = CreateBaselineEntries();

        var first = new RewardEntryModifierPipeline().Apply(baseline, new[]
        {
            new RewardEntryModifier("mutate", "gold", string.Empty, Dict(("amount", 40))),
            new RewardEntryModifier("add", string.Empty, "relic", Dict(("relic_id", "relic.twilight_coin"))),
        });
        var second = new RewardEntryModifierPipeline().Apply(baseline, Array.Empty<RewardEntryModifier>());

        first.Entries.Should().Contain(entry => entry.RewardType == "gold" && ReadInt(entry.Config, "amount") == 40);
        first.Entries.Should().Contain(entry => entry.RewardType == "relic" && ReadString(entry.Config, "relic_id") == "relic.twilight_coin");
        second.Entries.Should().Contain(entry => entry.RewardType == "gold" && ReadInt(entry.Config, "amount") == 35);
        second.Entries.Should().NotContain(entry => entry.RewardType == "relic" && ReadString(entry.Config, "relic_id") == "relic.twilight_coin");
    }

    // acceptance anchor: ACC:T133.6
    [Fact]
    [Trait("acceptance", "ACC:T133.6")]
    public void ShouldRejectUnsupportedOrPartiallyInvalidModifiersWithoutPartialMutation()
    {
        AssertAcceptanceRefsContain(5, ThisTestRef);
        var baseline = CreateBaselineEntries();
        var result = new RewardEntryModifierPipeline().Apply(baseline, new[]
        {
            new RewardEntryModifier("mutate", "gold", string.Empty, Dict(("amount", -5))),
        });

        result.Rejected.Should().BeTrue();
        result.Entries.Should().BeEquivalentTo(baseline, options => options.WithStrictOrdering());
        new RewardEntryModifierPipeline().CanRegister(new RewardEntryModifier(
            "add",
            string.Empty,
            "unknown",
            Dict())).Should().BeFalse();
        var invalidAdd = new RewardEntryModifierPipeline().Apply(baseline, new[]
        {
            new RewardEntryModifier("add", string.Empty, "relic", Dict()),
        });
        invalidAdd.Rejected.Should().BeTrue();
        invalidAdd.Entries.Should().BeEquivalentTo(baseline, options => options.WithStrictOrdering());
    }

    private static Task0133Evidence LoadTask0133DeterministicEvidence()
    {
        var latestPath = Path.Combine(RepoRoot, PipelineLatestPath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(latestPath).Should().BeTrue("Task133 pipeline latest.json must exist.");

        using var latestDocument = JsonDocument.Parse(File.ReadAllText(latestPath));
        var latest = latestDocument.RootElement;
        latest.GetProperty("task_id").GetString().Should().Be("133");
        latest.GetProperty("status").GetString().Should().Be("ok");

        var summaryPath = latest.GetProperty("summary_path").GetString();
        summaryPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(summaryPath!).Should().BeTrue();

        using var summaryDocument = JsonDocument.Parse(File.ReadAllText(summaryPath!));
        var summary = summaryDocument.RootElement.Clone();
        summary.GetProperty("status").GetString().Should().Be("ok");
        summary.GetProperty("reason").GetString().Should().Be("pipeline_clean");

        var testSummaryPath = summary
            .GetProperty("steps")
            .EnumerateArray()
            .First(step => string.Equals(step.GetProperty("name").GetString(), "sc-test", StringComparison.Ordinal))
            .GetProperty("summary_file")
            .GetString();
        testSummaryPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(testSummaryPath!).Should().BeTrue();

        using var testSummaryDocument = JsonDocument.Parse(File.ReadAllText(testSummaryPath!));
        var testSummary = testSummaryDocument.RootElement;
        var gdunitStep = testSummary
            .GetProperty("steps")
            .EnumerateArray()
            .First(step => string.Equals(step.GetProperty("name").GetString(), "gdunit-hard", StringComparison.Ordinal));
        gdunitStep.GetProperty("status").GetString().Should().Be("ok");

        var gdunitCommand = string.Join(" ", gdunitStep.GetProperty("cmd").EnumerateArray().Select(item => item.GetString()));
        gdunitCommand.Should().Contain("tests/Integration/test_m1_visible_text_flow.gd");
        gdunitCommand.Should().Contain("tests/Integration/test_reward_offer_lock_persist_reenter.gd");

        var reportDir = gdunitStep.GetProperty("report_dir").GetString();
        reportDir.Should().NotBeNullOrWhiteSpace();
        var gdunitRunSummaryPath = Path.Combine(RepoRoot, reportDir!, "run-summary.json");
        File.Exists(gdunitRunSummaryPath).Should().BeTrue();

        using var gdunitRunSummaryDocument = JsonDocument.Parse(File.ReadAllText(gdunitRunSummaryPath));
        var gdunitRunSummary = gdunitRunSummaryDocument.RootElement.Clone();
        var addedTests = gdunitRunSummary
            .GetProperty("added")
            .EnumerateArray()
            .Select(item => item.GetString() ?? string.Empty)
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();

        var acceptanceSummaryPath = summary
            .GetProperty("steps")
            .EnumerateArray()
            .First(step => string.Equals(step.GetProperty("name").GetString(), "sc-acceptance-check", StringComparison.Ordinal))
            .GetProperty("summary_file")
            .GetString();
        acceptanceSummaryPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(acceptanceSummaryPath!).Should().BeTrue();

        using var acceptanceSummaryDocument = JsonDocument.Parse(File.ReadAllText(acceptanceSummaryPath!));
        var acceptanceSummary = acceptanceSummaryDocument.RootElement.Clone();

        return new Task0133Evidence(summary, gdunitRunSummary, addedTests, acceptanceSummary, testSummaryPath!, acceptanceSummaryPath!);
    }

    private static void AssertAcceptanceRefsContain(int acceptanceIndex, params string[] expectedRefs)
    {
        AssertAcceptanceRefsContain(TasksBackPath, acceptanceIndex, expectedRefs);
        AssertAcceptanceRefsContain(TasksGameplayPath, acceptanceIndex, expectedRefs);
    }

    private static void AssertAcceptanceRefsContain(string taskFilePath, int acceptanceIndex, params string[] expectedRefs)
    {
        var task = LoadTaskNode(taskFilePath, 133);
        var acceptance = task.GetProperty("acceptance")[acceptanceIndex].GetString() ?? string.Empty;
        foreach (var expected in expectedRefs)
        {
            acceptance.Should().Contain(expected);
        }
    }

    private static JsonElement LoadTaskNode(string taskFilePath, int taskmasterId)
    {
        using var document = JsonDocument.Parse(ReadRepoText(taskFilePath));
        foreach (var task in document.RootElement.EnumerateArray())
        {
            if (!task.TryGetProperty("taskmaster_id", out var idElement))
            {
                continue;
            }

            if (idElement.ValueKind == JsonValueKind.Number && idElement.GetInt32() == taskmasterId)
            {
                return task.Clone();
            }

            if (idElement.ValueKind == JsonValueKind.String
                && int.TryParse(idElement.GetString(), NumberStyles.Integer, CultureInfo.InvariantCulture, out var parsed)
                && parsed == taskmasterId)
            {
                return task.Clone();
            }
        }

        throw new Xunit.Sdk.XunitException($"Task {taskmasterId} not found in {taskFilePath}.");
    }

    private static string ReadRepoText(string relativePath)
    {
        var fullPath = Path.Combine(RepoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(fullPath).Should().BeTrue($"expected file: {relativePath}");
        return File.ReadAllText(fullPath);
    }

    private static string ResolveRepoRoot()
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

    private sealed record Task0133Evidence(
        JsonElement PipelineSummary,
        JsonElement GdUnitRunSummary,
        string[] AddedTests,
        JsonElement AcceptanceSummary,
        string TestSummaryPath,
        string AcceptanceSummaryPath);

    private static RewardEntrySnapshot[] CreateBaselineEntries()
    {
        return new[]
        {
            new RewardEntrySnapshot("gold", "gold", Dict(("amount", 35))),
            new RewardEntrySnapshot("consumable", "consumable", Dict(("item_id", "potion.minor_heal"))),
            new RewardEntrySnapshot("common_card_choice", "common_card_choice", Dict(("pool_id", "reward.common"), ("pick", 3))),
        };
    }

    private static Dictionary<string, object?> Dict(params (string Key, object? Value)[] items)
    {
        return items.ToDictionary(item => item.Key, item => item.Value, StringComparer.Ordinal);
    }

    private static int ReadInt(IReadOnlyDictionary<string, object?> config, string key)
    {
        return config.TryGetValue(key, out var raw) && raw is int value ? value : 0;
    }

    private static string ReadString(IReadOnlyDictionary<string, object?> config, string key)
    {
        return config.TryGetValue(key, out var raw) && raw is string value ? value : string.Empty;
    }
}
