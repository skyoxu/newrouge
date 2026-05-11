using FluentAssertions;
using Game.Core.Contracts.Combat;
using Game.Core.Domain;
using Game.Core.Services;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0129AcceptanceTests
{
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string CandidatesPath = "docs/gdd/ui-gdd-flow.candidates.json";
    private const string AcceptanceSummaryPath = "logs/ci/2026-05-11/sc-acceptance-check-task-129/summary.json";
    private const string CombatUiBindingsGdPath = "Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd";
    private const string ThisTestRef = "Game.Core.Tests/Tasks/Task0129AcceptanceTests.cs";

    private const string FirstRelicId = "relic.ashen_hourglass";
    private const string SecondRelicId = "relic.obsidian_mirror";
    private static readonly IReadOnlySet<string> KnownRelicIds = StartingRelicService.Definitions
        .Select(definition => definition.RelicId)
        .ToHashSet(StringComparer.Ordinal);

    // ACC:T129.1
    [Fact]
    [Trait("acceptance", "ACC:T129.1")]
    public void ShouldExposeRelicParticipantOwnership_WhenValidatingLine1()
    {
        AssertRefs(0);

        var service = BuildRunRelicStateService();
        var granted = service.TryGrantAndEquip(FirstRelicId);
        var snapshot = service.CreateSnapshot();

        granted.Should().BeTrue();
        snapshot.AcquiredRelicIds.Should().Contain(FirstRelicId);
        snapshot.EquippedRelicId.Should().Be(FirstRelicId);

        var candidate = LoadRelicParticipantCandidate();
        GetStringArray(candidate, "suggested_standalone_surfaces")
            .Should().Contain(new[] { "RelicTray", "ParticipantStatusPanel", "TriggerFeedbackPanel" });
    }

    // ACC:T129.2
    [Fact]
    [Trait("acceptance", "ACC:T129.2")]
    public void ShouldRequireAllStandaloneSurfaces_WhenValidatingLine2()
    {
        AssertRefs(1);
        var surfaces = GetStringArray(LoadRelicParticipantCandidate(), "suggested_standalone_surfaces");
        surfaces.Should().Contain(new[] { "RelicTray", "ParticipantStatusPanel", "TriggerFeedbackPanel" });
        surfaces.Distinct(StringComparer.Ordinal).Count().Should().Be(3);
    }

    // ACC:T129.3
    [Fact]
    [Trait("acceptance", "ACC:T129.3")]
    public void ShouldExposeCombatAndRunBoundaryOutcomes_WhenValidatingLine3()
    {
        AssertRefs(2);

        var combatService = new CombatService();
        var input = new PlayCardPipelineInput(
            DifficultyId: 10,
            CardsPlayedThisTurn: 1,
            OverplayTriggerN: 3,
            OverplayTaxPerCard: 1,
            BaseCardCost: 1,
            EnergyBefore: 3,
            BaseDamage: 8,
            Strength: 2,
            WeakMultiplier: 1.0,
            VulnerableMultiplier: 1.0,
            IsFixedDamage: false,
            CombatantId: "combatant.player.main",
            StableId: FirstRelicId);

        var combatResult = combatService.ExecutePlayCardPipeline(input);
        var runSnapshot = BuildRunRelicStateService().CreateSnapshot();

        combatResult.Success.Should().BeTrue();
        combatResult.OrderingKey.Should().StartWith("combatant.player.main|");
        runSnapshot.AcquiredRelicIds.Should().BeEmpty("run boundary starts with empty ownership until acquisition");
    }

    // ACC:T129.4
    [Fact]
    [Trait("acceptance", "ACC:T129.4")]
    public void ShouldShowEmptyStateBeforeOwnership_WhenValidatingLine4()
    {
        AssertRefs(3);

        var service = BuildRunRelicStateService();
        var snapshot = service.CreateSnapshot();

        snapshot.AcquiredRelicIds.Should().BeEmpty();
        snapshot.EquippedRelicId.Should().BeEmpty();
        snapshot.EquippedDisplayName.Should().BeEmpty();
    }

    // ACC:T129.5
    [Fact]
    [Trait("acceptance", "ACC:T129.5")]
    public void ShouldKeepStateStableOnFailurePaths_WhenValidatingLine5()
    {
        AssertRefs(4);

        var service = BuildRunRelicStateService();
        service.TryGrantAndEquip(FirstRelicId).Should().BeTrue();

        var before = service.CreateSnapshot();
        var duplicateGrant = service.TryGrantAndEquip(FirstRelicId);
        var unknownEquip = service.TryEquipExisting("relic.undefined_marker");
        var after = service.CreateSnapshot();

        duplicateGrant.Should().BeFalse();
        unknownEquip.Should().BeFalse();
        after.AcquiredRelicIds.Should().Equal(before.AcquiredRelicIds);
        after.EquippedRelicId.Should().Be(before.EquippedRelicId);
    }

    // ACC:T129.6
    [Fact]
    [Trait("acceptance", "ACC:T129.6")]
    public void ShouldAllowInspectingEquippedAndTriggerRelevantState_WhenValidatingLine6()
    {
        AssertRefs(5);

        var service = BuildRunRelicStateService();
        service.TryGrantAndEquip(FirstRelicId).Should().BeTrue();
        service.TryGrantAndEquip(SecondRelicId).Should().BeTrue();
        service.TryEquipExisting(SecondRelicId).Should().BeTrue();

        var snapshot = service.CreateSnapshot();
        snapshot.AcquiredRelicIds.Should().Contain(new[] { FirstRelicId, SecondRelicId });
        snapshot.EquippedRelicId.Should().Be(SecondRelicId);
        snapshot.EquippedDisplayName.Should().Be($"name::{SecondRelicId}");
    }

    // ACC:T129.7
    [Fact]
    [Trait("acceptance", "ACC:T129.7")]
    public void ShouldMapScopeTaskIdsAndGdUnitAnchors_WhenValidatingLine7()
    {
        AssertRefs(6);

        var scope = LoadRelicParticipantCandidate().GetProperty("scope_task_ids").EnumerateArray().Select(e => e.GetInt32()).ToArray();
        scope.Should().Equal(new[] { 88, 99, 106, 110, 111, 112 });

        var accBack = LoadAcceptanceLines(TasksBackPath, 129);
        accBack.Should().Contain(line => line.StartsWith("ACC:T129.7", StringComparison.Ordinal));
        accBack.Should().Contain(line => line.Contains("Out-of-scope gameplay changes", StringComparison.OrdinalIgnoreCase));

        var gd = LoadTextFromRepoRoot(CombatUiBindingsGdPath);
        gd.Should().Contain("ACC:T106.1");
        gd.Should().Contain("ACC:T106.2");
        gd.Should().Contain("ACC:T106.4");
        gd.Should().Contain("test_t106_power_and_relic_participants_are_visible_and_inspectable_without_scene_local_stack");
        gd.Should().Contain("GetVisiblePowerIdsForTest");
        gd.Should().Contain("GetVisibleRelicIdsForTest");
        gd.Should().Contain("HasPowerRelicSurfaceForTest");
    }

    // ACC:T129.8
    [Fact]
    [Trait("acceptance", "ACC:T129.8")]
    public void ShouldExposeAuditableXUnitAndGdUnitStatus_WhenValidatingLine8()
    {
        AssertRefs(7);

        var summary = LoadJsonFromRepoRoot(AcceptanceSummaryPath);

        var accGameplay = LoadAcceptanceLines(TasksGameplayPath, 129);
        accGameplay.Should().Contain(line => line.StartsWith("ACC:T129.8", StringComparison.Ordinal));
        accGameplay.Should().Contain(line => line.Contains("behavior assertions tied to this slice", StringComparison.OrdinalIgnoreCase));
        summary.GetProperty("status").GetString().Should().Be("ok");

        var testQuality = summary
            .GetProperty("steps")
            .EnumerateArray()
            .First(step => string.Equals(step.GetProperty("name").GetString(), "test-quality", StringComparison.Ordinal))
            .GetProperty("details");
        var gdunit = testQuality.GetProperty("gdunit");
        gdunit.GetProperty("tests_scanned").GetInt32().Should().BeGreaterThan(0);
        gdunit.GetProperty("behavior_tests_total").GetInt32().Should().BeGreaterThan(0);

        var unit = summary.GetProperty("metrics").GetProperty("unit").GetProperty("tests");
        unit.GetProperty("passed").GetInt32().Should().BeGreaterThan(0);
        unit.GetProperty("failed").GetInt32().Should().Be(0);

        var taskRefsBack = LoadTaskTestRefs(TasksBackPath, 129);
        var taskRefsGameplay = LoadTaskTestRefs(TasksGameplayPath, 129);
        taskRefsBack.Should().Contain(item => item.EndsWith("test_combat_scene_ui_bindings.gd", StringComparison.OrdinalIgnoreCase));
        taskRefsGameplay.Should().Contain(item => item.EndsWith("test_combat_scene_ui_bindings.gd", StringComparison.OrdinalIgnoreCase));

    }

    
    // ACC:T129.9
    [Fact]
    [Trait("acceptance", "ACC:T129.9")]
    public void ShouldRequireSourceAttributedTriggerFeedbackAcrossBoundaries_WhenValidatingLine9()
    {
        AssertRefs(8);

        var gd = LoadTextFromRepoRoot(CombatUiBindingsGdPath);
        gd.Should().Contain("Power.berserk_aura");
        gd.Should().Contain("Relic.obsidian_mirror");
        gd.Should().Contain("WasPotionRuntimeClosureExecutedForTest");

        var candidate = LoadRelicParticipantCandidate();
        var response = candidate.GetProperty("system_response").GetString() ?? string.Empty;
        response.Should().Contain("trigger outcomes").And.Contain("combat-boundary").And.Contain("run-boundary");
    }

    // ACC:T129.10
    [Fact]
    [Trait("acceptance", "ACC:T129.10")]
    public void ShouldPrioritizeFailureVisibleStateOverGenericEmptyPlaceholder_WhenValidatingLine10()
    {
        AssertRefs(9);

        var service = BuildRunRelicStateService();
        var empty = service.CreateSnapshot();
        empty.AcquiredRelicIds.Should().BeEmpty();

        service.TryGrantAndEquip(FirstRelicId).Should().BeTrue();
        var before = service.CreateSnapshot();
        var refusal = service.TryEquipExisting("relic.undefined_marker");
        refusal.Should().BeFalse();
        var after = service.CreateSnapshot();

        after.AcquiredRelicIds.Should().Equal(before.AcquiredRelicIds);
        after.EquippedRelicId.Should().Be(before.EquippedRelicId);
        after.EquippedDisplayName.Should().Be(before.EquippedDisplayName);
    }

private static RunRelicStateService BuildRunRelicStateService()
    {
        var inventory = new Inventory();
        var inventoryService = new InventoryService(inventory, maxSlots: 10);
        return new RunRelicStateService(
            inventoryService,
            id => $"name::{id}",
            validRelicIdSet: KnownRelicIds);
    }

    private static void AssertRefs(int acceptanceIndex)
    {
        TaskAcceptanceRefAssertions.AssertAcceptanceRefsContain(TasksBackPath, 129, acceptanceIndex, ThisTestRef);
        TaskAcceptanceRefAssertions.AssertAcceptanceRefsContain(TasksGameplayPath, 129, acceptanceIndex, ThisTestRef);
    }

    private static JsonElement LoadRelicParticipantCandidate()
    {
        var root = LoadJsonFromRepoRoot(CandidatesPath);
        foreach (var candidate in root.GetProperty("candidates").EnumerateArray())
        {
            var bucket = candidate.GetProperty("bucket").GetString() ?? string.Empty;
            if (string.Equals(bucket, "relic_participants", StringComparison.Ordinal))
            {
                return candidate;
            }
        }

        throw new Xunit.Sdk.XunitException("relic_participants candidate not found.");
    }

    private static List<string> GetStringArray(JsonElement parent, string propertyName)
    {
        return parent.GetProperty(propertyName).EnumerateArray().Select(e => e.GetString() ?? string.Empty).ToList();
    }

    
    private static string[] LoadTaskTestRefs(string taskFilePath, int taskmasterId)
    {
        var root = LoadJsonFromRepoRoot(taskFilePath);
        var best = Array.Empty<string>();
        foreach (var task in root.EnumerateArray())
        {
            if (!TaskAcceptanceRefAssertions.TryReadTaskmasterIdForTask(task, out var parsedId) || parsedId != taskmasterId)
            {
                continue;
            }

            if (!task.TryGetProperty("test_refs", out var refsElement) || refsElement.ValueKind != JsonValueKind.Array)
            {
                continue;
            }

            var refs = refsElement.EnumerateArray().Select(e => e.GetString() ?? string.Empty).ToArray();
            if (refs.Length > best.Length)
            {
                best = refs;
            }
        }

        return best;
    }

private static string[] LoadAcceptanceLines(string taskFilePath, int taskmasterId)
    {
        var root = LoadJsonFromRepoRoot(taskFilePath);
        foreach (var task in root.EnumerateArray())
        {
            if (!TaskAcceptanceRefAssertions.TryReadTaskmasterIdForTask(task, out var parsedId) || parsedId != taskmasterId)
            {
                continue;
            }

            if (!task.TryGetProperty("acceptance", out var acceptanceElement) || acceptanceElement.ValueKind != JsonValueKind.Array)
            {
                return Array.Empty<string>();
            }

            return acceptanceElement.EnumerateArray().Select(e => e.GetString() ?? string.Empty).ToArray();
        }

        return Array.Empty<string>();
    }

private static string LoadTextFromRepoRoot(string repoRelativePath)
    {
        var path = ResolveFromRepoRoot(repoRelativePath);
        File.Exists(path).Should().BeTrue($"expected file: {path}");
        return File.ReadAllText(path);
    }

    private static JsonElement LoadJsonFromRepoRoot(string repoRelativePath)
    {
        var path = ResolveFromRepoRoot(repoRelativePath);
        File.Exists(path).Should().BeTrue($"expected file: {path}");
        using var doc = JsonDocument.Parse(File.ReadAllText(path));
        return doc.RootElement.Clone();
    }

    private static string ResolveFromRepoRoot(string repoRelativePath)
    {
        var current = new DirectoryInfo(Directory.GetCurrentDirectory());
        while (current is not null)
        {
            var candidate = Path.Combine(current.FullName, repoRelativePath.Replace('/', Path.DirectorySeparatorChar));
            if (File.Exists(candidate))
            {
                return candidate;
            }

            current = current.Parent;
        }

        return repoRelativePath;
    }
}

internal static class TaskAcceptanceRefAssertions
{
    public static void AssertAcceptanceRefsContain(string taskFilePath, int taskmasterId, int acceptanceIndex, string expectedRef)
    {
        var absolutePath = ResolveFromRepoRoot(taskFilePath);
        File.Exists(absolutePath).Should().BeTrue($"task file should exist: {absolutePath}");

        var json = File.ReadAllText(absolutePath);
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        foreach (var task in root.EnumerateArray())
        {
            if (!TaskAcceptanceRefAssertions.TryReadTaskmasterIdForTask(task, out var parsedId) || parsedId != taskmasterId)
            {
                continue;
            }

            var acceptance = task.GetProperty("acceptance");
            var line = acceptance[acceptanceIndex].GetString() ?? string.Empty;
            line.Should().Contain(expectedRef);
            return;
        }

        throw new Xunit.Sdk.XunitException($"Task {taskmasterId} not found in {absolutePath}.");
    }

    internal static bool TryReadTaskmasterIdForTask(JsonElement task, out int taskmasterId)
    {
        taskmasterId = 0;
        if (!task.TryGetProperty("taskmaster_id", out var idElement))
        {
            return false;
        }

        if (idElement.ValueKind == JsonValueKind.Number)
        {
            return idElement.TryGetInt32(out taskmasterId);
        }

        if (idElement.ValueKind == JsonValueKind.String)
        {
            return int.TryParse(idElement.GetString(), NumberStyles.Integer, CultureInfo.InvariantCulture, out taskmasterId);
        }

        return false;
    }

    private static string ResolveFromRepoRoot(string repoRelativePath)
    {
        var current = new DirectoryInfo(Directory.GetCurrentDirectory());
        while (current is not null)
        {
            var candidate = Path.Combine(current.FullName, repoRelativePath.Replace('/', Path.DirectorySeparatorChar));
            if (File.Exists(candidate))
            {
                return candidate;
            }

            current = current.Parent;
        }

        return repoRelativePath;
    }
}
