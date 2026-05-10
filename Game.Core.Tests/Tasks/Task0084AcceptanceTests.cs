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

public sealed class Task0084AcceptanceTests
{
    private const string ThisTestRef = "Game.Core.Tests/Tasks/Task0084AcceptanceTests.cs";
    private const string CoreServiceRef = "Game.Core.Tests/Services/CardPoolSelectionTests.cs";
    private const string RewardSceneRef = "Tests.Godot/tests/Scenes/Reward/test_reward_scene_three_cards_rendered.gd";
    private const string RewardIntegrationRef = "Tests.Godot/tests/Integration/test_reward_first_entry_shared_pool_route.gd";
    private const string LegacyLockPersistRef = "Tests.Godot/tests/Integration/test_reward_offer_lock_persist_reenter.gd";
    private const string WorkflowSelectionSummaryRef = "logs/ci/<date>/single-task-light-lane-t84-t89/shards/shard-001-t84-89/summary.json";
    private const string StrictEvidenceEnvName = "TASK0084_GATE_EVIDENCE_REQUIRED";
    private const string PipelineTaskPrefix = "sc-review-pipeline-task-84";
    private static readonly string RepoRoot = ResolveRepoRoot();

    // acceptance: ACC:T84.1
    // ACC:T128.1
    [Fact]
    [Trait("acceptance", "ACC:T84.1")]
    public void ShouldBindFirstEntryThreeOfferGenerationToSharedPoolRefs_WhenValidatingT84AcceptanceLine1()
    {
        var (back, gameplay) = ReadTask84Views();
        AssertAcceptanceRefsContain(back, 0, CoreServiceRef, RewardSceneRef);
        AssertAcceptanceRefsContain(gameplay, 0, CoreServiceRef, RewardSceneRef);
        var preview = new OfferPreviewService()
            .PreviewSelection(act: 1, encounterType: "normal", seed: 8401, streamPosition: 0, pickCount: 3);
        preview.SelectedCardIds.Should().HaveCount(3);
        preview.SelectedCardIds.Should().OnlyContain(cardId => cardId.StartsWith("card.", StringComparison.Ordinal));
    }

    // acceptance: ACC:T84.2
    // ACC:T128.2
    [Fact]
    [Trait("acceptance", "ACC:T84.2")]
    public void ShouldBindDeterministicFirstEntryConstraintToPoolServiceRef_WhenValidatingT84AcceptanceLine2()
    {
        var (back, gameplay) = ReadTask84Views();
        AssertAcceptanceRefsContain(back, 1, CoreServiceRef);
        AssertAcceptanceRefsContain(gameplay, 1, CoreServiceRef);
        var service = new OfferPreviewService();
        var first = service.PreviewSelection(act: 1, encounterType: "elite", seed: 8420, streamPosition: 3, pickCount: 3);
        var second = service.PreviewSelection(act: 1, encounterType: "elite", seed: 8420, streamPosition: 3, pickCount: 3);
        second.SelectedCardIds.Should().Equal(first.SelectedCardIds);
    }

    // acceptance: ACC:T84.3
    // ACC:T128.3
    [Fact]
    [Trait("acceptance", "ACC:T84.3")]
    public void ShouldBindChapter6ScopeConstraintToTestRefsOnly_WhenValidatingT84AcceptanceLine3()
    {
        var (back, gameplay) = ReadTask84Views();
        AssertAcceptanceRefsContain(back, 2, CoreServiceRef, RewardSceneRef, ThisTestRef);
        AssertAcceptanceRefsContain(gameplay, 2, CoreServiceRef, RewardSceneRef, ThisTestRef);
        AssertScopeIsFirstEntryOnly(back.Acceptance[2], back.TestRefs);
        AssertScopeIsFirstEntryOnly(gameplay.Acceptance[2], gameplay.TestRefs);

        var firstEntryIntegrationCode = ReadRepoText(RewardIntegrationRef);
        firstEntryIntegrationCode.Should().Contain("test_first_entry_reward_offer_must_use_shared_pool_on_existing_route");
        firstEntryIntegrationCode.Should().Contain("test_first_entry_reward_offer_should_be_deterministic_across_independent_entries_for_same_context");
    }

    // acceptance: ACC:T84.4
    // ACC:T128.4
    [Fact]
    [Trait("acceptance", "ACC:T84.4")]
    public void ShouldBindInvalidPoolFallbackDeferralToRewardSceneRef_WhenValidatingT84AcceptanceLine4()
    {
        var (back, gameplay) = ReadTask84Views();
        AssertAcceptanceRefsContain(back, 3, RewardSceneRef, ThisTestRef);
        AssertAcceptanceRefsContain(gameplay, 3, RewardSceneRef, ThisTestRef);
        AssertFallbackDeferralContract(back.Acceptance[3]);
        AssertFallbackDeferralContract(gameplay.Acceptance[3]);

        var act = () => new OfferPreviewService()
            .PreviewSelection(act: 1, encounterType: "unknown-encounter", seed: 8440, streamPosition: 0, pickCount: 3);
        act.Should().Throw<ArgumentException>(
            "T84 scope defers invalid-pool fallback and should not claim fallback acceptance in this task.");

        var rewardSceneTestCode = ReadRepoText(RewardSceneRef);
        rewardSceneTestCode.Should().NotContain("# acceptance: ACC:T84.4",
            "ACC:T84.4 deferral is asserted by this task-level contract test, not by a first-entry scene flow test.");
    }

    // acceptance: ACC:T84.5
    // ACC:T128.5
    [Fact]
    [Trait("acceptance", "ACC:T84.5")]
    public void ShouldRequireWorkflowSelectionEvidenceBeforeImplementationEvidence_WhenValidatingT84AcceptanceLine5()
    {
        var (back, gameplay) = ReadTask84Views();
        AssertAcceptanceRefsContain(back, 4, CoreServiceRef, RewardSceneRef, ThisTestRef);
        AssertAcceptanceRefsContain(gameplay, 4, CoreServiceRef, RewardSceneRef, ThisTestRef);
        AssertEvidenceRefsContain(back, WorkflowSelectionSummaryRef);
        AssertEvidenceRefsContain(gameplay, WorkflowSelectionSummaryRef);

        if (!TryResolveLatestPipelineIndexPath(out var latestIndexPath, out var missingReason))
        {
            EnsurePipelineEvidenceOrSkip(missingReason);
            return;
        }

        var latestIndex = ReadJsonRoot(latestIndexPath);
        latestIndex.GetProperty("task_id").GetString().Should().Be("84");

        var summaryPath = latestIndex.GetProperty("summary_path").GetString();
        summaryPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(summaryPath!).Should().BeTrue("workflow selection guard must be verifiable from pipeline summary.");

        var runEventsPath = latestIndex.GetProperty("run_events_path").GetString();
        runEventsPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(runEventsPath!).Should().BeTrue("workflow selection guard must be verifiable from run-events.");

        var runEvents = ReadRunEvents(runEventsPath!);
        runEvents.Should().NotBeEmpty();
        HasSelectionEventBeforeImplementationEvidence(runEvents).Should().BeTrue(
            "workflow selection records must appear before implementation evidence events.");
    }

    // acceptance: ACC:T84.5
    // ACC:T128.6
    [Fact]
    [Trait("acceptance", "ACC:T84.5")]
    public void ShouldRejectWorkflowSelectionGuard_WhenSelectionEvidenceIsMissing()
    {
        if (!TryResolveLatestPipelineIndexPath(out var latestIndexPath, out var missingReason))
        {
            EnsurePipelineEvidenceOrSkip(missingReason);
            return;
        }

        var latestIndex = ReadJsonRoot(latestIndexPath);
        var runEventsPath = latestIndex.GetProperty("run_events_path").GetString();
        runEventsPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(runEventsPath!).Should().BeTrue();

        var runEvents = ReadRunEvents(runEventsPath!);
        var withoutSelection = runEvents.Where(record => !IsSelectionEvent(record)).ToArray();
        withoutSelection.Should().NotBeEmpty("negative case should keep implementation evidence events.");
        withoutSelection.Any(IsImplementationEvidenceEvent).Should().BeTrue();

        HasSelectionEventBeforeImplementationEvidence(withoutSelection).Should().BeFalse(
            "without workflow-selection events, acceptance line 5 guard must fail.");
    }

    // acceptance: ACC:T84.6
    // ACC:T128.7
    [Fact]
    [Trait("acceptance", "ACC:T84.6")]
    public void ShouldBindSceneAndIntegrationCoverageForFirstEntryOfferGeneration_WhenValidatingT84AcceptanceLine6()
    {
        var (back, gameplay) = ReadTask84Views();
        AssertAcceptanceRefsContain(back, 5, RewardSceneRef, RewardIntegrationRef);
        AssertAcceptanceRefsContain(gameplay, 5, RewardSceneRef, RewardIntegrationRef);
        var integrationCode = ReadRepoText(RewardIntegrationRef);
        integrationCode.Should().Contain("test_first_entry_reward_offer_must_use_shared_pool_on_existing_route", "integration coverage must target first-entry shared pool route.");
        integrationCode.Should().Contain("test_first_entry_reward_offer_should_be_deterministic_across_independent_entries_for_same_context");
        integrationCode.Should().Contain("GetRewardOfferSnapshotForScene");
        integrationCode.Should().Contain("shared-card-pool");
    }

    // acceptance: ACC:T84.7
    // ACC:T128.8
    [Fact]
    [Trait("acceptance", "ACC:T84.7")]
    public void ShouldBindSharedPoolOwnerConstraintToCoreAndSceneRefs_WhenValidatingT84AcceptanceLine7()
    {
        var (back, gameplay) = ReadTask84Views();
        AssertAcceptanceRefsContain(back, 6, CoreServiceRef, RewardSceneRef);
        AssertAcceptanceRefsContain(gameplay, 6, CoreServiceRef, RewardSceneRef);
        var previewService = new OfferPreviewService();
        var normal = previewService.PreviewSelection(act: 1, encounterType: "normal", seed: 8470, streamPosition: 0, pickCount: 3);
        var elite = previewService.PreviewSelection(act: 1, encounterType: "elite", seed: 8470, streamPosition: 0, pickCount: 3);
        normal.SelectedCardIds.Should().HaveCount(3);
        elite.SelectedCardIds.Should().HaveCount(3);
        normal.SelectedCardIds.Should().NotEqual(elite.SelectedCardIds,
            "owner path must be context-driven and should not synthesize one fixed alternate offer set.");
    }

    private static (ViewTask back, ViewTask gameplay) ReadTask84Views()
    {
        var back = ReadTask84FromView(Path.Combine(RepoRoot, ".taskmaster", "tasks", "tasks_back.json"));
        var gameplay = ReadTask84FromView(Path.Combine(RepoRoot, ".taskmaster", "tasks", "tasks_gameplay.json"));
        back.TestRefs.Should().Contain(ThisTestRef);
        gameplay.TestRefs.Should().Contain(ThisTestRef);
        return (back, gameplay);
    }

    private static ViewTask ReadTask84FromView(string viewPath)
    {
        File.Exists(viewPath).Should().BeTrue($"missing task view file: {viewPath}");
        using var doc = JsonDocument.Parse(File.ReadAllText(viewPath));
        var task = doc.RootElement
            .EnumerateArray()
            .FirstOrDefault(item => item.TryGetProperty("taskmaster_id", out var taskId) && taskId.GetInt32() == 84);
        task.ValueKind.Should().NotBe(JsonValueKind.Undefined, $"taskmaster_id=84 must exist in {viewPath}");
        var acceptance = task.GetProperty("acceptance").EnumerateArray().Select(item => item.GetString() ?? string.Empty).ToArray();
        var testRefs = task.GetProperty("test_refs").EnumerateArray().Select(item => item.GetString() ?? string.Empty).ToArray();
        var evidenceRefs = task.TryGetProperty("evidence_refs", out var evidenceRefsElement) && evidenceRefsElement.ValueKind == JsonValueKind.Array
            ? evidenceRefsElement.EnumerateArray().Select(item => item.GetString() ?? string.Empty).ToArray()
            : Array.Empty<string>();
        return new ViewTask(acceptance, testRefs, evidenceRefs);
    }

    private static void AssertAcceptanceRefsContain(ViewTask task, int acceptanceIndex, params string[] expectedRefs)
    {
        task.Acceptance.Length.Should().BeGreaterThan(acceptanceIndex);
        var line = task.Acceptance[acceptanceIndex];
        line.Should().Contain("Refs:");
        foreach (var expected in expectedRefs)
        {
            line.Should().Contain(expected);
            task.TestRefs.Should().Contain(expected);
        }
    }

    private static void AssertEvidenceRefsContain(ViewTask task, params string[] expectedRefs)
    {
        foreach (var expected in expectedRefs)
        {
            task.EvidenceRefs.Should().Contain(expected);
        }
    }

    private static void AssertScopeIsFirstEntryOnly(string acceptanceLine, string[] testRefs)
    {
        acceptanceLine.Should().Contain("first-entry offer generation only");
        acceptanceLine.Should().Contain("out of scope");
        acceptanceLine.Should().NotContain(LegacyLockPersistRef, "scope line must not bind re-entry lock persistence as T84 criteria.");
        testRefs.Should().NotContain(LegacyLockPersistRef, "T84 acceptance scope excludes re-entry/failure-handling evidence.");
    }

    private static void AssertFallbackDeferralContract(string acceptanceLine)
    {
        acceptanceLine.Should().Contain("deferred");
        acceptanceLine.Should().Contain("must not require, implement, or claim acceptance");
    }

    private static bool TryResolveLatestPipelineIndexPath(out string latestIndexPath, out string reason)
    {
        var ciRoot = Path.Combine(RepoRoot, "logs", "ci");
        if (!Directory.Exists(ciRoot))
        {
            latestIndexPath = string.Empty;
            reason = $"missing logs/ci root: {ciRoot}";
            return false;
        }

        latestIndexPath = Directory
            .EnumerateFiles(ciRoot, "latest.json", SearchOption.AllDirectories)
            .Where(path => path.Contains(PipelineTaskPrefix, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(path => File.GetLastWriteTimeUtc(path))
            .FirstOrDefault() ?? string.Empty;

        if (string.IsNullOrWhiteSpace(latestIndexPath))
        {
            reason = $"missing pipeline latest.json for task 84 under logs/ci/<date>/{PipelineTaskPrefix}*/latest.json";
            return false;
        }

        reason = string.Empty;
        return true;
    }

    private static void EnsurePipelineEvidenceOrSkip(string reason)
    {
        if (!ShouldRequirePipelineEvidence())
        {
            return;
        }

        throw new Xunit.Sdk.XunitException(
            "Task0084 pipeline evidence is required but missing. "
            + reason
            + " Set TASK0084_GATE_EVIDENCE_REQUIRED=0 (or unset) to suppress in CI/non-Task84 runs.");
    }

    private static bool ShouldRequirePipelineEvidence()
    {
        var raw = Environment.GetEnvironmentVariable(StrictEvidenceEnvName);
        if (string.IsNullOrWhiteSpace(raw))
        {
            return false;
        }

        return raw.Equals("1", StringComparison.OrdinalIgnoreCase)
               || raw.Equals("true", StringComparison.OrdinalIgnoreCase)
               || raw.Equals("yes", StringComparison.OrdinalIgnoreCase)
               || raw.Equals("on", StringComparison.OrdinalIgnoreCase);
    }

    private static JsonElement ReadJsonRoot(string path)
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(path));
        return doc.RootElement.Clone();
    }

    private static IReadOnlyList<RunEventRecord> ReadRunEvents(string runEventsPath)
    {
        var records = new List<RunEventRecord>();
        foreach (var rawLine in File.ReadAllLines(runEventsPath))
        {
            var line = rawLine.Trim();
            if (string.IsNullOrWhiteSpace(line))
            {
                continue;
            }

            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            if (!root.TryGetProperty("ts", out var tsNode) || tsNode.ValueKind != JsonValueKind.String)
            {
                continue;
            }

            var timestamp = DateTimeOffset.Parse(tsNode.GetString()!, CultureInfo.InvariantCulture);
            records.Add(new RunEventRecord(
                timestamp,
                root.TryGetProperty("event_family", out var familyNode) ? familyNode.GetString() ?? string.Empty : string.Empty,
                root.TryGetProperty("event", out var eventNode) ? eventNode.GetString() ?? string.Empty : string.Empty,
                root.TryGetProperty("step_name", out var stepNode) ? stepNode.GetString() ?? string.Empty : string.Empty));
        }

        return records;
    }

    private static bool HasSelectionEventBeforeImplementationEvidence(IEnumerable<RunEventRecord> runEvents)
    {
        var ordered = runEvents.OrderBy(record => record.Timestamp).ToArray();
        var selection = ordered.FirstOrDefault(IsSelectionEvent);
        var implementation = ordered.FirstOrDefault(IsImplementationEvidenceEvent);

        if (selection is null || implementation is null)
        {
            return false;
        }

        return selection.Timestamp <= implementation.Timestamp;
    }

    private static bool IsSelectionEvent(RunEventRecord record)
    {
        if (!string.Equals(record.EventFamily, "run", StringComparison.Ordinal))
        {
            return false;
        }

        return string.Equals(record.EventName, "run_forked", StringComparison.Ordinal)
               || string.Equals(record.EventName, "run_resumed", StringComparison.Ordinal)
               || string.Equals(record.EventName, "run_started", StringComparison.Ordinal);
    }

    private static bool IsImplementationEvidenceEvent(RunEventRecord record)
    {
        if (!string.Equals(record.EventFamily, "step", StringComparison.Ordinal))
        {
            return false;
        }

        if (!string.Equals(record.EventName, "step_completed", StringComparison.Ordinal))
        {
            return false;
        }

        return string.Equals(record.StepName, "sc-test", StringComparison.Ordinal)
               || string.Equals(record.StepName, "sc-acceptance-check", StringComparison.Ordinal)
               || string.Equals(record.StepName, "sc-llm-review", StringComparison.Ordinal);
    }

    private static string ReadRepoText(string relativePath)
    {
        var fullPath = Path.Combine(RepoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(fullPath).Should().BeTrue($"missing file: {relativePath}");
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

        throw new DirectoryNotFoundException("Could not locate repository root from AppContext.BaseDirectory.");
    }

    private sealed record ViewTask(string[] Acceptance, string[] TestRefs, string[] EvidenceRefs);

    private sealed record RunEventRecord(
        DateTimeOffset Timestamp,
        string EventFamily,
        string EventName,
        string StepName);
}
