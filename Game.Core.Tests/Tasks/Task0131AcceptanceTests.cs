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

public sealed class Task0131AcceptanceTests
{
    private const string IntentDefinitionsPath = "Game.Core/Data/m1-enemy-intent-definitions.json";

    // ACC:T131.1
    [Fact]
    [Trait("acceptance", "ACC:T131.1")]
    public void ShouldResolveAttackPlusSecondaryEffects_WhenAcceptedEndTurnUsesDisplayedPreview()
    {
        var service = new CombatService();
        var attackBlockBundle = CreateBundle(
            "act1-slime-scout",
            "intent.attack_block",
            "fp:attack-block",
            CreateEffect("attack", 6, timing: "current_turn", target: "player"),
            CreateEffect("block", 4, timing: "next_enemy_turn", target: "self"));
        var attackStatusBundle = CreateBundle(
            "act1-moss-rat",
            "intent.attack_status",
            "fp:attack-status",
            CreateEffect("attack", 5, timing: "current_turn", target: "player"),
            CreateEffect("status", 1, timing: "current_turn", statusId: "status.poison", target: "self"));

        var resolution = service.ResolveEnemyIntentBundleOnce(new EndTurnEnemyIntentInput(
            IntentDamage: 0,
            FallbackDamage: 0,
            PreviewBundles: new[] { attackBlockBundle, attackStatusBundle }));

        resolution.FailureCode.Should().BeEmpty();
        resolution.ImmediateDamage.Should().Be(11,
            "the accepted end_turn path should resolve attack damage from every displayed preview bundle without opening a second enemy-turn execution lane");
        resolution.ImmediateEffects.Select(effect => effect.Kind).Should().ContainInOrder("attack", "attack", "status");
        resolution.DelayedEffects.Select(effect => effect.Kind).Should().ContainSingle("block");
    }

    // ACC:T131.2
    [Fact]
    [Trait("acceptance", "ACC:T131.2")]
    public void ShouldScheduleNextTurnBlockAfterCurrentTurnDamage_WhenPreviewIncludesDelayedBlock()
    {
        var service = new CombatService();
        var delayedBlockBundle = CreateBundle(
            "act1-slime-scout",
            "intent.attack_block",
            "fp:delayed-block",
            CreateEffect("attack", 6, timing: "current_turn", target: "player"),
            CreateEffect("block", 4, timing: "next_enemy_turn", target: "self"));

        var resolution = service.ResolveEnemyIntentBundleOnce(new EndTurnEnemyIntentInput(
            IntentDamage: 0,
            FallbackDamage: 0,
            PreviewBundles: new[] { delayedBlockBundle }));
        var damage = service.ResolveEndTurnIncomingDamage(new EndTurnEnemyIntentInput(
            IntentDamage: 0,
            FallbackDamage: 0,
            PreviewBundles: new[] { delayedBlockBundle }));

        damage.Should().Be(6, "current-turn attack damage should still resolve on the accepted end_turn path");
        resolution.ImmediateEffects.Select(effect => effect.Kind).Should().ContainSingle("attack");
        resolution.DelayedEffects.Should().ContainSingle(effect =>
            string.Equals(effect.Kind, "block", StringComparison.OrdinalIgnoreCase)
            && effect.Magnitude == 4
            && IsDelayedToNextEnemyTurn(effect.Timing),
            "the displayed preview should keep its next-turn block effect scheduled for the next governed enemy-turn boundary instead of applying it immediately or dropping it");
    }

    // ACC:T131.3
    [Fact]
    [Trait("acceptance", "ACC:T131.3")]
    public void ShouldUseDisplayedPreviewBundleAsExecutionSourceOfTruth_WhenRuntimeSelectsIntent()
    {
        var intents = LoadIntentDefinitions();
        var firstEnemyId = intents.Select(intent => intent.EnemyId).First();
        var pool = intents
            .Where(intent => string.Equals(intent.EnemyId, firstEnemyId, StringComparison.Ordinal))
            .Select(intent => intent.IntentId)
            .ToArray();
        var selectionService = new EnemyIntentSelectionService();
        var selectedIntentId = selectionService.SelectIntent(
            firstEnemyId,
            "Opening",
            new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal)
            {
                ["Opening"] = pool,
            },
            new[] { 0, 1, 2, 3 });
        var selectedPreview = intents.Single(intent =>
            string.Equals(intent.EnemyId, firstEnemyId, StringComparison.Ordinal)
            && string.Equals(intent.IntentId, selectedIntentId, StringComparison.Ordinal));
        var selectedEffects = GetStructuredEffects(selectedPreview.Raw)
            .Select(BuildEffectFromJson)
            .ToArray();
        var displayedBundle = CreateBundle(
            firstEnemyId,
            selectedIntentId,
            $"fp:{firstEnemyId}:{selectedIntentId}:displayed",
            selectedEffects);

        var resolution = new CombatService().ResolveEnemyIntentBundleOnce(new EndTurnEnemyIntentInput(
            IntentDamage: 0,
            FallbackDamage: 99,
            PreviewBundles: new[] { displayedBundle }));

        resolution.FailureCode.Should().BeEmpty();
        resolution.ExecutionFingerprint.Should().Be(displayedBundle.ExecutionFingerprint,
            "the exact displayed preview instance should remain the runtime source of truth, with no re-roll, substitution, or description-only fallback before execution");
        resolution.ImmediateEffects.Should().BeEquivalentTo(
            selectedEffects.Where(effect => !IsDelayedToNextEnemyTurn(effect.Timing)),
            options => options.WithStrictOrdering());
        resolution.DelayedEffects.Should().BeEquivalentTo(
            selectedEffects.Where(effect => IsDelayedToNextEnemyTurn(effect.Timing)),
            options => options.WithStrictOrdering());
    }

    // ACC:T131.4
    [Fact]
    [Trait("acceptance", "ACC:T131.4")]
    public void ShouldResolveMultiEffectBundleInStableImmediateAndDelayedOrder_WhenAcceptedEndTurnInputsRepeat()
    {
        var service = new CombatService();
        var replayedBundle = CreateBundle(
            "enemy-replay",
            "intent.attack_status",
            "fp:stable-order",
            CreateEffect("attack", 7, timing: "current_turn", target: "player"),
            CreateEffect("status", 2, timing: "current_turn", statusId: "status.strength", target: "self"),
            CreateEffect("block", 3, timing: "next_enemy_turn", target: "self"));
        var input = new EndTurnEnemyIntentInput(
            IntentDamage: 0,
            FallbackDamage: 0,
            PreviewBundles: new[] { replayedBundle });

        var first = service.ResolveEnemyIntentBundleOnce(input);
        var second = service.ResolveEnemyIntentBundleOnce(input);

        first.Should().BeEquivalentTo(second, options => options.WithStrictOrdering(),
            "identical accepted end_turn inputs should preserve deterministic immediate and delayed effect ordering for the displayed multi-effect bundle");
        first.ExecutionFingerprint.Should().Be("fp:stable-order");
        first.ImmediateEffects.Select(effect => effect.Kind).Should().ContainInOrder("attack", "status");
        first.DelayedEffects.Select(effect => effect.Kind).Should().ContainSingle("block");
        first.ImmediateDamage.Should().Be(7);
    }

    // ACC:T131.5
    [Fact]
    [Trait("acceptance", "ACC:T131.5")]
    public void ShouldExposeHudFieldsForImmediateAndDelayedEnemyEffects_WhenCombatStateUpdatesInSync()
    {
        var snapshot = new CombatHudSnapshot(
            HandCards: new[] { "Strike", "Defend" },
            Energy: 3,
            DrawPileCount: 5,
            DiscardPileCount: 1,
            Difficulty: 1,
            PlayerHp: 74,
            TurnState: "PlayerTurn",
            EnemyHp: 18,
            EnemyBlock: 4,
            EnemyStatuses: new[] { "status.poison +1" },
            IntentRows: new[]
            {
                "act1-slime-scout: attack 6",
            },
            CombatFeedback: new[]
            {
                "scheduled act1-slime-scout block +4",
            });

        snapshot.EnemyHp.Should().Be(18);
        snapshot.EnemyBlock.Should().Be(4);
        snapshot.EnemyStatuses.Should().Contain("status.poison +1");
        snapshot.IntentRows.Should().ContainSingle();
        snapshot.CombatFeedback.Should().ContainSingle();
    }

    // ACC:T131.6
    [Fact]
    [Trait("acceptance", "ACC:T131.6")]
    public void ShouldRefuseExecutionWithoutPartialMutation_WhenIntentPayloadIsInvalid()
    {
        var service = new CombatService();
        var invalidBundles = new[]
        {
            CreateBundle("enemy-a", "intent.missing-fingerprint", string.Empty, CreateEffect("attack", 6)),
            CreateBundle("enemy-b", "intent.empty-effects", "fp:empty-effects"),
            CreateBundle("enemy-c", "intent.unknown-kind", "fp:unknown-kind", CreateEffect("bogus", 2)),
            CreateBundle("enemy-d", "intent.status-missing-id", "fp:status-missing-id", CreateEffect("status", 1, timing: "current_turn"))
        };

        foreach (var invalidBundle in invalidBundles)
        {
            var resolution = service.ResolveEnemyIntentBundleOnce(new EndTurnEnemyIntentInput(
                IntentDamage: 0,
                FallbackDamage: 0,
                PreviewBundles: new[] { invalidBundle }));

            resolution.FailureCode.Should().Be("InvalidEnemyIntentPayload");
            resolution.ImmediateDamage.Should().Be(0);
            resolution.ImmediateEffects.Should().BeEmpty();
            resolution.DelayedEffects.Should().BeEmpty();
        }
    }

    private static IReadOnlyList<IntentEnvelope> LoadIntentDefinitions()
    {
        using var document = JsonDocument.Parse(ReadRepoText(IntentDefinitionsPath));
        var intents = new List<IntentEnvelope>();
        var enemies = document.RootElement.GetProperty("enemies");

        foreach (var enemy in enemies.EnumerateArray())
        {
            var enemyId = enemy.GetProperty("enemyId").GetString() ?? string.Empty;
            foreach (var intent in enemy.GetProperty("intents").EnumerateArray())
            {
                var intentId = intent.GetProperty("intentId").GetString() ?? string.Empty;
                intents.Add(new IntentEnvelope(enemyId, intentId, intent.Clone()));
            }
        }

        return intents;
    }

    private static IReadOnlyList<JsonElement> GetStructuredEffects(JsonElement intent)
    {
        foreach (var propertyName in new[] { "effects", "structured_effects", "effectBundle", "effect_bundle" })
        {
            if (intent.TryGetProperty(propertyName, out var effectsElement) && effectsElement.ValueKind == JsonValueKind.Array)
            {
                return effectsElement.EnumerateArray().Select(element => element.Clone()).ToArray();
            }
        }

        return Array.Empty<JsonElement>();
    }

    private static string GetEffectKind(JsonElement effect)
    {
        foreach (var propertyName in new[] { "kind", "type", "effectType", "effect_type" })
        {
            if (effect.TryGetProperty(propertyName, out var value) && value.ValueKind == JsonValueKind.String)
            {
                return value.GetString() ?? string.Empty;
            }
        }

        return string.Empty;
    }

    private static bool IsDelayedToNextEnemyTurn(JsonElement effect)
    {
        foreach (var propertyName in new[] { "timing", "phase", "when", "boundary" })
        {
            if (effect.TryGetProperty(propertyName, out var value) && value.ValueKind == JsonValueKind.String)
            {
                var timing = value.GetString() ?? string.Empty;
                if (string.Equals(timing, "next_enemy_turn", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(timing, "next_turn", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(timing, "enemy_turn_start", StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
        }

        return false;
    }

    private static bool IsDelayedToNextEnemyTurn(string timing)
    {
        return string.Equals(timing, "next_enemy_turn", StringComparison.OrdinalIgnoreCase)
               || string.Equals(timing, "next_turn", StringComparison.OrdinalIgnoreCase)
               || string.Equals(timing, "enemy_turn_start", StringComparison.OrdinalIgnoreCase);
    }

    private static EnemyIntentBundleInput CreateBundle(
        string enemyId,
        string intentId,
        string executionFingerprint,
        params EnemyIntentEffectInput[] effects)
    {
        return new EnemyIntentBundleInput(enemyId, intentId, executionFingerprint, effects);
    }

    private static EnemyIntentEffectInput CreateEffect(
        string kind,
        int magnitude,
        string timing = "current_turn",
        string statusId = "",
        string target = "self")
    {
        return new EnemyIntentEffectInput(kind, magnitude, timing, statusId, target);
    }

    private static EnemyIntentEffectInput BuildEffectFromJson(JsonElement effect)
    {
        var kind = GetEffectKind(effect);
        var magnitude = effect.TryGetProperty("amount", out var amountValue) && amountValue.ValueKind == JsonValueKind.Number
            ? amountValue.GetInt32()
            : 0;
        var timing = effect.TryGetProperty("timing", out var timingValue) && timingValue.ValueKind == JsonValueKind.String
            ? timingValue.GetString() ?? string.Empty
            : string.Empty;
        var statusId = effect.TryGetProperty("statusId", out var statusValue) && statusValue.ValueKind == JsonValueKind.String
            ? statusValue.GetString() ?? string.Empty
            : string.Empty;
        var target = effect.TryGetProperty("target", out var targetValue) && targetValue.ValueKind == JsonValueKind.String
            ? targetValue.GetString() ?? "self"
            : "self";
        return new EnemyIntentEffectInput(kind, magnitude, timing, statusId, target);
    }

    private static string ReadRepoText(string repoRelativePath)
    {
        var fullPath = Path.Combine(ResolveRepoRoot(), repoRelativePath.Replace('/', Path.DirectorySeparatorChar));
        return File.ReadAllText(fullPath);
    }

    private static string ResolveRepoRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (Directory.Exists(Path.Combine(current.FullName, ".taskmaster")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate repository root.");
    }

    private sealed record IntentEnvelope(string EnemyId, string IntentId, JsonElement Raw);
}
