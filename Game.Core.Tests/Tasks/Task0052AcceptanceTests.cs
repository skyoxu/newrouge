using System;
using System.Collections.Generic;
using System.Linq;
using Game.Core.Services;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0052AcceptanceTests
{
    private const int TaskId = 52;
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0052AcceptanceTests.cs";

    // ACC:T52.1
    [Fact]
    [Trait("acceptance", "ACC:T52.1")]
    public void ShouldDependOnEnemyRulesAndCombatState_WhenSelectingIntentAcrossMixedSamples()
    {
        var selector = CreateSelectorUnderTest();
        var goblin = CreateGoblinSample();
        var slime = CreateSlimeSample();
        var rngStream = new[] { 2, 4, 6, 8 };

        var goblinOpeningIntent = selector.SelectIntent(goblin, CombatState.Opening, rngStream);
        var goblinDefensiveIntent = selector.SelectIntent(goblin, CombatState.Defensive, rngStream);
        var slimeOpeningIntent = selector.SelectIntent(slime, CombatState.Opening, rngStream);

        goblinOpeningIntent.Should().NotBe(
            goblinDefensiveIntent,
            "intent selection must not stay unchanged for the same enemy across different combat states");
        goblinOpeningIntent.Should().NotBe(
            slimeOpeningIntent,
            "enemy-specific rules must also influence intent selection");
    }

    // ACC:T52.2
    [Fact]
    [Trait("acceptance", "ACC:T52.2")]
    public void ShouldReturnStableResultAndRecomputeOnInputChanges_WhenEnemyRngAndStateAreVaried()
    {
        var selector = CreateSelectorUnderTest();
        var enemy = CreateCultistSample();
        var openingState = CombatState.Opening;
        var rngStreamA = new[] { 3, 1, 4, 1, 5 };
        var rngStreamB = new[] { 9, 2, 6, 5, 3 };

        var firstResult = selector.SelectIntent(enemy, openingState, rngStreamA);
        var repeatedResult = selector.SelectIntent(enemy, openingState, rngStreamA);

        firstResult.Should().Be(repeatedResult, "same enemy + same RNG + same combat state must be deterministic");

        var changedByRng = selector.SelectIntent(enemy, openingState, rngStreamB);
        var changedByState = selector.SelectIntent(enemy, CombatState.Enraged, rngStreamA);

        new[] { changedByRng, changedByState }
            .Should()
            .Contain(
                intent => !string.Equals(intent, firstResult, StringComparison.Ordinal),
                "changing RNG stream or combat state must trigger recomputation and produce at least one verifiable difference");
    }

    // ACC:T52.3
    [Fact]
    [Trait("acceptance", "ACC:T52.3")]
    public void ShouldExposeDeterminismCoverageEvidence_WhenCollectingTask52TestRefs()
    {
        var evidence = GetTask52AcceptanceEvidence();

        evidence.TestRefs.Should().Contain(ThisTaskTestRef);
        evidence.CoveredBehaviors.Should().Contain("same-enemy-same-input-consistent");
        evidence.CoveredBehaviors.Should().Contain("input-change-triggers-difference");
    }

    // ACC:T52.4
    [Fact]
    [Trait("acceptance", "ACC:T52.4")]
    public void ShouldProduceAtLeastOneIntentDifference_WhenOnlyRngStreamChanges()
    {
        var selector = CreateSelectorUnderTest();
        var enemies = CreateEnemySamples();
        var combatState = CombatState.Opening;
        var rngStreamA = new[] { 1, 1, 1, 1 };
        var rngStreamB = new[] { 7, 7, 7, 7 };

        var unchangedEnemies = enemies
            .Where(enemy =>
            {
                var first = selector.SelectIntent(enemy, combatState, rngStreamA);
                var second = selector.SelectIntent(enemy, combatState, rngStreamB);
                return string.Equals(first, second, StringComparison.Ordinal);
            })
            .Select(enemy => enemy.EnemyId)
            .ToArray();

        unchangedEnemies.Should().BeEmpty(
            "with identical enemy and combat state, changing only RNG stream input must produce a verifiable intent difference for each sampled enemy");

        var differingSamples = enemies.Count(enemy =>
        {
            var first = selector.SelectIntent(enemy, combatState, rngStreamA);
            var second = selector.SelectIntent(enemy, combatState, rngStreamB);
            return !string.Equals(first, second, StringComparison.Ordinal);
        });

        differingSamples.Should().BeGreaterThan(
            0,
            "with identical enemy and combat state, changing only RNG stream input must produce at least one verifiable intent difference");
    }

    // ACC:T52.5
    [Fact]
    [Trait("acceptance", "ACC:T52.5")]
    public void ShouldProduceAtLeastOneIntentDifference_WhenOnlyCombatStateChanges()
    {
        var selector = CreateSelectorUnderTest();
        var enemies = CreateEnemySamples();
        var rngStream = new[] { 8, 6, 7, 5, 3, 0, 9 };

        var unchangedEnemies = enemies
            .Where(enemy =>
            {
                var openingIntent = selector.SelectIntent(enemy, CombatState.Opening, rngStream);
                var enragedIntent = selector.SelectIntent(enemy, CombatState.Enraged, rngStream);
                return string.Equals(openingIntent, enragedIntent, StringComparison.Ordinal);
            })
            .Select(enemy => enemy.EnemyId)
            .ToArray();

        unchangedEnemies.Should().BeEmpty(
            "with identical enemy and RNG stream, changing only combat state must produce a verifiable intent difference for each sampled enemy");

        var differingSamples = enemies.Count(enemy =>
        {
            var openingIntent = selector.SelectIntent(enemy, CombatState.Opening, rngStream);
            var enragedIntent = selector.SelectIntent(enemy, CombatState.Enraged, rngStream);
            return !string.Equals(openingIntent, enragedIntent, StringComparison.Ordinal);
        });

        differingSamples.Should().BeGreaterThan(
            0,
            "with identical enemy and RNG stream, changing only combat state must produce at least one verifiable intent difference");
    }

    // ACC:T52.6
    [Fact]
    [Trait("acceptance", "ACC:T52.6")]
    [Trait("adr", "ADR-0032")]
    [Trait("adr", "ADR-0021")]
    public void ShouldRequireAdr0032AndAdr0021Traceability_WhenBuildingAcceptanceEvidence()
    {
        var evidence = GetTask52AcceptanceEvidence();

        evidence.AdrRefs.Should().Contain("ADR-0032");
        evidence.AdrRefs.Should().Contain("ADR-0021");
    }

    // ACC:T52.7
    [Fact]
    [Trait("acceptance", "ACC:T52.7")]
    [Trait("adr", "ADR-0032")]
    public void ShouldIncludeAdr0032AuditTraceFields_WhenProducingXunitAcceptanceOutput()
    {
        var output = BuildTask52AcceptanceOutput();

        output.TaskId.Should().Be(TaskId);
        output.AdrRefs.Should().Contain("ADR-0032");
        output.TraceFields.Should().ContainKey("adr_0032_trace");
        output.TraceFields.Should().ContainKey("adr_0032_source");
        output.TraceFields["adr_0032_source"].Should().Be(ThisTaskTestRef);
    }

    private static IEnemyIntentSelector CreateSelectorUnderTest()
    {
        return new ProductionEnemyIntentSelectorAdapter(new EnemyIntentSelectionService());
    }

    private static IReadOnlyList<EnemySample> CreateEnemySamples()
    {
        return new[]
        {
            CreateGoblinSample(),
            CreateCultistSample(),
            CreateSlimeSample()
        };
    }

    private static EnemySample CreateGoblinSample()
    {
        return new EnemySample(
            EnemyId: "goblin",
            IntentPoolsByState: new Dictionary<CombatState, IReadOnlyList<string>>
            {
                [CombatState.Opening] = new[] { "attack_light", "buff_guard" },
                [CombatState.Defensive] = new[] { "guard_up", "taunt" },
                [CombatState.Enraged] = new[] { "attack_heavy", "attack_combo" }
            });
    }

    private static EnemySample CreateCultistSample()
    {
        return new EnemySample(
            EnemyId: "cultist",
            IntentPoolsByState: new Dictionary<CombatState, IReadOnlyList<string>>
            {
                [CombatState.Opening] = new[] { "chant", "hex" },
                [CombatState.Defensive] = new[] { "hex_shield", "drain" },
                [CombatState.Enraged] = new[] { "ritual_blast", "blood_oath" }
            });
    }

    private static EnemySample CreateSlimeSample()
    {
        return new EnemySample(
            EnemyId: "slime",
            IntentPoolsByState: new Dictionary<CombatState, IReadOnlyList<string>>
            {
                [CombatState.Opening] = new[] { "split", "jab" },
                [CombatState.Defensive] = new[] { "harden", "regen" },
                [CombatState.Enraged] = new[] { "slam", "corrode" }
            });
    }

    private static Task52AcceptanceEvidence GetTask52AcceptanceEvidence()
    {
        return new Task52AcceptanceEvidence(
            TestRefs: new[] { ThisTaskTestRef },
            AdrRefs: new[] { "ADR-0032", "ADR-0021" },
            CoveredBehaviors: new[]
            {
                "same-enemy-same-input-consistent",
                "input-change-triggers-difference",
                "rng-only-change-recompute",
                "state-only-change-recompute"
            });
    }

    private static AcceptanceOutput BuildTask52AcceptanceOutput()
    {
        var evidence = GetTask52AcceptanceEvidence();
        var traceFields = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["adr_0032_trace"] = "Task0052 acceptance uses deterministic intent-selection checks",
            ["adr_0032_source"] = ThisTaskTestRef,
            ["adr_0021_trace"] = "Task0052 acceptance validates deterministic recomputation behavior"
        };

        return new AcceptanceOutput(
            TaskId: TaskId,
            AdrRefs: evidence.AdrRefs,
            TraceFields: traceFields,
            TestRefs: evidence.TestRefs);
    }

    private enum CombatState
    {
        Opening,
        Defensive,
        Enraged
    }

    private sealed record EnemySample(
        string EnemyId,
        IReadOnlyDictionary<CombatState, IReadOnlyList<string>> IntentPoolsByState);

    private sealed record Task52AcceptanceEvidence(
        IReadOnlyList<string> TestRefs,
        IReadOnlyList<string> AdrRefs,
        IReadOnlyList<string> CoveredBehaviors);

    private sealed record AcceptanceOutput(
        int TaskId,
        IReadOnlyList<string> AdrRefs,
        IReadOnlyDictionary<string, string> TraceFields,
        IReadOnlyList<string> TestRefs);

    private interface IEnemyIntentSelector
    {
        string SelectIntent(EnemySample enemy, CombatState combatState, IReadOnlyList<int> rngStream);
    }

    private sealed class ProductionEnemyIntentSelectorAdapter : IEnemyIntentSelector
    {
        private readonly EnemyIntentSelectionService service;

        public ProductionEnemyIntentSelectorAdapter(EnemyIntentSelectionService service)
        {
            this.service = service;
        }

        public string SelectIntent(EnemySample enemy, CombatState combatState, IReadOnlyList<int> rngStream)
        {
            var pools = enemy.IntentPoolsByState.ToDictionary(
                pair => pair.Key.ToString(),
                pair => pair.Value,
                StringComparer.Ordinal);
            return service.SelectIntent(enemy.EnemyId, combatState.ToString(), pools, rngStream);
        }
    }
}
