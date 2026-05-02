using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Contracts.Combat;
using Game.Core.Contracts.Status;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0096AcceptanceTests
{
    private const int TaskmasterId = 96;
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0096AcceptanceTests.cs";
    private const string WorkflowSelectionTestRef = "Game.Core.Tests/Tasks/Task0096WorkflowSelectionEvidenceTests.cs";
    private const string CombatSceneTestRef = "Tests.Godot/tests/Scenes/Combat/test_task0096_rage_runtime_bridge.gd";

    // ACC:T96.1
    [Fact]
    [Trait("acceptance", "ACC:T96.1")]
    public void ShouldCreateRageInSharedRuntimeContainer_WhenWarriorFlowAppliesRage()
    {
        var statusService = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);

        statusService.TryApplyRage(statuses, stacks: 2, sourceId: "card.warrior.rage_surge").Should().BeTrue();
        statusService.TryApplyRage(statuses, stacks: 1, sourceId: "card.warrior.bloodrush").Should().BeTrue();

        statuses.Keys.Should().Contain(StatusOperations.RageStatusId);
        statuses.Count(entry => string.Equals(entry.Key, StatusOperations.RageStatusId, StringComparison.Ordinal)).Should().Be(1);
        statusService.GetRageStacks(statuses).Should().Be(3);
    }

    // ACC:T96.2
    [Fact]
    [Trait("acceptance", "ACC:T96.2")]
    public void ShouldUseExistingCombatAndPlayerContracts_WhenRageIsApplied()
    {
        var statusService = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal)
        {
            [StatusOperations.RageStatusId] = new StatusInstance(
                StableId: "stable.status.rage",
                StatusId: StatusOperations.RageStatusId,
                StatusType: StatusType.Buff,
                Stacks: 2,
                DurationTurns: 0,
                SourceId: "card.warrior.rage_surge",
                ExpiresTiming: ExpiresTiming.Never,
                Strength: 0)
        };

        statusService.TryApplyRage(statuses, stacks: 1, sourceId: "card.warrior.bloodrush").Should().BeTrue();
        var rage = statuses[StatusOperations.RageStatusId];

        rage.StatusId.Should().Be(StatusOperations.RageStatusId);
        rage.StatusType.Should().Be(StatusType.Buff);
        rage.ExpiresTiming.Should().Be(ExpiresTiming.Never);
        rage.Stacks.Should().Be(3);
        statuses.Keys.Should().OnlyContain(key => string.Equals(key, StatusOperations.RageStatusId, StringComparison.Ordinal));
        statuses.Should().HaveCount(1, "existing shared-runtime Rage entry must be consumed/mutated, not forked into parallel copy");
    }

    // ACC:T96.3
    [Fact]
    [Trait("acceptance", "ACC:T96.3")]
    public void ShouldKeepCombatSceneCoverageReference_WhenRuntimeRageNeedsPlayerVisibleEvidence()
    {
        var taskBack = ReadTaskNode(TasksBackPath, TaskmasterId);
        var taskGameplay = ReadTaskNode(TasksGameplayPath, TaskmasterId);

        ReadStringArray(taskBack, "test_refs").Should().Contain(CombatSceneTestRef);
        ReadStringArray(taskGameplay, "test_refs").Should().Contain(CombatSceneTestRef);
        File.Exists(Path.Combine(FindRepositoryRoot(), CombatSceneTestRef.Replace('/', Path.DirectorySeparatorChar))).Should().BeTrue();
    }

    // ACC:T96.4
    [Fact]
    [Trait("acceptance", "ACC:T96.4")]
    public void ShouldPersistRageAcrossWarriorFlowSegments_WhenCombatStillActive()
    {
        var statusService = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);

        statusService.TryApplyRage(statuses, stacks: 2, sourceId: "card.warrior.rage_surge").Should().BeTrue();
        statusService.TryApplyRage(statuses, stacks: 1, sourceId: "card.warrior.bloodrush").Should().BeTrue();

        statusService.GetRageStacks(statuses).Should().Be(3);
        statusService.ProcessTurnPhase(statuses, ExpiresTiming.OwnerEndOfTurnCleanup);
        statusService.GetRageStacks(statuses).Should().Be(3);
    }

    // ACC:T96.5
    [Fact]
    [Trait("acceptance", "ACC:T96.5")]
    public void ShouldKeepBothWarriorAndSceneTestFamiliesInTaskEvidence_WhenValidatingAcceptanceRefs()
    {
        var taskBack = ReadTaskNode(TasksBackPath, TaskmasterId);
        var taskGameplay = ReadTaskNode(TasksGameplayPath, TaskmasterId);

        var backRefs = ReadStringArray(taskBack, "test_refs");
        var gameplayRefs = ReadStringArray(taskGameplay, "test_refs");

        backRefs.Should().Contain(ThisTaskTestRef);
        backRefs.Should().Contain(CombatSceneTestRef);
        gameplayRefs.Should().Contain(ThisTaskTestRef);
        gameplayRefs.Should().Contain(CombatSceneTestRef);
    }

    // ACC:T96.6
    [Fact]
    [Trait("acceptance", "ACC:T96.6")]
    public void ShouldApplyRageThroughSharedRuntimeService_WhenWarriorActionsExecute()
    {
        var combatService = new CombatService();
        var statusService = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);

        statusService.TryApplyRage(statuses, stacks: 0, sourceId: "card.warrior.rage_surge").Should().BeFalse();
        statusService.TryApplyRage(statuses, stacks: 2, sourceId: "card.warrior.rage_surge").Should().BeTrue();

        var result = combatService.PlayCard(NewPipelineInput(rageStacks: statusService.GetRageStacks(statuses)));
        statusService.GetRageStacks(statuses).Should().Be(2);
        result.Success.Should().BeTrue();
        result.StateAfter.FinalDamage.Should().BeGreaterThan(result.StateBefore.FinalDamage);
    }

    // ACC:T96.7
    [Fact]
    [Trait("acceptance", "ACC:T96.7")]
    public void ShouldChangeCombatResultWhenRageAppliedThroughSharedRuntime_WhenDamagePipelineRuns()
    {
        var statusService = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);
        var pipeline = new PlayCardResolutionPipeline();

        var baseline = pipeline.Execute(NewPipelineInput(rageStacks: statusService.GetRageStacks(statuses)));

        statusService.TryApplyRage(statuses, stacks: 3, sourceId: "card.warrior.rage_surge").Should().BeTrue();
        var boosted = pipeline.Execute(NewPipelineInput(rageStacks: statusService.GetRageStacks(statuses)));

        boosted.StateAfter.FinalDamage.Should().BeGreaterThan(baseline.StateAfter.FinalDamage);
    }

    // ACC:T96.9
    [Fact]
    [Trait("acceptance", "ACC:T96.9")]
    public void ShouldMutateSameRageEntry_WhenSharedRuntimeAlreadyContainsRage()
    {
        var statusService = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal)
        {
            [StatusOperations.RageStatusId] = new StatusInstance(
                StableId: "stable.status.rage",
                StatusId: StatusOperations.RageStatusId,
                StatusType: StatusType.Buff,
                Stacks: 2,
                DurationTurns: 0,
                SourceId: "card.warrior.rage_surge",
                ExpiresTiming: ExpiresTiming.Never,
                Strength: 0)
        };

        statusService.TryApplyRage(statuses, stacks: 3, sourceId: "card.warrior.battlecry").Should().BeTrue();
        statuses.Should().HaveCount(1);
        statusService.GetRageStacks(statuses).Should().Be(5);
    }

    // ACC:T96.10
    [Fact]
    [Trait("acceptance", "ACC:T96.10")]
    public void ShouldVerifyRageThroughCombatServiceEntryPath_WhenLiveLoopUsesService()
    {
        var statusService = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);
        var combatService = new CombatService();

        statusService.TryApplyRage(statuses, stacks: 2, sourceId: "card.warrior.rage_surge").Should().BeTrue();
        var input = NewPipelineInput(rageStacks: statusService.GetRageStacks(statuses));

        var serviceResult = combatService.PlayCard(input);
        var directResult = new PlayCardResolutionPipeline().Execute(input);

        serviceResult.Success.Should().BeTrue();
        serviceResult.StateAfter.FinalDamage.Should().Be(directResult.StateAfter.FinalDamage);
        serviceResult.ExecutionFingerprint.Should().Be(directResult.ExecutionFingerprint);
    }

    private static PlayCardPipelineInput NewPipelineInput(int rageStacks)
    {
        return new PlayCardPipelineInput(
            DifficultyId: 5,
            CardsPlayedThisTurn: 0,
            OverplayTriggerN: 3,
            OverplayTaxPerCard: 1,
            BaseCardCost: 1,
            EnergyBefore: 3,
            BaseDamage: 10,
            Strength: 0,
            WeakMultiplier: 1.0,
            VulnerableMultiplier: 1.0,
            IsFixedDamage: false,
            CombatantId: "combatant-1",
            StableId: "stable-card-1",
            RageStacks: rageStacks);
    }

    private static JsonElement ReadTaskNode(string taskFilePath, int taskmasterId)
    {
        var absolutePath = Path.Combine(FindRepositoryRoot(), taskFilePath.Replace('/', Path.DirectorySeparatorChar));
        using var document = JsonDocument.Parse(File.ReadAllText(absolutePath));
        var task = document.RootElement
            .EnumerateArray()
            .FirstOrDefault(node =>
                node.TryGetProperty("taskmaster_id", out var idNode)
                && idNode.ValueKind == JsonValueKind.Number
                && idNode.GetInt32() == taskmasterId);

        task.ValueKind.Should().NotBe(JsonValueKind.Undefined, $"taskmaster_id={taskmasterId} must exist in {taskFilePath}");
        return JsonDocument.Parse(task.GetRawText()).RootElement.Clone();
    }

    private static string[] ReadStringArray(JsonElement node, string propertyName)
    {
        if (!node.TryGetProperty(propertyName, out var property) || property.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<string>();
        }

        return property.EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString() ?? string.Empty)
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
    }

    private static string FindRepositoryRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);

        while (current is not null)
        {
            var marker = Path.Combine(current.FullName, ".taskmaster");
            if (Directory.Exists(marker))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate repository root containing .taskmaster directory.");
    }
}
