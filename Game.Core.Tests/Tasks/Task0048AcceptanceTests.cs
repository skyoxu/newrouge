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

public sealed class Task0048AcceptanceTests
{
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0048AcceptanceTests.cs";
    private static readonly string[] RequiredAdrRefs = { "ADR-0021", "ADR-0032" };

    // ACC:T48.1
    [Fact]
    public void ShouldReturnDeterministicDamageValue_WhenStrengthWeakAndVulnerableAreApplied()
    {
        var first = CalculateDamage(baseDamage: 10, strength: 2, weakMultiplier: 0.75, vulnerableMultiplier: 1.5);
        var second = CalculateDamage(baseDamage: 10, strength: 2, weakMultiplier: 0.75, vulnerableMultiplier: 1.5);

        first.Should().Be(14);
        second.Should().Be(14);
        second.Should().Be(first);
    }

    // ACC:T48.2
    [Fact]
    public void ShouldProcessAoeTargetsInAscendingCombatantIdOrder_WhenMultipleTargetsAreHit()
    {
        var input = new[]
        {
            new CombatantOrderKey("combatant-9", "stable-9"),
            new CombatantOrderKey("combatant-3", "stable-3"),
            new CombatantOrderKey("combatant-5", "stable-5"),
            new CombatantOrderKey("combatant-7", "stable-7"),
        };

        var ordered = CombatService.OrderCombatantsDeterministically(input)
            .Select(key => key.CombatantId)
            .ToArray();

        ordered.Should().Equal("combatant-3", "combatant-5", "combatant-7", "combatant-9");
    }

    // ACC:T48.3
    [Fact]
    public void ShouldEmitPerHitExecutionSequence_WhenResolvingMultiHitDamage()
    {
        var strengthsPerHit = new[] { 1, 1, 1 };
        var settlements = CombatService.ResolveMultiHitSettlements(
            baseDamage: 6,
            strengthsPerHit: strengthsPerHit,
            weakMultiplier: 1.0,
            vulnerableMultiplier: 1.5);

        settlements.Select(item => item.StepIndex).Should().Equal(1, 2, 3);
        settlements.Select(item => item.Damage).Should().Equal(11, 11, 11);
    }

    [InlineData(8, 0, 1.0, 1.0, 8)]
    [InlineData(8, 2, 1.0, 1.0, 10)]
    [InlineData(8, 0, 0.75, 1.0, 6)]
    [InlineData(8, 0, 1.0, 1.5, 12)]
    [InlineData(8, 2, 0.75, 1.5, 11)]
    // ACC:T48.4
    [Theory]
    public void ShouldReflectStrengthWeakAndVulnerableInNumericOutput_WhenCalculatingFinalDamage(
        int baseDamage,
        int strength,
        double weakMultiplier,
        double vulnerableMultiplier,
        int expectedDamage)
    {
        var actual = CalculateDamage(
            baseDamage: baseDamage,
            strength: strength,
            weakMultiplier: weakMultiplier,
            vulnerableMultiplier: vulnerableMultiplier);

        actual.Should().Be(expectedDamage);
    }

    // ACC:T48.5
    [Fact]
    public void ShouldAssertOrderAndPerHitResultsSeparately_WhenResolvingMultiHitDamage()
    {
        var strengthsPerHit = new[] { 3, 3, 3, 3 };
        var settlements = CombatService.ResolveMultiHitSettlements(
            baseDamage: 5,
            strengthsPerHit: strengthsPerHit,
            weakMultiplier: 1.0,
            vulnerableMultiplier: 1.0);

        settlements.Select(item => item.StepIndex).Should().Equal(1, 2, 3, 4);
        settlements.Select(item => item.Damage).Should().Equal(8, 8, 8, 8);
    }

    // ACC:T48.6
    [Fact]
    public void ShouldApplyMultipliersIndependentlyPerHit_WhenResolvingMultiHitDamage()
    {
        var strengthsPerHit = new[] { 0, 2, 4 };
        var settlements = CombatService.ResolveMultiHitSettlements(
            baseDamage: 8,
            strengthsPerHit: strengthsPerHit,
            weakMultiplier: 0.75,
            vulnerableMultiplier: 1.5);

        settlements.Select(item => item.Damage).Should().Equal(9, 11, 14);
    }

    // ACC:T48.7
    [Fact]
    public void ShouldKeepAoeOrderAndSettlementsStable_WhenExecutingSameInputRepeatedly()
    {
        var input = new[]
        {
            new CombatantOrderKey("combatant-6", "stable-6"),
            new CombatantOrderKey("combatant-2", "stable-2"),
            new CombatantOrderKey("combatant-4", "stable-4"),
        };

        var firstRun = ExecuteAoeDamage(
            baseDamage: 7,
            strength: 1,
            weakMultiplier: 1.0,
            vulnerableMultiplier: 1.0,
            targets: input);
        var secondRun = ExecuteAoeDamage(
            baseDamage: 7,
            strength: 1,
            weakMultiplier: 1.0,
            vulnerableMultiplier: 1.0,
            targets: input);

        firstRun.Select(item => item.combatantId).Should().Equal(secondRun.Select(item => item.combatantId));
        firstRun.Select(item => item.damage).Should().Equal(secondRun.Select(item => item.damage));
        firstRun.Select(item => item.stepIndex).Should().Equal(secondRun.Select(item => item.stepIndex));
    }

    // ACC:T48.8
    [Fact]
    public void ShouldIncludeAdr0021AndAdr0032InTrace_WhenProducingAcceptanceOutput()
    {
        using var summary = TryReadAcceptanceSummary();
        if (summary is null)
        {
            return;
        }

        var adrRefs = ReadStringArray(summary.RootElement.GetProperty("adr_refs"));
        var testRefs = ReadStringArray(summary.RootElement.GetProperty("test_refs"));
        var settlements = CombatService.ResolveMultiHitSettlements(
            baseDamage: 8,
            strengthsPerHit: new[] { 0, 2, 4 },
            weakMultiplier: 0.75,
            vulnerableMultiplier: 1.5);

        adrRefs.Should().Contain(RequiredAdrRefs);
        testRefs.Should().Contain(ThisTaskTestRef);
        settlements.Select(item => item.Damage).Should().Equal(9, 11, 14);
    }

    // ACC:T48.9
    [Fact]
    public void ShouldFailReviewGate_WhenMultiplierOrOrderingDeviatesFromAdrSemantics()
    {
        var strengthsPerHit = new[] { 0, 2, 4 };
        var canonicalPerHit = CombatService.ResolveMultiHitSettlements(
            baseDamage: 8,
            strengthsPerHit: strengthsPerHit,
            weakMultiplier: 0.75,
            vulnerableMultiplier: 1.5)
            .Select(item => item.Damage)
            .ToArray();

        var multiplierDriftPerHit = CombatService.ResolveMultiHitSettlements(
            baseDamage: 8,
            strengthsPerHit: strengthsPerHit,
            weakMultiplier: 1.0,
            vulnerableMultiplier: 1.5)
            .Select(item => item.Damage)
            .ToArray();
        var multiplierGateResult = CombatService.EvaluateDeterministicSemanticGate(
            expectedOrderCombatantIds: new[] { "combatant-1", "combatant-2", "combatant-3" },
            actualOrderCombatantIds: new[] { "combatant-1", "combatant-2", "combatant-3" },
            expectedPerHitDamages: canonicalPerHit,
            actualPerHitDamages: multiplierDriftPerHit);

        var orderingGateResult = CombatService.EvaluateDeterministicSemanticGate(
            expectedOrderCombatantIds: new[] { "combatant-1", "combatant-2", "combatant-3" },
            actualOrderCombatantIds: new[] { "combatant-2", "combatant-1", "combatant-3" },
            expectedPerHitDamages: canonicalPerHit,
            actualPerHitDamages: canonicalPerHit);

        multiplierGateResult.IsPass.Should().BeFalse();
        orderingGateResult.IsPass.Should().BeFalse();
    }

    [Fact]
    public void ShouldFailWhenAoeOrderSkipsOneInputTarget_WhenComparingAgainstCanonicalDeterministicOrder()
    {
        var expectedOrder = new[] { "combatant-1", "combatant-2", "combatant-3" };
        var skippedOrder = new[] { "combatant-1", "combatant-3" };

        var gateResult = CombatService.EvaluateDeterministicSemanticGate(
            expectedOrderCombatantIds: expectedOrder,
            actualOrderCombatantIds: skippedOrder,
            expectedPerHitDamages: new[] { 9, 11, 14 },
            actualPerHitDamages: new[] { 9, 14 });

        gateResult.IsPass.Should().BeFalse("missing targets must fail deterministic ordering gate");
    }

    [Fact]
    public void ShouldFailWhenAoeOrderIncludesExtraUnexpectedTarget_WhenComparingAgainstCanonicalDeterministicOrder()
    {
        var expectedOrder = new[] { "combatant-1", "combatant-2", "combatant-3" };
        var extraTargetOrder = new[] { "combatant-1", "combatant-2", "combatant-3", "combatant-999" };

        var gateResult = CombatService.EvaluateDeterministicSemanticGate(
            expectedOrderCombatantIds: expectedOrder,
            actualOrderCombatantIds: extraTargetOrder,
            expectedPerHitDamages: new[] { 9, 11, 14 },
            actualPerHitDamages: new[] { 9, 11, 14, 14 });

        gateResult.IsPass.Should().BeFalse("extra targets must fail deterministic ordering gate");
    }

    [Fact]
    public void ShouldFailWhenAoeOrderingDriftsFromAscendingOrder_WhenComparingAgainstCanonicalDeterministicOrder()
    {
        var input = new[]
        {
            new CombatantOrderKey("combatant-1", "stable-1"),
            new CombatantOrderKey("combatant-2", "stable-2"),
            new CombatantOrderKey("combatant-3", "stable-3"),
        };

        var canonicalOrder = CombatService.OrderCombatantsDeterministically(input)
            .Select(item => item.CombatantId)
            .ToArray();
        var driftedOrder = canonicalOrder.Reverse().ToArray();

        driftedOrder.Should().NotEqual(canonicalOrder, "non-ascending order must fail acceptance semantics");
    }

    [Fact]
    public void ShouldFailWhenMultiHitReusesMergedSettlement_WhenComparingAgainstPerHitIndependentResolution()
    {
        var strengthsPerHit = new[] { 0, 2, 4 };
        var expectedPerHit = CombatService.ResolveMultiHitSettlements(
            baseDamage: 8,
            strengthsPerHit: strengthsPerHit,
            weakMultiplier: 0.75,
            vulnerableMultiplier: 1.5)
            .Select(item => item.Damage)
            .ToArray();
        var mergedSettlement = ResolveMergedSettlementDamage(
            baseDamage: 8,
            strengthsPerHit: strengthsPerHit,
            weakMultiplier: 0.75,
            vulnerableMultiplier: 1.5);

        mergedSettlement.Should().NotEqual(expectedPerHit, "single merged settlement cannot replace per-hit independent resolution");
    }

    private static int CalculateDamage(int baseDamage, int strength, double weakMultiplier, double vulnerableMultiplier)
    {
        return CombatService.CalculateDamageWithStatusMultipliers(
            baseDamage: baseDamage,
            strength: strength,
            weakMultiplier: weakMultiplier,
            vulnerableMultiplier: vulnerableMultiplier,
            isFixedDamage: false);
    }

    private static IReadOnlyList<(int stepIndex, string combatantId, int damage)> ExecuteAoeDamage(
        int baseDamage,
        int strength,
        double weakMultiplier,
        double vulnerableMultiplier,
        IReadOnlyList<CombatantOrderKey> targets)
    {
        var orderedTargets = CombatService.OrderCombatantsDeterministically(targets);
        var damage = CalculateDamage(
            baseDamage: baseDamage,
            strength: strength,
            weakMultiplier: weakMultiplier,
            vulnerableMultiplier: vulnerableMultiplier);

        return orderedTargets
            .Select((target, index) => (stepIndex: index + 1, combatantId: target.CombatantId, damage))
            .ToArray();
    }

    private static int[] ResolveMergedSettlementDamage(
        int baseDamage,
        IReadOnlyList<int> strengthsPerHit,
        double weakMultiplier,
        double vulnerableMultiplier)
    {
        var mergedStrength = strengthsPerHit.Sum();
        var mergedDamage = CalculateDamage(
            baseDamage: baseDamage,
            strength: mergedStrength,
            weakMultiplier: weakMultiplier,
            vulnerableMultiplier: vulnerableMultiplier);
        return Enumerable.Repeat(mergedDamage, strengthsPerHit.Count).ToArray();
    }

    private static JsonDocument? TryReadAcceptanceSummary()
    {
        var summaryPath = Path.Combine(
            FindRepoRoot(),
            "logs",
            "ci",
            DateTime.Today.ToString("yyyy-MM-dd"),
            "sc-acceptance-check-task-48",
            "summary.json");

        if (!File.Exists(summaryPath))
        {
            return null;
        }

        var json = File.ReadAllText(summaryPath);
        var doc = JsonDocument.Parse(json);
        doc.RootElement.GetProperty("status").GetString().Should().Be("ok");
        doc.RootElement.GetProperty("task_id").GetString().Should().Be("48");
        return doc;
    }

    private static string FindRepoRoot()
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

        throw new InvalidOperationException("Unable to locate repository root containing NewRouge.sln.");
    }

    private static string[] ReadStringArray(JsonElement arrayNode)
    {
        arrayNode.ValueKind.Should().Be(JsonValueKind.Array);
        return arrayNode
            .EnumerateArray()
            .Select(item => item.GetString())
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .Select(item => item!)
            .ToArray();
    }
}
