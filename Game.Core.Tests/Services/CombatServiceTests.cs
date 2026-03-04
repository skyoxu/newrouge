using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Combat;
using Game.Core.Contracts.Interfaces;
using Game.Core.Domain;
using Game.Core.Domain.ValueObjects;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class CombatServiceTests
{
    private static readonly string[] RequiredTask6Refs =
    {
        "Game.Core.Tests/Services/CombatServiceTests.cs",
        "Game.Core.Tests/Domain/ValueObjects/DamageTests.cs",
        "Game.Core.Tests/State/CombatLoopPhaseTransitionTests.cs",
        "Game.Core.Tests/Tasks/Task0006CombatContractsTraceabilityTests.cs",
    };

    private static readonly PlayCardPipelineStep[] CanonicalPipelineOrder =
    {
        PlayCardPipelineStep.Validate,
        PlayCardPipelineStep.ComputeCost,
        PlayCardPipelineStep.PayCost,
        PlayCardPipelineStep.BeforePlayTriggers,
        PlayCardPipelineStep.ResolveEffect,
        PlayCardPipelineStep.AfterPlayTriggers,
        PlayCardPipelineStep.MoveCard,
        PlayCardPipelineStep.DeathCheck,
    };

    private static string RepoRoot => FindRepoRoot();

    private static string WarriorFeatureSlicePath =>
        Path.Combine(
            RepoRoot,
            "docs",
            "architecture",
            "overlays",
            "PRD-NEWROUGE-GAME-0001",
            "08",
            "08-Feature-Slice-M1-Warrior.md");

    private static string FindRepoRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            var taskmasterDir = Path.Combine(current.FullName, ".taskmaster");
            if (Directory.Exists(taskmasterDir))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Cannot locate repository root from test execution directory.");
    }

    private sealed class CapturingEventBus : IEventBus
    {
        public List<DomainEvent> Published { get; } = new();

        public Task PublishAsync(DomainEvent evt)
        {
            Published.Add(evt);
            return Task.CompletedTask;
        }

        public IDisposable Subscribe(Func<DomainEvent, Task> handler) => new DummySubscription();

        private sealed class DummySubscription : IDisposable
        {
            public void Dispose()
            {
            }
        }
    }

    // ACC:T6.1
    // ACC:T6.2
    // ACC:T6.9
    // ACC:T6.20
    // ACC:T6.21
    // ACC:T6.22
    [Fact]
    public void ShouldExposeCombatContractsAsConcreteTypes_WhenInspectingCoreAssembly()
    {
        var assembly = typeof(CombatService).Assembly;

        assembly.GetType("Game.Core.Contracts.Combat.CombatLoop").Should().NotBeNull();
        assembly.GetType("Game.Core.Contracts.Combat.PlayCardResolutionPipeline").Should().NotBeNull();
        typeof(CombatService).GetMethod(nameof(CombatService.ExecutePlayCardPipeline)).Should().NotBeNull();
        typeof(CombatService).GetMethod(nameof(CombatService.CalculateDamageWithStatusMultipliers)).Should().NotBeNull();
        typeof(CombatService).GetMethod(nameof(CombatService.CalculateOverplayTax)).Should().NotBeNull();
    }

    // ACC:T6.3
    [Fact]
    public void ShouldContainTask6TestRefsInOverlay_WhenReviewingFeatureSliceFrontMatter()
    {
        File.Exists(WarriorFeatureSlicePath).Should().BeTrue("Task 6 requires overlay Test-Refs to stay aligned.");
        var content = File.ReadAllText(WarriorFeatureSlicePath);

        foreach (var requiredRef in RequiredTask6Refs)
        {
            content.Should().Contain(requiredRef);
        }
    }

    // ACC:T6.4
    [Fact]
    public void ShouldExposeOnlyFourCombatLoopPhases_WhenInspectingPhaseEnum()
    {
        Enum.GetNames<CombatLoopPhase>().Should().Equal("StartOfTurn", "Draw", "Main", "EndOfTurn");
    }

    // ACC:T6.5
    [Fact]
    public void ShouldExecutePlayCardPipelineInCanonicalOrder_WhenInputIsValid()
    {
        var service = new CombatService();
        var input = CreateValidPipelineInput();

        var result = service.ExecutePlayCardPipeline(input);

        result.Success.Should().BeTrue(result.FailureReason);
        result.ExecutedSteps.Should().Equal(CanonicalPipelineOrder);
        result.StateAfter.ResolvedEffects.Should().Be(1);
        result.StateAfter.CardMoved.Should().BeTrue();
        result.StateAfter.DeathCheckCompleted.Should().BeTrue();
    }

    // ACC:T6.7
    // ACC:T6.15
    [Theory]
    [InlineData(9, 2, 3, 2, 0)]   // difficulty below threshold
    [InlineData(10, 2, 3, 2, 0)]  // N-1
    [InlineData(10, 3, 3, 2, 2)]  // N
    [InlineData(10, 4, 3, 2, 4)]  // N+1
    public void ShouldApplyOverplayTaxOnlyAtThreshold_WhenEvaluatingBoundaryCases(
        int difficultyId,
        int cardsPlayedThisTurn,
        int overplayTriggerN,
        int overplayTaxPerCard,
        int expectedTax)
    {
        var tax = CombatService.CalculateOverplayTax(
            difficultyId: difficultyId,
            cardsPlayedThisTurn: cardsPlayedThisTurn,
            overplayTriggerN: overplayTriggerN,
            overplayTaxPerCard: overplayTaxPerCard);

        tax.Should().Be(expectedTax);
    }

    // ACC:T6.8
    [Fact]
    public void ShouldSortByCombatantThenStableId_WhenDeterministicOrderingIsRequested()
    {
        var input = new[]
        {
            new CombatantOrderKey("b", "2"),
            new CombatantOrderKey("a", "2"),
            new CombatantOrderKey("b", "1"),
            new CombatantOrderKey("a", "1"),
        };

        var sorted = CombatService.OrderCombatantsDeterministically(input)
            .Select(x => $"{x.CombatantId}|{x.StableId}")
            .ToArray();

        sorted.Should().Equal("a|1", "a|2", "b|1", "b|2");
    }

    // ACC:T6.10
    [Fact]
    public void ShouldRejectInvalidPhaseTransitionAndKeepState_WhenGuardFails()
    {
        var loop = new CombatLoop(CombatLoopPhase.StartOfTurn);

        var allowed = loop.TryTransitionTo(CombatLoopPhase.Main, out var reason);

        allowed.Should().BeFalse();
        reason.Should().NotBeNullOrWhiteSpace();
        loop.LastGuardFailureReason.Should().Be(reason);
        loop.CurrentPhase.Should().Be(CombatLoopPhase.StartOfTurn);
    }

    // ACC:T6.12
    // ACC:T6.13
    [Fact]
    public void ShouldStopAtValidateAndKeepStateUnchanged_WhenOrderingKeysAreMissing()
    {
        var service = new CombatService();
        var input = CreateValidPipelineInput(combatantId: string.Empty, stableId: string.Empty);

        var result = service.ExecutePlayCardPipeline(input);

        result.Success.Should().BeFalse();
        result.ExecutedSteps.Should().Equal(PlayCardPipelineStep.Validate);
        result.ExecutedSteps.Should().NotEqual(CanonicalPipelineOrder);
        result.StateAfter.Should().Be(result.StateBefore);
        result.FailureReason.Should().Contain("ordering keys");
    }

    // ACC:T6.24
    [Theory]
    [InlineData(PlayCardPipelineStep.ComputeCost, 2)]
    [InlineData(PlayCardPipelineStep.PayCost, 3)]
    public void ShouldStopAtComputeOrPayCostAndKeepStateUnchanged_WhenFailureIsInjected(
        PlayCardPipelineStep failAtStep,
        int expectedExecutedStepCount)
    {
        var service = new CombatService();
        var input = CreateValidPipelineInput(failAtStep: failAtStep);

        var result = service.ExecutePlayCardPipeline(input);

        result.Success.Should().BeFalse();
        result.ExecutedSteps.Should().HaveCount(expectedExecutedStepCount);
        result.ExecutedSteps.Should().Equal(CanonicalPipelineOrder.Take(expectedExecutedStepCount));
        result.StateAfter.Should().Be(result.StateBefore);
        result.FailureReason.Should().Contain($"Injected failure at {failAtStep}");
    }

    [Fact]
    public void ShouldStopAtPayCostAndKeepStateUnchanged_WhenEnergyIsInsufficientAfterTax()
    {
        var service = new CombatService();
        var input = CreateValidPipelineInput(
            difficultyId: 10,
            cardsPlayedThisTurn: 4,
            overplayTriggerN: 3,
            overplayTaxPerCard: 2,
            baseCardCost: 4,
            energyBefore: 3);

        var result = service.ExecutePlayCardPipeline(input);

        result.Success.Should().BeFalse();
        result.ExecutedSteps.Should().Equal(
            PlayCardPipelineStep.Validate,
            PlayCardPipelineStep.ComputeCost,
            PlayCardPipelineStep.PayCost);
        result.StateAfter.Should().Be(result.StateBefore);
        result.FailureReason.Should().Contain("Insufficient energy");
    }

    // ACC:T6.23
    [Fact]
    public void ShouldIncludeOverplayTaxInComputedCostAndPaidEnergy_WhenThresholdIsReached()
    {
        var service = new CombatService();
        var input = CreateValidPipelineInput(
            difficultyId: 10,
            cardsPlayedThisTurn: 3,
            overplayTriggerN: 3,
            overplayTaxPerCard: 2,
            baseCardCost: 1,
            energyBefore: 10);

        var result = service.ExecutePlayCardPipeline(input);

        result.Success.Should().BeTrue(result.FailureReason);
        result.OverplayTax.Should().Be(2);
        result.StateAfter.FinalCost.Should().Be(3);
        result.StateAfter.Energy.Should().Be(7);
    }

    // ACC:T6.16
    [Theory]
    [InlineData(9, 2, 3, 2, "a", "1")]
    [InlineData(10, 3, 3, 2, "a", "1")]
    [InlineData(10, 4, 3, 2, "b", "2")]
    public void ShouldReturnIdenticalResultAcrossRepeatedRuns_WhenInputCaseIsSame(
        int difficultyId,
        int cardsPlayedThisTurn,
        int overplayTriggerN,
        int overplayTaxPerCard,
        string combatantId,
        string stableId)
    {
        var service = new CombatService();
        var input = CreateValidPipelineInput(
            difficultyId: difficultyId,
            cardsPlayedThisTurn: cardsPlayedThisTurn,
            overplayTriggerN: overplayTriggerN,
            overplayTaxPerCard: overplayTaxPerCard,
            combatantId: combatantId,
            stableId: stableId);

        var first = service.ExecutePlayCardPipeline(input);
        var second = service.ExecutePlayCardPipeline(input);

        first.Success.Should().BeTrue();
        second.Success.Should().BeTrue();
        first.ExecutionFingerprint.Should().Be(second.ExecutionFingerprint);
        first.OrderingKey.Should().Be(second.OrderingKey);
        first.OverplayTax.Should().Be(second.OverplayTax);
        first.ExecutedSteps.Should().Equal(second.ExecutedSteps);
        first.StateAfter.Should().Be(second.StateAfter);
    }

    [Fact]
    public void ShouldCalculateDamageAppliesResistanceAndCritical_WhenExecuted()
    {
        var cfg = new CombatConfig { CritMultiplier = 2.0 };
        cfg.Resistances[DamageType.Fire] = 0.5;

        var service = new CombatService();
        var reduced = service.CalculateDamage(new Damage(100, DamageType.Fire), cfg);
        var reducedCrit = service.CalculateDamage(new Damage(100, DamageType.Fire, IsCritical: true), cfg);

        reduced.Should().Be(50);
        reducedCrit.Should().Be(100);
    }

    [Fact]
    public void ShouldCalculateDamageWithArmorMitigatesLinearly_WhenExecuted()
    {
        var service = new CombatService();
        var result = service.CalculateDamage(new Damage(40, DamageType.Physical), CombatConfig.Default, armor: 10);

        result.Should().Be(30);
    }

    [Fact]
    public void ShouldApplyDamageWithConfigPublishesPlayerDamagedEvent_WhenExecuted()
    {
        var bus = new CapturingEventBus();
        var service = new CombatService(bus);
        var player = new Player(maxHealth: 50);

        service.ApplyDamage(player, new Damage(7, DamageType.Physical), CombatConfig.Default);

        player.Health.Current.Should().Be(43);
        bus.Published.Should().ContainSingle();
        bus.Published[0].Type.Should().Be("player.damaged");
        bus.Published[0].Source.Should().Be(nameof(CombatService));
    }

    [Fact]
    public void ShouldApplyDamageEventPayloadMatchesCalculatedDamage_WhenExecuted()
    {
        var bus = new CapturingEventBus();
        var service = new CombatService(bus);
        var player = new Player(maxHealth: 100);
        var cfg = new CombatConfig { CritMultiplier = 2.0 };
        cfg.Resistances[DamageType.Fire] = 0.5;

        service.ApplyDamage(player, new Damage(20, DamageType.Fire, IsCritical: true), cfg);

        bus.Published.Should().ContainSingle();
        var evt = bus.Published[0];
        evt.Type.Should().Be("player.damaged");
        evt.DataJson.Should().NotBeNullOrWhiteSpace();

        using var doc = JsonDocument.Parse(evt.DataJson!);
        doc.RootElement.GetProperty("amount").GetInt32().Should().Be(20);
        doc.RootElement.GetProperty("type").GetString().Should().Be(nameof(DamageType.Fire));
        doc.RootElement.GetProperty("critical").GetBoolean().Should().BeTrue();
        player.Health.Current.Should().Be(80);
    }

    [Fact]
    public void ShouldNotPublishEventForPlainAmountOverload_WhenApplyingRawDamage()
    {
        var bus = new CapturingEventBus();
        var service = new CombatService(bus);
        var player = new Player(maxHealth: 30);

        service.ApplyDamage(player, amount: 5);

        player.Health.Current.Should().Be(25);
        bus.Published.Should().BeEmpty();
    }

    private static PlayCardPipelineInput CreateValidPipelineInput(
        int difficultyId = 10,
        int cardsPlayedThisTurn = 2,
        int overplayTriggerN = 3,
        int overplayTaxPerCard = 2,
        int baseCardCost = 1,
        int energyBefore = 10,
        int baseDamage = 12,
        int strength = 2,
        double weakMultiplier = 1.0,
        double vulnerableMultiplier = 1.0,
        bool isFixedDamage = false,
        string combatantId = "combatant-a",
        string stableId = "stable-001",
        PlayCardPipelineStep? failAtStep = null)
    {
        return new PlayCardPipelineInput(
            DifficultyId: difficultyId,
            CardsPlayedThisTurn: cardsPlayedThisTurn,
            OverplayTriggerN: overplayTriggerN,
            OverplayTaxPerCard: overplayTaxPerCard,
            BaseCardCost: baseCardCost,
            EnergyBefore: energyBefore,
            BaseDamage: baseDamage,
            Strength: strength,
            WeakMultiplier: weakMultiplier,
            VulnerableMultiplier: vulnerableMultiplier,
            IsFixedDamage: isFixedDamage,
            CombatantId: combatantId,
            StableId: stableId,
            FailAtStep: failAtStep);
    }
}
