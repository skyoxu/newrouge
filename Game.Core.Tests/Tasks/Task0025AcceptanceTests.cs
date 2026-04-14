using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Contracts.Combat;
using Game.Core.Contracts.Status;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

[Trait("task", "T25")]
[Trait("adr", "ADR-0033")]
[Trait("adr", "ADR-0021")]
public sealed class Task0025AcceptanceTests
{
    // ACC:T25.1
    [Fact]
    [Trait("acceptance", "ACC:T25.1")]
    public void ShouldKeepRageAcrossTurnCleanup_WhenCombatRemainsActive()
    {
        var statusService = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);

        statusService.TryApplyRage(statuses, stacks: 2, sourceId: "card.warrior.rage_surge").Should().BeTrue();

        statusService.ProcessTurnPhase(statuses, ExpiresTiming.OwnerEndOfTurnCleanup);

        statuses.Should().ContainKey(StatusOperations.RageStatusId);
        statuses[StatusOperations.RageStatusId].StatusType.Should().Be(StatusType.Buff);
        statuses[StatusOperations.RageStatusId].Stacks.Should().Be(2);
        statuses[StatusOperations.RageStatusId].ExpiresTiming.Should().Be(ExpiresTiming.Never);
    }

    // ACC:T25.2
    [Fact]
    [Trait("acceptance", "ACC:T25.2")]
    public void ShouldApplyRageOnlyFromAllowedSources_WhenStackingDeterministically()
    {
        var statusService = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);

        statusService.TryApplyRage(statuses, stacks: 2, sourceId: "card.warrior.rage_surge").Should().BeTrue();
        var snapshotBeforeInvalid = statuses[StatusOperations.RageStatusId];

        statusService.TryApplyRage(statuses, stacks: 2, sourceId: "card.invalid").Should().BeFalse();
        statusService.TryApplyRage(statuses, stacks: 0, sourceId: "card.warrior.rage_surge").Should().BeFalse();
        statusService.TryApplyRage(statuses, stacks: -1, sourceId: "card.warrior.rage_surge").Should().BeFalse();
        statuses[StatusOperations.RageStatusId].Should().Be(snapshotBeforeInvalid);

        statusService.TryApplyRage(statuses, stacks: 1, sourceId: "card.warrior.bloodrush").Should().BeTrue();

        statusService.GetRageStacks(statuses).Should().Be(3);
    }

    // ACC:T25.3
    [Fact]
    [Trait("acceptance", "ACC:T25.3")]
    public void ShouldResetRageAfterCombatEnd_WhenCombatOnlyStatusesAreCleared()
    {
        var statusService = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);
        statusService.TryApplyRage(statuses, stacks: 3, sourceId: "card.warrior.rage_surge").Should().BeTrue();

        statusService.ResetCombatOnlyStatuses(statuses);

        statuses.Should().NotContainKey(StatusOperations.RageStatusId);
        statusService.GetRageStacks(statuses).Should().Be(0);
    }

    // ACC:T25.4
    [Fact]
    [Trait("acceptance", "ACC:T25.4")]
    public void ShouldReflectRageInDamagePipeline_WhenResetReturnsToBaseline()
    {
        var statusService = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);
        statusService.TryApplyRage(statuses, stacks: 3, sourceId: "card.warrior.rage_surge").Should().BeTrue();
        var pipeline = new PlayCardResolutionPipeline();

        var withRage = pipeline.Execute(NewPipelineInput(rageStacks: statusService.GetRageStacks(statuses)));

        statusService.ResetCombatOnlyStatuses(statuses);
        var baseline = pipeline.Execute(NewPipelineInput(rageStacks: statusService.GetRageStacks(statuses)));

        withRage.StateAfter.FinalDamage.Should().Be(13);
        baseline.StateAfter.FinalDamage.Should().Be(10);
        withRage.StateAfter.FinalDamage.Should().BeGreaterThan(baseline.StateAfter.FinalDamage);
    }

    // ACC:T25.5
    [Fact]
    [Trait("acceptance", "ACC:T25.5")]
    public void ShouldProduceDeterministicOrderingWithOtherStatuses_WhenInputIsSame()
    {
        var statusesA = new[]
        {
            NewStatus("stable-002", "status.poison", StatusType.Debuff, stacks: 1, durationTurns: 2, ExpiresTiming.OwnerEndOfTurnCleanup),
            NewStatus("stable-001", StatusOperations.RageStatusId, StatusType.Buff, stacks: 3, durationTurns: 0, ExpiresTiming.Never),
            NewStatus("stable-003", "status.focus", StatusType.Buff, stacks: 1, durationTurns: 3, ExpiresTiming.OwnerEndOfTurnCleanup),
        };
        var statusesB = statusesA.Reverse().ToArray();

        var firstOrder = StatusOperations.SortByStableId(statusesA).Select(status => $"{status.StableId}:{status.StatusId}").ToArray();
        var secondOrder = StatusOperations.SortByStableId(statusesB).Select(status => $"{status.StableId}:{status.StatusId}").ToArray();
        var pipeline = new PlayCardResolutionPipeline();
        var firstResult = pipeline.Execute(NewPipelineInput(rageStacks: 3));
        var secondResult = pipeline.Execute(NewPipelineInput(rageStacks: 3));

        firstOrder.Should().Equal(secondOrder);
        firstResult.ExecutionFingerprint.Should().Be(secondResult.ExecutionFingerprint);
        firstResult.StateAfter.FinalDamage.Should().Be(secondResult.StateAfter.FinalDamage);
    }

    // ACC:T25.6
    [Fact]
    [Trait("acceptance", "ACC:T25.6")]
    public void ShouldResolveSameDamageForSameInput_WhenRageAndOtherStatusesRepeat()
    {
        var statusService = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal)
        {
            ["status.focus"] = NewStatus(
                stableId: "stable-010",
                statusId: "status.focus",
                statusType: StatusType.Buff,
                stacks: 1,
                durationTurns: 3,
                expiresTiming: ExpiresTiming.OwnerEndOfTurnCleanup),
        };
        statusService.TryApplyRage(statuses, stacks: 2, sourceId: "card.warrior.rage_surge").Should().BeTrue();
        var pipeline = new PlayCardResolutionPipeline();

        var rageStacks = statusService.GetRageStacks(statuses);
        var run1 = pipeline.Execute(NewPipelineInput(rageStacks: rageStacks));
        var run2 = pipeline.Execute(NewPipelineInput(rageStacks: rageStacks));

        run1.ExecutionFingerprint.Should().Be(run2.ExecutionFingerprint);
        run1.ExecutedSteps.Should().Equal(run2.ExecutedSteps);
        run1.StateAfter.FinalDamage.Should().Be(run2.StateAfter.FinalDamage);
    }

    // ACC:T25.7
    [Fact]
    [Trait("acceptance", "ACC:T25.7")]
    public void ShouldContainAdr0033AndAdr0021InTaskMetadataAndAcceptanceTest_WhenTraceabilityAudited()
    {
        var repoRoot = FindRepositoryRoot();
        var taskNode = ReadTaskNodeByTaskmasterId(
            Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_gameplay.json"),
            25);

        var adrRefs = ReadStringArray(taskNode, "adr_refs");
        adrRefs.Should().Contain("ADR-0033");
        adrRefs.Should().Contain("ADR-0021");

        var thisSource = File.ReadAllText(GetCurrentSourceFilePath());
        thisSource.Should().Contain("ADR-0033");
        thisSource.Should().Contain("ADR-0021");
    }

    // ACC:T25.8
    [Fact]
    [Trait("acceptance", "ACC:T25.8")]
    public void ShouldKeepImplementationAndTestsAdrMappingAligned_WhenReviewGateAuditsTraceability()
    {
        var repoRoot = FindRepositoryRoot();
        var statusServicePath = Path.Combine(repoRoot, "Game.Core", "Services", "StatusService.cs");
        File.Exists(statusServicePath).Should().BeTrue();

        var implementationSource = File.ReadAllText(statusServicePath);
        implementationSource.Should().Contain("ADR-0033");
        implementationSource.Should().Contain("ADR-0021");
    }

    private static StatusInstance NewStatus(
        string stableId,
        string statusId,
        StatusType statusType,
        int stacks,
        int durationTurns,
        ExpiresTiming expiresTiming)
    {
        return new StatusInstance(
            StableId: stableId,
            StatusId: statusId,
            StatusType: statusType,
            Stacks: stacks,
            DurationTurns: durationTurns,
            SourceId: "task-25",
            ExpiresTiming: expiresTiming,
            Strength: 0);
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
            var marker = Path.Combine(current.FullName, ".taskmaster");
            if (Directory.Exists(marker))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate repository root from test execution directory.");
    }

    private static string GetCurrentSourceFilePath([CallerFilePath] string path = "") => path;
}
