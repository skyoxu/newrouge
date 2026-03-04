using Game.Core.Domain;
using Game.Core.Domain.ValueObjects;
using Game.Core.Contracts.Combat;
using Game.Core.Contracts.Interfaces;
using System.Text.Json;

namespace Game.Core.Services;

public class CombatService
{
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
        var payload = JsonSerializer.Serialize(new { amount = damage.EffectiveAmount, type = damage.Type.ToString(), critical = damage.IsCritical });
        _ = _bus?.PublishAsync(new Contracts.DomainEvent(
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
        var payload = JsonSerializer.Serialize(new { amount = final, type = damage.Type.ToString(), critical = damage.IsCritical });
        _ = _bus?.PublishAsync(new Contracts.DomainEvent(
            Type: "player.damaged",
            Source: nameof(CombatService),
            DataJson: payload,
            Timestamp: DateTimeOffset.UtcNow,
            Id: $"dmg-{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}"
        ));
    }

    public PlayCardPipelineResult ExecutePlayCardPipeline(PlayCardPipelineInput input)
    {
        return _playCardPipeline.Execute(input);
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
}
