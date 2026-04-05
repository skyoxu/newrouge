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
        var semanticMarkersByRef = new Dictionary<string, string[]>
        {
            ["Game.Core.Tests/Services/CombatServiceTests.cs"] = new[] { "ACC:T6.5", "ACC:T6.23", "ACC:T6.24" },
            ["Game.Core.Tests/Domain/ValueObjects/DamageTests.cs"] = new[] { "ACC:T6.17", "ACC:T6.18", "ACC:T6.19" },
            ["Game.Core.Tests/State/CombatLoopPhaseTransitionTests.cs"] = new[] { "ACC:T6.14" },
            ["Game.Core.Tests/Tasks/Task0006CombatContractsTraceabilityTests.cs"] = new[] { "ACC:T6.11" },
        };

        foreach (var requiredRef in RequiredTask6Refs)
        {
            content.Should().Contain(requiredRef);

            var absolutePath = Path.Combine(RepoRoot, requiredRef.Replace('/', Path.DirectorySeparatorChar));
            File.Exists(absolutePath).Should().BeTrue($"Referenced test file must exist: {requiredRef}");

            if (semanticMarkersByRef.TryGetValue(requiredRef, out var markers))
            {
                var refContent = File.ReadAllText(absolutePath);
                foreach (var marker in markers)
                {
                    refContent.Should().Contain(marker, $"Referenced file must carry semantic anchor: {marker}");
                    AssertAnchorBoundToAssertion(refContent, marker);
                }
            }
        }
    }

    // ACC:T6.4
    [Fact]
    public void ShouldExposeOnlyFourCombatLoopPhases_WhenInspectingPhaseEnum()
    {
        Enum.GetNames<CombatLoopPhase>().Should().Equal("StartOfTurn", "Draw", "Main", "EndOfTurn");
    }

    // ACC:T6.5
    // ACC:T11.1
    // ACC:T11.5
    // ACC:T11.6
    // ACC:T11.9
    // ACC:T11.11
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

    // ACC:T6.8
    [Fact]
    public void ShouldProduceIdenticalSortedSequenceAcrossInputPermutations_WhenKeysAreSame()
    {
        var setA = new[]
        {
            new CombatantOrderKey("b", "2"),
            new CombatantOrderKey("a", "2"),
            new CombatantOrderKey("b", "1"),
            new CombatantOrderKey("a", "1"),
        };
        var setB = new[]
        {
            new CombatantOrderKey("a", "1"),
            new CombatantOrderKey("b", "1"),
            new CombatantOrderKey("a", "2"),
            new CombatantOrderKey("b", "2"),
        };

        var sortedA = CombatService.OrderCombatantsDeterministically(setA)
            .Select(x => $"{x.CombatantId}|{x.StableId}")
            .ToArray();
        var sortedB = CombatService.OrderCombatantsDeterministically(setB)
            .Select(x => $"{x.CombatantId}|{x.StableId}")
            .ToArray();

        sortedA.Should().Equal("a|1", "a|2", "b|1", "b|2");
        sortedB.Should().Equal(sortedA);
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
    // ACC:T11.2
    // ACC:T11.21
    // ACC:T11.25
    // ACC:T11.27
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

    // ACC:T6.26
    // ACC:T11.22
    [Fact]
    public void ShouldStopAtPostCostStepAndKeepStateUnchanged_WhenFailureIsInjected(
    )
    {
        var cases = new[]
        {
            (step: PlayCardPipelineStep.BeforePlayTriggers, expectedCount: 4),
            (step: PlayCardPipelineStep.ResolveEffect, expectedCount: 5),
            (step: PlayCardPipelineStep.AfterPlayTriggers, expectedCount: 6),
            (step: PlayCardPipelineStep.MoveCard, expectedCount: 7),
            (step: PlayCardPipelineStep.DeathCheck, expectedCount: 8),
        };

        foreach (var testCase in cases)
        {
            var service = new CombatService();
            var input = CreateValidPipelineInput(failAtStep: testCase.step);

            var result = service.ExecutePlayCardPipeline(input);

            result.Success.Should().BeFalse();
            result.ExecutedSteps.Should().HaveCount(testCase.expectedCount);
            result.ExecutedSteps.Should().Equal(CanonicalPipelineOrder.Take(testCase.expectedCount));
            result.StateAfter.Should().Be(result.StateBefore);
            result.FailureReason.Should().Contain($"Injected failure at {testCase.step}");
        }
    }

    // ACC:T11.4
    // ACC:T11.10
    // ACC:T11.19
    // ACC:T11.20
    // ACC:T11.26
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

    // ACC:T11.36
    [Fact]
    public void ShouldConsumeExactlyComputedCostOnce_WhenPayCostExecutesInSuccessfulPath()
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
        var expectedCost = input.BaseCardCost + result.OverplayTax;
        var consumedEnergy = result.StateBefore.Energy - result.StateAfter.Energy;

        result.Success.Should().BeTrue(result.FailureReason);
        result.ExecutedSteps.Count(step => step == PlayCardPipelineStep.ComputeCost).Should().Be(1);
        result.ExecutedSteps.Count(step => step == PlayCardPipelineStep.PayCost).Should().Be(1);
        result.StateAfter.FinalCost.Should().Be(expectedCost);
        consumedEnergy.Should().Be(expectedCost);
    }

    // ACC:T6.16
    // ACC:T6.25
    // ACC:T11.3
    // ACC:T11.12
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

    // ACC:T6.27
    // ACC:T11.14
    [Fact]
    public void ShouldKeepStageContractStableWithDeterministicOutputs_WhenVerifyingPipelineAndDamageRules()
    {
        var pipeline = new PlayCardResolutionPipeline();
        var input = CreateValidPipelineInput(
            baseDamage: 10,
            strength: 2,
            weakMultiplier: 0.75,
            vulnerableMultiplier: 1.5,
            isFixedDamage: false);

        var first = pipeline.Execute(input);
        var second = pipeline.Execute(input);
        var damage = PlayCardResolutionPipeline.CalculateDamageWithStatusMultipliers(
            baseDamage: 10,
            strength: 2,
            weakMultiplier: 0.75,
            vulnerableMultiplier: 1.5,
            isFixedDamage: false);

        typeof(PlayCardResolutionPipeline).Namespace.Should().Be("Game.Core.Contracts.Combat");
        first.Success.Should().BeTrue(first.FailureReason);
        first.ExecutedSteps.Should().ContainInOrder(
            PlayCardPipelineStep.BeforePlayTriggers,
            PlayCardPipelineStep.ResolveEffect,
            PlayCardPipelineStep.AfterPlayTriggers);
        first.StateAfter.ResolvedEffects.Should().Be(1);
        first.StateAfter.CardMoved.Should().BeTrue();
        first.StateAfter.DeathCheckCompleted.Should().BeTrue();
        first.StateAfter.FinalDamage.Should().Be(14);
        second.Should().BeEquivalentTo(first, "fixed input should produce deterministic stage contract outputs");
        damage.Should().Be(14);
    }

    // ACC:T6.28
    [Fact]
    public void ShouldApplyComparatorPrecedenceAndStableTieHandling_WhenOrderingCombatants()
    {
        var keyA1First = new CombatantOrderKey("a", "1");
        var keyA1Second = new CombatantOrderKey("a", "1");
        var keyA2 = new CombatantOrderKey("a", "2");
        var keyB1 = new CombatantOrderKey("b", "1");

        var input = new[] { keyA1Second, keyB1, keyA1First, keyA2 };

        var sorted1 = CombatService.OrderCombatantsDeterministically(input).ToArray();
        var sorted2 = CombatService.OrderCombatantsDeterministically(input).ToArray();

        sorted1.Select(x => $"{x.CombatantId}|{x.StableId}").Should().Equal("a|1", "a|1", "a|2", "b|1");
        object.ReferenceEquals(sorted1[0], keyA1Second).Should().BeTrue();
        object.ReferenceEquals(sorted1[1], keyA1First).Should().BeTrue();
        sorted2.Should().Equal(sorted1);
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

    // ACC:T11.35
    // ACC:T11.15
    // ACC:T11.30
    // ACC:T11.31
    // ACC:T11.32
    [Fact]
    public void ShouldExposeTask11TraceabilityAndGateMetadata_WhenInspectingGameplayTaskView()
    {
        var taskPath = Path.Combine(RepoRoot, ".taskmaster", "tasks", "tasks_gameplay.json");
        File.Exists(taskPath).Should().BeTrue();

        using var doc = JsonDocument.Parse(File.ReadAllText(taskPath));
        var task11 = doc.RootElement
            .EnumerateArray()
            .FirstOrDefault(node =>
                node.TryGetProperty("taskmaster_id", out var idNode)
                && idNode.ValueKind == JsonValueKind.Number
                && idNode.GetInt32() == 11);

        task11.ValueKind.Should().Be(JsonValueKind.Object);

        var adrRefs = task11.GetProperty("adr_refs").EnumerateArray().Select(x => x.GetString()).ToArray();
        adrRefs.Should().Contain(new[] { "ADR-0021", "ADR-0032" });

        var chapterRefs = task11.GetProperty("chapter_refs").EnumerateArray().Select(x => x.GetString()).ToArray();
        chapterRefs.Should().Contain(new[] { "CH01", "CH06", "CH07", "CH05" });

        var testRefs = task11.GetProperty("test_refs").EnumerateArray().Select(x => x.GetString()).Where(x => !string.IsNullOrWhiteSpace(x)).ToArray();
        testRefs.Should().NotBeEmpty();
        testRefs.Should().Contain("Game.Core.Tests/Services/CombatServiceTests.cs");

        var acceptanceItems = task11.GetProperty("acceptance").EnumerateArray().Select(x => x.GetString()).Where(x => !string.IsNullOrWhiteSpace(x)).ToArray();
        acceptanceItems.Should().NotBeEmpty();
        acceptanceItems.Should().OnlyContain(item => item!.Contains("Refs:", StringComparison.Ordinal),
            "task acceptance must fail-closed when required refs are missing");
    }

    // ACC:T11.33
    // ACC:T11.34
    [Fact]
    public void ShouldExposeTask11ExecutionAndOptionalGateSemantics_WhenInspectingAcceptanceText()
    {
        var taskPath = Path.Combine(RepoRoot, ".taskmaster", "tasks", "tasks_gameplay.json");
        File.Exists(taskPath).Should().BeTrue();

        using var doc = JsonDocument.Parse(File.ReadAllText(taskPath));
        var task11 = doc.RootElement
            .EnumerateArray()
            .FirstOrDefault(node =>
                node.TryGetProperty("taskmaster_id", out var idNode)
                && idNode.ValueKind == JsonValueKind.Number
                && idNode.GetInt32() == 11);

        task11.ValueKind.Should().Be(JsonValueKind.Object);
        var acceptanceItems = task11.GetProperty("acceptance")
            .EnumerateArray()
            .Select(x => x.GetString())
            .Where(x => !string.IsNullOrWhiteSpace(x))
            .ToArray();

        acceptanceItems.Should().Contain(item => item!.Contains("test_refs", StringComparison.OrdinalIgnoreCase)
                                                || item.Contains("执行", StringComparison.OrdinalIgnoreCase));
        acceptanceItems.Should().Contain(item => item!.Contains("executed=false", StringComparison.OrdinalIgnoreCase)
                                                || item.Contains("skipped", StringComparison.OrdinalIgnoreCase));
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

    private static void AssertAnchorBoundToAssertion(string fileContent, string marker)
    {
        var lines = fileContent.Replace("\r\n", "\n").Split('\n');
        var anchorLine = Array.FindIndex(lines, line => line.Contains(marker, StringComparison.Ordinal));
        anchorLine.Should().BeGreaterThanOrEqualTo(0);

        var attributeLine = -1;
        for (var i = anchorLine + 1; i < lines.Length; i++)
        {
            if (lines[i].Contains("[Fact]", StringComparison.Ordinal) || lines[i].Contains("[Theory]", StringComparison.Ordinal))
            {
                attributeLine = i;
                break;
            }

            if (lines[i].Contains("ACC:T6.", StringComparison.Ordinal))
            {
                continue;
            }
        }

        attributeLine.Should().BeGreaterThanOrEqualTo(0, $"Anchor {marker} must bind to a concrete xUnit test method.");

        var methodLine = -1;
        for (var i = attributeLine + 1; i < lines.Length; i++)
        {
            if (lines[i].Contains("public void ", StringComparison.Ordinal))
            {
                methodLine = i;
                break;
            }
        }

        methodLine.Should().BeGreaterThanOrEqualTo(0, $"Anchor {marker} must bind to a named test method.");

        var hasAssertion = false;
        var braceDepth = 0;
        var bodyEntered = false;
        for (var i = methodLine; i < lines.Length; i++)
        {
            var line = lines[i];
            if (line.Contains(".Should(", StringComparison.Ordinal) || line.Contains("Assert.", StringComparison.Ordinal))
            {
                hasAssertion = true;
            }

            foreach (var ch in line)
            {
                if (ch == '{')
                {
                    braceDepth++;
                    bodyEntered = true;
                }
                else if (ch == '}' && bodyEntered)
                {
                    braceDepth--;
                    if (braceDepth == 0)
                    {
                        i = lines.Length;
                        break;
                    }
                }
            }
        }

        hasAssertion.Should().BeTrue($"Anchor {marker} must bind to behavior assertion, not comments only.");
    }
}
