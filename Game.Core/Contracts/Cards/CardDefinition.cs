namespace Game.Core.Contracts.Cards;

/// <summary>
/// Immutable card definition keyed by stable card identity.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0033, ADR-0020.
/// </remarks>
public sealed record CardDefinition(
    string CardId,
    string NameKey,
    CardForm DefaultForm,
    bool IsCurse,
    bool IsUpgradeable,
    bool IsUltimateEligible
);

