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

public sealed class Task0090AcceptanceTests
{
    private const int TaskmasterId = 90;
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string CombatScenePath = "Game.Godot/Scripts/UI/CombatScene.cs";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0090AcceptanceTests.cs";

    // ACC:T90.1
    [Fact]
    [Trait("acceptance", "ACC:T90.1")]
    public void ShouldExecuteLiveCombatRuntimePathThroughCombatService_WhenRunningPlayCardAndEndTurnProgression()
    {
        var source = ReadRepositoryText(CombatScenePath);
        source.Should().Contain("private readonly CombatService _combatService = new()", "live player-facing path must own a shared CombatService runtime instance.");
        source.Should().Contain("_combatService.PlayCard(", "card-play entry should route through shared runtime play-card pipeline.");
        source.Should().Contain("_combatService.ResolveCardRuntime(", "card-resolution entry should route through shared runtime resolver.");
        source.Should().Contain("_combatService.ResolveEndTurnProgression(", "turn progression entry should route through shared runtime resolver.");

        var service = new CombatService();
        var input = CreatePipelineInput(baseDamage: 10, strength: 2, isFixedDamage: false);

        var playResult = service.PlayCard(input);
        var runtimeResult = service.ResolveCardRuntime(new CardResolutionInput(
            Target: "enemy",
            TargetEnemyId: "enemy_m1_slime",
            AliveEnemyCount: 1,
            ResolvedDamageFromPipeline: playResult.StateAfter.FinalDamage,
            Block: 0,
            StatusId: string.Empty,
            StatusStacks: 0,
            Exhaust: false));
        var endTurn = service.ResolveEndTurnProgression(new EndTurnProgressionInput(
            Difficulty: 10,
            PlayerHp: 30,
            PlayerBlock: 2,
            DrawPileCount: 8,
            DiscardPileCount: 2,
            HandCount: 5,
            IncomingEnemyDamage: 7,
            NextHandCards: Array.Empty<string>()));

        playResult.Success.Should().BeTrue(playResult.FailureReason);
        runtimeResult.TotalDamage.Should().Be(playResult.StateAfter.FinalDamage);
        endTurn.DamageTaken.Should().Be(5);
        endTurn.NextPlayerHp.Should().Be(25);
    }

    // ACC:T90.2
    [Fact]
    [Trait("acceptance", "ACC:T90.2")]
    public void ShouldPreserveDeterministicTriggerOrderingAndSingleRuntimeOwner_WhenApplyingSameInputs()
    {
        var service = new CombatService();
        var input = CreatePipelineInput(baseDamage: 11, strength: 1, isFixedDamage: false);

        var first = service.PlayCard(input);
        var second = service.PlayCard(input);

        first.Success.Should().BeTrue(first.FailureReason);
        second.Success.Should().BeTrue(second.FailureReason);
        first.ExecutionFingerprint.Should().Be(second.ExecutionFingerprint);
        first.ExecutedSteps.Should().Equal(second.ExecutedSteps);

        var ordered = PlayCardResolutionPipeline.ResolveTriggerOrder(new[]
        {
            new CombatTriggerOrderKey("Status.Weak", Priority: 1, RegistrationOrder: 1),
            new CombatTriggerOrderKey("Relic.Anchor", Priority: 1, RegistrationOrder: 2),
            new CombatTriggerOrderKey("Status.Vulnerable", Priority: 2, RegistrationOrder: 0),
        });
        ordered.Should().Equal("Relic.Anchor", "Status.Weak", "Status.Vulnerable");
    }

    // ACC:T90.3
    [Fact]
    [Trait("acceptance", "ACC:T90.3")]
    public void ShouldKeepRuntimeFeedbackScopeLimitedWithoutIntroducingGlobalFeedbackReconciliation_WhenResolvingCardRuntime()
    {
        var service = new CombatService();
        var singleTarget = service.ResolveCardRuntime(new CardResolutionInput(
            Target: "enemy",
            TargetEnemyId: "enemy_m1_slime",
            AliveEnemyCount: 1,
            ResolvedDamageFromPipeline: 9,
            Block: 0,
            StatusId: "status.weak",
            StatusStacks: 2,
            Exhaust: false));
        var aoe = service.ResolveCardRuntime(new CardResolutionInput(
            Target: "all_enemies",
            TargetEnemyId: string.Empty,
            AliveEnemyCount: 3,
            ResolvedDamageFromPipeline: 9,
            Block: 0,
            StatusId: "status.weak",
            StatusStacks: 2,
            Exhaust: false));

        singleTarget.TotalDamage.Should().Be(9);
        singleTarget.PerTargetDamage.Should().Be(9);
        singleTarget.StatusDetail.Should().Be("applied status.weak +2 to enemy_m1_slime");
        singleTarget.StatusDetail.Should().NotContain("all_enemies", "broader full-surface feedback reconciliation is out of T90 scope.");
        aoe.TotalDamage.Should().Be(27);
        aoe.PerTargetDamage.Should().Be(9);
        aoe.StatusDetail.Should().Be("applied status.weak +2 to all_enemies");
        aoe.StatusDetail.Should().NotContain("enemy_m1_slime", "AOE feedback should not collapse into a single-target ownership path.");
    }

    // ACC:T90.4
    [Fact]
    [Trait("acceptance", "ACC:T90.4")]
    public void ShouldNotExpandToAoeOrderingPath_WhenTaskScopeRemainsSingleTargetRuntimePromotion()
    {
        var service = new CombatService();
        var singleTarget = service.ResolveCardRuntime(new CardResolutionInput(
            Target: "enemy",
            TargetEnemyId: "enemy_m1_slime",
            AliveEnemyCount: 3,
            ResolvedDamageFromPipeline: 12,
            Block: 0,
            StatusId: "status.weak",
            StatusStacks: 1,
            Exhaust: false));
        var aoe = service.ResolveCardRuntime(new CardResolutionInput(
            Target: "all_enemies",
            TargetEnemyId: string.Empty,
            AliveEnemyCount: 3,
            ResolvedDamageFromPipeline: 12,
            Block: 0,
            StatusId: "status.weak",
            StatusStacks: 1,
            Exhaust: false));

        singleTarget.PerTargetDamage.Should().Be(12);
        singleTarget.TotalDamage.Should().Be(12);
        singleTarget.StatusDetail.Should().Contain("enemy_m1_slime");
        singleTarget.StatusDetail.Should().NotContain("all_enemies", "single-target runtime must not fan out to AOE branch metadata.");
        aoe.PerTargetDamage.Should().Be(12);
        aoe.TotalDamage.Should().Be(36);
        aoe.StatusDetail.Should().Contain("all_enemies");
        aoe.StatusDetail.Should().NotContain("enemy_m1_slime", "AOE branch metadata must not leak single-target ownership.");
        singleTarget.Should().NotBeEquivalentTo(aoe, "T90 scope should not implicitly switch single-target runtime path into AOE ordering behavior.");
    }

    // ACC:T90.5
    [Theory]
    [InlineData(TasksBackPath)]
    [InlineData(TasksGameplayPath)]
    [Trait("acceptance", "ACC:T90.5")]
    public void ShouldVerifyFixedDamageExemptionAndTaskEvidenceRefs_WhenValidatingAcceptance(string taskFilePath)
    {
        var task = ReadTaskNode(taskFilePath, TaskmasterId);
        var testRefs = ReadStringArray(task, "test_refs");
        var acceptance = ReadStringArray(task, "acceptance");

        testRefs.Should().Contain(ThisTaskTestRef);
        acceptance.Should().Contain(
            line => line.Contains("Automated tests must execute the live combat runtime path", StringComparison.Ordinal)
                && line.Contains(ThisTaskTestRef, StringComparison.Ordinal),
            "T90 acceptance runtime evidence must reference Task0090 acceptance behavior tests.");

        var fixedDamage = CombatService.CalculateDamageWithStatusMultipliers(
            baseDamage: 7,
            strength: 100,
            weakMultiplier: 0.25,
            vulnerableMultiplier: 2.0,
            isFixedDamage: true);
        var mutableDamage = CombatService.CalculateDamageWithStatusMultipliers(
            baseDamage: 7,
            strength: 100,
            weakMultiplier: 0.25,
            vulnerableMultiplier: 2.0,
            isFixedDamage: false);

        fixedDamage.Should().Be(7);
        mutableDamage.Should().NotBe(fixedDamage);
    }

    private static PlayCardPipelineInput CreatePipelineInput(int baseDamage, int strength, bool isFixedDamage)
    {
        return new PlayCardPipelineInput(
            DifficultyId: 10,
            CardsPlayedThisTurn: 1,
            OverplayTriggerN: 3,
            OverplayTaxPerCard: 1,
            BaseCardCost: 1,
            EnergyBefore: 5,
            BaseDamage: baseDamage,
            Strength: strength,
            WeakMultiplier: 1.0,
            VulnerableMultiplier: 1.5,
            IsFixedDamage: isFixedDamage,
            CombatantId: "combatant.player",
            StableId: "stable.player.001");
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

        return property
            .EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString() ?? string.Empty)
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
    }

    private static string ReadRepositoryText(string relativePath)
    {
        var absolutePath = Path.Combine(FindRepositoryRoot(), relativePath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(absolutePath).Should().BeTrue($"required source file is missing: {relativePath}");
        return File.ReadAllText(absolutePath);
    }

    private static string FindRepositoryRoot()
    {
        var current = AppContext.BaseDirectory;
        while (!string.IsNullOrWhiteSpace(current))
        {
            var candidate = Path.Combine(current, "newrouge.sln");
            if (File.Exists(candidate))
            {
                return current;
            }

            var parent = Directory.GetParent(current);
            if (parent is null)
            {
                break;
            }

            current = parent.FullName;
        }

        throw new DirectoryNotFoundException("Cannot locate repository root containing newrouge.sln.");
    }
}
