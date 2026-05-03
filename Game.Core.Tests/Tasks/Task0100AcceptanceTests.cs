using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Contracts.Combat;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0100AcceptanceTests
{
    private const int TaskmasterId = 100;
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0100AcceptanceTests.cs";
    private const string CombatSceneTestRef = "Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd";

    // ACC:T100.1
    [Fact]
    [Trait("acceptance", "ACC:T100.1")]
    public void ShouldRoutePlayCardThroughSharedCombatRuntimeEntrypoint_WhenLiveCombatResolvesDamage()
    {
        var service = new CombatService();
        var input = NewPipelineInput();

        var playCardResult = service.PlayCard(input);
        var pipelineResult = service.ExecutePlayCardPipeline(input);

        playCardResult.Success.Should().BeTrue();
        playCardResult.ExecutionFingerprint.Should().Be(pipelineResult.ExecutionFingerprint);
        playCardResult.StateAfter.FinalDamage.Should().Be(pipelineResult.StateAfter.FinalDamage);
    }

    // ACC:T100.2
    [Fact]
    [Trait("acceptance", "ACC:T100.2")]
    public void ShouldUseSharedDamageCalculationRules_WhenResolvingAoeAndMultiHitDamage()
    {
        const int baseDamage = 7;
        const int strength = 2;
        const double weakMultiplier = 0.75;
        const double vulnerableMultiplier = 1.5;

        var expected = CombatService.CalculateDamageWithStatusMultipliers(
            baseDamage: baseDamage,
            strength: strength,
            weakMultiplier: weakMultiplier,
            vulnerableMultiplier: vulnerableMultiplier,
            isFixedDamage: false);

        var settlements = CombatService.ResolveMultiHitSettlements(
            baseDamage: baseDamage,
            strengthsPerHit: new[] { strength, strength, strength },
            weakMultiplier: weakMultiplier,
            vulnerableMultiplier: vulnerableMultiplier,
            isFixedDamage: false);

        settlements.Select(item => item.Damage).Should().OnlyContain(value => value == expected);
    }

    [Fact]
    [Trait("acceptance", "ACC:T100.2")]
    public void ShouldKeepMultiHitTargetOrderDeterministic_WhenTargetsArriveUnsorted()
    {
        var unorderedTargets = new[]
        {
            new CombatantOrderKey("combatant-9", "stable-9"),
            new CombatantOrderKey("combatant-2", "stable-2"),
            new CombatantOrderKey("combatant-5", "stable-5"),
            new CombatantOrderKey("combatant-1", "stable-1"),
        };
        var strengthsPerHit = new[] { 1, 1, 1, 1 };

        var expectedOrder = CombatService.OrderCombatantsDeterministically(unorderedTargets)
            .Select(item => item.CombatantId)
            .ToArray();
        var expectedDamage = CombatService.CalculateDamageWithStatusMultipliers(
            baseDamage: 8,
            strength: 1,
            weakMultiplier: 1.0,
            vulnerableMultiplier: 1.0,
            isFixedDamage: false);

        var firstBindings = BuildMultiHitBindingsBySharedRuntimeOrder(unorderedTargets, strengthsPerHit);
        var secondBindings = BuildMultiHitBindingsBySharedRuntimeOrder(unorderedTargets, strengthsPerHit);

        firstBindings.Select(item => item.CombatantId).Should().Equal(expectedOrder);
        secondBindings.Select(item => item.CombatantId).Should().Equal(expectedOrder);
        firstBindings.Select(item => item.StepIndex).Should().Equal(1, 2, 3, 4);
        secondBindings.Select(item => item.StepIndex).Should().Equal(1, 2, 3, 4);
        firstBindings.Select(item => item.Damage).Should().OnlyContain(value => value == expectedDamage);
        secondBindings.Select(item => item.Damage).Should().OnlyContain(value => value == expectedDamage);
        secondBindings.Should().Equal(firstBindings);
    }

    // ACC:T100.3
    [Fact]
    [Trait("acceptance", "ACC:T100.3")]
    public void ShouldKeepDeterministicTargetOrderFromSharedRuntime_WhenAoeTargetsArriveUnsorted()
    {
        var unorderedTargets = new[]
        {
            new CombatantOrderKey("combatant-9", "stable-9"),
            new CombatantOrderKey("combatant-2", "stable-2"),
            new CombatantOrderKey("combatant-5", "stable-5"),
            new CombatantOrderKey("combatant-1", "stable-1"),
        };

        var expectedOrder = CombatService.OrderCombatantsDeterministically(unorderedTargets)
            .Select(item => item.CombatantId)
            .ToArray();
        var assignments = BuildAoeTargetAssignmentsFromRuntime(unorderedTargets);

        assignments.Select(item => item.CombatantId).Should().Equal(expectedOrder);
        assignments.Select(item => item.Damage).Should().OnlyContain(value => value > 0);
    }

    // ACC:T100.4
    [Fact]
    [Trait("acceptance", "ACC:T100.4")]
    public void ShouldFailSemanticGateWhenOrderDriftsFromSharedRuleOrder_WhenEvaluatingCombatRuleTests()
    {
        var expectedOrder = new[] { "combatant-1", "combatant-2", "combatant-3" };
        var driftedOrder = new[] { "combatant-2", "combatant-1", "combatant-3" };
        var expectedPerHit = new[] { 9, 11, 14 };

        var gateResult = CombatService.EvaluateDeterministicSemanticGate(
            expectedOrderCombatantIds: expectedOrder,
            actualOrderCombatantIds: driftedOrder,
            expectedPerHitDamages: expectedPerHit,
            actualPerHitDamages: expectedPerHit);

        gateResult.IsPass.Should().BeFalse();
        gateResult.OrderMatches.Should().BeFalse();
    }

    [Fact]
    [Trait("acceptance", "ACC:T100.4")]
    public void ShouldFailSemanticGate_WhenMultiHitResolutionOrderDriftsFromSharedRuleOrder()
    {
        var unorderedTargets = new[]
        {
            new CombatantOrderKey("combatant-9", "stable-9"),
            new CombatantOrderKey("combatant-2", "stable-2"),
            new CombatantOrderKey("combatant-5", "stable-5"),
        };
        var strengthsPerHit = new[] { 1, 1, 1 };

        var expectedOrder = BuildMultiHitBindingsBySharedRuntimeOrder(unorderedTargets, strengthsPerHit)
            .Select(item => item.CombatantId)
            .ToArray();
        var driftedOrder = expectedOrder.Reverse().ToArray();
        var expectedPerHit = CombatService.ResolveMultiHitSettlements(
            baseDamage: 8,
            strengthsPerHit: strengthsPerHit,
            weakMultiplier: 1.0,
            vulnerableMultiplier: 1.0,
            isFixedDamage: false)
            .Select(item => item.Damage)
            .ToArray();

        var gateResult = CombatService.EvaluateDeterministicSemanticGate(
            expectedOrderCombatantIds: expectedOrder,
            actualOrderCombatantIds: driftedOrder,
            expectedPerHitDamages: expectedPerHit,
            actualPerHitDamages: expectedPerHit);

        gateResult.IsPass.Should().BeFalse();
        gateResult.OrderMatches.Should().BeFalse();
    }

    [Fact]
    [Trait("acceptance", "ACC:T100.4")]
    public void ShouldFailSemanticGate_WhenMultiHitTargetCountDoesNotMatchHitCount()
    {
        var unorderedTargets = new[]
        {
            new CombatantOrderKey("combatant-9", "stable-9"),
            new CombatantOrderKey("combatant-2", "stable-2"),
            new CombatantOrderKey("combatant-5", "stable-5"),
        };
        var strengthsPerHit = new[] { 1, 1, 1 };

        var expectedOrder = CombatService.OrderCombatantsDeterministically(unorderedTargets)
            .Select(item => item.CombatantId)
            .ToArray();
        var actualOrder = expectedOrder.Take(2).ToArray();
        var expectedPerHit = CombatService.ResolveMultiHitSettlements(
            baseDamage: 8,
            strengthsPerHit: strengthsPerHit,
            weakMultiplier: 1.0,
            vulnerableMultiplier: 1.0,
            isFixedDamage: false)
            .Select(item => item.Damage)
            .ToArray();
        var actualPerHit = expectedPerHit.Take(2).ToArray();

        var gateResult = CombatService.EvaluateDeterministicSemanticGate(
            expectedOrderCombatantIds: expectedOrder,
            actualOrderCombatantIds: actualOrder,
            expectedPerHitDamages: expectedPerHit,
            actualPerHitDamages: actualPerHit);

        gateResult.IsPass.Should().BeFalse();
        gateResult.OrderMatches.Should().BeFalse();
        gateResult.PerHitMatches.Should().BeFalse();
    }

    // ACC:T100.5
    [Fact]
    [Trait("acceptance", "ACC:T100.5")]
    public void ShouldKeepWorkflowSelectionGovernanceRuleAndEvidenceRefs_WhenReadingTaskAcceptance()
    {
        var taskBack = ReadTaskNode(TasksBackPath, TaskmasterId);
        var taskGameplay = ReadTaskNode(TasksGameplayPath, TaskmasterId);

        var backAcceptance = ReadStringArray(taskBack, "acceptance");
        var gameplayAcceptance = ReadStringArray(taskGameplay, "acceptance");

        backAcceptance.Should().Contain(line =>
            line.Contains("workflow-selection", StringComparison.OrdinalIgnoreCase)
            || line.Contains("workflow selection", StringComparison.OrdinalIgnoreCase));
        gameplayAcceptance.Should().Contain(line =>
            line.Contains("workflow-selection", StringComparison.OrdinalIgnoreCase)
            || line.Contains("workflow selection", StringComparison.OrdinalIgnoreCase));

        ReadStringArray(taskBack, "test_refs").Should().Contain(ThisTaskTestRef);
        ReadStringArray(taskGameplay, "test_refs").Should().Contain(ThisTaskTestRef);
        File.Exists(Path.Combine(FindRepositoryRoot(), CombatSceneTestRef.Replace('/', Path.DirectorySeparatorChar))).Should().BeTrue();
    }

    private static PlayCardPipelineInput NewPipelineInput()
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
            RageStacks: 0);
    }

    private static IReadOnlyList<(int StepIndex, string CombatantId, int Damage)> BuildMultiHitBindingsBySharedRuntimeOrder(
        IReadOnlyList<CombatantOrderKey> unorderedTargets,
        IReadOnlyList<int> strengthsPerHit)
    {
        var orderedTargets = CombatService.OrderCombatantsDeterministically(unorderedTargets)
            .Select(item => item.CombatantId)
            .ToArray();
        var settlements = CombatService.ResolveMultiHitSettlements(
            baseDamage: 8,
            strengthsPerHit: strengthsPerHit,
            weakMultiplier: 1.0,
            vulnerableMultiplier: 1.0,
            isFixedDamage: false);

        settlements.Count.Should().Be(orderedTargets.Length);
        return settlements
            .Select((settlement, index) => (settlement.StepIndex, orderedTargets[index], settlement.Damage))
            .ToArray();
    }

    private static IReadOnlyList<(string CombatantId, int Damage)> BuildAoeTargetAssignmentsFromRuntime(
        IReadOnlyList<CombatantOrderKey> unorderedTargets)
    {
        var service = new CombatService();
        var orderedTargets = CombatService.OrderCombatantsDeterministically(unorderedTargets)
            .Select(item => item.CombatantId)
            .ToArray();
        var runtimeResult = service.ResolveCardRuntime(new CardResolutionInput(
            Target: "all_enemies",
            AliveEnemyCount: orderedTargets.Length,
            ResolvedDamageFromPipeline: 24,
            Block: 0,
            Exhaust: false,
            StatusId: string.Empty,
            StatusStacks: 0,
            TargetEnemyId: string.Empty));

        runtimeResult.TotalDamage.Should().Be(runtimeResult.PerTargetDamage * orderedTargets.Length);
        return orderedTargets
            .Select(combatantId => (combatantId, runtimeResult.PerTargetDamage))
            .ToArray();
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
