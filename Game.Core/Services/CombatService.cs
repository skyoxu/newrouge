using Game.Core.Domain;
using Game.Core.Domain.ValueObjects;
using Game.Core.Contracts;
using Game.Core.Contracts.Combat;
using Game.Core.Contracts.Interfaces;

namespace Game.Core.Services;

public class CombatService
{
    private const int HardCapCardsPerTurn = 100;
    private readonly IEventBus? _bus;
    private readonly PlayCardResolutionPipeline _playCardPipeline = new();

    public CombatService(IEventBus? bus = null)
    {
        _bus = bus;
    }

    public void ApplyDamage(Player player, int amount)
    {
        player.TakeDamage(amount);
    }

    public void ApplyDamage(Player player, Damage damage)
    {
        // Placeholder for future type-based mitigation; for now apply raw amount
        player.TakeDamage(damage.EffectiveAmount);
        var payload = BuildDamagePayload(damage.EffectiveAmount, damage.Type.ToString(), damage.IsCritical);
        _ = _bus?.PublishAsync(new DomainEvent(
            Type: "player.damaged",
            Source: nameof(CombatService),
            DataJson: payload,
            Timestamp: DateTimeOffset.UtcNow,
            Id: $"dmg-{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}"
        ));
    }

    public int CalculateDamage(Damage damage, CombatConfig? config = null)
    {
        config ??= CombatConfig.Default;
        var amount = Math.Max(0, damage.EffectiveAmount);
        double mult = 1.0;
        if (config.Resistances.TryGetValue(damage.Type, out var r)) mult *= r;
        if (damage.IsCritical) mult *= Math.Max(1.0, config.CritMultiplier);
        var result = (int)Math.Round(amount * mult);
        return Math.Max(0, result);
    }

    public int CalculateDamage(Damage damage, CombatConfig config, int armor)
    {
        var baseDmg = CalculateDamage(damage, config);
        // Simple linear armor mitigate; can be replaced with non-linear curve later
        var mitigated = Math.Max(0, baseDmg - Math.Max(0, armor));
        return mitigated;
    }

    public void ApplyDamage(Player player, Damage damage, CombatConfig config)
    {
        var final = CalculateDamage(damage, config);
        player.TakeDamage(final);
        var payload = BuildDamagePayload(final, damage.Type.ToString(), damage.IsCritical);
        _ = _bus?.PublishAsync(new DomainEvent(
            Type: "player.damaged",
            Source: nameof(CombatService),
            DataJson: payload,
            Timestamp: DateTimeOffset.UtcNow,
            Id: $"dmg-{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}"
        ));
    }

    public PlayCardPipelineResult ExecutePlayCardPipeline(PlayCardPipelineInput input)
    {
        if (input.CardsPlayedThisTurn >= HardCapCardsPerTurn)
        {
            var hardStopResult = BuildHardStopResult(input);
            PublishHardStopAuditTrail(hardStopResult, input.CardsPlayedThisTurn);
            return hardStopResult;
        }

        var result = _playCardPipeline.Execute(input);
        PublishPipelineAuditTrail(result);
        return result;
    }

    public PlayCardPipelineResult PlayCard(PlayCardPipelineInput input)
    {
        return ExecutePlayCardPipeline(input);
    }

    public static int CalculateDamageWithStatusMultipliers(
        int baseDamage,
        int strength,
        double weakMultiplier,
        double vulnerableMultiplier,
        bool isFixedDamage)
    {
        return PlayCardResolutionPipeline.CalculateDamageWithStatusMultipliers(
            baseDamage: baseDamage,
            strength: strength,
            weakMultiplier: weakMultiplier,
            vulnerableMultiplier: vulnerableMultiplier,
            isFixedDamage: isFixedDamage);
    }

    public static IReadOnlyList<MultiHitSettlement> ResolveMultiHitSettlements(
        int baseDamage,
        IReadOnlyList<int> strengthsPerHit,
        double weakMultiplier,
        double vulnerableMultiplier,
        bool isFixedDamage = false)
    {
        ArgumentNullException.ThrowIfNull(strengthsPerHit);

        return strengthsPerHit
            .Select((strength, index) => new MultiHitSettlement(
                StepIndex: index + 1,
                Damage: CalculateDamageWithStatusMultipliers(
                    baseDamage: baseDamage,
                    strength: strength,
                    weakMultiplier: weakMultiplier,
                    vulnerableMultiplier: vulnerableMultiplier,
                    isFixedDamage: isFixedDamage)))
            .ToArray();
    }

    public static int CalculateOverplayTax(
        int difficultyId,
        int cardsPlayedThisTurn,
        int overplayTriggerN,
        int overplayTaxPerCard)
    {
        return PlayCardResolutionPipeline.CalculateOverplayTax(
            difficultyId: difficultyId,
            cardsPlayedThisTurn: cardsPlayedThisTurn,
            overplayTriggerN: overplayTriggerN,
            overplayTaxPerCard: overplayTaxPerCard);
    }

    public static IReadOnlyList<CombatantOrderKey> OrderCombatantsDeterministically(IEnumerable<CombatantOrderKey> items)
    {
        return PlayCardResolutionPipeline.SortByDeterministicOrder(items);
    }

    public static DeterministicSemanticGateResult EvaluateDeterministicSemanticGate(
        IReadOnlyList<string> expectedOrderCombatantIds,
        IReadOnlyList<string> actualOrderCombatantIds,
        IReadOnlyList<int> expectedPerHitDamages,
        IReadOnlyList<int> actualPerHitDamages)
    {
        ArgumentNullException.ThrowIfNull(expectedOrderCombatantIds);
        ArgumentNullException.ThrowIfNull(actualOrderCombatantIds);
        ArgumentNullException.ThrowIfNull(expectedPerHitDamages);
        ArgumentNullException.ThrowIfNull(actualPerHitDamages);

        var orderMatches = expectedOrderCombatantIds.SequenceEqual(actualOrderCombatantIds);
        var perHitMatches = expectedPerHitDamages.SequenceEqual(actualPerHitDamages);
        return new DeterministicSemanticGateResult(
            IsPass: orderMatches && perHitMatches,
            OrderMatches: orderMatches,
            PerHitMatches: perHitMatches);
    }

    private void PublishPipelineAuditTrail(PlayCardPipelineResult result)
    {
        if (_bus is null)
        {
            return;
        }

        foreach (var step in result.ExecutedSteps)
        {
            var phase = step switch
            {
                PlayCardPipelineStep.BeforePlayTriggers => "BeforePlayTriggers",
                PlayCardPipelineStep.ResolveEffect => "ResolveEffect",
                PlayCardPipelineStep.AfterPlayTriggers => "AfterPlayTriggers",
                _ => null,
            };

            if (phase is null)
            {
                continue;
            }

            var payload = $"{{\"phase\":\"{phase}\"}}";
            _ = _bus.PublishAsync(new DomainEvent(
                Type: EventTypes.AuditLogged,
                Source: nameof(CombatService),
                DataJson: payload,
                Timestamp: DateTimeOffset.UtcNow,
                Id: $"audit-{phase}-{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}"));
        }
    }

    private PlayCardPipelineResult BuildHardStopResult(PlayCardPipelineInput input)
    {
        var normalizedEnergy = Math.Max(0, input.EnergyBefore);
        var normalizedCardsPlayed = Math.Max(0, input.CardsPlayedThisTurn);
        var orderingKey = $"{input.CombatantId}|{input.StableId}";
        var stateBefore = new PlayCardPipelineState(
            Energy: normalizedEnergy,
            FinalCost: 0,
            FinalDamage: 0,
            CardsPlayedThisTurn: normalizedCardsPlayed,
            ResolvedEffects: 0,
            CardMoved: false,
            DeathCheckCompleted: false);

        var failureReason = normalizedCardsPlayed == HardCapCardsPerTurn
            ? $"HardLimitExceeded: single-turn play-card hard cap {HardCapCardsPerTurn} reached (ADR-0029)."
            : $"HardStopAlreadyTriggered: single-turn play-card hard cap {HardCapCardsPerTurn} exceeded (ADR-0029).";

        var fingerprint = string.Join(
            "|",
            orderingKey,
            "fail",
            "hard-stop",
            normalizedCardsPlayed,
            normalizedEnergy);

        return new PlayCardPipelineResult(
            Success: false,
            FailureReason: failureReason,
            ExecutedSteps: Array.Empty<PlayCardPipelineStep>(),
            StateBefore: stateBefore,
            StateAfter: stateBefore,
            OverplayTax: 0,
            OrderingKey: orderingKey,
            ExecutionFingerprint: fingerprint);
    }

    private void PublishHardStopAuditTrail(PlayCardPipelineResult result, int cardsPlayedThisTurn)
    {
        if (_bus is null)
        {
            return;
        }

        var reasonCode = cardsPlayedThisTurn == HardCapCardsPerTurn ? "HardLimitExceeded" : "HardStopAlreadyTriggered";
        var hardStoppedPayload = $"{{\"cards_played_this_turn\":{cardsPlayedThisTurn},\"threshold\":{HardCapCardsPerTurn},\"reason_code\":\"{reasonCode}\"}}";
        _ = _bus.PublishAsync(new DomainEvent(
            Type: EventTypes.CombatLoopHardStopped,
            Source: nameof(CombatService),
            DataJson: hardStoppedPayload,
            Timestamp: DateTimeOffset.UtcNow,
            Id: $"combat-loop-hard-stop-{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}"));

        _ = _bus.PublishAsync(new DomainEvent(
            Type: EventTypes.CombatCardInvalidPlayBlocked,
            Source: nameof(CombatService),
            DataJson: hardStoppedPayload,
            Timestamp: DateTimeOffset.UtcNow,
            Id: $"combat-card-invalid-play-blocked-{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}"));

        var auditPayload = $"{{\"event\":\"hard-stop-triggered\",\"reason_code\":\"{reasonCode}\",\"cards_played_this_turn\":{cardsPlayedThisTurn},\"threshold\":{HardCapCardsPerTurn}}}";
        _ = _bus.PublishAsync(new DomainEvent(
            Type: EventTypes.AuditLogged,
            Source: nameof(CombatService),
            DataJson: auditPayload,
            Timestamp: DateTimeOffset.UtcNow,
            Id: $"audit-hard-stop-{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}"));
    }

    private static string BuildDamagePayload(int amount, string type, bool critical)
    {
        var escapedType = type.Replace("\\", "\\\\").Replace("\"", "\\\"");
        var criticalLiteral = critical ? "true" : "false";
        return $"{{\"amount\":{amount},\"type\":\"{escapedType}\",\"critical\":{criticalLiteral}}}";
    }
}

public sealed record MultiHitSettlement(int StepIndex, int Damage);
public sealed record DeterministicSemanticGateResult(bool IsPass, bool OrderMatches, bool PerHitMatches);
