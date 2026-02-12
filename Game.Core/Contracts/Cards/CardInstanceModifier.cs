namespace Game.Core.Contracts.Cards;

/// <summary>
/// Permanent modifier attached to a card instance.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0033.
/// </remarks>
public sealed record CardInstanceModifier(
    string ModifierId,
    string ModifierType,
    int Value,
    DateTimeOffset AppliedAt
);

