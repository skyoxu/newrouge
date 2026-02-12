namespace Game.Core.Contracts.Cards;

/// <summary>
/// Runtime instance of a card owned in a run.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0033, ADR-0032.
/// </remarks>
public sealed record CardInstance(
    string InstanceId,
    string CardId,
    CardForm Form,
    UpgradeRoute? Route,
    int UpgradeTier,
    IReadOnlyList<CardInstanceModifier> PermanentCardInstanceModifiers
)
{
    public bool IsUltimate => Form == CardForm.Ultimate;
}

