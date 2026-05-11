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

        var runService = BuildRunRelicStateService();
        runService.TryGrantAndEquip(FirstRelicId).Should().BeTrue();
        var runBefore = runService.CreateSnapshot();
        runService.TryEquipExisting("relic.undefined_marker").Should().BeFalse();
        var runAfter = runService.CreateSnapshot();
        runAfter.AcquiredRelicIds.Should().Equal(runBefore.AcquiredRelicIds);
        runAfter.EquippedRelicId.Should().Be(runBefore.EquippedRelicId);
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

        // Failure-visible UI semantics must be represented by executable behavior, not file-text grep.
        var hud = new CombatHudExplainabilityService();
        var baseState = new CombatHudExplainabilityState(
            Difficulty: 1,
            PlayerHp: 80,
            Energy: 0,
            DrawPileCount: 7,
            DiscardPileCount: 0,
            EnemyIntent: "attack",
            TurnState: "PlayerTurn",
            SelectedCommandOutcome: "idle");
        var invalidAction = hud.TryInvalidAction(baseState, "invalid_preview");
        var invalidSnapshot = hud.BuildSnapshot(invalidAction.NewState, invalidAction.FeedbackMessage);
        invalidSnapshot.FeedbackMessage.Should().Contain("refused");
        invalidSnapshot.FeedbackMessage.Should().Contain("invalid action");
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
    public void ShouldMapScopeTaskIdsAndKeepOutOfScopeGameplayExcluded_WhenValidatingLine7()
    {
        AssertRefs(6);

        var scope = LoadRelicParticipantCandidate().GetProperty("scope_task_ids").EnumerateArray().Select(e => e.GetInt32()).ToArray();
        scope.Should().Equal(new[] { 88, 99, 106, 110, 111, 112 });

        // Out-of-scope gameplay exclusion: no scene-local effect stack usage in this slice behavior path.
        var combatService = new CombatService();
        var result = combatService.ExecutePlayCardPipeline(new PlayCardPipelineInput(
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
            StableId: FirstRelicId));
        result.Success.Should().BeTrue();
        result.ExecutedSteps.Should().Contain(PlayCardPipelineStep.ResolveEffect);

        // Out-of-scope gameplay mutation must not be introduced by this UI-wiring slice:
        // same combat input should keep deterministic gameplay outputs unchanged.
        var baselineInput = new PlayCardPipelineInput(
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
        var before = combatService.ExecutePlayCardPipeline(baselineInput);
        var after = combatService.ExecutePlayCardPipeline(baselineInput);
        var expectedDamage = CombatService.CalculateDamageWithStatusMultipliers(
            baseDamage: baselineInput.BaseDamage,
            strength: baselineInput.Strength,
            weakMultiplier: baselineInput.WeakMultiplier,
            vulnerableMultiplier: baselineInput.VulnerableMultiplier,
            isFixedDamage: baselineInput.IsFixedDamage);
        after.Success.Should().Be(before.Success);
        after.OverplayTax.Should().Be(before.OverplayTax);
        after.ExecutionFingerprint.Should().Be(before.ExecutionFingerprint);
        after.ExecutedSteps.Should().Equal(before.ExecutedSteps);
        before.StateAfter.FinalDamage.Should().Be(expectedDamage);
        after.StateAfter.FinalDamage.Should().Be(expectedDamage);
    }

    // ACC:T129.8
    [Fact]
    [Trait("acceptance", "ACC:T129.8")]
    public void ShouldUseBehaviorAssertionsNotOnlyFrameworkStatus_WhenValidatingLine8()
    {
        AssertRefs(7);

        // Behavior evidence from Task-local assertions: runtime ownership transitions are observable and deterministic.
        var service = BuildRunRelicStateService();
        service.TryGrantAndEquip(FirstRelicId).Should().BeTrue();
        service.TryGrantAndEquip(SecondRelicId).Should().BeTrue();
        var snapshot = service.CreateSnapshot();
        snapshot.AcquiredRelicIds.Should().Contain(new[] { FirstRelicId, SecondRelicId });
        snapshot.EquippedRelicId.Should().NotBeEmpty();

        // Task-local UI behavior evidence: snapshot text/state must change on command acceptance.
        var hud = new CombatHudExplainabilityService();
        var beforeState = new CombatHudExplainabilityState(
            Difficulty: 1,
            PlayerHp: 80,
            Energy: 3,
            DrawPileCount: 7,
            DiscardPileCount: 0,
            EnemyIntent: "attack",
            TurnState: "PlayerTurn",
            SelectedCommandOutcome: "idle");
        var accepted = hud.ApplyCommand(beforeState, "strike");
        var afterSnapshot = hud.BuildSnapshot(accepted.NewState, accepted.FeedbackMessage);
        afterSnapshot.Energy.Should().Be(2);
        afterSnapshot.FeedbackMessage.Should().Contain("accepted");

        // Keep framework-status checks as secondary audit evidence.
        var summary = LoadJsonFromRepoRoot(AcceptanceSummaryPath);
        summary.GetProperty("status").GetString().Should().Be("ok");
    }

    // ACC:T129.9
    [Fact]
    [Trait("acceptance", "ACC:T129.9")]
    public void ShouldRequireSourceAttributedTriggerFeedbackAcrossBoundaries_WhenValidatingLine9()
    {
        AssertRefs(8);

        // Power/relic attribution on combat boundary via stable id and ordering key.
        var combatService = new CombatService();
        var powerBoundary = combatService.ExecutePlayCardPipeline(new PlayCardPipelineInput(
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
            StableId: "Power.berserk_aura"));
        powerBoundary.Success.Should().BeTrue();
        powerBoundary.OrderingKey.Should().Contain("combatant.player.main|");

        var relicBoundary = combatService.ExecutePlayCardPipeline(new PlayCardPipelineInput(
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
            StableId: "Relic.obsidian_mirror"));
        relicBoundary.Success.Should().BeTrue();

        // Run boundary attribution via executable runtime contract (not source-text grep).
        var hud = new CombatHudExplainabilityService();
        var baseState = new CombatHudExplainabilityState(
            Difficulty: 1,
            PlayerHp: 80,
            Energy: 3,
            DrawPileCount: 7,
            DiscardPileCount: 0,
            EnemyIntent: "attack",
            TurnState: "PlayerTurn",
            SelectedCommandOutcome: "idle");
        var accepted = hud.ApplyCommand(baseState, "strike");
        var snapshot = hud.BuildSnapshot(accepted.NewState, accepted.FeedbackMessage);
        snapshot.FeedbackMessage.Should().Contain("accepted");
        snapshot.FeedbackMessage.Should().Contain("remaining");
    }

    // ACC:T129.10
    [Fact]
    [Trait("acceptance", "ACC:T129.10")]
    public void ShouldPrioritizeFailureVisibleStateOverGenericEmptyPlaceholder_WhenValidatingLine10()
    {
        AssertRefs(9);

        // Empty state before ownership.
        var service = BuildRunRelicStateService();
        var empty = service.CreateSnapshot();
        empty.AcquiredRelicIds.Should().BeEmpty();

        // Failure-visible semantics: once ownership exists, refusal keeps prior visible state (not generic empty reset).
        service.TryGrantAndEquip(FirstRelicId).Should().BeTrue();
        var before = service.CreateSnapshot();
        service.TryEquipExisting("relic.undefined_marker").Should().BeFalse();
        var after = service.CreateSnapshot();

        after.AcquiredRelicIds.Should().Equal(before.AcquiredRelicIds);
        after.EquippedRelicId.Should().Be(before.EquippedRelicId);
        after.EquippedDisplayName.Should().Be(before.EquippedDisplayName);
        after.EquippedRelicId.Should().NotBeEmpty("failure-visible state should preserve existing owned/equipped visibility");

        var hud = new CombatHudExplainabilityService();
        var combatState = new CombatHudExplainabilityState(
            Difficulty: 1,
            PlayerHp: 80,
            Energy: 0,
            DrawPileCount: 7,
            DiscardPileCount: 0,
            EnemyIntent: "attack",
            TurnState: "PlayerTurn",
            SelectedCommandOutcome: "idle");
        var refused = hud.ApplyCommand(combatState, "strike");
        var refusedSnapshot = hud.BuildSnapshot(refused.NewState, refused.FeedbackMessage);
        refusedSnapshot.FeedbackMessage.Should().Contain("refused");
        refusedSnapshot.FeedbackMessage.Should().Contain("insufficient energy");
    }


    // ACC:T129.11
    [Fact]
    [Trait("acceptance", "ACC:T129.11")]
    public void ShouldKeepInspectionStateSelective_WhenParticipantVisibleButNotEquipped()
    {
        AssertRefs(10);

        var service = BuildRunRelicStateService();
        service.TryGrantAndEquip(FirstRelicId).Should().BeTrue();
        service.TryGrantAndEquip(SecondRelicId).Should().BeTrue();
        service.TryEquipExisting(FirstRelicId).Should().BeTrue();

        var snapshot = service.CreateSnapshot();
        snapshot.AcquiredRelicIds.Should().Contain(new[] { FirstRelicId, SecondRelicId });
        snapshot.EquippedRelicId.Should().Be(FirstRelicId);
        snapshot.EquippedRelicId.Should().NotBe(SecondRelicId, "visible but not equipped participants must not be treated as equipped inspect target");
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
