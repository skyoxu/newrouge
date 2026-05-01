using System;
using System.IO;
using System.Linq;
using System.Reflection;
using FluentAssertions;
using Game.Core.Contracts.Combat;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0011AcceptanceTests
{
    private static readonly PlayCardPipelineStep[] CanonicalOrder =
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

    private static readonly string[] ForbiddenGodotNamespaceTokens =
    {
        "using Godot;",
        "using Godot.",
        " Godot.",
        ": Godot.",
    };

    // ACC:T11.7
    // ACC:T95.5
    [Fact]
    public void ShouldResolveThroughPlayCardEntrypoint_WhenCoreCombatServiceReceivesValidPipelineInput()
    {
        var service = new CombatService();
        var input = CreateValidInput();

        var playCardCandidates = typeof(CombatService)
            .GetMethods(BindingFlags.Public | BindingFlags.Instance)
            .Where(method => method.Name == "PlayCard")
            .Where(method => method.GetParameters().Length == 1)
            .Where(method => method.GetParameters()[0].ParameterType == typeof(PlayCardPipelineInput))
            .ToArray();

        playCardCandidates.Should().ContainSingle(
            because: "Task 11 acceptance requires a public CombatService.PlayCard(PlayCardPipelineInput) entrypoint in Core.");

        var rawResult = playCardCandidates[0].Invoke(service, new object[] { input });

        rawResult.Should().BeOfType<PlayCardPipelineResult>();
        var result = (PlayCardPipelineResult)rawResult!;
        result.Success.Should().BeTrue();
        result.ExecutedSteps.Should().Equal(CanonicalOrder);
    }

    // ACC:T11.7
    [Fact]
    public void ShouldNotReferenceGodotNamespaces_WhenScanningCombatServiceSource()
    {
        var sourcePath = Path.Combine(FindRepoRoot(), "Game.Core", "Services", "CombatService.cs");

        File.Exists(sourcePath).Should().BeTrue("CombatService source must exist for boundary validation.");
        var source = File.ReadAllText(sourcePath);

        ContainsForbiddenGodotToken(source).Should().BeFalse(
            because: "core combat implementation must stay engine-agnostic and avoid direct Godot API namespaces");
    }

    // ACC:T11.7
    [Fact]
    public void ShouldDetectGodotBoundaryViolation_WhenSourceSampleContainsForbiddenNamespace()
    {
        var sourceSample = "using Godot;\npublic sealed class CombatService { }";

        ContainsForbiddenGodotToken(sourceSample).Should().BeTrue();
    }

    // ACC:T11.8
    [Fact]
    public void ShouldRunWithoutGodotRuntime_WhenExecutingPipelineInPureXunitProcess()
    {
        var service = new CombatService();

        var result = service.ExecutePlayCardPipeline(CreateValidInput());

        result.Success.Should().BeTrue();

        var loadedAssemblyNames = AppDomain.CurrentDomain
            .GetAssemblies()
            .Select(assembly => assembly.GetName().Name ?? string.Empty)
            .ToArray();

        loadedAssemblyNames.Should().NotContain(
            name => name.StartsWith("Godot", StringComparison.OrdinalIgnoreCase),
            because: "Task 11 acceptance requires pure xUnit validation without starting Godot runtime");
    }

    // ACC:T11.8
    [Fact]
    public void ShouldReturnValidationFailureAndKeepStateUnchanged_WhenDeterministicOrderingKeysAreMissing()
    {
        var service = new CombatService();
        var input = CreateValidInput(combatantId: string.Empty, stableId: string.Empty);

        var result = service.ExecutePlayCardPipeline(input);

        result.Success.Should().BeFalse();
        result.ExecutedSteps.Should().Equal(PlayCardPipelineStep.Validate);
        result.StateAfter.Should().Be(result.StateBefore);
        result.FailureReason.Should().Contain("ordering keys");
    }

    // ACC:T11.8
    [Fact]
    public void ShouldReturnPayCostFailureAndKeepStateUnchanged_WhenEnergyIsInsufficientAfterTax()
    {
        var service = new CombatService();
        var input = CreateValidInput(
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

    // ACC:T11.8
    [Fact]
    public void ShouldCompleteMoveCardAndDeathCheckTail_WhenPipelineExecutionSucceeds()
    {
        var service = new CombatService();

        var result = service.ExecutePlayCardPipeline(CreateValidInput());

        result.Success.Should().BeTrue();
        result.ExecutedSteps.Should().Equal(CanonicalOrder);
        result.StateAfter.CardMoved.Should().BeTrue();
        result.StateAfter.DeathCheckCompleted.Should().BeTrue();
    }

    // ACC:T83.1
    [Fact]
    public void ShouldResolveCardRuntimeDeterministically_WhenGivenEquivalentInputs()
    {
        var service = new CombatService();
        var input = new CardResolutionInput(
            Target: "enemy",
            TargetEnemyId: "enemy_m1_slime",
            AliveEnemyCount: 1,
            ResolvedDamageFromPipeline: 6,
            Block: 5,
            StatusId: "status.weak",
            StatusStacks: 1,
            Exhaust: false);

        var first = service.ResolveCardRuntime(input);
        var second = service.ResolveCardRuntime(input);

        first.Should().Be(second);
        first.TotalDamage.Should().Be(6);
        first.PerTargetDamage.Should().Be(6);
        first.BlockGain.Should().Be(5);
        first.StatusDetail.Should().Contain("status.weak");
    }

    // ACC:T83.7
    [Fact]
    public void ShouldResolveEndTurnProgressionDeterministically_WhenGivenEquivalentInputs()
    {
        var service = new CombatService();
        var input = new EndTurnProgressionInput(
            Difficulty: 10,
            PlayerHp: 80,
            PlayerBlock: 5,
            DrawPileCount: 7,
            DiscardPileCount: 2,
            HandCount: 3,
            IncomingEnemyDamage: 6,
            NextHandCards: new[] { "Strike", "Defend", "Strike" });

        var first = service.ResolveEndTurnProgression(input);
        var second = service.ResolveEndTurnProgression(input);

        first.Should().Be(second);
        first.DamageTaken.Should().Be(1);
        first.NextPlayerHp.Should().Be(79);
        first.NextEnergy.Should().Be(3);
        first.NextDiscardPileCount.Should().Be(5);
    }

    private static bool ContainsForbiddenGodotToken(string content)
    {
        return ForbiddenGodotNamespaceTokens.Any(token => content.Contains(token, StringComparison.Ordinal));
    }

    private static PlayCardPipelineInput CreateValidInput(
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

    private static string FindRepoRoot()
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

        throw new DirectoryNotFoundException("Cannot locate repository root from test execution directory.");
    }
}
